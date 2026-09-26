#!/usr/bin/env python3
"""Private stdin-controlled test host. No test-only HTTP endpoints."""
import json
from pathlib import Path
import sys
import threading
import queue
import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.api.server import make_server
from backend.api.store import ResultStore
from backend.api.jobs import JobManager, RunFailure


def main():
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    directory = Path(sys.argv[1])
    with ResultStore(directory / 'store') as store:
        sources = {kind: json.loads((directory / f'{kind}.json').read_text()) for kind in ('planning', 'simulation')}
        initial = {kind: store.publish(kind, payload) for kind, payload in sources.items()}
        behaviors = queue.Queue()
        def execute(record, directory, log):
            try:
                behavior = behaviors.get_nowait()
            except queue.Empty:
                behavior = None
            if behavior == 'fail':
                raise RunFailure('INJECTED_FAILURE', 'Deliberate acceptance job failure')
            return jobs._export(record, directory, log)
        jobs = JobManager(store, executor=execute)
        server = make_server(store, jobs=jobs)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.server_port
        serving = True
        print(json.dumps({'port': server.server_port, 'initial': initial}), flush=True)
        try:
            for line in sys.stdin:
                try:
                    command = json.loads(line)
                    if command['action'] == 'publish':
                        response = store.publish(command['kind'], command.get('payload', sources[command['kind']]))
                    elif command['action'] == 'fail-next':
                        behaviors.put('fail')
                        response = True
                    elif command['action'] == 'stop-http':
                        server.shutdown(); worker.join(timeout=5); server.server_close()
                        serving = False
                        response = True
                    elif command['action'] == 'start-http':
                        if serving:
                            raise ValueError('Already serving')
                        server = make_server(store, port=port, jobs=jobs)
                        worker = threading.Thread(target=server.serve_forever, daemon=True)
                        worker.start()
                        serving = True
                        response = True
                    else:
                        raise ValueError('Unsupported private test command')
                    print(json.dumps({'value': response}), flush=True)
                except Exception as exc:
                    print(json.dumps({'error': str(exc)}), flush=True)
        finally:
            if serving:
                server.shutdown()
                worker.join(timeout=5)
                server.server_close()
            jobs.close()


if __name__ == '__main__':
    main()
