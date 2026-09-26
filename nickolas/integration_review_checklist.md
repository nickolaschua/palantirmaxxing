# Integration code review checklist

Review target: `3e4dc60` (`frontend backend merge, untested`) against parent `8f254c8`. Read [integration_summary.md](integration_summary.md) first. All boxes below are intentionally unchecked: retained acceptance evidence is available, but these boxes represent your review and sign-off. Mark an item complete only after inspecting its code or recording the relevant reproduction/evidence. Record a reason for anything judged not applicable.

Reviewer: __________  Reviewed revision: __________  Date: __________

## 1. Establish scope and evidence

- [ ] Inspect `git show --stat 3e4dc60` and `git diff 3e4dc60^ 3e4dc60`; account for all 44 changed files using the inventory below.
- [ ] Check `git status --short` and record any additional changes being reviewed. Distinguish the integration commit from these later documentation files and unrelated untracked files.
- [ ] Read the canonical [HTTP/job contract](../contracts/frontend-backend-api.md), [planning schema](../contracts/planning-result.md) and [simulation schema](../contracts/simulation-result.md).
- [ ] Confirm the expected scope: fixed planning demo, baseline simulation with seed, local delivery/run controls; no scenario editor, dynamic replanning or policy-improvement claim.
- [ ] Open the fixed [retained report](../outputs/integration-mvp/evidence/20260926T032523.419873Z/results.json). Check overall status, all ten gates, command exits and `testedStateUnchanged`.
- [ ] Understand that retained evidence records pre-commit HEAD `8f254c8` plus source/diff hashes, not a post-commit execution at `3e4dc60`. Rerun acceptance on the revision you intend to approve.
- [ ] Confirm evidence/input snapshots are available to the reviewer. Ignored `outputs/` evidence is not present merely because the commit was pushed.

## 2. Payload and delivery validation

Inspect [validation.py](../backend/api/validation.py), existing [delivery.ts](../frontend/src/demo/delivery.ts), [decision-model.ts](../frontend/src/demo/decision-model.ts) and [simulation-model.ts](../frontend/src/demo/simulation-model.ts).

- [ ] Compare backend publication validation with both existing frontend parsers; identify and justify differences in accepted payloads.
- [ ] Check both schema versions remain unchanged and wrong-kind/unsupported-version responses fail visibly.
- [ ] Check missing fields, incorrect containers, empty identifiers, duplicate IDs and invalid cross-references.
- [ ] Check numeric validation rejects booleans where numbers are required, NaN/infinity, and out-of-range coordinates/times/radii.
- [ ] Check timestamps are real UTC instants, with supported precision; inspect invalid dates, offsets and malformed strings.
- [ ] Check planning candidate/opportunity/selection references and simulation threat/resource/assignment/path references remain consistent.
- [ ] Check optional/null values, partial coverage and absent consequence data retain their documented meaning rather than becoming fabricated zeros.
- [ ] Confirm payload units and axes remain unchanged: longitude/latitude, height, metres, timestamps and population quantities.
- [ ] Confirm delivery identity stays separate from scenario/episode identity and payload fields are not altered by envelope handling.
- [ ] Verify fresh exporter outputs are accepted by both Python validation and TypeScript parsers, including simulation seeds 7, 17 and 10020.

## 3. Result storage and atomic publication

Inspect [store.py](../backend/api/store.py) and [test_result_store.py](../tests/integration/test_result_store.py).

