# Singapore canvas — API design

Last updated 2026-09-15. The first half describes the library **as built**. The
next section records the approved structure for the three-view decision demo.
The `planning-result/1` contract at the end is owned by the backend and is the
single source of truth for backend data.

Population milestone (14 September 2026): the viewer gained an independent
`addPolygonLayer` capability, a population explorer and offline data-preparation
tests — see [POPULATION-VERIFICATION.md](POPULATION-VERIFICATION.md).

| Status | Surface |
|---|---|
| **Built** | `createSingaporeCanvas`, `camera`, `scene`, `time`, `addPolygonLayer`, `addLabels`, `addPath`, `addMarkers`, `addGroundCircles`, `on`, `destroy`; the three-view demo switcher |
| **Next** | grey-canvas features, the decision demo — see "Next" below |
| **Dropped** | the earlier debris design — moving tracks, particle bursts, ground heatmap, `camera.follow` (removed) |

## Shape

```ts
const canvas = await createSingaporeCanvas(element, options);  // resolving IS "ready"
canvas.camera / canvas.scene
canvas.addPolygonLayer(data, callbacks)
canvas.on(event, handler)                                        // returns its own unsubscribe
canvas.destroy()
```

Ids everywhere. No Cesium object ever crosses the boundary.

## Contracts at the boundary

- **Positions** are `GeoPoint { lon, lat, height? }` — WGS84 degrees and metres. `Cartesian3` stays inside.
- **Instants** are JS `Date`. `JulianDate` stays inside.
- **Timed positions** are `TimedSample extends GeoPoint { time: Date }`. The
  `planning-result/1` contract below refers to this type.

---

## Construction — built

```ts
interface Bounds { west: number; south: number; east: number; north: number }  // WGS84 degrees
type BasemapKind = "plain" | "extruded" | "photorealistic";

interface CanvasOptions {
  ionToken?: string;
  googleApiKey?: string;
  basemap?: BasemapKind;              // default: photorealistic if googleApiKey, else extruded if ionToken, else plain
  lighting?: "midday" | "blue-hour";  // default "midday"
  bounds?: Bounds | null;             // default SINGAPORE_BOUNDS; null unlocks the cage
  maxHeight?: number;                 // default 80_000 m
  minHeight?: number;                 // default 60 m
  maximumScreenSpaceError?: number;   // Cesium's tile detail threshold, default 16; smaller is finer
}
```

The cage is enforced per frame — Cesium has no built-in geographic bounds.
`minHeight` rarely binds in practice: terrain collision stops the camera around
97–102 m above the ellipsoid first.

## camera — built

```ts
interface CameraModule {
  flyToPreset(name: string, opts?: { duration?: number }): Promise<void>;
  flyTo(pose: CameraPose, opts?: { duration?: number }): Promise<void>;
  orbit(opts: { centre: GeoPoint; radius: number; pitch?: number; degreesPerSecond?: number }): void;
  stop(): void;                          // cancels flight and orbit
  readonly pose: CameraPose;
  readonly presets: readonly string[];
}
```

Flights resolve on arrival and reject with `FlightCancelled` when interrupted.

## scene — built

```ts
interface SceneModule {
  setBasemap(kind: BasemapKind): Promise<void>;
  setLighting(preset: "midday" | "blue-hour"): void;
  readonly basemap: BasemapKind;
}
```

| Basemap | What it is |
|---|---|
| `plain` | Flat globe, no terrain or buildings, with the grey/blue ground layer. Needs no credentials; the fallback when remote data fails |
| `extruded` | World terrain + OSM buildings + the grey/blue ground layer |
| `photorealistic` | Google Photorealistic 3D Tiles |

The grey/blue ground layer (coastline, reservoirs, roads, pavements) is hidden on
`photorealistic`, and **also whenever a polygon layer is visible** — both draw on
the ground surface and would paint over each other. A failed remote basemap load
keeps the current map rather than blanking it.

## polygon layers — built

```ts
canvas.addPolygonLayer(data: object, callbacks: PolygonCallbacks, options?: { outline?: string }): Promise<PolygonLayer>;

interface PolygonCallbacks { hover(id: string | null): void; click(id: string | null): void }
interface PolygonLayer {
  setVisible(visible: boolean): void;
  setStyles(styles: ReadonlyMap<string, PolygonStyle>): void;
  destroy(): void;
}
interface PolygonStyle { color: string; visible: boolean; selected?: boolean }
```

`data` is geographic GeoJSON of `Polygon` / `MultiPolygon` features with unique
string IDs, drawn clamped to the ground. Picking returns the feature ID or `null`.
The loader replaces feature properties internally, so keep domain data in
application state keyed by ID. A multipart feature keeps its one ID.

`outline` (added 2026-09-16) draws every ring's boundary as a 2 px ground-draped
line in that CSS colour. It follows the layer's visibility, not each feature's
`visible` style.

## labels — built

```ts
canvas.addLabels(labels: readonly { position: GeoPoint; text: string }[], style?: { font?: string }): LabelLayer;
interface LabelLayer { setVisible(visible: boolean): void; destroy(): void }
```

Added 2026-09-16 for the population view's area names. White text with a dark
outline, never hidden by terrain or buildings, not pickable. A position without
`height` sits on the ground. Non-finite positions throw. The population view
uses two layers — planning-area names above 12 km camera height, subzone names
below — toggled through `cameraChange`.

## addBuildingTint — built

```ts
addBuildingTint(
  areas: readonly { id: string; ring: readonly GeoPoint[] }[],
  style: { color: string; outlineColor?: string; outlineWidth?: number },
): TintLayer;                       // setVisible, destroy
```

