# Handoff: interceptor bases in the decision view

Emmanuel · 27 Sep 2026 · branch `EMMANUEL` · **not committed yet**

## What changed

The decision view now shows friendly interceptors. Three bases sit on the map, each holding 8 interceptors. When a threat is detected, the nearest base that can reach the intercept point in time launches one. It flies a parabolic arc and meets the threat exactly at the backend's intercept point and time. The existing descent and burst then play as before.

**This changes the decision view's behaviour. There is no FIRE button any more.** The flow is now:

1. **Standby.** The three bases are shown with their `8/8 ready` labels.
2. **Space or Play.** The threat is detected. The backend's **lowest-exposure** option becomes the intercept, and the tray says which base will launch and when.
3. **The base waits, then launches on its own** at the computed time. One interceptor is taken from that base's stock.
4. **Intercept.** The interceptor meets the threat, then the existing descent, burst and outcome follow.

What was removed:
- the FIRE button;
- selecting an option by clicking a card;
- the 1–9 key shortcuts.

The option cards are now display only.

## Files

| File | Change |
|---|---|
| `frontend/src/demo/interceptor-model.ts` | **New.** All the interceptor math. Pure functions with no DOM or Cesium, so they can be unit-tested. |
| `frontend/src/demo/decision.ts` | Base markers and their labels, the interceptor path, and the automatic launch in `render()`. Also the new tray messages and the read-only cards. |
| `frontend/src/demo/decision-model.ts` | New `engagementOption()`. `detect()` and `advance()` now take the planned engagement. `select()` and `fire()` are removed. |
| `frontend/src/demo/style.css` | Removed the `.fire` and tray `kbd` styles, which are no longer used. |
| `frontend/package.json` | Added `tests/unit/interceptor-model.test.ts` to `npm test`. |
| `tests/unit/interceptor-model.test.ts` | **New.** |
| `tests/unit/decision-model.test.ts` | Flow tests rewritten for the automatic launch. |

Nothing changed in `src/lib/`. The interceptor reuses the existing `addPath` with the `"craft"` marker, plus `addMarkers`, `addBurst` and the time module.

## How the interceptor model works (`interceptor-model.ts`)

**`BASES`**
- Khatib Camp, Tengah Air Base and Paya Lebar Air Base, with 8 interceptors each.
- The coordinates are the centres of their outlines in `military.json`.

**`planLaunch(base, target, detectionS)`**
- Launch time = intercept time − distance ÷ 400 m/s.
  - Distance is measured flat over the ground.
  - 400 m/s is the horizontal speed. It is deliberately slow so an audience can follow the flight.
- If the launch time comes before detection, the target is **out of range** for that base.
- If the launch time is later than now, the base simply waits.

**`chooseBase(bases, stock, target, detectionS)`**
- Of the bases that have interceptors left and can reach the target in time, it picks the one nearest the intercept point.
- It returns `null` if no base qualifies.

**`interceptorSamples(base, target, plan, start)`**
- Returns 25 time-stamped points for `addPath`.
- The path is a straight line over the ground. Its height follows a ballistic parabola: it leaves the ground at launch and reaches the intercept height exactly on time.
- The last point is set exactly to the intercept point.

Tuning:
- Speed is `INTERCEPTOR_SPEED_MPS`.
- Bases and their stock are in `BASES`.
- The rule for which intercept to engage is `engagementOption()` in `decision-model.ts`. It currently uses the backend's `categoryAssignments.lowestExposure`.

## How it's wired in `decision.ts`

- **`planEngagement()`** runs in `detectNow()`. It picks the option and the base, builds the interceptor path, and keeps it hidden. If no base can fire, it stores the reason in `noLaunch`.
- **`render()`** passes `engagement.plan.launchS` to `advance()`.
  - When the flow goes from `live` to `fired`, the base's stock goes down by one, the labels are redrawn, and the interceptor is shown.
- **`beginImpact()`** also hides the interceptor's craft marker.
- **`reset()`** (Restart) destroys the interceptor and clears the engagement.
  - **Stock is not reset.** It is kept across restarts, the same way History is, so the count visibly goes down. Reloading the page resets it.
- **The standby camera framing** now includes all three bases.

## What you'll see with the demo fixture

- **Paya Lebar fires.** It is 5.8 km from the intercept point.
- **Timing:** launch at T+2.3 s, intercept at T+16.8 s, so about 14.5 s of flight.
- **Khatib:** 6.55 km away, so it takes over once Paya Lebar has used all 8.
- **Tengah:** 16.6 km away. It would have to launch before the threat is detected, so it is out of range.

## Running it

```sh
cd frontend
npm test          # 40/40, including the new interceptor tests
npm run test:ui   # 28/28
npm run build
npm run dev       # then open /?source=fixture and press Space
```

All of the above passed tonight. The flow was also checked in a headless browser against the dev server: it launched from Paya Lebar at T+2.3 s, reached the intercept at T+16.8 s, and threw no console errors.

## Known issues and open questions

- **The standby view is zoomed further out.** Framing now includes Tengah in the far west, so it shows the whole island and the threat corridor is small on screen. One option is to frame only the corridor and the firing base.
- **Labels overlap near Khatib.** When zoomed in, the base label overlaps the OSM labels for Khatib Camp and Yishun Community Hospital. It could be shortened to just `8/8 ready`, or offset.
- **The arc looks flat from above.** The planning result puts intercepts at a 1,000 m visualization height, so the arc peaks at about 1,020 m. It reads well from a tilted camera but looks almost straight from the default top-down pitch.
- **The base choice never really shows here.** The decision view has only one threat, so the same base fires on every run. Showing all three bases engaging needs a multi-threat view.
  - The 8-threat simulation view has backend data but no playback yet.
  - The comparison view has playback but uses a synthetic fixture.
- **The inspector's "Window" row still shows "Fired"** for the engaged option. It wasn't changed.

The full plan and rationale are in `docs/plans/2026-09-27-interceptor-base-khatib.md`.
