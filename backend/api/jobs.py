"""Durable, serial execution of fixed demo exporters; user data is never a command."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import uuid

from .store import atomic_json, canonical_id, StoreUnavailable
from .validation import InvalidResult
from backend.simulation.scenario_manifest import (
    load_scenario_manifest, validate_scenario_ref)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_POLICIES = frozenset((
    'naive-launch-on-detection/1',
    'feasible-immediate-matching/1',
    'optimal-fixed-rank-assignment/1',
    'structured-behavior-cloning/1',
))


class InvalidSubmission(ValueError):
    pass


class QueueFull(RuntimeError):
    pass


class RunNotFound(LookupError):
    pass


class RunFailure(RuntimeError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def validate_submission(value, manifest=None):
    if not isinstance(value, dict) or value.get('kind') not in ('planning', 'simulation'):
        raise InvalidSubmission('kind must be planning or simulation')
    kind = value['kind']
    if kind == 'planning':
        if set(value) != {'kind'}:
            raise InvalidSubmission('Planning submissions accept only kind')
        return {'kind': kind}
    manifest_mode = 'scenarioRef' in value or 'policy' in value
    if not manifest_mode:
        unknown = set(value) - {'kind', 'seed'}
        if unknown:
            raise InvalidSubmission(
                'Unknown submission fields: ' + ', '.join(sorted(unknown)))
        seed = value.get('seed', 7)
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise InvalidSubmission(
                'seed must be an integer from 0 through 2147483647')
        return {'kind': kind, 'seed': seed}
    expected = {'kind', 'scenarioRef', 'policy'}
    if set(value) != expected:
        raise InvalidSubmission(
            'Manifest simulations require exactly scenarioRef and policy; '
            'seed and unknown fields are forbidden')
    try:
        scenario_ref = validate_scenario_ref(value['scenarioRef'])
    except ValueError as exc:
        raise InvalidSubmission(str(exc)) from exc
    if value['policy'] not in MANIFEST_POLICIES:
        raise InvalidSubmission('Unsupported manifest simulation policy')
    try:
        checked = manifest or load_scenario_manifest()
    except ValueError as exc:
        raise InvalidSubmission('Checked scenario manifest is unavailable') from exc
    if scenario_ref not in checked.entries_by_ref:
        raise InvalidSubmission('Unknown scenario reference')
    return {'kind': kind, 'scenarioRef': scenario_ref,
            'policy': value['policy']}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


class JobManager:
    def __init__(self, store, *, executor=None, timeout=120):
        self.store = store
        self.directory = store.directory / 'runs'
        self.directory.mkdir(exist_ok=True)
        self._queue = queue.Queue(maxsize=8)
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._unavailable = False
        self._process = None
        self._executor = executor or self._export
        self.timeout = timeout
        committed = store.completed_runs()
        self._records = deepcopy(committed)
        for path in self.directory.glob('*.json'):
            record = json.loads(path.read_text())
            if not canonical_id(record.get('runId')) or path.stem != record['runId']:
                raise StoreUnavailable('Invalid persisted run identity')
            if record['runId'] in committed:
                record = committed[record['runId']]
            elif record['status'] in ('queued', 'running'):
                record.update(status='failed', updatedAt=utc(), error={
                    'code': 'INTERRUPTED', 'message': 'Service restarted before the run completed.'})
                atomic_json(path, record)
            self._records[record['runId']] = record
        self._worker = threading.Thread(target=self._work, name='mvp-export-worker', daemon=True)
        self._worker.start()

    def _save(self, record):
        atomic_json(self.directory / (record['runId'] + '.json'), record)
        self._records[record['runId']] = deepcopy(record)

    def submit(self, value):
        submission = validate_submission(value)
        with self._lock:
            if self._stopping.is_set():
                raise StoreUnavailable('Run worker is shutting down')
            if self._unavailable or not self._worker.is_alive():
                raise StoreUnavailable('Run worker is unavailable; restart the service after restoring storage')
            if self._queue.full():
                raise QueueFull('The queue already contains eight waiting runs.')
            record = dict(submission, runId=str(uuid.uuid4()), status='queued', createdAt=utc(), updatedAt=utc())
            try:
                self._save(record)
            except OSError as exc:
                raise StoreUnavailable('Cannot persist run submission') from exc
            self._queue.put_nowait(record['runId'])
            return deepcopy(record)

    def get(self, identity):
        with self._lock:
            if not canonical_id(identity) or identity not in self._records:
                raise RunNotFound('No matching run.')
            if (self._records[identity]['status'] in ('queued', 'running')
                    and (self._unavailable or not self._worker.is_alive())):
                raise StoreUnavailable('Run worker cannot persist progress; restart after restoring storage')
            return deepcopy(self._records[identity])

    def _export(self, submission, directory, log):
        output = directory / 'result.json'
        if submission['kind'] == 'planning':
            args = [sys.executable, str(ROOT / 'scripts/export_static_mvp_planning_result.py'),
                    '--scenario', str(ROOT / 'data/scenarios/demo-singapore.json'), '--output', str(output)]
        else:
            args = [sys.executable,
                    str(ROOT / 'scripts/export_simulation_result.py')]
            if 'scenarioRef' in submission:
                args.extend((
                    '--scenario-ref', submission['scenarioRef'],
                    '--policy', submission['policy']))
            else:
                args.extend((
                    '--seed', str(submission['seed']),
                    '--policy', 'baseline'))
            args.extend(('--output', str(output)))
        self._execute(args, log)
        try:
            return json.loads(output.read_text())
        except (OSError, ValueError) as exc:
            raise RunFailure('INVALID_OUTPUT', 'Exporter produced no valid JSON result.') from exc

    def _execute(self, args, log):
        """Only fixed internal commands reach this method. Tests may inject a runner."""
        with log.open('wb') as stream:
            with self._lock:
                if self._stopping.is_set():
                    raise RunFailure('INTERRUPTED', 'Service stopped before execution.')
                process = subprocess.Popen(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                self._process = process
            try:
                try:
                    code = process.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired as exc:
                    raise RunFailure('TIMEOUT', f'Exporter exceeded its {self.timeout:g}-second execution timeout.') from exc
                if code == 42:
                    raise RunFailure(
                        'SCENARIO_IDENTITY_MISMATCH',
                        'The frozen scenario no longer matches its checked identity.')
                if code:
                    raise RunFailure('EXPORT_FAILED', f'Exporter exited with status {code}.')
            finally:
                if process.poll() is None:
                    self._terminate(process)
                with self._lock:
                    self._process = None

    @staticmethod
    def _terminate(process):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)

    def _work(self):
        while not self._stopping.is_set():
            try:
                identity = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                with self._lock:
                    if self._stopping.is_set():
                        return
                    record = dict(self._records[identity], status='running', updatedAt=utc())
                    self._save(record)
                try:
                    with tempfile.TemporaryDirectory(prefix='export-', dir=self.directory) as temporary:
                        payload = self._executor(record, Path(temporary), self.directory / (identity + '.log'))
                        with self._lock:
                            if self._stopping.is_set():
                                raise RunFailure('INTERRUPTED', 'Service stopped before publication.')
                            result = self.store.publish(record['kind'], payload, completed_run=record)
                            record.update(status='succeeded', resultKind=record['kind'], resultId=result['resultId'],
                                          updatedAt=result['publishedAt'])
                except Exception as exc:
                    if record['status'] == 'succeeded':
                        logging.exception('Cannot clean up export directory after committed run %s', identity)
                    else:
                        if isinstance(exc, RunFailure):
                            code, message = exc.code, exc.message
                        elif isinstance(exc, InvalidResult):
                            code, message = 'INVALID_OUTPUT', str(exc)
                        else:
                            code, message = 'RUN_FAILED', str(exc)
                        record.update(status='failed', error={'code': code, 'message': message})
                with self._lock:
                    if record['status'] == 'succeeded':
                        self._records[identity] = deepcopy(record)
                        try:
                            self._save(record)
                        except OSError:
                            # Success already has its authoritative durable copy
                            # in the publication index. The per-run file is a cache.
                            logging.exception('Cannot mirror committed run file; publication index retains success')
                    else:
                        record['updatedAt'] = utc()
                        self._save(record)
            except OSError:
                # A state write can fail before execution or while recording a
                # failed export. Try to make that failure terminal once, then
                # continue servicing jobs only if persistence has recovered.
                logging.exception('Cannot persist run state')
                with self._lock:
                    failed = dict(self._records[identity], status='failed', updatedAt=utc(), error={
                        'code': 'STORAGE_FAILED', 'message': 'Run stopped because its state could not be persisted.'})
                    try:
                        self._save(failed)
                    except OSError:
                        self._unavailable = True
                        logging.exception('Run storage remains unavailable; refusing further work until restart')
                        return
            finally:
                self._queue.task_done()

    def close(self):
        self._stopping.set()
        with self._lock:
            process = self._process
        if process is not None:
            self._terminate(process)
        self._worker.join(timeout=10)
        if self._worker.is_alive():
            raise StoreUnavailable('Run worker did not stop')
        with self._lock:
            for identity, old in list(self._records.items()):
                if old['status'] in ('queued', 'running'):
                    record = dict(old, status='failed', updatedAt=utc(), error={
                        'code': 'INTERRUPTED', 'message': 'Service stopped before the run completed.'})
                    self._save(record)
