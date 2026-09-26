"""Loopback standard-library HTTP delivery. GET never executes a model."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import threading
import time
from urllib.parse import unquote, urlsplit

from .store import ResultNotFound, ResultStore, StoreUnavailable
from .jobs import JobManager, InvalidSubmission, QueueFull, RunNotFound


class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def make_server(store, host='127.0.0.1', port=0, jobs=None):
    if host != '127.0.0.1':
        raise ValueError('Local MVP server must bind to 127.0.0.1')

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body):
            encoded = json.dumps(body, allow_nan=False, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(encoded)

        def error(self, status, code, message):
            self.respond(status, {'error': {'code': code, 'message': message}})

        def send_error(self, code, message=None, explain=None):
            self.error(code, 'HTTP_ERROR', message or 'Invalid HTTP request')

        def do_GET(self):
            try:
                segments = urlsplit(self.path).path.split('/')
                if len(segments) != 5 or segments[1:3] != ['api', 'v1']:
                    raise ResultNotFound()
                if segments[3] == 'runs' and jobs is not None:
                    self.respond(200, jobs.get(unquote(segments[4])))
                    return
                kind = {'planning-results': 'planning', 'simulation-results': 'simulation'}.get(segments[3])
                if not kind or not segments[4]:
                    raise ResultNotFound()
                self.respond(200, store.get(kind, unquote(segments[4])))
            except ResultNotFound:
                self.error(404, 'RESULT_NOT_FOUND', 'No matching published result.')
            except RunNotFound:
                self.error(404, 'RUN_NOT_FOUND', 'No matching run.')
            except StoreUnavailable:
                self.error(503, 'DELIVERY_UNAVAILABLE', 'Result delivery is temporarily unavailable.')
            except Exception:
                self.log_error('Unexpected request failure')
                self.error(500, 'INTERNAL_ERROR', 'Unexpected server failure.')

        def unsupported(self):
            self.error(405, 'METHOD_NOT_ALLOWED', 'This route supports GET only.')

        def do_POST(self):
            if urlsplit(self.path).path != '/api/v1/runs' or jobs is None:
                self.unsupported()
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 < length <= 4096 or self.headers.get('Transfer-Encoding'):
                    raise InvalidSubmission('Provide a JSON request body of at most 4096 bytes.')
                self.connection.settimeout(5)
                raw = self.rfile.read(length)
                record = jobs.submit(json.loads(raw))
                self.respond(202, record)
            except (InvalidSubmission, ValueError, UnicodeDecodeError):
                self.error(400, 'INVALID_SUBMISSION', 'Expected planning kind only, or simulation kind with an integer seed from 0 through 2147483647; no unknown fields.')
            except QueueFull as exc:
                self.error(429, 'QUEUE_FULL', str(exc))
            except StoreUnavailable:
                self.error(503, 'RUN_UNAVAILABLE', 'Run submission is temporarily unavailable.')
            except Exception:
                self.error(500, 'INTERNAL_ERROR', 'Unexpected run submission failure.')

        do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = unsupported

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--store', type=Path, default=Path('outputs/integration-mvp/store'))
    parser.add_argument('--bootstrap', action='store_true', help='Publish missing default demos before reporting readiness')
    args = parser.parse_args()
    with ResultStore(args.store) as store:
        jobs = JobManager(store)
        server = None
        stopping = threading.Event()
        def stop(*_):
            stopping.set()
            if server is not None:
                threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            if args.bootstrap:
                for kind in ('planning', 'simulation'):
                    try:
                        store.get(kind)
                    except ResultNotFound:
                        run = jobs.submit({'kind': kind})
                        deadline = time.monotonic() + 130
                        while True:
                            if stopping.is_set():
                                raise RuntimeError('Startup interrupted')
                            state = jobs.get(run['runId'])
                            if state['status'] == 'failed':
                                raise RuntimeError('Default demo failed: ' + state['error']['message'])
                            if state['status'] == 'succeeded':
                                break
                            if time.monotonic() >= deadline:
                                raise RuntimeError('Default demo readiness timed out')
                            time.sleep(.05)
            if stopping.is_set():
                return
            server = make_server(store, port=args.port, jobs=jobs)
            print(json.dumps({'ready': True, 'host': '127.0.0.1', 'port': server.server_port}), flush=True)
            server.serve_forever(poll_interval=0.1)
        finally:
            if server is not None:
                server.server_close()
            jobs.close()


if __name__ == '__main__':
    main()
