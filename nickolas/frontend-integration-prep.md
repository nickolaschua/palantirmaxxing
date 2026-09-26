# Frontend integration preparation

Prepared on 2026-09-26. Frontend preparation and canonical API contracts are complete in an isolated branch. The branch remains unmerged; no backend HTTP endpoint has been implemented or tested.

## Location and revision

- **Commit:** `d4f1a08` — frontend prepared for integration.
- **Branch:** `frontend/api-contract-complete`.
- **Final worktree:** `/tmp/sdth-frontend-contract` (`/private/tmp/sdth-frontend-contract` on macOS).
- **Owning local clone:** `/tmp/sdth-frontend-repository`. This branch belongs to that clone, not the main checkout.
- **Base commit:** `dc14c836de9b848e059d465dec85278ec63bddb7`.

Work initially started in `/Users/nicko/Desktop/Hackathons/SDTH-frontend-contract` on `frontend/api-contract-preparation`. When workspace permissions changed, the frontend changes were carried into the final worktree above. The original sibling worktree remains an incomplete earlier copy; use the final commit for review and reconciliation.

The implementation did not modify or merge into the backend agent's dirty checkout. This summary is a subsequent documentation addition in the requested `nickolas/` folder.

## Canonical contracts

The final branch adds `contracts/frontend-backend-api.md` and `contracts/planning-result.md`, indexed from `contracts/contracts.md`.

The HTTP contract specifies four future same-origin, read-only routes:

- `GET /api/v1/planning-results/latest`
- `GET /api/v1/planning-results/{resultId}`
- `GET /api/v1/simulation-results/latest`
- `GET /api/v1/simulation-results/{resultId}`

Only completed results are published. Latest means most recently published; ID lookup returns an immutable snapshot. Successful delivery uses `{resultId, publishedAt, result}`, with a separate opaque delivery identity, UTC publication timestamp, and unchanged nested payload. Failures use `{error:{code,message}}` with 404, 503, or 500. Responses require `Cache-Control: no-store`.

Planning and simulation retain independent `planning-result/1` and `simulation-result/1` versions. Incompatible payload changes need a new schemaVersion; HTTP envelope or route-semantic changes need `/api/v2`. V1 includes no authentication, submission, polling, push updates, or automatic replacement of a displayed result.

The planning contract documents exporter/parser/artifact evidence, required fields, units, WGS84 coordinates, synthetic display height and clocks, IDs and ordering, omitted versus null evidence, and supplied-radius wording. It explicitly identifies exporter outputs the current frontend cannot display. The existing simulation contract is referenced unchanged.

The new documents explicitly supersede historical guidance in `frontend/docs/API-DESIGN.md`, without editing that file.

## Frontend behavior

Both views remain fixture-backed through injectable asynchronous loaders. They now show Loading, Unavailable with a reason, and Retry. Payload validation precedes drawing. Superseded requests and requests settling after disposal cannot update the UI. Successful retries dispose previous layers without duplicates; failed validation preserves any already displayed valid snapshot.

Simulation summaries display omitted people or casualty figures as **Unavailable**, while preserving genuine zero as **0**. Planning disposal also removes burst layers.

`frontend/src/demo/delivery.ts` provides pure success-envelope and failure-body adapters for a later HTTP client. It does not fetch a live URL or modify nested payloads. Existing illustrative planning consequence enrichment remains confined to the fixture loader.

## Verification

Checks ran in the final isolated worktree. npm commands ran from `frontend/`.

| Command | Result |
| --- | --- |
| `npm ci` | Passed; 139 packages installed |
| `npm test` | Passed; 26 tests, including 8 delivery contract tests |
| `npm run test:ui` | Passed; 18 Vitest/jsdom tests |
| `npm run build` | Passed; TypeScript and Vite |
| `git diff --check` | Passed; committed diff also checked |
| `graphify update .` | Passed; generated graph retained locally outside the delivery diff |

Contract tests use envelopes around the actual checked-in planning and simulation artifacts. They verify unchanged parser inputs and rejection of wrong result kinds, missing/empty delivery identities, invalid publication times, unsupported schemas, malformed results, and malformed error bodies. All three documented error examples are tested.

UI tests exercise both real mount functions with mocked canvas/inspector dependencies: pending and valid loads, rejection, invalid schema, Retry recovery, repeated loads without duplicate layers, stale success/failure, disposal during loading, retention of a validated snapshot after failed retry, and omitted figures versus zero.

Nonblocking output included large-bundle warnings, a deprecated transitive `sourcemap-codec` package, and an optional `fsevents` install-script notice.

## Changed files in the implementation commit

- `contracts/contracts.md`
- `contracts/frontend-backend-api.md`
- `contracts/planning-result.md`
- `frontend/docs/API-PREPARATION-VERIFICATION.md`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vitest.config.ts`
- `frontend/src/demo/decision-model.ts` — contract reference comment only
- `frontend/src/demo/decision.ts`
- `frontend/src/demo/delivery.ts`
- `frontend/src/demo/result-loader.ts`
- `frontend/src/demo/simulation.ts`
- `frontend/src/demo/source.ts`
- `frontend/src/demo/style.css`
- `frontend/tests/delivery.test.ts`
- `frontend/tests/views.ui.test.ts`

Scope verification confirmed no changes to backend code, existing result artifacts, `contracts/simulation-result.md`, `frontend/src/demo/simulation-model.ts`, `tests/unit/simulation-model.test.ts`, or `frontend/docs/API-DESIGN.md` relative to the base commit. Tests used the committed baseline artifacts and parser, not the backend agent's uncommitted changes.

## Remaining integration work

When backend work is ready, reconcile its updated parser, simulation contract, and artifacts with this branch before merging. Implement the service against the canonical delivery contract, then add an explicit HTTP loader using the pure adapters and rerun the frontend suites against the reconciled artifacts.

Backend integration tests must establish route behavior, publication ordering, immutable snapshots, response headers, and failure statuses. **Backend HTTP conformance remains untested.** The jsdom tests also do not establish real Cesium/WebGL rendering correctness.

Detailed verification is recorded in `frontend/docs/API-PREPARATION-VERIFICATION.md` within the final worktree.
