#!/usr/bin/env python3
"""Start the local MVP; own and clean up only the child processes started here."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def check_ports(ports):
    held = []
    try:
        for port in ports:
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            held.append(sock)
            try:
                sock.bind(('127.0.0.1', port))
            except OSError as exc:
                raise RuntimeError(f'Port 127.0.0.1:{port} is occupied or unavailable. Stop its owner or choose another port.') from exc
    finally:
        for sock in held:
            sock.close()


class Children:
    def __init__(self, directory):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.rows = []

    def start(self, name, args, cwd=ROOT, env=None):
        path = self.directory / (name + '.log')
        stream = path.open('w')
        try:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        except BaseException:
            stream.close()
            raise
        self.rows.append((process, stream, path))
        return process

    def healthy(self):
        for process, _, path in self.rows:
            if process.poll() is not None:
                tail = path.read_text(errors='replace')[-3000:]
                raise RuntimeError(f'Child exited {process.returncode}: {path}\n{tail}')

    def close(self):
        for process, stream, _ in reversed(self.rows):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            stream.close()


def ready(url, children, stop, timeout=150):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stop[0]:
            raise InterruptedError('Startup interrupted')
        children.healthy()
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(.1)
    raise RuntimeError('Readiness timed out: ' + url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--store', type=Path, default=ROOT / 'outputs/integration-mvp/store')
    args = parser.parse_args()
    stop = [False]
    def interrupt(*_):
        stop[0] = True
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    children = None
    try:
        if args.backend_port == args.frontend_port or not all(1 <= p <= 65535 for p in (args.backend_port, args.frontend_port)):
            raise RuntimeError('Choose two distinct ports from 1 through 65535.')
        check_ports((args.backend_port, args.frontend_port))
        store = args.store.resolve()
        children = Children(store.parent / (store.name + '-logs'))
        preflight = children.start('preflight', [sys.executable, 'scripts/integration_preflight.py'])
        deadline = time.monotonic() + 60
        while preflight.poll() is None:
            if stop[0]:
                raise InterruptedError('Startup interrupted')
            if time.monotonic() > deadline:
                raise RuntimeError('Prerequisite check timed out')
            time.sleep(.1)
        if preflight.returncode:
            raise RuntimeError('Prerequisite check failed:\n' + children.rows[-1][2].read_text()[-5000:])
        # The completed preflight is no longer a required live process.
        _, stream, _ = children.rows.pop()
        stream.close()
        api = f'http://127.0.0.1:{args.backend_port}'
        children.start('backend', [sys.executable, '-m', 'backend.api.server', '--port', str(args.backend_port),
                                   '--store', str(store), '--bootstrap'])
        for kind in ('planning', 'simulation'):
            ready(f'{api}/api/v1/{kind}-results/latest', children, stop)
        children.start('frontend', ['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                                    '--port', str(args.frontend_port), '--strictPort'],
                       cwd=ROOT / 'frontend', env=dict(os.environ, MVP_API_TARGET=api))
        origin = f'http://127.0.0.1:{args.frontend_port}'
        ready(origin, children, stop, timeout=30)
        # Readiness also proves both payloads travel through the frontend proxy.
        for kind in ('planning', 'simulation'):
            ready(f'{origin}/api/v1/{kind}-results/latest', children, stop, timeout=10)
        print(f'Ready: {origin}/?basemap=plain', flush=True)
        print(f'Publications: {store}\nLogs: {children.directory}\nPress Ctrl-C to stop both services.', flush=True)
        while not stop[0]:
            children.healthy()
            time.sleep(.2)
        return 0
    except InterruptedError:
        return 0
    except Exception as exc:
        print(f'Startup failed: {exc}', file=sys.stderr, flush=True)
        return 1
    finally:
        if children:
            children.close()


if __name__ == '__main__':
    raise SystemExit(main())