- [ ] Trace validation → immutable snapshot write → index replacement → readable publication. Confirm no partial output becomes latest.
- [ ] Check UUID validation, result-kind lookup and reserved `latest` handling; test wrong-kind, missing, malformed and traversal-like IDs.
- [ ] Check independent latest selection per kind and monotonically persisted sequence ordering, including equal publication timestamps and concurrent calls.
- [ ] Confirm repeated identical payloads produce distinct immutable IDs; fetching an older ID returns its original payload/time.
- [ ] Inspect file and directory fsync, temporary-file cleanup and index replacement. Confirm pre-index failure leaves preceding latest readable.
- [ ] Inspect the failure boundary after `os.replace` but before directory fsync completes: decide whether reported failure and committed visibility need additional handling/testing.
- [ ] Confirm orphan snapshot files are ignored, and read errors/corrupt index/snapshot failures are handled explicitly.
- [ ] Review the degree of validation on persisted index/envelope contents and decide whether corruption/tampering cases need additional coverage.
- [ ] Confirm one writable store per directory, correct lock release on close/error, and behavior of read-only/closed stores.
- [ ] Check payload copying prevents caller mutation from altering published data or returned in-memory run state.
- [ ] Verify restart preserves publication order and exact-ID lookup; note macOS/Linux `fcntl` dependency.
- [ ] Decide whether unbounded index/history growth and orphan-file cleanup are acceptable for the local MVP; record follow-up ownership if needed.

## 4. HTTP service

Inspect [server.py](../backend/api/server.py) and [test_result_http.py](../tests/integration/test_result_http.py).

- [ ] Exercise all four result routes and both run routes over real HTTP, directly and through Vite.
- [ ] Verify JSON content type, no-store, content length and strict JSON encoding on successes and errors.
- [ ] Check 404 missing result/run, 503 store unavailable, 500 unexpected failure, 400 invalid submission and 429 queue-full behavior.
- [ ] Check unsupported methods, malformed paths, encoded IDs, empty path segments and query strings behave consistently with the contract.
- [ ] Confirm GET is read-only: it never exports, publishes, trains or rewrites curated artifacts.
- [ ] Check request-body size limit (4096 bytes), missing/invalid Content-Length, transfer encoding, invalid/truncated JSON and read timeout behavior.
- [ ] Review JSON content-type handling and malformed/slow request behavior; decide whether current local-service behavior is sufficient.
- [ ] Confirm server binding is restricted to `127.0.0.1`; understand that loopback binding alone does not implement authentication or browser-origin authorization.
- [ ] Check error messages rendered in the browser are treated as text and unexpected server exceptions do not expose tracebacks in response bodies.
- [ ] Confirm standalone server startup works without Vite and bootstrap is explicit; missing latest without bootstrap is a normal 404.

## 5. Run queue, exporter execution and restart

Inspect [jobs.py](../backend/api/jobs.py) and [test_run_jobs.py](../tests/integration/test_run_jobs.py).

- [ ] Verify accepted request shapes exactly: planning kind only; simulation kind plus optional seed, default 7.
- [ ] Check seed endpoints 0 and 2147483647 and reject negative, oversized, fractional, boolean, string and unknown-field inputs.
- [ ] Trace queued → running → succeeded/failed persistence and timestamps, including submission/save failures.
- [ ] Confirm one exporter runs at a time, eight jobs may wait, overflow returns 429, and a failed job does not kill the worker.
- [ ] Inspect fixed argv and working directory: planning scenario is fixed; simulation policy is baseline; user input cannot select shell commands or paths.
- [ ] Check per-run isolated output/logs and validate exporter output before publication.
- [ ] Verify nonzero exit, missing/invalid JSON, schema-invalid output, timeout and shutdown leave preceding latest unchanged.
- [ ] Inspect 120-second timeout and termination/escalation of owned subprocess groups; confirm children are reaped.
- [ ] Check shutdown with an active job and queued jobs, and whether any race permits publication after stopping.
- [ ] Confirm terminal jobs persist and interrupted queued/running jobs become failed on restart.
- [ ] Trace the atomic commit of successful run status plus result ID in `index.json`; verify committed success overrides a missing/stale run-file mirror.
- [ ] Read the injected mirror-write-failure regression and confirm it checks restart and exact result identity.
- [ ] Inspect corrupt run-file recovery and persistent write-error handling; record any unsupported recovery cases rather than assuming all disk failures are covered.
- [ ] Consider ambiguous submission failures (server accepted but response was lost). Decide whether duplicate jobs on user retry are acceptable; no idempotency key is specified.

