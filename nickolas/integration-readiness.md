# Local integration acceptance

The B01–B10 goal remains the finish line. Only a passing final `--all` run proves
completion. The table links to machine evidence; manual edits cannot override it.

## Setup

Use Python 3.9–3.12 and Node.js 22.12+ (or a supported newer Node release).
From the repository root:

```sh
python3 -m venv .venv-rl
.venv-rl/bin/python -m pip install -r scripts/requirements-integration.txt
npm --prefix frontend ci
cd frontend
npx playwright install chromium
cd ..
.venv-rl/bin/python scripts/population_data.py acquire
.venv-rl/bin/python scripts/population_data.py prepare
.venv-rl/bin/python scripts/integration_preflight.py
```

Acquisition needs network access. Preserve the pinned population source snapshot
when reproducing the demo identity; preflight rejects mismatches and reports
missing input paths with recovery commands. Consequence CSVs and military geometry
come from the repository. Preflight loads actual population/display/scenario data
and launches managed Chromium. Dependency installation is checked for lockfile drift.

[Playwright browser installation](https://playwright.dev/docs/browsers),
[server lifecycle](https://playwright.dev/docs/test-webserver), and
[trace viewer](https://playwright.dev/docs/trace-viewer) document the tooling.

## Start and verify

```sh
.venv-rl/bin/python scripts/run_integration_mvp.py
.venv-rl/bin/python scripts/verify_integration_mvp.py --all
# Independently test one gate:
.venv-rl/bin/python scripts/verify_integration_mvp.py --gate B04
```

Startup binds backend 127.0.0.1:8000 and Vite 127.0.0.1:5173, bootstraps missing
planning and seed-7 baseline publications, verifies the proxy, and prints the URL.
Ctrl-C stops both owned children. Restart retains results. Occupied ports fail
without stopping unrelated processes. Optional `--backend-port`, `--frontend-port`
and `--store` support isolated local runs. Defaults require no manual fixture copies.

Both views use HTTP by default. Refresh explicitly fetches latest; errors preserve
the previous snapshot and identity. Run controls submit fixed demos, show status,
and load the exact completed publication. Simulation seed is editable within the
contract range. Planning Restart affects presentation only. `?source=fixture`
selects labelled illustrative fixtures and disables backend Run controls;
`?basemap=plain` uses the local map without remote providers or fonts.
See the [HTTP/job contract](../contracts/frontend-backend-api.md).

## Evidence checklist

Each gate's status is authoritative in [the latest full result](../outputs/integration-mvp/evidence/latest-full/results.json).
The runner updates this link only after a full attempt; check its overall status
and `testedStateUnchanged`, not merely the existence of files.

| Gate | Capability | Evidence |
| --- | --- | --- |
| B01 | Prerequisites, dependency install, baseline | [Assertions and commands](../outputs/integration-mvp/evidence/latest-full/results.json), [backend tests](../outputs/integration-mvp/evidence/latest-full/backend.xml) |
| B02 | Fresh deterministic exports, both language parsers | [Assertions](../outputs/integration-mvp/evidence/latest-full/results.json), [export hashes](../outputs/integration-mvp/evidence/latest-full/fresh-exports.json) |
| B03 | Immutable, durable, serial publication | [Store tests](../outputs/integration-mvp/evidence/latest-full/store.xml) |
| B04 | Actual HTTP routes, errors and read-only GET | [HTTP tests](../outputs/integration-mvp/evidence/latest-full/http.xml) |
| B05 | HTTP views, explicit failures and fixtures | [Browser assertions](../outputs/integration-mvp/evidence/latest-full/B05/browser-results.json), [trace](../outputs/integration-mvp/evidence/latest-full/B05/trace.zip) |
| B06 | Refresh, metadata, races, resource cleanup, history | [Browser assertions](../outputs/integration-mvp/evidence/latest-full/B06/browser-results.json), [trace](../outputs/integration-mvp/evidence/latest-full/B06/trace.zip) |
| B07 | Real serial jobs, failures, queue and restart | [Job tests](../outputs/integration-mvp/evidence/latest-full/jobs.xml) |
| B08 | Browser run controls and exact result identity | [Browser assertions](../outputs/integration-mvp/evidence/latest-full/B08/browser-results.json), [trace](../outputs/integration-mvp/evidence/latest-full/B08/trace.zip) |
| B09 | Actual Cesium/WebGL geometry, visibility, recovery | [Observations](../outputs/integration-mvp/evidence/latest-full/B09/cesium-observations.json), [browser assertions](../outputs/integration-mvp/evidence/latest-full/B09/browser-results.json) |
| B10 | Launcher, final regression, curated artifacts, graph | [Final tests](../outputs/integration-mvp/evidence/latest-full/final-backend.xml), [commands and checks](../outputs/integration-mvp/evidence/latest-full/results.json) |

Screenshots: [planning](../outputs/integration-mvp/evidence/latest-full/B09/planning-success.png),
[simulation](../outputs/integration-mvp/evidence/latest-full/B09/simulation-success.png),
[API loss](../outputs/integration-mvp/evidence/latest-full/B09/api-loss.png),
[recovery](../outputs/integration-mvp/evidence/latest-full/B09/api-recovered.png).
Open traces with `cd frontend && npx playwright show-trace <absolute-trace-path>`.

Evidence lives in ignored `outputs/integration-mvp/evidence/<UTC>/`. Every gate
records commands, exit codes, elapsed time and assertion/evidence paths. The root
JSON records HEAD, tracked working-tree diff SHA-256, source content hashes
(including untracked implementation), input hashes, runtime versions and lockfile
hash. A source/input change during verification makes the full result fail.
The backend suite uses pytest; top-level unittest discovery would find zero tests.

## Nonblocking scope and tooling limits

This is local integration, not deployment or validation of simulation assumptions.
The model versions, policies, source settings and curated artifacts are preserved.
Runtime stores use macOS/Linux file locking. Existing dependency deprecation and
large Vite bundle warnings remain; logs retain their exact text. No required check
may be skipped to obtain a passing result.

Browser diagnostics are enabled only by `?acceptance=1` and return copied,
read-only observations. Geometry checks inspect actual Cesium EllipseGeometry
instances and path collections, readiness, WebGL and real postRender/renderError
events. Center tolerance is 1e-7 degrees; radius tolerance is 1e-6 metres. External
requests are blocked in core browser tests. JS DOM fault/race tests supplement,
but do not replace, real browser checks.

Graphify runs at execution start and at B10 after code changes. Its AST-only
refresh does not cover semantic document content. It reports unsupported files
and any hub-based community relabelling in the B10 log; the initial refresh
skipped 22 unsupported files. These warnings do not waive application acceptance.
