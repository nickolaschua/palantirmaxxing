"""Actual launcher processes, default ports, durable restart and occupied ports."""
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def wait_ready(process, log, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f'Launcher exited {process.returncode}: {log.read_text()}')
        if 'Ready:' in log.read_text():
            return
        time.sleep(.1)
    raise AssertionError('Launcher readiness timed out: ' + log.read_text())


def available(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


class LauncherTests(unittest.TestCase):
    def test_default_ports_bootstrap_restart_and_owned_cleanup(self):
        self.assertTrue(available(8000) and available(5173), 'Default MVP ports must be free for acceptance; unrelated owners will not be stopped')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            store = base / 'publications'
            expected = None
            for cycle in range(2):
                log = base / f'launcher-{cycle}.log'
                with log.open('w') as stream:
                    process = subprocess.Popen([sys.executable, 'scripts/run_integration_mvp.py', '--store', str(store)],
                                               cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                    try:
                        wait_ready(process, log)
                        results = {}
                        for kind in ('planning', 'simulation'):
                            with urlopen(f'http://127.0.0.1:5173/api/v1/{kind}-results/latest', timeout=5) as response:
                                results[kind] = json.load(response)
                        if expected is None:
                            expected = results
                            self.assertEqual(results['simulation']['result']['seed'], 7)
                        else:
                            self.assertEqual(results, expected, 'Restart replaced existing immutable publications')
                        self.assertIn('http://127.0.0.1:5173/?basemap=plain', log.read_text())
                    finally:
                        process.send_signal(signal.SIGTERM)
                        try:
                            process.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=5)
                            self.fail('Launcher did not clean up promptly')
                self.assertEqual(process.returncode, 0, log.read_text())
                self.assertTrue(available(8000) and available(5173), 'Launcher leaked a listener')
            self.assertEqual(len(json.loads((store / 'index.json').read_text())['records']), 2)

    def test_occupied_ports_fail_without_stopping_the_owner(self):
        for occupied in (8000, 5173):
            with socket.socket() as sentinel, tempfile.TemporaryDirectory() as directory:
                sentinel.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sentinel.bind(('127.0.0.1', occupied)); sentinel.listen()
                process = subprocess.run([sys.executable, 'scripts/run_integration_mvp.py', '--store', str(Path(directory) / 'store')],
                                         cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn(f'127.0.0.1:{occupied}', process.stderr)
                self.assertIn('occupied', process.stderr)
                with socket.create_connection(('127.0.0.1', occupied), timeout=1):
                    pass
                connection, _ = sentinel.accept(); connection.close()
                self.assertFalse((Path(directory) / 'store').exists(), 'Failed port preflight mutated publication state')