## 6. Frontend HTTP source, refresh and identity

Inspect [source.ts](../frontend/src/demo/source.ts), [fixture-source.ts](../frontend/src/demo/fixture-source.ts), [result-loader.ts](../frontend/src/demo/result-loader.ts) and [views.ui.test.ts](../frontend/tests/views.ui.test.ts).

- [ ] Confirm HTTP is the default and only explicit query/environment selection enables fixtures; unsupported source names fail visibly.
- [ ] Verify fixtures are dynamically imported only in fixture mode and no transport/status/parse error triggers silent fallback.
- [ ] Check URL encoding, no-store fetches, abort signal propagation and requested-ID/envelope-ID matching.
- [ ] Check initial loading, unavailable, retry and successful states in each view, including malformed JSON/envelope/payload.
- [ ] Confirm result ID and publication time displayed correspond to the visible payload.
- [ ] Confirm Refresh fetches latest explicitly and publication alone does not swap the current view.
- [ ] Test overlapping refreshes, out-of-order responses and disposal during pending requests; only the current request may update UI/resources.
- [ ] Confirm failed fetch, validation or render construction preserves the preceding snapshot, identity and usable controls.
- [ ] Check successful replacement disposes the previous view once and leaves exactly one active set of controls/layers/listeners.
- [ ] Inspect retry after an exact-ID load failure: generic Retry fetches latest. Decide whether that behavior needs an explicit label or exact-ID retry for the intended workflow.
- [ ] Confirm planning history carries its source result ID, resets for a new snapshot and does not mix results.
- [ ] Verify planning Restart resets presentation only and produces no POST request.

## 7. Render resources and Cesium integration

Inspect [result-resources.ts](../frontend/src/demo/result-resources.ts), [decision.ts](../frontend/src/demo/decision.ts), [simulation.ts](../frontend/src/demo/simulation.ts) and changed `frontend/src/lib/` files.

- [ ] Trace ownership of paths, markers, circles, labels, bursts, event subscriptions, timers and DOM nodes from first allocation through disposal.
- [ ] Inject failure partway through each view's construction; verify partial resources are released and the old view remains functional.
- [ ] Check resource cleanup is idempotent and cleanup order is safe; inspect behavior if a cleanup callback itself throws.
- [ ] Confirm keyboard/clock listeners and pending outcome timers do not survive replacement or navigation.
- [ ] Check shared canvas resources are not accidentally owned/destroyed by an individual result view.
- [ ] Inspect proxy method binding and the intercepted layer-creation list; verify all new resource-producing APIs are accounted for.
- [ ] Verify actual circle centers/radii and paths match payload geometry, including initial visibility and user visibility controls.
- [ ] Confirm draw/render failures are observed and geometry checks use actual Cesium objects, not only a copied expected-value manifest.
- [ ] Check `?acceptance=1` gates diagnostics and returns copies; normal page use should not expose a mutable test-control surface.
- [ ] Inspect API loss and recovery screenshots and exercise recovery while keeping the previous snapshot visible.
- [ ] Verify plain-basemap mode and removal of remote fonts allow the tested core experience without remote providers.
- [ ] Review labels, keyboard operation, focus behavior and status announcements for loading, retry, run submission and seed validation.

## 8. Frontend run controls

Inspect [run-controls.ts](../frontend/src/demo/run-controls.ts) and B08 in [browser-integration.mjs](../frontend/tests/browser-integration.mjs).

