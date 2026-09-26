# Frontend–backend integration summary

Prepared 26 September 2026. Scope: integration commit `3e4dc60` (`frontend backend merge, untested`), pushed to `origin/main`, relative to parent `8f254c8`. The commit contains 44 changed files, 3,199 insertions and 126 deletions. This document records implementation and existing evidence; the companion [review checklist](integration_review_checklist.md) is for your independent review.

## Outcome and scope

The planning and simulation views now load validated results from a local Python HTTP service by default. Users can refresh a published snapshot or submit a new fixed demo run, follow its job status, and display its exact result. Results and terminal job identities persist across service restarts. A root launcher starts the API and Vite together; an independent acceptance runner checks prerequisites, exports, storage, HTTP, frontend lifecycle, jobs, real Cesium rendering and startup.

This work connects existing exporters and parsers. It preserves the separate `planning-result/1` and `simulation-result/1` schemas, existing model settings, simulation baseline policy and curated result artifacts. It does not implement scenario editing, dynamic replanning, model training, production hosting or a database. Simulation/model validity and policy improvement are separate questions from successful integration.

## End-to-end flow

1. `scripts/run_integration_mvp.py` checks ports and prerequisites, then starts the API with bootstrap enabled.
2. Bootstrap submits missing planning and seed-7 simulation demos through the job manager. Existing publications are retained.
3. One worker executes the existing exporter in an isolated directory. Planning uses `data/scenarios/demo-singapore.json`; simulation uses the baseline policy and requested seed.
4. The backend validates the full output before publication. A UUID snapshot file is written first; the atomic index replacement makes it visible and commits the successful job/result association.
5. Vite proxies same-origin `/api` requests to the loopback API. Each view loads its own result kind, validates the envelope and payload, then constructs its render resources.
6. Refresh fetches latest explicitly. Run controls submit a job, poll its status, then request the returned result ID. Publishing alone does not replace the displayed snapshot.

The important identities are distinct: `runId` identifies execution, `resultId` identifies immutable delivery, and `scenarioId`/`episodeId` remain payload identities. `publishedAt` records UTC publication time. Latest is selected by a persisted publication sequence, independently of scenario time or filesystem timestamps.

## Backend changes

| File | Responsibility |
| --- | --- |
| [server.py](../backend/api/server.py) | Loopback-only standard-library HTTP service, JSON/no-store responses, route/error handling and optional bootstrap. |
| [validation.py](../backend/api/validation.py) | Strict JSON values and result-kind/schema validation, including timestamps, coordinates, identifiers, references and required payload structure. |
| [store.py](../backend/api/store.py) | UUID snapshots, durable sequence, atomic JSON writes, single-writer file lock, indexed lookup and committed successful runs. |
| [jobs.py](../backend/api/jobs.py) | Submission validation, persisted run records, bounded serial queue, fixed subprocess commands, timeout/shutdown and restart recovery. |

### HTTP contract

The authoritative specification is [frontend-backend-api.md](../contracts/frontend-backend-api.md).

| Request | Purpose |
| --- | --- |
| `GET /api/v1/planning-results/latest` | Latest planning publication. |
| `GET /api/v1/planning-results/{resultId}` | Exact planning publication. |
| `GET /api/v1/simulation-results/latest` | Latest simulation publication. |
| `GET /api/v1/simulation-results/{resultId}` | Exact simulation publication. |
| `POST /api/v1/runs` | Submit a fixed planning or baseline simulation job; returns 202. |
| `GET /api/v1/runs/{runId}` | Read queued, running, succeeded or failed status. |

Successful result bodies are `{ resultId, publishedAt, result }`; the payload is preserved inside the envelope. Responses use JSON and `Cache-Control: no-store`. Missing results/runs return 404; temporary store failures return 503; unexpected server errors return 500. Submission validation returns 400, queue overflow 429, and unsupported implemented methods 405. GET never starts an exporter.

