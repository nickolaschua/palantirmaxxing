# Local result delivery

Run `.venv-rl/bin/python -m backend.api.server` from the repository root. The
standard-library service binds to `127.0.0.1:8000`; `--port` and `--store` override
the port and local publication directory. It starts independently of Vite.

`GET /api/v1/{planning|simulation}-results/{latest|resultId}` implements the
[delivery contract](../../contracts/frontend-backend-api.md). Empty/unknown
results return 404, temporary storage errors 503, unexpected errors 500, and
unsupported methods 405. Responses are JSON with `Cache-Control: no-store`.
GET never invokes exporters or publishes results.

`ResultStore.publish(kind, payload)` validates before writing, assigns a UUID
and UTC publication time, persists an increasing sequence, flushes the immutable
snapshot, and atomically replaces the index. Latest uses sequence, including
timestamp ties. Only indexed snapshots are readable. One process owns the writer
lock; threads serialize publications. A read-only store can inspect publications
without acquiring the writer lock. File locking currently targets macOS/Linux.

The browser defaults to same-origin HTTP through Vite. `POST /api/v1/runs` and
`GET /api/v1/runs/{runId}` expose the persisted serial job worker (eight waiting
slots, fixed exporters, 120-second execution timeout). See the canonical contract
for request/error fields. `--bootstrap` explicitly publishes missing default demos
before readiness; the root launcher supplies that flag. No GET publishes.

[Readiness](../../nickolas/integration-readiness.md) links to independent evidence.

Successful job status and its result identity commit in the same atomic publication
index replacement. Per-run JSON files mirror that state; a failed mirror write
cannot turn an already committed success into an interrupted job on restart.
