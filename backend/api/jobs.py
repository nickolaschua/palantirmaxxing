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

ROOT = Path(__file__).resolve().parents[2]


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


def validate_submission(value):
    if not isinstance(value, dict) or value.get('kind') not in ('planning', 'simulation'):
        raise InvalidSubmission('kind must be planning or simulation')
    kind = value['kind']
    allowed = {'kind', 'seed'} if kind == 'simulation' else {'kind'}
    if set(value) - allowed:
        raise InvalidSubmission('Unknown submission fields: ' + ', '.join(sorted(set(value) - allowed)))
    submission = {'kind': kind}
    if kind == 'simulation':
        seed = value.get('seed', 7)
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise InvalidSubmission('seed must be an integer from 0 through 2147483647')
        submission['seed'] = seed
    return submission


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
            if self._queue.full():
                raise QueueFull('The queue already contains eight waiting runs.')
            record = dict(submission, runId=str(uuid.uuid4()), status='queued', createdAt=utc(), updatedAt=utc())
            self._save(record)
            self._queue.put_nowait(record['runId'])
            return deepcopy(record)

    def get(self, identity):
        with self._lock:
            if not canonical_id(identity) or identity not in self._records:
                raise RunNotFound('No matching run.')
            return deepcopy(self._records[identity])

    def _export(self, submission, directory, log):
        output = directory / 'result.json'
        if submission['kind'] == 'planning':
            args = [sys.executable, str(ROOT / 'scripts/export_static_mvp_planning_result.py'),
                    '--scenario', str(ROOT / 'data/scenarios/demo-singapore.json'), '--output', str(output)]
        else:
            args = [sys.executable, str(ROOT / 'scripts/export_simulation_result.py'),
                    '--seed', str(submission['seed']), '--policy', 'baseline', '--output', str(output)]
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