- [ ] Confirm separate planning/simulation submission bodies and client-side seed validation agree with the server.
- [ ] Confirm repeated clicks cannot submit another job while a run is active; seed is disabled during submission/execution.
- [ ] Check queued/running/succeeded/failed messages and run/result identities are visible and accurate.
- [ ] Verify one-second polling does not overlap, stops on terminal status and cancels timers/fetches on disposal.
- [ ] Check polling response identity/status validation rejects malformed or mismatched run records.
- [ ] Confirm polling transport failure keeps the existing run active and Retry run status does not create another job.
- [ ] Publish a competing result before the job finishes; confirm the UI requests the job's exact result ID rather than latest.
- [ ] Verify job failure preserves the previous view and permits a new submission.
- [ ] Inspect successful job followed by result-fetch/render failure; distinguish job success from display failure and check recovery is understandable.
- [ ] Confirm fixture mode disables backend runs and labels illustrative data clearly.

## 9. Launcher, prerequisites and dependencies

Inspect [run_integration_mvp.py](../scripts/run_integration_mvp.py), [integration_preflight.py](../scripts/integration_preflight.py), [preflight.mjs](../frontend/tests/preflight.mjs), [test_mvp_launcher.py](../tests/integration/test_mvp_launcher.py) and [vite.config.ts](../frontend/vite.config.ts).

- [ ] Follow setup from a clean environment: Python requirements, `npm ci`, managed Chromium, population acquire/prepare and preflight.
- [ ] Check preflight validates actual data and pinned identity, reports exact missing paths/recovery commands and fails when Chromium is absent.
- [ ] Inspect Python requirement inclusions and the Playwright pin/lockfile change; confirm installation does not change the lockfile.
- [ ] Verify distinct valid port arguments, occupied-port rejection and failure without killing an unrelated process.
- [ ] Test missing-store bootstrap and existing-store restart; confirm bootstrap adds only missing result kinds.
- [ ] Confirm readiness checks both result kinds directly and through the Vite proxy before printing Ready.
- [ ] Inspect `MVP_API_TARGET`, proxy target and strict-port behavior, including custom ports/store directory.
- [ ] Test Ctrl-C, startup interruption, preflight failure, backend failure and frontend failure; verify owned children are stopped and logs remain available.
- [ ] Check logs identify failed children and provide enough diagnostic context without modifying unrelated processes/files.
- [ ] Confirm the supported launch path is Vite development serving; production build success does not itself configure a deployed API proxy.

## 10. Automated verification and evidence quality

Inspect [verify_integration_mvp.py](../scripts/verify_integration_mvp.py), [check_fresh_results.py](../scripts/check_fresh_results.py), [fresh-results.mjs](../frontend/tests/fresh-results.mjs), [browser_fixture_server.py](../scripts/browser_fixture_server.py) and [browser-integration.mjs](../frontend/tests/browser-integration.mjs).

- [ ] Read each gate B01–B10 and check its assertions prove the stated capability, including failure paths rather than only successful rendering.
- [ ] Distinguish real exporter/server tests from fault-injection fixture-server tests and JS DOM tests; verify coverage claims match the execution path.
- [ ] Verify deterministic comparisons use fresh outputs and repeated seeds rather than only checked-in fixtures.
- [ ] Check the fixture server's malformed/unavailable/delayed responses model the intended client failure cases.
- [ ] Confirm core browser gates block external requests and fail on missing WebGL/browser prerequisites rather than skipping.
- [ ] Inspect B09 actual geometry observations, postRender/renderError observations, path counts/visibility and circle tolerances.
- [ ] Confirm JUnit and frontend/UI output checks reject failures/skips and meaningful test counts are present; use pytest for the full backend suite.
- [ ] Inspect subprocess timeouts and cleanup in the harness so failures do not leave servers/browsers running.
- [ ] Confirm fingerprints include untracked implementation, input hashes, lockfile and runtime versions; inspect intentional exclusions.
- [ ] Check source/input stability compares beginning and end state; do not edit files during a full run.
- [ ] Check all gate results and final status, not just exit logs or the existence of `latest-full` (which also advances on failed full attempts).
- [ ] Verify `data/results` curated artifacts remain unchanged and runtime stores/evidence are ignored.
- [ ] Inspect dependency deprecation and bundle-size warnings and decide whether follow-up work is needed.
- [ ] Note graphify AST refresh limitations; use source as authority when graph/document semantics are absent.