Planning submission is exactly `{"kind":"planning"}`. Simulation accepts `{"kind":"simulation","seed":7}`; omitted seed defaults to 7. Seeds must be integers from 0 through 2147483647. Unknown fields, booleans and invalid seeds are rejected. Clients cannot supply commands, paths, policies or arbitrary configuration.

### Persistence and execution

The store permits one writer using `fcntl.flock`; threads serialize publication with a reentrant lock. Atomic writes flush the file, replace it, then flush the parent directory. Only indexed snapshots are visible, so an orphan file from a failed pre-index publication is not delivered as latest. Repeated identical payloads still receive distinct publication IDs.

The job manager has one active worker and eight waiting slots. Exporter execution times out after 120 seconds. Failed, invalid or timed-out exports preserve the preceding latest publication. Restart retains terminal records and fails interrupted queued/running jobs. Successful status and result identity are committed together in the publication index; per-run JSON files are mirrors. A tested mirror-write failure after publication does not reclassify that successful run as interrupted on restart.

## Frontend changes

- [source.ts](../frontend/src/demo/source.ts) defaults to HTTP, encodes result IDs, forwards abort signals, validates responses and checks exact-ID matches. [fixture-source.ts](../frontend/src/demo/fixture-source.ts) is dynamically imported only for explicit fixture mode. HTTP errors never silently load fixtures.
- [result-loader.ts](../frontend/src/demo/result-loader.ts) owns loading, retry, refresh and snapshot metadata. Generation counters and abort controllers make stale/disposed requests inert. The preceding view stays visible on fetch, parse or render-construction failure.
- [result-resources.ts](../frontend/src/demo/result-resources.ts) owns layers, event subscriptions and DOM nodes for each render attempt. Failed construction can release partial resources; successful replacement disposes the preceding view.
- [run-controls.ts](../frontend/src/demo/run-controls.ts) submits each kind separately, validates the simulation seed, disables duplicate clicks, polls without overlapping requests and loads the exact successful result ID. Polling transport failure exposes Retry run status while retaining the active job.
- Planning and simulation mounts integrate these controls and resource scopes. Planning history carries its originating result ID and restarts for each new snapshot. Planning Restart remains a presentation action.
- `?source=fixture` or `VITE_RESULT_SOURCE=fixture` selects labelled illustrative fixtures and disables backend run submission. Fixture-only planning consequence values are not added to HTTP results.
- `?basemap=plain` avoids remote map providers; remote Google Fonts loading was removed. An opt-in `?acceptance=1` diagnostic hook exposes copied observations of actual Cesium objects and rendering events for browser tests.

## Setup, run and verification

Use Python 3.9–3.12 and Node.js 22.12+ or a supported newer Node release. From the repository root:

```sh
python3 -m venv .venv-rl
.venv-rl/bin/python -m pip install -r scripts/requirements-integration.txt
npm --prefix frontend ci
(cd frontend && npx playwright install chromium)
.venv-rl/bin/python scripts/population_data.py acquire
.venv-rl/bin/python scripts/population_data.py prepare
.venv-rl/bin/python scripts/integration_preflight.py
.venv-rl/bin/python scripts/run_integration_mvp.py
```

Acquisition requires network access unless the verified cache is available. Preserve the pinned raw population snapshot when reproducing input identity. Preflight reports missing/mismatched inputs and recovery commands; it also launches managed Chromium. See [integration-readiness.md](integration-readiness.md) for setup details.

Default endpoints are API `127.0.0.1:8000` and Vite `127.0.0.1:5173`. Open the printed `/?basemap=plain` URL. Startup verifies both direct and proxied result routes. Ctrl-C stops the owned children; occupied ports fail without stopping their owners. Optional `--backend-port`, `--frontend-port` and `--store` permit isolated runs. Runtime state defaults to `outputs/integration-mvp/store`, with adjacent launcher logs.

For independent acceptance, stop the default launcher first because launcher tests use the default ports:

