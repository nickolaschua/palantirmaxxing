"""Persisted job state, serial execution, HTTP submission and real exporter proof."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.api.jobs import JobManager, validate_submission, InvalidSubmission, RunFailure
from backend.api.server import make_server
from backend.api.store import ResultStore, atomic_json

ROOT = Path(__file__).resolve().parents[2]


def wait_for(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError('Timed out waiting for job state')


def completed(manager, identity):
    return wait_for(lambda: (record if (record := manager.get(identity))['status'] in ('failed', 'succeeded') else None))


@contextmanager
def host(manager):
    server = make_server(manager.store, jobs=manager)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(method, path='/api/v1/runs', body=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            encoded = json.dumps(body) if body is not None else None
            connection.request(method, path, encoded, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = json.loads(response.read())
            assert response.getheader('Cache-Control') == 'no-store'
            assert response.getheader('Content-Type').startswith('application/json')
            return response.status, data
        finally:
            connection.close()
    try:
        yield request
    finally:
        server.shutdown(); worker.join(timeout=5); server.server_close()


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ResultStore(Path(self.temporary.name) / 'store')
        self.manager = None
        self.payload = json.loads((ROOT / 'data/results/demo-planning-result.json').read_text())

    def tearDown(self):
        if self.manager:
            self.manager.close()
        self.store.close()
        self.temporary.cleanup()

    def test_transient_run_state_write_failure_does_not_strand_later_jobs(self):
        for failed_status in ('running', 'failed'):
            with self.subTest(status=failed_status):
                injected = threading.Event()
                def write(path, record, *args, **kwargs):
                    if record.get('status') == failed_status and not injected.is_set():
                        injected.set()
                        raise OSError('Transient run-state write failure')
                    return atomic_json(path, record, *args, **kwargs)
                def execute(*_):
                    if failed_status == 'failed':
                        raise RunFailure('INJECTED', 'Exporter failed')
                    return self.payload
                self.manager = JobManager(self.store, executor=execute)
                with patch('backend.api.jobs.atomic_json', side_effect=write):
                    first = self.manager.submit({'kind': 'planning'})
                    self.assertTrue(injected.wait(5))
                    final = completed(self.manager, first['runId'])
                    self.assertEqual(final['status'], 'failed')
                    self.assertEqual(final['error']['code'], 'STORAGE_FAILED')
                    self.manager._executor = lambda *_: self.payload
                    later = self.manager.submit({'kind': 'planning'})
                    self.assertEqual(completed(self.manager, later['runId'])['status'], 'succeeded')
                self.assertTrue(self.manager._worker.is_alive())
                self.manager.close()
                self.manager = JobManager(self.store)
                self.assertEqual(self.manager.get(first['runId']), final)
                self.manager.close()
                self.manager = None

    def test_persistent_state_write_failure_rejects_work_and_recovers_on_restart(self):
        entered, release = threading.Event(), threading.Event()
        def execute(*_):
            entered.set()
            self.assertTrue(release.wait(5))
            raise RunFailure('INJECTED', 'Exporter failed')
        self.manager = JobManager(self.store, executor=execute)
        first = self.manager.submit({'kind': 'planning'})
        self.assertTrue(entered.wait(5))
        queued = self.manager.submit({'kind': 'planning'})
        def write(path, record, *args, **kwargs):
            if record.get('status') == 'failed':
                raise OSError('Persistent run-state write failure')
            return atomic_json(path, record, *args, **kwargs)
        with patch('backend.api.jobs.atomic_json', side_effect=write):
            release.set()
            wait_for(lambda: not self.manager._worker.is_alive())
            with host(self.manager) as request:
                self.assertEqual(request('POST', body={'kind': 'planning'})[0], 503)
                for identity in (first['runId'], queued['runId']):
                    self.assertEqual(request('GET', '/api/v1/runs/' + identity)[0], 503)
        self.manager.close()
        self.manager = JobManager(self.store)
        for identity in (first['runId'], queued['runId']):
            self.assertEqual(self.manager.get(identity)['status'], 'failed')
        next_run = self.manager.submit({'kind': 'planning'})
        self.assertEqual(completed(self.manager, next_run['runId'])['status'], 'succeeded')

    def test_submission_write_failure_returns_unavailable_without_queueing(self):
        self.manager = JobManager(self.store, executor=lambda *_: self.payload)
        with patch('backend.api.jobs.atomic_json', side_effect=OSError('Cannot save submission')):
            with host(self.manager) as request:
                self.assertEqual(request('POST', body={'kind': 'planning'})[0], 503)
        self.assertTrue(self.manager._queue.empty())
        self.assertEqual(self.manager._records, {})

    def test_real_jobs_are_serial_and_frontend_compatible(self):
        active = 0
        maximum = 0
        observed = []
        def execute(record, directory, log):
            nonlocal active, maximum
            active += 1; maximum = max(maximum, active)
            observed.append((record['runId'], 'start', str(directory)))
            try:
                return self.manager._export(record, directory, log)
            finally:
                observed.append((record['runId'], 'end', str(directory)))
                active -= 1
        self.manager = JobManager(self.store, executor=execute)
        self.assertEqual(self.manager.timeout, 120)
        with host(self.manager) as request:
            with ThreadPoolExecutor(max_workers=3) as pool:
                responses = list(pool.map(lambda body: request('POST', body=body), [
                    {'kind': 'planning'}, {'kind': 'simulation'}, {'kind': 'simulation', 'seed': 17}]))
            for status, record in responses:
                self.assertEqual(status, 202)
                self.assertEqual(record['status'], 'queued')
            corpus = []
            for _, record in responses:
                final = completed(self.manager, record['runId'])
                self.assertEqual(final['status'], 'succeeded', final)
                status, fetched_run = request('GET', '/api/v1/runs/' + record['runId'])
                self.assertEqual(status, 200); self.assertEqual(fetched_run, final)
                status, result = request('GET', f"/api/v1/{final['resultKind']}-results/{final['resultId']}")
                self.assertEqual(status, 200)
                self.assertEqual(result['resultId'], final['resultId'])
                if final['kind'] == 'simulation':
                    self.assertEqual(result['result']['seed'], record['seed'])
                    self.assertEqual(result['result']['policyVersusBaseline']['policyIdentity'], 'feasible-immediate-matching/1')
                corpus.append({'kind': final['kind'], 'name': final['runId'], 'payload': result['result']})
            path = Path(self.temporary.name) / 'jobs-corpus.json'
            path.write_text(json.dumps({'accepted': corpus, 'rejected': []}))
            subprocess.run(['node', '--experimental-strip-types', 'tests/fresh-results.mjs', str(path)],
                           cwd=ROOT / 'frontend', check=True, timeout=30)
            self.assertEqual(maximum, 1)
            self.assertEqual([row[1] for row in observed], ['start', 'end'] * 3)
            self.assertEqual(len({row[2] for row in observed}), 3)
            before = {r['runId']: self.manager.get(r['runId']) for _, r in responses}
        self.manager.close()
        self.manager = JobManager(self.store)
        for identity, record in before.items():
            self.assertEqual(self.manager.get(identity), record)
            self.assertEqual(self.store.get(record['kind'], record['resultId'])['resultId'], record['resultId'])

    def test_invalid_submissions_and_unknown_run_over_http(self):
        self.manager = JobManager(self.store)
        with host(self.manager) as request:
            invalid = [{'kind': 'simulation', 'seed': value} for value in (True, False, 1.5, -1, 2**31, '7', None)]
            invalid += [None, [], {}, {'kind': 'other'}, {'kind': 'planning', 'seed': 7},
                        {'kind': 'planning', 'command': 'echo nope'}, {'kind': 'simulation', 'output': '/tmp/not-allowed'}]
            for body in invalid:
                status, error = request('POST', body=body)
                self.assertEqual(status, 400, body)
                self.assertTrue(error['error']['message'])
            status, error = request('GET', '/api/v1/runs/unknown')
            self.assertEqual(status, 404); self.assertEqual(error['error']['code'], 'RUN_NOT_FOUND')
        self.assertEqual(validate_submission({'kind': 'simulation'}), {'kind': 'simulation', 'seed': 7})
        for seed in (0, 2**31 - 1):
            self.assertEqual(validate_submission({'kind': 'simulation', 'seed': seed})['seed'], seed)

    def test_eight_waiting_jobs_overflow_and_failure_does_not_stop_worker(self):
        entered, release = threading.Event(), threading.Event()
        count = 0
        def execute(*_):
            nonlocal count
            count += 1
            if count == 1:
                entered.set()
                if not release.wait(10):
                    raise AssertionError('release not set')
                raise RunFailure('INJECTED', 'Deliberate failed job')
            return self.payload
        self.manager = JobManager(self.store, executor=execute)
        with host(self.manager) as request:
            status, first = request('POST', body={'kind': 'planning'})
            self.assertEqual(status, 202); self.assertTrue(entered.wait(5))
            try:
                waiting = [request('POST', body={'kind': 'planning'}) for _ in range(8)]
                self.assertTrue(all(status == 202 and row['status'] == 'queued' for status, row in waiting))
                status, error = request('POST', body={'kind': 'planning'})
                self.assertEqual(status, 429); self.assertEqual(error['error']['code'], 'QUEUE_FULL')
            finally:
                release.set()
            self.assertEqual(completed(self.manager, first['runId'])['status'], 'failed')
            for _, row in waiting:
                self.assertEqual(completed(self.manager, row['runId'])['status'], 'succeeded')

    def test_failed_timeout_invalid_output_leave_latest_unchanged(self):
        preceding = self.store.publish('planning', self.payload)
        for mode, expected in (('failure', 'EXPORT_FAILED'), ('timeout', 'TIMEOUT'), ('invalid', 'INVALID_OUTPUT')):
            def execute(record, directory, log):
                if mode == 'invalid':
                    return {'schemaVersion': 'broken'}
                code = 'import time; time.sleep(30)' if mode == 'timeout' else 'raise SystemExit(9)'
                self.manager._execute([sys.executable, '-c', code], log)
                raise AssertionError('unexpected subprocess success')
            self.manager = JobManager(self.store, executor=execute, timeout=.1)
            record = self.manager.submit({'kind': 'planning'})
            final = completed(self.manager, record['runId'])
            self.assertEqual(final['status'], 'failed')
            self.assertEqual(final['error']['code'], expected)
            self.assertEqual(self.store.get('planning'), preceding)
            self.assertIsNone(self.manager._process)
            self.manager.close(); self.manager = None

    def test_restart_marks_actual_interrupted_running_and_queued_records_failed(self):
        # The subprocess has a blocking injected executor, so SIGKILL interrupts
        # actual persisted states without leaving an exporter child behind.
        code = '''
import json,sys,time
from pathlib import Path
from backend.api.store import ResultStore
from backend.api.jobs import JobManager
store=ResultStore(Path(sys.argv[1]))
def blocked(*args):
    time.sleep(60)
manager=JobManager(store, executor=blocked)
a=manager.submit({'kind':'planning'})
while manager.get(a['runId'])['status'] != 'running': time.sleep(.01)
b=manager.submit({'kind':'planning'})
print(json.dumps([a['runId'],b['runId']]),flush=True)
time.sleep(60)
'''
        interrupted_store = Path(self.temporary.name) / 'interrupted'
        process = subprocess.Popen([sys.executable, '-c', code, str(interrupted_store)], cwd=ROOT,
                                   stdout=subprocess.PIPE, text=True)
        import selectors
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=10))
            identities = json.loads(process.stdout.readline())
        finally:
            process.kill(); process.wait(timeout=5); process.stdout.close()
        with ResultStore(interrupted_store) as store:
            manager = JobManager(store)
            try:
                for identity in identities:
                    record = manager.get(identity)
                    self.assertEqual(record['status'], 'failed')
                    self.assertEqual(record['error']['code'], 'INTERRUPTED')
            finally:
                manager.close()

    def test_success_and_publication_commit_together_when_run_file_mirror_fails(self):
        from unittest.mock import patch
        from backend.api.store import atomic_json
        def fail_success_mirror(path, value, *args, **kwargs):
            if value.get('status') == 'succeeded':
                raise OSError('Injected failure after publication before run-file mirror')
            return atomic_json(path, value, *args, **kwargs)
        self.manager = JobManager(self.store, executor=lambda *_: self.payload)
        with patch('backend.api.jobs.atomic_json', side_effect=fail_success_mirror):
            submitted = self.manager.submit({'kind': 'planning'})
            final = completed(self.manager, submitted['runId'])
            self.assertEqual(final['status'], 'succeeded')
        identity = final['resultId']
        self.assertEqual(self.store.get('planning')['resultId'], identity)
        self.manager.close()
        self.manager = JobManager(self.store)
        self.assertEqual(self.manager.get(submitted['runId']), final)
        # A mirror write failure did not kill the sole worker.
        next_run = self.manager.submit({'kind': 'planning'})
        self.assertEqual(completed(self.manager, next_run['runId'])['status'], 'succeeded')

    def test_post_replace_directory_failure_keeps_run_success_consistent_on_restart(self):
        real_replace, real_fsync = os.replace, os.fsync
        index_replaced = threading.Event()
        injected = threading.Event()
        def replace(source, target):
            real_replace(source, target)
            if Path(target).name == 'index.json':
                index_replaced.set()
        def fsync(descriptor):
            if index_replaced.is_set() and not injected.is_set():
                injected.set()
                raise OSError('Index directory flush failed after commit')
            return real_fsync(descriptor)
        self.manager = JobManager(self.store, executor=lambda *_: self.payload)
        with patch('backend.api.store.os.replace', side_effect=replace), \
                patch('backend.api.store.os.fsync', side_effect=fsync):
            run = self.manager.submit({'kind': 'planning'})
            final = completed(self.manager, run['runId'])
        self.assertTrue(injected.is_set())
        self.assertEqual(final['status'], 'succeeded')
        self.assertEqual(self.store.get('planning')['resultId'], final['resultId'])
        self.manager.close()
        self.store.close()
        self.store = ResultStore(Path(self.temporary.name) / 'store')
        self.manager = JobManager(self.store, executor=lambda *_: self.payload)
        self.assertEqual(self.manager.get(run['runId']), final)
        self.assertEqual(self.store.get('planning', final['resultId'])['resultId'], final['resultId'])

    def test_export_directory_cleanup_failure_cannot_reclassify_committed_success(self):
        temporary_directory = tempfile.TemporaryDirectory
        @contextmanager
        def cleanup_failure(*args, **kwargs):
            with temporary_directory(*args, **kwargs) as directory:
                yield directory
            raise OSError('Injected export-directory cleanup failure')
        self.manager = JobManager(self.store, executor=lambda *_: self.payload)
        with patch('backend.api.jobs.tempfile.TemporaryDirectory', cleanup_failure):
            run = self.manager.submit({'kind': 'planning'})
            final = completed(self.manager, run['runId'])
        self.assertEqual(final['status'], 'succeeded')
        self.assertEqual(self.store.get('planning')['resultId'], final['resultId'])
        self.manager.close()
        self.manager = JobManager(self.store)
        self.assertEqual(self.manager.get(run['runId']), final)