Run from the repository root after stopping any default-port launcher:

```sh
.venv-rl/bin/python scripts/verify_integration_mvp.py --all
```

Focused commands for investigating a finding:

```sh
.venv-rl/bin/python -m pytest -q tests/integration/test_result_store.py tests/integration/test_result_http.py tests/integration/test_run_jobs.py tests/integration/test_mvp_launcher.py
npm --prefix frontend test
npm --prefix frontend run test:ui
npm --prefix frontend run build
.venv-rl/bin/python scripts/verify_integration_mvp.py --gate B06
# Replace B06 with the gate under investigation.
```

- [ ] Record your new evidence path, revision, overall status and any findings. Open browser traces with `npx playwright show-trace <absolute-trace-path>` from `frontend/`.

## 11. Manual end-to-end walkthrough

- [ ] Start the launcher and open its plain-basemap URL; inspect both views and their HTTP snapshot metadata.
- [ ] Run planning, observe job progress, confirm a new exact result appears, then use planning presentation controls and Restart.
- [ ] Run simulation with seed 7, then another valid seed; confirm separate run/result IDs and updated visible output.
- [ ] Submit an invalid seed and verify visible rejection without a job request.
- [ ] Refresh both views and inspect Network requests for latest versus exact-ID paths.
- [ ] Stop the API during an existing view, refresh, and confirm an explicit error retains the view; restore service and retry.
- [ ] Restart the launcher and confirm stored IDs remain readable; verify no unnecessary demo rerun changes latest.
- [ ] Navigate away/reload during pending activity and inspect for stale controls, leaked layers/listeners and browser console errors.
- [ ] Open fixture mode, verify its label and disabled runs, then return to HTTP mode.
- [ ] Inspect planning, simulation, API-loss and recovery screenshots; record any layout/interaction problems the automated assertions miss.

## 12. Documentation and review decision

- [ ] Cross-check README, backend API guide, HTTP/planning contracts and readiness instructions against actual behavior.
- [ ] Flag older README “Open decisions” and historical frontend API-design prose that conflicts with the implemented local transport; keep canonical-versus-historical status clear.
- [ ] Confirm docs distinguish integration correctness from model validity, baseline demonstration from trained-policy improvement, and local MVP from production deployment.
- [ ] Record limitations: POSIX process/locking behavior, single writer/worker, no production auth/deployment, no retention policy, local evidence availability and limited platform coverage.
- [ ] Assign every blocking finding an owner and reproduction; resolve or explicitly defer nonblocking findings with a reason.
- [ ] Rerun affected checks after fixes, then the full acceptance run for the final reviewed source state. Refresh graphify after code changes per project instructions.
- [ ] Sign off only on the revision/evidence you actually reviewed.

| Finding | File / location | Reproduction or evidence | Severity | Owner / resolution |
| --- | --- | --- | --- | --- |
| | | | | |

Decision: Approve / Request changes / Approve with documented follow-ups

Final revision: __________  Evidence directory: __________  Reviewer: __________

## Changed-file inventory

Use this inventory as a completeness check. Existing parsers/exporters/contracts referenced above are important dependencies even when they were not changed in this commit.

- [ ] [.gitignore](../.gitignore) — reviewed.

- [ ] [README.md](../README.md) — reviewed.

- [ ] [backend/api/__init__.py](../backend/api/__init__.py) — reviewed.

- [ ] [backend/api/api.md](../backend/api/api.md) — reviewed.

- [ ] [backend/api/jobs.py](../backend/api/jobs.py) — reviewed.

- [ ] [backend/api/server.py](../backend/api/server.py) — reviewed.

- [ ] [backend/api/store.py](../backend/api/store.py) — reviewed.

- [ ] [backend/api/validation.py](../backend/api/validation.py) — reviewed.