```sh
.venv-rl/bin/python scripts/verify_integration_mvp.py --all
# Or a focused gate:
.venv-rl/bin/python scripts/verify_integration_mvp.py --gate B04
```

## Recorded verification

The retained full run completed on 26 September 2026 from 03:25:23 to 03:29:08 UTC (11:25–11:29 Singapore time). Its [results.json](../outputs/integration-mvp/evidence/20260926T032523.419873Z/results.json) reports `status: passed`, `testedStateUnchanged: true`, and all B01–B10 gates passed.

| Gate | Verified area |
| --- | --- |
| B01 | Dependencies, preflight failures, baseline suites and build. |
| B02 | Fresh repeated planning/simulation exports, deterministic checks, Python/TypeScript compatibility, curated artifact preservation. |
| B03 | Immutable indexed storage, validation failure, atomicity, concurrent publication and restart. |
| B04 | Real HTTP routes, error responses and read-only GET. |
| B05 | HTTP-backed views, invalid/unavailable delivery and explicit fixture behavior. |
| B06 | Refresh, metadata, stale-request races, resource disposal and planning history. |
| B07 | Real serial jobs, queue capacity, failures, timeout, interruption and committed-success recovery. |
| B08 | Browser run submission, polling, duplicate prevention and exact result selection. |
| B09 | Real Chromium/WebGL/Cesium geometry, visibility, API loss and recovery. |
| B10 | Launcher lifecycle, final regression/build, curated artifacts and graph refresh. |

The final backend suite had 333 tests; frontend tests had 27; UI tests had 25. Browser gates recorded 135 assertions (B05: 35; B06: 29; B08: 34; B09: 37). Production build and whitespace checks passed. The browser was Chromium 153.0.8010.12 on macOS ARM64 with Python 3.9.6. Counts describe this retained run, not a new run performed while writing this document.

Despite the requested commit message saying “untested,” evidence was generated before the commit on parent HEAD `8f254c874362be73a005ecc89c60e6665d69c911` plus the then-uncommitted integration files. It is not a test run whose recorded HEAD is `3e4dc60`. The harness included untracked implementation in source fingerprints and checked source/input stability during execution. The two new review documents also change the workspace fingerprint; rerun acceptance to obtain evidence for your reviewed state.

Recorded hashes:

```text
trackedDiffSha256 b3a05eda56d61458669d41b286dc66f58bdda5ed5e3a7cae0b03bd3971fef4e3
sourceFilesSha256 6cf47119f5037ac1a517b991ed9cedc9b2691d30b26ebe3f72fcff032956f91b
lockfileSha256    0471ee3185427a0b5eec74b85a31b92e6bc5a7c5253c3a237b6cafba961e7949
```

Evidence includes command logs/exit codes, JUnit XML, export hashes, browser assertions, traces, screenshots and Cesium observations. [latest-full](../outputs/integration-mvp/evidence/latest-full/results.json) is a moving pointer updated after any full attempt, including a failed attempt: inspect status rather than assuming it passes. Evidence and runtime stores are ignored and are not included in the pushed commit; their links work only where those local files exist. Share a retained evidence directory separately if another reviewer needs it.

## Limits and review attention

This is a loopback local MVP. File locking and process-group management target macOS/Linux. The single worker, file store and Vite development proxy are not a production deployment design. No production authentication, multi-host coordination or store retention policy was added.

The core browser gates block external requests and inspect actual Cesium geometry: center tolerance is 1e-7 degrees and radius tolerance is 1e-6 metres. This does not establish remote-provider availability or broad browser/platform compatibility. Dependency deprecation and large-bundle warnings remain in the logs. Graphify refresh is AST-only; unsupported/semantic document content is not fully represented.

Review storage commit boundaries, restart behavior, exception cleanup and request races first. Also inspect the boundary cases listed in the companion checklist rather than treating passing gates as proof of every possible failure. The existing README still contains older broad “Open decisions” wording about transport/integration; use the canonical HTTP contract for this implemented local service and flag conflicting historical prose during review.