Added 2026-09-16. Colours the city's buildings whose footprint centre lies
inside any of `areas` and, when `outlineColor` is set, draws each area's
boundary on the ground (on Google's tiles too). Buildings are painted per tile
as tiles come into view, through a scene-internal `onTileset` hook, so the tint
survives basemap switches and tile reloads. It reads the footprint centre from
Cesium OSM Buildings' `cesium#longitude` / `cesium#latitude` feature
properties; Google's photorealistic tiles carry no per-building features, so
there only the outline draws. Outer rings only, no holes. Duplicate ids and
rings under three finite points throw. Known limit: after `destroy()`,
buildings already painted keep their colour until their tile reloads.

## events — built

```ts
type CanvasEvents = {
  cameraChange: CameraPose;
  tileLoadProgress: { pending: number };
  boundsHit: { edge: "west" | "south" | "east" | "north" | "ceiling" | "floor" };
};
```

- **`ready` was removed.** It fired inside `createSingaporeCanvas` before the
  function returned, so no caller could ever subscribe in time. The resolved
  promise is the ready signal.
- **There is no generic `pick` event.** Polygon layers take their own hover and
  click callbacks.

`on` returns its own unsubscribe. There is no `off(event, handler)` —
identity-matching handlers leaks whenever a caller passes an inline arrow function.

---

## Next — three views and decision demo

Design status, 2026-09-15: sections 1–3 are **approved**. The red areas and the
side window in section 3 are the user's own requests, with a few details still
**open**. Section 5 (data, errors, verification) is a **draft**, not yet
approved. Every unanswered item is in "Open questions" at the end of this
section. Implementation has not started.

### 1. Structure — approved

```
frontend/src/lib/                      library — no defence concepts
  time.ts             NEW       clock: setRange, play, pause, seek
  overlays.ts         NEW       addPath, addMarkers, addGroundCircles
  coastline.ts        EXTENDED  + forest / parks greens, road + rail bridges & tunnels
  camera.ts           CHANGED   `follow` stub removed
  scene.ts            unchanged — terrain stays at true heights
  polygons.ts         unchanged

frontend/src/demo/                     the application
  main.ts             CHANGED   three-view switcher replaces the basemap dropdown
  decision.ts         NEW       loads planning-result/1; cards, countdowns, FIRE, outcome
  decision-model.ts   NEW       pure logic: validation, countdown maths, deadline positions, flow states
  inspector.ts        NEW       side window: a zoomed second canvas on one area, plus its stats
  population.ts       TRIMMED   colours + legend + hover/click details only
  population-model.ts unchanged, along with its test
```

**Three exclusive views**, grey canvas by default:

| View | Scene basemap | Extra |
|---|---|---|
| Grey canvas *(default)* | `extruded` | grey ground + forest/parks greens + road & MRT/LRT bridges and tunnels, true-height terrain |
| Population | `plain` | coloured subzones, legend, hover/click details — no search, filter or ranking |
| Google | `photorealistic` | — |

The threat path, candidate markers, deadline marks and red option areas are added
once and survive view switches. `plain` is no longer a menu option: it is the
automatic fallback if terrain or buildings fail to load, and the base of the
population view.

**Terrain stays at true heights — no exaggeration.** `Scene.verticalExaggeration`
stretches terrain and every 3D tileset together, and no per-tileset opt-out was
found in the Cesium3DTileset source, so exaggeration would misstate building
heights. Canvas heights never feed the backend, which plans in 2D. Building
heights are recorded OSM values, or 3 m per level (at least one level) when OSM
has none.

**Heads-up for the backend partner:** `population.ts` loses its search,
planning-area filter, ranking chart and browse list; `plain` leaves the basemap
menu; `frontend/CODEBASE-SUMMARY.md` §10 still describes the dropped debris plan.

### 2. Library API — approved

Follows the `addPolygonLayer` pattern: each call returns a small handle, items
inside are addressed by string IDs, and no Cesium object leaves the library.

```ts
interface TimeModule {
  setRange(start: Date, stop: Date): void;   // stops at `stop`, never loops
  play(): void;                              // actual speed, 1×
  pause(): void;
  seek(t: Date): void;
  readonly current: Date;
  readonly playing: boolean;
}
type CanvasEvents = { /* existing … */ clockTick: Date };  // drives the countdowns

// Threat route: the full line, plus a marker that moves with the clock
addPath(samples: readonly TimedSample[], style?: { color?: string; width?: number }): PathLayer;
interface PathLayer { setVisible(visible: boolean): void; destroy(): void }

// Candidate markers and deadline marks — not pickable
addMarkers(markers: readonly { id: string; position: GeoPoint }[]): MarkerLayer;
interface MarkerStyle { color: string; size: number; visible: boolean; label?: string }
interface MarkerLayer {
  setStyles(styles: ReadonlyMap<string, MarkerStyle>): void;
  setVisible(visible: boolean): void;
  destroy(): void;
}

// Option areas, draped on whatever surface is showing — pickable
addGroundCircles(
  circles: readonly { id: string; center: GeoPoint; radiusM: number }[],
  callbacks?: CircleCallbacks,
): CircleLayer;
interface CircleCallbacks { hover(id: string | null): void; click(id: string | null): void }
interface CircleStyle { fill: string; outline: string; visible: boolean }
interface CircleLayer {
  readonly ready: Promise<void>;   // added in step 8 — see "Built in step 8"
  setStyles(styles: ReadonlyMap<string, CircleStyle>): void;
  setVisible(visible: boolean): void;
  destroy(): void;
}
```

| Call | Built on |
|---|---|
| clock | Viewer clock, `ClockStep.SYSTEM_CLOCK_MULTIPLIER` at ×1, `ClockRange.CLAMPED` *(verified)* |
| `addPath` | A route polyline, plus a point whose position is a `SampledPositionProperty` |
| `addMarkers` | A `PointPrimitiveCollection` with labels |
| `addGroundCircles` | `GroundPrimitive` + `EllipseGeometry`, radius in metres *(verified)*, draped on terrain and 3D tiles |

- **Actual speed only.** `setMultiplier` stays out of the API; slowed playback was
  considered and dropped.
- Countdowns subscribe through `clockTick` on the existing `on()`.
- The threat holds at its first sample before T+0.4 s, and at its last after T+20 s.
- **Circles are pickable; markers are not.** Circle hover and click return a
  circle ID, mirroring `addPolygonLayer`, and drive the side window.
- Circles never trigger the "require globe" rule, so the grey canvas stays visible.
- Duplicate IDs and non-finite coordinates or radii throw. Full payload
  validation happens once, in `decision-model.ts`.
- Deadline marks need no new API: `decision-model.ts` computes where the threat
  is at each option's close time, and they draw through `addMarkers`.
- The side window needs no new API: it is a second `createSingaporeCanvas`
  instance (the no-singleton rule allows it), framed with the existing
  `camera.flyTo`.
- Grey-canvas features need no API; they are internal to the ground layer.

**Built 2026-09-16 (step 7).** Checked in the browser against the demo result:

1. Circles render on Google's 3D tiles — **yes**, draped over the buildings.
2. Circles draw above the grey land and road fills — **yes** (vegetation is step 9).
3. A circle's fill and outline colour change without rebuilding — **yes**, via
   per-instance attributes once the primitives are ready; styles set earlier wait.
4. `ExtrapolationType.HOLD` holds the threat before its first and after its last sample.
5. `clockTick` does **not** fire while paused and unchanged: it fires whenever
   host time changes — every frame while playing, once per `seek`.
6. Picking a circle returns its ID — **yes**, on hover and click.
7. In population view, clicking a circle does not pin the zone underneath —
   **yes**: a polygon layer yields the pick when another layer's string-ID hit
   is on top.
8. Cost of the second canvas — still open; measured in step 8.

**Clock and sun.** Lighting pins the sun by setting the Viewer clock, and the
host animates with its own dates, so the time module maps between them: the
Viewer clock reads `sunInstant + (host − rangeStart)`. A 20 s scenario moves the
sun 20 s; switching lighting mid-play keeps host time. `setRange` seeks to the
start and pauses; playback stops at `stop` and `playing` turns false.

**Seen during the check:** the route and markers sit at the payload's synthetic
1,000 m height while circles drape on the ground, so at an oblique camera the
route appears offset from its circles. True scale, not nudged; a steeper camera
reduces it. Decide the Standby framing in step 8.

### 3. Demo flow — approved

**Data: `data/results/demo-planning-result.json`.** A fictional eastbound Ang Mo
Kio → Serangoon path: 20 s, 4.5 km at 225 m/s, a synthetic 1,000 m display
height, supplied 500 m footprints and real Census 2020 population. 50 candidates,
40 reachable, 10 on the frontier. Do **not** use `static-mvp-planning-result.json`
on stage — its population is synthetic.

| Option | Categories | Threat at circle | Window closes | People potentially exposed | Supplied success |
|---|---|---:|---:|---:|---:|
| `k11` | earliest viable, highest success | T+4.4 s | T+0.29 s | 15,252 | 0.9524 |
| `k46` | lowest exposure | T+18.4 s | T+8.51 s | 1,643 | 0.8964 |

```
STANDBY ──[Space: threat detected]──▶ LIVE ──[Enter: FIRE]──▶ FIRED ──(clock reaches intercept)──▶ OUTCOME
                                        │                                                           │
                                        └──(every option's window closes)──▶ EXPIRED                │
                                                                                  │                 │
                                                          STANDBY ◀──[R: reset]───┴─────────────────┘
```

| State | Clock | Map | Decision tray |
|---|---|---|---|
| **Standby** | Stopped at T+0 | Camera zoomed out, framing the whole path and every option's area; nothing drawn yet | "Standby — press Space on detection" |
| **Live** | Runs at actual speed, 1× | Route, moving threat, candidate markers, deadline marks, options' areas in red | One card per option: category badges, people potentially exposed, supplied success, intercept time, countdown bar; FIRE on the selected card |
| **Fired** | Keeps running | Chosen area locked; other areas and markers dimmed | Chosen card locked; others disabled |
| **Outcome** | Stops at the intercept time | Threat held at the intercept point, inside its area | Summary |
| **Expired** | Runs to T+20 s | Threat continues along the route; areas faded | "All engagement windows expired — nothing fired" |

- **Actual speed, zoomed out.** The threat moves at its real supplied speed. The
  camera is far enough out to frame the whole path and every option's area, so
  real-speed motion reads slowly on screen. Slowed playback was considered and
  dropped.
- **Countdown = `timeMarginS − elapsed`.** Confirmed as-is for now, although
  the backend assumes the interceptor launches at T+0 and models no decision
  delay. At zero the card greys out; if it was selected, the selection clears.
  With nothing fired, the flow reaches Expired when the last window closes —
  T+8.51 s for the demo file.
- **Deadline marks.** Each option gets a mark on the path where the threat will be
  when that option's window closes; the threat crossing the mark is the option
  expiring. An option does **not** expire when the threat reaches its circle
  (`k46`'s window closes about 10 s of flight before that). A close time before
  the first sample (`k11`, T+0.29 s) pins the mark to the start of the path,
  shown expired.
- **Option areas in red.** Each option's supplied 500 m area is highlighted red
  from the start of Live. The selected option's area is emphasised; an expired
  option's area fades. See open question 1.
- **Side window.** Hovering a red area opens a side window with a live, zoomed-in
  view of that area and its stats: intercept time, people potentially exposed,
  supplied success, time left in its window or "expired", and coverage status.
  Clicking pins it, like the population details card. See open questions 2–3.
- **Cards come from `representativeCandidateIds`,** in backend order, with badges
  from each candidate's `categories`. Unknown future categories get a readable
  fallback label. Nothing else is selectable, so the dominated `k32` contrast is
  not shown.
- **Wording comes from `assumptions`:** "people potentially exposed", "supplied
  success (synthetic)", "supplied 500 m area". Never "damage", "casualties" or
  "destroyed". The areas may be red and informally called the blast radius, but
  on-screen labels say "supplied 500 m area" — the backend does not calculate a
  blast radius. Labels are read from `assumptions.footprintModel` and
  `footprintRadiusM`, never hard-coded, so a new radius shows automatically. If
  the backend later calculates footprints, its new `footprintModel` value gets
  its own wording, and unknown values fall back to a neutral label. A
  non-circular footprint would need a contract change.
- **Outcome summary:** intercept time, people potentially exposed, supplied
  success, and deltas against the other options from `comparisons` — e.g. `k46`
  vs `k11`: −13,609 people potentially exposed (−89.2%), −5.6 pp supplied success.
  The threat is held at the intercept point; success is a supplied probability,
  not a result.
- **Missile path only.** The payload has no interceptor path or launch origin,
  and none is drawn.
- **The drawn circle is a display approximation** of PEC's 128-edge calculation
  polygon. Accepted.
- **Time shows as T+seconds from detection.** The contract's 2026-09-15 date has
  no meaning and is never shown.
- **Keyboard:** Space detect, 1–9 select, Enter FIRE, R reset. The mouse also works.
- **The result loads and validates in Standby,** so no loading or error happens
  mid-countdown.
- **The main camera frames the corridor in Standby** and never flies
  automatically during Live. Only the side window's own camera moves.
- **Layout:** map full-screen; compact top-left panel (view switcher, lighting,
  17 town presets collapsed); decision tray along the bottom; side window on the
  right. The population hover card moves so it doesn't collide with the side
  window — placed in the layout pass.

### 4. Stashed — presentation polish (step after grey-canvas detail)

Requested 2026-09-15 with a reference screenshot of an ops-console style
interface. The zoomed-out framing, red areas and side window have moved into
section 3; what remains is styling, designed in its own pass once the decision
flow works. None of it changes the library API.

- **Ops-console styling:** dark side panels and a bottom timeline with a "now" cursor.
- **A larger, more visible missile marker,** with the trajectory marked out ahead of it.

### 5. Data, errors and verification — draft, not yet approved

- **Loading the result.** It lives in `data/results/`, outside `frontend/`, and
  Vite only serves `frontend/public/`. Either import it into the bundle (the Vite
  dev server must be allowed to read the parent folder) or copy it into
  `public/`. Undecided.
- **Validation in `decision-model.ts`:** `schemaVersion` must be
  `planning-result/1`; representative and category IDs must resolve; numbers must
  be finite. An empty frontier is a valid state with its own message. Any failure
  blocks in Standby and says why.
- **Grey-canvas feature data** comes from OSM via Overpass: forest, nature
  reserves and mangroves; parks, grass and golf courses; road bridges and tunnels
  (roads re-fetched with their bridge/tunnel tags); MRT/LRT viaducts and tunnels.
  Overpass rate-limits large pulls, so fetch in bands with pauses. The bundle is
  already about 6.3 MB.
- **Population view** needs `frontend/public/population.geojson` from the
  partner's Python pipeline. It is missing locally, so it goes on the pre-demo
  checklist.
- **Checks:** browser verification, per `CLAUDE.md`. `decision-model.ts` is pure,
  so it carries one runnable check — countdown, expiry, deadline positions,
  validation — through the existing `npm test` runner.
- **Height accuracy check** before the grey canvas ships: compare terrain height in
  an open field against a dense HDB estate, and building bases against the
  surrounding terrain. Cesium's terrain draws on SRTM, which can partly measure
  rooftops and canopy; its docs don't state the source or datum for Singapore.
- **Frame rate** cannot be measured in the headless browser; check it on the demo
  machine — especially with the side window's second canvas running.

### Decisions for step 8 — answered 2026-09-16

These supersede the matching bullets in section 3.

- **Areas drawn:** only the backend's representatives (2 in the demo file).
- **Area colours by backend category**, one colour per area, priority
  highest success → lowest exposure → earliest viable: highest success **blue**,
  lowest exposure **red**, earliest viable **amber**, unknown future categories
  a neutral fallback. `k11` (earliest viable + highest success) is blue; its card
  still shows both badges. The user also wants **military sites in green** —
  the contract has no such data, so that is a request for the partner (see 6).
- **FIRE is a pointer click on a visible FIRE button only.** No Enter-key fire;
  keyboard activation of the button is ignored. Clicking a map area only pins the
  side window — it never selects or fires. Cards and number keys select.
- **Side window:** a live second canvas mirroring the current basemap (the
  population layer is not duplicated), plus the stats.
- **Playback starts at T+0.**
- **Loading:** the demo imports `data/results/demo-planning-result.json` into
  the bundle; the Vite dev server is allowed to read the parent folder.
- **Camera:** Standby frames the corridor at about −70° pitch, so the route at
  1,000 m appears ~360 m from its circles — inside the 500 m radius.
- **Temporary presenter buttons,** bottom-right: Play (= Space, detect) and
  Restart (= R). Removed in the polish pass.

### Built in step 8 — 2026-09-16

`decision-model.ts`, `decision.ts`, `inspector.ts`; `decision-model.test.ts` runs
under `npm test`. Two Cesium problems surfaced once the second canvas existed:

- **Shared environment-map queue (Cesium 1.145 bug).**
  `DynamicEnvironmentMapManager` queues its compute commands in one module-level
  queue shared by every Scene, so with two canvases one WebGL context executed
  the other's commands: "object does not belong to this context" warnings and a
  large corrupted shape on the main map. `scene.ts` now sets
  `tileset.environmentMapManager.enabled = false` on every tileset. Visible cost:
  OSM building walls lose their olive image-based shading and read flat light
  grey. Google tiles are unaffected.
- **Slow circle builds.** Ground geometry builds on Cesium's shared web workers;
  with the side window also building its road layer, the areas took ~9.6 s after
  Standby to become drawable — longer than `k46`'s whole window. `CircleLayer`
  gained `ready: Promise<void>`, and Standby shows "Preparing map layers…" and
  refuses detection until both canvases' areas are ready (~14 s after load
  here). A `display:none` canvas never renders and so never builds, so the side
  window pre-builds while laid out with `visibility:hidden`, then hides.

**Fixed 2026-09-16 — side window map rendered white (grey view).** Stats,
pin/unpin and countdown worked and the circle drew, but the rest of the zoomed
map was white. Pixel probes showed the white was the OSM Buildings tileset
itself: hiding it fixed the window, hiding the globe did not, and the corner
pixels picked buildings kilometres outside the view. Cause: Cesium 1.145
generates `CESIUM_primitive_outline` outlines by rewriting each tile's index
array in place (`PrimitiveOutlineGenerator`), and that array is a view onto
bytes the module-level `ResourceCache` shares between scenes. When two
canvases load the same tile at once, whichever runs its outline pass second
reads already-rewritten indices and draws stretched triangles across its view.
Upstream: CesiumGS/cesium#11484 (open; the cause is not identified there).
Fix: `scene.ts` loads the tileset with `enableShowOutline: false` in every
canvas, which removes the in-place rewrite. A single canvas cannot opt back in
without reintroducing the race. Cost: no building edge lines — invisible at
the demo framing, a small loss up close. The environment map stays off (the
user chose the flat light-grey buildings); the corrupted shape seen when the
second canvas first appeared may have been this bug rather than the env-map
queue, so re-enabling the env map is worth one retest if the walls matter.

### Built in step 9 — grey-canvas detail, 2026-09-16

`scripts/fetch-ground-detail.mjs` (new, no dependencies) pulls four OSM layers
from Overpass in three latitude bands with pauses, drops areas under 3,000 m²
and anything whose centroid falls outside the coastline rings, simplifies
(~11 m areas, ~9 m lines) and writes `src/lib/greens.json` and
`src/lib/structures.json` in the same delta-encoded integer form as
`roads.json`. Re-run it only when the data should change; it is not part of the
build.

`coastline.ts` draws them, no API change: land → forest → parks → water →
pavements → roads → road bridges/tunnels → MRT/LRT viaducts and tunnels →
coast. Forest `#5f6f57`, parks `#74845e`, road structures `#44484d`, rail
`#383c42`.

Known limits: outer rings only, so a hole in a green area shows the green
underneath unless water covers it; rail is viaducts and tunnels only, per the
plan, so at-grade MRT/LRT sections leave gaps; features on islands outside the
two coastline rings (Ubin, Tekong) are dropped, as with the existing water.

### Built in steps 10 and 11 — 2026-09-16

**Presentation polish.** Monospace is used only for figures, so ticking numbers
do not jitter. The temporary Play/Restart buttons stay for now, at the user's
request.

**No bottom timeline.** One was built — ticks, a bar per option to its window
close, a diamond at each intercept, a now cursor — and the user removed it
outright ("get rid of this totally"). The cards already carry each countdown.
Do not rebuild it unless asked.

**Missile marker.** `addPath` gained `PathStyle`: `trailColor` dims the stretch
already flown, `markerSize` sets the marker (0 draws a line with no marker at
all), and `dashed` draws a dashed line. The threat now has a 16 px marker with a
halo, a bright track ahead and a dim trail behind.

**Illustrative inbound track.** The user asked for the track to reach back to a
likely origin outside Singapore. `planning-result/1` supplies no launch origin,
so `approachOrigin()` extrapolates the first two samples' heading and speed
backwards to 6 km beyond the canvas bounds (~35 km, about 150 s before
detection). It draws dashed and dim, is labelled "Illustrative inbound track ·
not supplied" on the map, and is called out in the tray footnote. Nothing about
it is presented as planner output, and the flow still starts at T+0. Replace it
as soon as the backend supplies a long-range scenario.

**Lighting.** Both presets now set every value explicitly, so switching is
symmetric: sun instant, `scene.light` (a `SunLight` at midday, a low cool
`DirectionalLight` at blue hour), globe and sky atmosphere shifts, and fog.

The ground layer draws in flat colours that Cesium does not light, so the sun
alone barely changed the grey canvas. Blue hour therefore also runs a colour
grade over the finished frame (`PostProcessStage`, tint × brightness), which
moves ground, buildings and Google tiles together. Midday disables the stage.

### Intercept sequence — 2026-09-16

Requested by the user: the threat should leave its route at the intercept, come
down inside the chosen option's area, and burst there.

Flow gains an `impact` phase: Fired → (intercept time) Impact → (`DESCENT_S`,
2 s) Outcome. At the intercept the supplied route's marker hides and a second
path draws the fall; the clock then holds at intercept + `DESCENT_S`. With
nothing fired, the clock holds at the supplied end (T+20) instead. The clock
range is extended past the latest intercept so the fall has room.

`descentSamples()` drops straight onto the area's centre — which is where the
contract centres the footprint — with an accelerating fall. `PathLayer` gained
`setMarkerVisible`.

**Illustration, stated on screen.** The contract supplies no impact model,
debris physics or post-intercept path, so the footnote says the descent and
burst are illustration. Nothing here is presented as planner output.

### Marker and burst — 2026-09-16

Two new library modules, drafted by Fable 5.1 subagents at the user's explicit
request for this task only (the repo's "no subagent fan-out" rule stands for
everything else), then tuned and integrated here.

```ts
// craft.ts — a solid marker that points along its direction of travel
addCraftMarker(viewer, { color?, lengthM?, minimumPixelLength? }): CraftMarker
// burst.ts — a one-shot burst at a point
canvas.addBurst(center, { color?, radiusM?, durationS? }): BurstLayer
```

- `PathStyle.markerShape: "point" | "craft"` swaps the dot for the solid shape.
  It is built from a cylinder body, a cone nose and four fins, lit rather than
  flat, and scaled per frame so it never drops below a minimum pixel length.
- The burst is a bright core, a fading dome and a ground wave, animated on
  wall-clock time because the app's clock is paused when it plays. It is created
  with the result so its ground geometry is built before it is needed.
- Tuned after seeing them: fins cut to ~2.4x the body radius; core widened to
  1.2x the area radius and the dome density raised, because at the demo's 6 km
  framing the first values vanished. The chosen area's fill drops to 0.18 alpha
  during impact so the burst reads over it.
- Both modules keep the library domain-agnostic: "craft" and "burst", no
  defence vocabulary.

Known limits: the craft is depth-tested, so at very low camera angles a tall
building can hide it; the burst's dome is depth-tested too, so towers poke
through it.

### Open questions — original list, now answered above

1. **Which areas are red.** Recommended: only the backend's options — 2 in the
   demo file. Alternatives: all 40 reachable candidates, which overlap into one
   continuous red band along the path; or only the selected option.
2. **Does clicking a red area also select that option for FIRE,** or only pin the
   side window? Cards and number keys select either way.
3. **Side window view and cost.** A live second canvas mirroring the current view
   is the most faithful, but loads a second map — rebuilding the ~243k-line
   ground layer and, on the Google view, doubling Map Tiles usage. A lighter inset
   (for example, the grey canvas without roads and pavements) would be cheaper.
4. **Where playback starts.** Raised alongside the dropped slow-motion idea: the
   missile appearing about 0.5 s before the first circle. Starting at the
   backend's T+0 keeps every window whole — the first sample (T+0.4 s) is 400 m
   before `k11`'s circle edge, about 1.8 s of flight. Starting later, e.g.
   T+3.9 s, cuts `k46`'s window from 8.51 s to 4.61 s. Still wanted?
5. **Result loading:** bundle import or a copy in `public/`.
6. **For the partner:** objectives beyond the three categories need a contract
   change, since `CandidateCategory` lists exactly three values.

---

## Demo ↔ backend contract — planning-result/1

This section is the **single source of truth for the frontend-facing planning
result**. It supersedes the earlier `Scenario` proposal, since removed.
It describes backend JSON, not the Singapore Canvas library API. The frontend
owns rendering, clock playback, camera, markers, footprint drawing, cards and
the human go/no-go decision. No UI changes accompany this contract.

### Handoff and regeneration

The generated golden file is
[`data/results/static-mvp-planning-result.json`](../../data/results/static-mvp-planning-result.json).
From the repository root, regenerate it with:

```sh
.venv/bin/python -B scripts/export_static_mvp_planning_result.py
```

The script evaluates `data/scenarios/static-mvp-scenario.json` against
`tests/fixtures/static-mvp-population.json`, then converts the authoritative
result. It does not manufacture candidate evidence. The adapter entry point is
`backend.presentation.planning_result_to_dict(result, settings, *, threat_id,
footprint_radius_m)`. Settings are `PresentationSettings(scenario_start_time,
visualization_height_m)`. This adapter is scoped to the existing synthetic
linear-success, fixed-circle static scenario; those model labels are not a
claim about arbitrary future planners.

### Exact wire types

All numbers are finite JSON numbers. Optional fields are omitted when their
downstream evaluation did not occur; explicit `null` means unavailable evidence
within a present record. Arrays preserve deterministic backend order.
Unknown schema versions require a separately agreed consumer adaptation.

```ts
type CandidateCategory =
  | "earliest_viable"
  | "highest_success"
  | "lowest_exposure";

interface PlanningTimedSample {
  time: string; // ISO 8601 UTC, six fractional digits, trailing Z
  lon: number;  // WGS84 longitude in degrees
  lat: number;  // WGS84 latitude in degrees
  height: number; // synthetic visualization metres above WGS84 ellipsoid
}

interface PlanningCandidate {
  id: string;
  sampleIndex: number; // existing one-based backend sample index
  timeFromStartS: number;
  time: string;
  position: { lon: number; lat: number; height: number };
  reachable: boolean;
  requiredTravelTimeS: number | null;
  timeMarginS: number | null;
  suppliedSuccessProbability?: number;
  exposure?: {
    status: "complete" | "partial_coverage";
    peoplePotentiallyExposed: number | null;
    knownAreaExposure: number;
    coveredAreaFraction: number | null;
  };
  footprint?: { id: string; radiusM: number };
  paretoEfficient: boolean;
  categories: readonly CandidateCategory[];
  eligibleForRecommendation: boolean;
  ineligibilityReasons: readonly string[];
}

interface CandidateComparison {
  referenceCandidateId: string;
  comparisonCandidateId: string;
  deltaTimeS: number;
  deltaSuccessProbability: number | null;
  deltaSuccessPercentagePoints: number | null;
  deltaPeoplePotentiallyExposed: number | null;
  relativeExposureChange: number | null;
}

interface PlanningResult {
  schemaVersion: "planning-result/1";
  scenarioId: string;
  start: string;
  end: string;
  threat: { id: string; samples: readonly PlanningTimedSample[] };
  candidates: readonly PlanningCandidate[];
  paretoCandidateIds: readonly string[];
  categoryAssignments: {
    earliestViable: string | null;
    highestSuccess: string | null;
    lowestExposure: string | null;
  };
  representativeCandidateIds: readonly string[];
  comparisons: readonly CandidateComparison[];
  diagnostics: {
    totalCandidates: number;
    reachableCandidates: number;
    eligibleCandidates: number;
    paretoCandidates: number;
  };
  assumptions: {
    successModel: "synthetic_linear_decay";
    footprintModel: "supplied_fixed_circle";
    footprintRadiusM: number;
    populationExposureMeaning: "estimated_people_potentially_exposed";
    kinematicsCalibration: "synthetic_not_operational";
    visualizationHeightM: number;
    heightMeaning: "synthetic_visualization_only";
    scenarioTimeMeaning: "synthetic_presentation_clock";
  };
  populationProvenance: {
    datasetId: string;
    datasetVersion: string;
    coordinateReferenceSystem: string;
    calculatorVersion?: string;
  };
}
```

`scenarioId` is the backend result identity, currently
`synthetic-high-speed-threat__synthetic-interceptor__static-scenario`; the fixture's
descriptive ID `scaled-synthetic-static-mvp` is not substituted for it.

### Coordinates, synthetic height and time

The adapter converts final positions from EPSG:3414 to EPSG:4326 with pinned
`pyproj` and `always_xy=True`, returning longitude then latitude. All frontend
positions are WGS84 degrees. The provenance CRS remains `EPSG:3414` because it
describes the source population calculation; consumers need not transform it.
There are no metre-coordinate positions in the wire payload.

The scenario's presentation-only settings are:

```json
{
  "scenario_start_time": "2026-09-15T00:00:00Z",
  "visualization_height_m": 1000
}
```

Neither setting has model significance. The 2D backend calculates no altitude.
The configured height is a synthetic visualization height above the WGS84
ellipsoid, copied to path samples and candidate positions. It does not describe
terrain clearance or elevate the ground consequence footprints.

Absolute time is `scenario_start_time + time_from_start_s`. Input timestamps
must include a timezone and are normalized to UTC. Wire timestamps use six
fractional digits (Python datetime microsecond precision); relative seconds
retain their original backend values and are used for comparisons.
`start` is the supplied clock origin and `end` is the last sample time, or
`start` for an empty trajectory. The golden path contains the original 50 future
samples at approximately 0.4-second intervals, from +0.4 s to +20 s, with no added
zero-time sample or resampling. This date is a fixed synthetic clock origin.

The Canvas library's `TimedSample.time` above remains a JavaScript `Date`.
The separate `PlanningTimedSample` name avoids conflating its API with JSON.
For example, consumer-side conversion is:

```ts
const canvasSamples = result.threat.samples.map(({ time, ...position }) => ({
  ...position,
  time: new Date(time),
}));
```

### Golden scenario geography

The complete synthetic geometry was translated by **(-20,000 m, +10,000 m)**
in EPSG:3414. Threat start is now `(30000, 30000)`; interceptor origin is
`(-20000, 10000)`; every population polygon received the identical translation.
Velocities, relative positions, populations, zone dimensions and the supplied
500 m radius are unchanged. Derived candidate and footprint centers follow the
translated threat automatically. Population dataset version is now `2`.

The intended Canvas bounds are west `103.56`, south `1.13`, east `104.14`, north
`1.52` degrees. The path runs approximately from `(103.854884, 1.287584)` to
`(104.030997, 1.287576)`. Population zones occupy EPSG:3414 x `[25000, 55000]`,
y `[20000, 40000]`, approximately lon `[103.80636, 104.07593]`, lat
`[1.19714, 1.37802]`. Path positions, candidate positions, supplied footprint
perimeters and population zones fit with visual margin. Tests check the wire
coordinates and fixture geometry against these bounds and detect drift from
the actual Canvas constant.

The interceptor origin remains outside this box and is not a frontend position
in this contract. The original complete geometry spans 75 km east-west, wider
than the Canvas box; translation alone cannot fit all of it. No interceptor
trajectory or marker is supplied. This preserves the synthetic reachability
problem without changing the frontend camera or model.

### Evidence, eligibility and trade-offs

All 50 opportunities are retained, including unreachable ones. The current
fixture has 14 unreachable followed by 36 reachable candidates with complete
population coverage. Unreachable records preserve time, position and available
travel-time/margin evidence, have `eligibleForRecommendation: false` and
`ineligibilityReasons: ["unreachable"]`, and omit success, exposure and footprint.
Null travel metrics mean no finite reachability solution was supplied.
`timeMarginS` is the backend's available-time-minus-required-travel-time evidence.

Enriched candidates copy the supplied success, exposure, fixed footprint,
eligibility and reasons exactly. `suppliedSuccessProbability` is the assumed
synthetic linear-decay profile, not a measured or operational success estimate.

A footprint is a **supplied circular ground consequence area** centered at the
candidate's longitude/latitude with the provided radius in metres. It is not a
calculated debris envelope, probability contour or guarantee of impact.
PEC evaluates its existing polygonal circle approximation; a displayed circle
does not imply a different exposure calculation.

`peoplePotentiallyExposed` estimates people within the footprint using the
supplied population-zone evidence. Fractional estimates are intentional. It is
not a casualty count, fatality estimate, expected loss, or success-weighted score.
Candidates represent alternatives; do not sum their exposures as simultaneous
events or interpret their difference as a count of identified people saved.

For `partial_coverage`, `peoplePotentiallyExposed` is null, `knownAreaExposure`
retains the available-area subtotal, and `coveredAreaFraction` retains PEC's
fraction or null when undefined. A subtotal is not a complete exposure or zero.
Such candidates have `partial_population_coverage` as the existing backend
reason and are ineligible for recommendation. Complete status does not imply
that coverage fractions are mathematically exactly one beyond PEC tolerances.

`paretoEfficient` means membership in the backend frontier over higher supplied
success and lower complete population exposure, using backend tolerances.
The adapter copies that frontier; the frontend need not run dominance tests.
Categories identify descriptive choices **within that frontier**:

- `earliest_viable`: earliest Pareto candidate according to backend ordering.
- `highest_success`: highest supplied success on the frontier.
- `lowest_exposure`: lowest complete exposure on the frontier.

Top-level assignments use camelCase keys; candidate labels use the snake_case
values above. A candidate may own multiple categories. Representatives are the
backend's unique IDs in category order; they are not forced to be three distinct
choices. An empty eligible set has null assignments and empty representatives
and comparisons. The backend does not choose one universal “best” candidate or
make the human go/no-go decision.

### Pairwise comparison evidence and example

`comparisons` contains every ordered pair of distinct unique representatives,
in representative-list order. Each delta is **comparison minus reference**:

- `deltaTimeS = tComparison - tReference`.
- `deltaSuccessProbability = pComparison - pReference`.
- `deltaSuccessPercentagePoints = 100 * deltaSuccessProbability`.
- `deltaPeoplePotentiallyExposed = eComparison - eReference`.
- `relativeExposureChange = deltaPeoplePotentiallyExposed / eReference`.

Success deltas are null if either success value is unavailable. Exposure deltas
require both complete finite values; partial/missing exposure gives null for
both exposure comparison fields. Relative change also requires nonzero reference
exposure; zero reference still permits an absolute delta. No NaN or Infinity is
emitted. Backend values are unrounded; display rounding belongs to the consumer.

Compact golden-file excerpt (IDs abbreviated and numbers rounded here only):

```json
{
  "schemaVersion": "planning-result/1",
  "categoryAssignments": {
    "earliestViable": "…__k15",
    "highestSuccess": "…__k15",
    "lowestExposure": "…__k37"
  },
  "representativeCandidateIds": ["…__k15", "…__k37"],
  "comparisons": [{
    "referenceCandidateId": "…__k15",
    "comparisonCandidateId": "…__k37",
    "deltaTimeS": 8.8,
    "deltaSuccessProbability": -0.0352,
    "deltaSuccessPercentagePoints": -3.52,
    "deltaPeoplePotentiallyExposed": -314.0331,
    "relativeExposureChange": -0.8
  }]
}
```

This is an explanatory excerpt, not a complete payload. The generated file
contains both ordered comparisons and full IDs. Consumers must resolve category
IDs dynamically; `k15` and `k37` are current results, not contract requirements.
Compact population provenance copies dataset ID/version, source CRS and
calculator version from PEC. Machine-readable `assumptions` accompany every
payload so the frontend can surface model limitations.

### Timing and scope

The golden JSON omits variable timing fields; `diagnostics` contains deterministic
counts only. Run `.venv/bin/python -B scripts/benchmark_planning_result.py` for
the separate `data/results/static-mvp-planning-result-benchmark.json` report.
It uses prepared population outside timing, one warm-up, seven measured runs,
and `perf_counter_ns`. Planning, presentation and total each report median,
minimum and maximum. The boundary ends at validated JSON-ready packaging and
excludes JSON text encoding, file writing, networking and frontend rendering.
The engineering target is a total median below 100 ms for 50 candidates.

The backend supplies **no fragment trajectories, particle tracks, physical fall
simulation, interceptor animation path or selected intercept action**. Optional
frontend visual effects must not be presented as backend-calculated physics.

### Grades and urgency — 2026-09-16

Requested by the user after seeing the side window: figures coloured "at a
glance", and countdowns that redden as time runs out. Buckets are the user's
delegated call; they are in `decision-model.ts` (`successGrade`,
`exposureGrade`, `urgency`) with a unit test.

- **Supplied success** is a probability, so the marks are fixed: ≥ 80% good
  (green), ≥ 50% fair (amber), below poor (red).
- **People potentially exposed** has no absolute scale in the contract, so it is
  graded only against the other options in the same result: lowest third of the
  range good, highest third poor, middle fair. One option, or all equal, gets no
  colour. The tray footnote says so.
- **Urgency** is 0 with the whole window ahead and 1 at close. The countdown
  text (cards and side window) and the card's bar blend toward red with
  `color-mix` on urgency², so the shift is gentle early and steep in the last
  seconds. It only runs while the option is open in Live.
- **Side window:** 400 × 300 px map (was 340 × 240), framed at 1.2 × the area
  radius (was 1.5), so the area fills about half the width.
- **Every building in the side window.** Cesium picks tile detail from
  screen-space error, which scales with canvas height, so the 300 px window
  only loaded the coarse OSM tiles and the smaller buildings were missing until
  you zoomed in. Measured at the k46 pose: threshold 16 selects 5,064 building
  features, 4 selects 6,475, 2 selects 13,163 and 1 saturates at 13,179, for
  14 MB. New `CanvasOptions.maximumScreenSpaceError` (applied to whichever
  city tileset the canvas shows); the side window passes 2. Not yet measured
  on Google tiles, where a fine threshold in a small window means many more
  tile requests.

Verified in the headless browser by computed colours: at T+3.0 s the option 2
countdown is barely tinted, at T+7.5 s (1.0 s left) it is most of the way to
red. Screenshots cannot catch a mid-countdown frame there (1 fps), so eyeball
the ramp on the demo machine.

### Military bases — 2026-09-16

Requested by the user: "identify all military bases in Singapore and colour
all of these models in the military base purple". This is a map layer from
public OSM data, not contract data; the option categories still cannot say
whether an intercept is over a base (see "Decisions for step 8").

- **Data:** `scripts/fetch-ground-detail.mjs military` pulls
  `landuse=military` areas plus `military=base|barracks|airfield|naval_base`
  (ranges, danger areas and training areas excluded) into
  `src/demo/military.json`, keeping each area's OSM name. The script now joins
  a relation's outer member ways into closed rings; greens and structures were
  not re-fetched with that change. 81 areas on the two coastline rings, 69
  named. OSM tags Home Team sites the same way (Home Team Academy, Police K-9
  Unit, Civil Defence Academy, ISD), so they are in the layer too; prune the
  JSON if that is wrong for the demo.
- **Demo:** `military.ts` mounts the layer on both canvases through
  `addBuildingTint` (purple `#a970ff`, 2 px outline) and, on the main map,
  labels each named base once on its largest ring below a 20 km camera height.
  The panel gains a "Layers" legend line naming the source. Off on the
  population view, which has its own labels and colours.
- **Checked in the browser:** at Paya Lebar Air Base every hangar and shelter
  inside the boundary is purple and the civilian blocks outside stay white.
  Many camps have no building footprints in OSM at all (Amoy Quee Camp shows
  only its boundary), and at the 6 km Standby framing the tileset drops small
  buildings anyway, so the tint reads best up close and in the side window.
- **Google view:** outline and label only.
