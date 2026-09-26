# Local result delivery

Run `.venv-rl/bin/python -m backend.api.server` from the repository root. The
standard-library service binds to `127.0.0.1:8000`; `--port` and `--store` override
the port and local publication directory. It starts independently of Vite.

`GET /api/v1/{planning|simulation}-results/{latest|resultId}` implements the
[delivery contract](../../contracts/frontend-backend-api.md). Empty/unknown
results return 404, temporary storage errors 503, unexpected errors 500, and
unsupported methods 405. Responses are JSON with `Cache-Control: no-store`.
GET never invokes exporters or publishes results.

`GET /api/v1/scenario-manifest` returns only the public metadata from the
checked 544-entry `rl-scenario-suites/5` manifest. It is read-only and does not
accept paths or configuration. An unavailable or invalid checked manifest
returns 503.

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

Simulation submissions use either the unchanged legacy seed form or the frozen
form `{"kind":"simulation","scenarioRef":"sg2:validation:000017","policy":"naive-launch-on-detection/1"}`.
The frozen form requires both fields, forbids `seed`, resolves only checked
references, and accepts the four fixed policy identities documented in the
delivery contract. Identity drift fails the job with
`SCENARIO_IDENTITY_MISMATCH` before publication.

[Readiness](../../nickolas/integration-readiness.md) links to independent evidence.

Successful job status and its result identity commit in the same atomic publication
index replacement. Per-run JSON files mirror that state; a failed mirror write
cannot turn an already committed success into an interrupted job on restart.

Run-state write failures are recorded as `STORAGE_FAILED` when storage recovers
on the next write. If that recovery write also fails, the worker stops accepting
work: submissions and nonterminal run lookups return 503 until storage is
restored and the service restarted. Terminal records remain readable. Restart
marks unfinished persisted jobs interrupted; it never silently re-executes them.

The index rename is the publication commit point. If its subsequent directory
open/flush fails, the result and successful run remain committed with the same
IDs; a warning records uncertain durability across power loss. The service does
not report an already-visible publication as a failed run. Errors before that
rename (including snapshot flush errors) leave the previous latest unchanged.
