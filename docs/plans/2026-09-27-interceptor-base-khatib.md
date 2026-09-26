# Plan: Khatib Camp interceptor base, auto-launched (decision view)

## Context

The demo shows incoming threats but no friendly interceptor. The backend already decides the intercept point and time. What's missing is something visible flying out to meet the threat. The final goal is three bases (Khatib Camp, Tengah Air Base, Paya Lebar Air Base), each holding 8 interceptors, with the right base engaging each target. **This step builds one base, Khatib Camp**, in the decision view (Space/Play → live threat → intercept → descent → burst). Once it looks right, the base list gets two more entries.

Decisions made with the user:
- **No FIRE click.** When the threat is detected, the intercept point is taken as fixed: it is the backend's `lowestExposure` option. The system works backwards from it to a launch time and launches automatically when that time arrives.
- **Launch time = intercept time − distance / 400 m/s.**
  - If the launch time is in the future, the base waits, then launches.
  - If it is before detection, the target is **out of range for that base**, and the base does not fire. With three bases, this rule is what excludes a base from the choice.
- **400 m/s horizontal, fixed.** This is slower than a real interceptor on purpose, so judges can follow it.
- All the new math lives in the frontend. The backend is unchanged.

Checked against `data/results/demo-planning-result.json`:
- The lowest-exposure option `k42` is at T+16.8 s, 6.55 km from Khatib.
- Flight time is 16.4 s, so the **launch is at T+0.4 s**. That is feasible and gives about 16 s of visible flight.
- `k11` would need a launch at T−9.3 s, which is out of range. It isn't used, but it is a good test case.

## Base coordinates

These are the centroids of the repo's own OSM military polygons in `frontend/src/demo/military.json`:

| Base | lon | lat |
|---|---|---|
| Khatib Camp (this step) | 103.8281 | 1.4226 |
| Tengah Air Base (later) | 103.7138 | 1.3913 |
| Paya Lebar Air Base (later) | 103.9105 | 1.3572 |

## Changes

### 1. New pure module `frontend/src/demo/interceptor-model.ts` (no DOM, no Cesium)
- `InterceptorBase { id, label, position: {lon, lat}, stock }` and `BASES`. For now `BASES` holds only Khatib, with stock 8.
- Constants: `INTERCEPTOR_SPEED_MPS = 400`, `GRAVITY_MPS2 = 9.80665` (the same value as the backend generator).
- `groundDistanceM(a, b)`: flat-earth metres, using the same `111_320·cos(lat)` and `110_574` factors already used in `decision-model.ts` (`framePose`, `circleBounds`, `approachOrigin`).
- `planLaunch(base, target: {position, timeFromStartS}, detectionS)` returns either:
  - `{ feasible: true, launchS, flightS, distanceM }`, where `flightS = d/400` and `launchS = tInt − flightS`; or
  - `{ feasible: false, requiredLaunchS }` when `launchS < detectionS`.
- `interceptorSamples(base, target, plan, start)` returns about 24 `TimedSample`s from launch to intercept:
  - lon and lat change linearly with time;
  - height is `z(t) = vz·t − ½g·t²`, with `vz = (h + ½g·T²)/T`, so the path leaves the ground at the base and reaches exactly the intercept height `h` at `T`. This is the same construction as the backend threat parabola in `singapore_scenario.py`.
  - At the demo's 1000 m visualization height the arc rises and flattens with its apex around 1,020 m, which is what a correct parabola gives for those numbers.
- `chooseBase(bases, stock, target, detectionS)`: among bases that have stock left and a feasible plan, pick the one **nearest the intercept point**, or return `null`. With one base this is trivial. It is the single piece of "decide between the 3" math, and later it only needs a longer `BASES` list.

### 2. `frontend/src/demo/decision-model.ts`: automatic flow
- Add `engagementOption(result, options)`, which returns the option whose id is `result.categoryAssignments.lowestExposure`.
- Extend `advance(flow, options, elapsed, launch?)`, where `launch` is `{ optionId, launchS } | null`:
  - `live` becomes `fired` once `elapsed >= launchS`, using the existing `fired` state.
  - While a launch is pending, `live` does not go to `expired` because the backend option's window closed. That window describes the backend's own synthetic interceptor, not our base.
  - If there is no feasible launch, the existing expiry rule stays.