- [ ] [contracts/frontend-backend-api.md](../contracts/frontend-backend-api.md) — reviewed.

- [ ] [contracts/planning-result.md](../contracts/planning-result.md) — reviewed.

- [ ] [frontend/index.html](../frontend/index.html) — reviewed.

- [ ] [frontend/package-lock.json](../frontend/package-lock.json) — reviewed.

- [ ] [frontend/package.json](../frontend/package.json) — reviewed.

- [ ] [frontend/src/demo/decision-model.ts](../frontend/src/demo/decision-model.ts) — reviewed.

- [ ] [frontend/src/demo/decision.ts](../frontend/src/demo/decision.ts) — reviewed.

- [ ] [frontend/src/demo/fixture-source.ts](../frontend/src/demo/fixture-source.ts) — reviewed.

- [ ] [frontend/src/demo/main.ts](../frontend/src/demo/main.ts) — reviewed.

- [ ] [frontend/src/demo/result-loader.ts](../frontend/src/demo/result-loader.ts) — reviewed.

- [ ] [frontend/src/demo/result-resources.ts](../frontend/src/demo/result-resources.ts) — reviewed.

- [ ] [frontend/src/demo/run-controls.ts](../frontend/src/demo/run-controls.ts) — reviewed.

- [ ] [frontend/src/demo/simulation-model.ts](../frontend/src/demo/simulation-model.ts) — reviewed.

- [ ] [frontend/src/demo/simulation.ts](../frontend/src/demo/simulation.ts) — reviewed.

- [ ] [frontend/src/demo/source.ts](../frontend/src/demo/source.ts) — reviewed.

- [ ] [frontend/src/demo/style.css](../frontend/src/demo/style.css) — reviewed.

- [ ] [frontend/src/lib/events.ts](../frontend/src/lib/events.ts) — reviewed.

- [ ] [frontend/src/lib/index.ts](../frontend/src/lib/index.ts) — reviewed.

- [ ] [frontend/src/lib/overlays.ts](../frontend/src/lib/overlays.ts) — reviewed.

- [ ] [frontend/src/lib/types.ts](../frontend/src/lib/types.ts) — reviewed.

- [ ] [frontend/tests/browser-integration.mjs](../frontend/tests/browser-integration.mjs) — reviewed.

- [ ] [frontend/tests/fresh-results.mjs](../frontend/tests/fresh-results.mjs) — reviewed.

- [ ] [frontend/tests/preflight.mjs](../frontend/tests/preflight.mjs) — reviewed.

- [ ] [frontend/tests/views.ui.test.ts](../frontend/tests/views.ui.test.ts) — reviewed.

- [ ] [frontend/vite.config.ts](../frontend/vite.config.ts) — reviewed.

- [ ] [nickolas/integration-readiness.md](../nickolas/integration-readiness.md) — reviewed.

- [ ] [scripts/browser_fixture_server.py](../scripts/browser_fixture_server.py) — reviewed.

- [ ] [scripts/check_fresh_results.py](../scripts/check_fresh_results.py) — reviewed.

- [ ] [scripts/integration_preflight.py](../scripts/integration_preflight.py) — reviewed.

- [ ] [scripts/requirements-integration.txt](../scripts/requirements-integration.txt) — reviewed.

- [ ] [scripts/run_integration_mvp.py](../scripts/run_integration_mvp.py) — reviewed.

- [ ] [scripts/verify_integration_mvp.py](../scripts/verify_integration_mvp.py) — reviewed.

- [ ] [tests/integration/test_mvp_launcher.py](../tests/integration/test_mvp_launcher.py) — reviewed.

- [ ] [tests/integration/test_result_http.py](../tests/integration/test_result_http.py) — reviewed.

- [ ] [tests/integration/test_result_store.py](../tests/integration/test_result_store.py) — reviewed.

- [ ] [tests/integration/test_run_jobs.py](../tests/integration/test_run_jobs.py) — reviewed.
