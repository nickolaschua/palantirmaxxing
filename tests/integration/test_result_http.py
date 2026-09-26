"""Wire-level assertions over real loopback sockets, including injected failures."""
from contextlib import contextmanager
import hashlib
import http.client
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import unittest

from backend.api.server import make_server
from backend.api.store import ResultStore, StoreUnavailable

ROOT = Path(__file__).resolve().parents[2]


def request(port, path, method='GET'):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read()
        return response.status, dict(response.getheaders()), json.loads(body) if body else None
    finally:
        connection.close()


@contextmanager
def serving(store):
    server = make_server(store)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


class HTTPTests(unittest.TestCase):
    def assert_response(self, result, status):
        code, headers, body = result
        self.assertEqual(code, status)
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        if status != 200:
            self.assertIsInstance(body['error']['code'], str)
            self.assertTrue(body['error']['code'])
            self.assertIsInstance(body['error']['message'], str)
            self.assertTrue(body['error']['message'])
        return body

    def test_four_routes_errors_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory, ResultStore(directory) as store:
            with serving(store) as port:
                self.assert_response(request(port, '/api/v1/planning-results/latest'), 404)
                self.assert_response(request(port, '/api/v1/simulation-results/latest'), 404)
                published = {}
                for kind in ('planning', 'simulation'):
                    payload = json.loads((ROOT / f'data/results/demo-{kind}-result.json').read_text())
                    published[kind] = store.publish(kind, payload)
                before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(directory).iterdir()}
                for kind, envelope in published.items():
                    prefix = f'/api/v1/{kind}-results/'
                    for identity in ('latest', envelope['resultId']):
                        self.assertEqual(self.assert_response(request(port, prefix + identity), 200), envelope)
                    self.assert_response(request(port, prefix + 'unknown'), 404)
                    other = published['simulation' if kind == 'planning' else 'planning']['resultId']
                    self.assert_response(request(port, prefix + other), 404)
                    for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
                        self.assert_response(request(port, prefix + 'latest', method), 405)
                    code, headers, body = request(port, prefix + 'latest', 'HEAD')
                    self.assertEqual(code, 405)
                    self.assertEqual(headers['Cache-Control'], 'no-store')
                    self.assertIsNone(body)
                after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(directory).iterdir()}
                self.assertEqual(before, after, 'GET requests modified the publication store')

    def test_injected_failures_over_http(self):
        class FailureStore:
            def __init__(self, failure):
                self.failure = failure
            def get(self, *_):
                raise self.failure
        for failure, status in ((StoreUnavailable('temporary'), 503), (RuntimeError('unexpected private detail'), 500)):
            with serving(FailureStore(failure)) as port:
                body = self.assert_response(request(port, '/api/v1/planning-results/latest'), status)
                self.assertNotIn('private detail', json.dumps(body))

    def test_standalone_process_without_vite(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([sys.executable, '-m', 'backend.api.server', '--port', '0', '--store', directory],
                                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=15), 'HTTP process failed to report readiness')
                readiness = json.loads(process.stdout.readline())
                self.assertTrue(readiness['ready'])
                self.assert_response(request(readiness['port'], '/api/v1/planning-results/latest'), 404)
            finally:
                process.terminate()
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
                    self.fail('HTTP process failed graceful termination')
            self.assertEqual(process.returncode, 0)