- The `fired → impact → outcome` transitions are unchanged.
- `select` becomes unused by the UI. Remove it and its lines in the existing test. `fire` is folded into `advance`.

### 3. `frontend/src/demo/decision.ts`: wiring and visuals
- **Base marker:** always visible, drawn with `canvas.addMarkers`. Its label is `Khatib Camp · 8/8 ready`, and the stock number goes down on each launch.
- **At detection** (`detectNow`):
  - Pick the option with `engagementOption`.
  - Pick the base with `chooseBase` and compute the plan.
  - If feasible, build the interceptor path with `canvas.addPath(interceptorSamples(...), { color: "#35c78a", trailColor: <green 40%>, width: 3, markerSize: 25, markerShape: "craft", markerPulse: true })`. Keep it hidden until launch. (`addPath` in `lib/overlays.ts` already interpolates by time and points the craft along its direction of travel, so no library changes are needed.)
- **At launch** (the `fired` transition): show the interceptor path and decrement the stock.
- **At intercept** (`impact`): hide the interceptor marker with `setMarkerVisible(false)`. The existing `beginImpact` descent and the burst at `outcome` run as they do now.
- **Cards:** read-only.
  - Remove the FIRE button, the pick click handler and digit-key selection.
  - The engaged card is shown as `selected`, then `fired`.
  - The countdown text becomes `Launch in X s · Khatib Camp`, then `Interceptor away`.
  - Keep `data-candidate-id`, because `frontend/tests/browser-integration.mjs` depends on it.
- **Messages:**
  - `Threat detected — Khatib Camp launches at T+0.4 s (lowest exposure)`
  - `Interceptor away — intercept at T+16.8 s`
  - Out of range: `Lowest-exposure intercept out of range for Khatib Camp at 400 m/s — no launch`
- **Restart:** destroy the interceptor path and re-plan on the next detection. **Stock is kept across restarts**, like the history marks, so 8 → 7 → … is visible. When no base has stock left, the message is `No interceptor available`.
- **History entry:** `Threat N · Khatib Camp → Option k (id) · intercepted at T+x s`.
- **Framing:** add the base position to `framePoints` so the camera shows the base and the corridor together.

### 4. Tests
- New `tests/unit/interceptor-model.test.ts`, added to the `npm test` script in `frontend/package.json`. It covers:
  - `k42` from Khatib gives a launch of about 0.4 s and a flight of about 16.4 s, and is feasible.
  - `k11` is out of range.
  - The samples start at the base with h = 0 at `launchS`, end at the intercept position and height at `timeFromStartS`, are strictly increasing in time, and have h ≥ 0 throughout.
  - `chooseBase` picks the nearest feasible base, skips bases with no stock and out-of-range bases, and returns `null` when none qualify. This is tested with a three-base fixture so the next step is covered in advance.
- Update `tests/unit/decision-model.test.ts` for the new `advance` launch parameter: auto-launch, no expiry while a launch is pending, and the remaining transitions unchanged.

### 5. Project records
On approval, copy this plan to `docs/plans/2026-09-27-interceptor-base-khatib.md` and create `STATE.md` at the repo root, as CLAUDE.md requires.

## Critical files
- `frontend/src/demo/interceptor-model.ts` (new)
- `frontend/src/demo/decision-model.ts`, `frontend/src/demo/decision.ts`
- `tests/unit/interceptor-model.test.ts` (new), `tests/unit/decision-model.test.ts`, `frontend/package.json` (test script only)
- Reused unchanged: `lib/overlays.ts` `addPath` / `addMarkers`, `lib/craft.ts`, `lib/burst.ts`, `lib/time.ts`

## Verification
1. `cd frontend && npm test`: the new and updated unit tests pass.
2. `npm run build`: the type check and build succeed.
3. `npm run test:ui`: the existing vitest UI tests still pass.
4. `npm run dev` and open with `?source=fixture`, then press Space. Expected:
   - the base marker at Khatib reads 8/8;
   - the message gives launch at T+0.4 s;
   - the green craft lifts off, arcs and meets the threat at T+16.8 s over the k42 circle;
   - the threat's descent and burst play;
   - the base reads 7/8.
   Press R and then Space again: the base reads 6/8.
5. Temporarily force the `k11` option (dev only) to check the out-of-range message and that no launch happens.
