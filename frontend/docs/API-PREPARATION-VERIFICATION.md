# Frontend API preparation verification

Verified 2026-09-26 against base dc14c836de9b848e059d465dec85278ec63bddb7.

Final worktree: /tmp/sdth-frontend-contract (macOS resolves to /private/tmp).
Branch: frontend/api-contract-complete, in local clone /tmp/sdth-frontend-repository.
The original sibling worktree was left in place when workspace write permissions
changed. This final branch carries its frontend work forward and remains unmerged.

## Required commands

Run npm commands from frontend/ and Git/graphify commands from the worktree root.

| Command | Result |
| --- | --- |
| npm ci | Exit 0, 139 packages installed |
| npm test | Exit 0, 26 tests passed (8 delivery contract tests plus 18 existing tests) |
| npm run test:ui | Exit 0, 18 Vitest/jsdom tests passed |
| npm run build | Exit 0, TypeScript and Vite build passed |
| git diff --check | Exit 0 |
| graphify update . | Exit 0, AST graph refreshed locally and excluded from delivery diff |

Build reports large bundle warnings; npm reports a deprecated transitive
sourcemap-codec package and an unapproved optional fsevents install script.
Neither prevented the required checks.

## Requirement evidence

- contracts/frontend-backend-api.md: all four GET routes, completed publication,
  immutable IDs, UTC publication time, no-store, 404/503/500 errors, version rules,
  no running HTTP service, explicit supersession of historical API-DESIGN.
- contracts/planning-result.md: exporter/parser/artifact sources; fields, units,
  WGS84, synthetic clocks/heights, ordering/references, absent/null evidence,
  supplied-radius language and documented producer/parser compatibility limits.
- contracts/contracts.md: links to both canonical documents and existing
  simulation contract.
- frontend/tests/delivery.test.ts: actual checked-in artifacts, unchanged parser
  inputs, wrong kinds, missing identities, invalid UTC dates/times, unsupported
  schemas, malformed results and the three documented failure examples.
- frontend/tests/views.ui.test.ts: both real mount functions with mocked canvas
  and inspector; pending, valid, rejected and invalid loads, Retry recovery,
  repeated successful loads with no duplicate live layers, late success/failure
  after disposal or supersession, failed refresh retaining prior snapshot, and
  missing simulation figures versus actual zero.
- source.ts retains fixture defaults and exports asynchronous loaders.
  result-loader.ts supplies visible status/retry with generation and disposal
  guards. delivery.ts contains only pure adapters, without a fetch implementation.

## Changed files

- contracts/contracts.md
- contracts/frontend-backend-api.md
- contracts/planning-result.md
- frontend/docs/API-PREPARATION-VERIFICATION.md
- frontend/package.json
- frontend/package-lock.json
- frontend/tsconfig.json
- frontend/vitest.config.ts
- frontend/src/demo/decision-model.ts (canonical contract comment only)
- frontend/src/demo/decision.ts
- frontend/src/demo/delivery.ts
- frontend/src/demo/result-loader.ts
- frontend/src/demo/simulation.ts
- frontend/src/demo/source.ts
- frontend/src/demo/style.css
- frontend/tests/delivery.test.ts
- frontend/tests/views.ui.test.ts

Scope was checked against the base: backend code, existing result artifacts,
contracts/simulation-result.md, frontend/src/demo/simulation-model.ts,
tests/unit/simulation-model.test.ts and frontend/docs/API-DESIGN.md are unchanged.
The backend agent's dirty checkout was not modified or merged into.

No backend endpoint has been implemented or tested. Backend HTTP conformance
remains untested. jsdom tests do not test real Cesium/WebGL rendering.
