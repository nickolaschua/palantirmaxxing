# Singapore canvas — API design

Population milestone update (14 September 2026): the viewer now has an independent `addPolygonLayer` capability, population explorer and offline data-preparation tests. See the [current implementation and verification](POPULATION-VERIFICATION.md). The original review/design below is retained as historical context; planned playback, tracks and camera-follow features remain unimplemented.

Last updated 2026-09-14. Reflects what is built through step 5 and the signed-off
scope for step 6.

| Status | Surface |
|---|---|
| **Built** (steps 1–5) | `createSingaporeCanvas`, `camera` (except `follow`), `scene`, `on`, `destroy` |
| **Step 6** (scoped, not built) | `time`, `layers.addTracks` / `addPath` / `addBurst` / `addGroundOverlay` / `updateGroundOverlay`, `camera.follow` |
| **Deferred** | `layers.addPoints` / `addModel` / `addPolygons` / `addClipRegion`, `pick` event |

Step 6 is scoped around one scenario — an intercept debris footprint — but every
verb below is domain-agnostic. The library never learns the word "missile"; that
vocabulary lives only in `src/demo/`.

## Shape

```ts
const canvas = await createSingaporeCanvas(element, options);  // resolving IS "ready"
canvas.camera / canvas.scene / canvas.time / canvas.layers
canvas.on(event, handler)                                        // returns its own unsubscribe
canvas.destroy()
```

Ids everywhere. No Cesium object ever crosses the boundary.

## Contracts at the boundary

- **Positions** are `GeoPoint { lon, lat, height? }` — WGS84 degrees and metres. `Cartesian3` stays inside.
- **Instants** are JS `Date`. `JulianDate` stays inside.

---

## Construction — built

```ts
interface Bounds { west: number; south: number; east: number; north: number }  // WGS84 degrees

interface CanvasOptions {
  ionToken?: string;
  googleApiKey?: string;
  basemap?: "photorealistic" | "extruded";  // default: photorealistic if googleApiKey, else extruded
  lighting?: "midday" | "blue-hour";         // default "midday"
  bounds?: Bounds | null;                    // default SINGAPORE_BOUNDS; null unlocks the cage
  maxHeight?: number;                        // default 80_000 m
  minHeight?: number;                        // default 60 m
}
```

The cage is enforced per frame — Cesium has no built-in geographic bounds.
`minHeight` rarely binds in practice: terrain collision stops the camera around
97–102 m above the ellipsoid first.

## camera — built, except `follow`

```ts
interface CameraModule {
  flyToPreset(name: string, opts?: { duration?: number }): Promise<void>;
  flyTo(pose: CameraPose, opts?: { duration?: number }): Promise<void>;
  orbit(opts: { centre: GeoPoint; radius: number; pitch?: number; degreesPerSecond?: number }): void;
  follow(layerId: string, trackId?: string, opts?: { range?: number; pitch?: number }): void;  // step 6
  stop(): void;                           // cancels flight, orbit and follow
  readonly pose: CameraPose;
  readonly presets: readonly string[];
}
```

Flights resolve on arrival and reject with `FlightCancelled` when interrupted.

**`follow` changed from `follow(pathId)`** so it can reach into a layer:
`follow("missile")` follows a path; `follow("fragments", "f-0412")` follows one
track inside a tracks layer.

**`follow` respects the cage.** Library flights and orbits suspend the cage;
follow does not. The follow position is computed each frame from the target plus
the offset and then clamped, so an object approaching from outside Singapore
leaves the camera pinned at the boundary, looking toward it, until it crosses in.
While the target has no position (before its first sample) the camera holds its
last pose.

## scene — built

```ts
interface SceneModule {
  setBasemap(kind: "photorealistic" | "extruded"): Promise<void>;
  setLighting(preset: "midday" | "blue-hour"): void;
  readonly basemap: "photorealistic" | "extruded";
}
```

On photorealistic the globe is hidden, so the grey/blue ground layer (coastline,
reservoirs, roads, pavements) is hidden too — Google's mesh carries its own.

---

## time — step 6, pulled forward from step 7

Unchanged from the original design. Every step 6 layer moves in time, so layers
are meaningless without a clock.

```ts
interface TimeModule {
  setRange(start: Date, stop: Date): void;
  play(): void;
  pause(): void;
  seek(t: Date): void;
  setMultiplier(n: number): void;
  readonly current: Date;
  readonly playing: boolean;
}
```

## layers — step 6

```ts
/** Replaces PathSample: same shape, now shared by both moving-object verbs. */
interface TimedSample extends GeoPoint { time: Date }

type OverlaySource = HTMLCanvasElement | HTMLImageElement | string;
interface PathStyle { color?: string; width?: number; trailTime?: number; leadTime?: number }

interface LayersModule {
  /** Many moving objects. Primitive-backed. Designed for ~1,000 tracks; not enforced. */
  addTracks(
    id: string,
    tracks: readonly { id: string; samples: readonly TimedSample[] }[],
    style?: { color?: string; size?: number; trailFor?: readonly string[]; trailTime?: number },
  ): void;

  /** One moving object that always draws a trail. Entity-backed. */
  addPath(id: string, samples: readonly TimedSample[], style?: PathStyle): void;

  /** A one-shot particle burst at a place and a clock moment. */
  addBurst(id: string, spec: {
    position: GeoPoint;
    time: Date;
    duration?: number;
    color?: string;
    endColor?: string;
    particleCount?: number;
    maxSpeed?: number;
  }): void;

  /** An image draped over the active basemap. */
  addGroundOverlay(id: string, source: OverlaySource, bbox: Bounds): void;
  /** Swap the image. The demo uses this to redraw the heatmap during playback. */
  updateGroundOverlay(id: string, source: OverlaySource): void;

  setVisible(id: string, visible: boolean): void;
  remove(id: string): void;
  removeAll(): void;
  has(id: string): boolean;
  readonly ids: readonly string[];
}
```

Adding a duplicate id throws. `remove` on an unknown id is a no-op. `trailTime`
is in seconds on both verbs. `trailFor` names which tracks get a trail — at a
thousand tracks, only a chosen subset can carry one.

### How it is built — approach A, hybrid

| Verb | Backing |
|---|---|
| `addTracks` | One `PointPrimitiveCollection`; every track's `SampledPositionProperty` evaluated at clock time each frame |
| `addTracks` trails | One entity with `PathGraphics` per id in `trailFor`, sharing that track's position property |
| `addPath` | One entity with `PathGraphics` |
| `addBurst` | `ParticleSystem` |
| `addGroundOverlay` | An `ImageryLayer` on the active tileset's `imageryLayers` |

Primitives only where the count demands it; Cesium's own interpolation and trail
code everywhere else. Interpolation is polynomial, not linear — linear turns
ballistic arcs into chevrons.

`tileset.imageryLayers` is marked **experimental** in Cesium ("subject to change
without Cesium's standard deprecation policy"). That is acceptable only because
the version is pinned to 1.145.

### Behaviour over time

| Case | Behaviour |
|---|---|
| Track before its first sample | Hidden |
| Track after its last sample | Held at its final position |
| Clock crosses a burst's `time` going forward | Burst fires |
| Seek to before a burst's `time` | Burst cleared |
| Seek into a burst's window | Burst starts fresh |

### Validating input

Samples arrive from a backend, so the library checks them rather than trusting them.

| Input | Handling |
|---|---|
| Samples out of time order | Sorted on ingest |
| Duplicate timestamps within a track | First kept, later duplicates dropped |
| Non-finite values, lon outside ±180, lat outside ±90 | That sample dropped |
| Track left with 1 sample | Drawn as a static point |
| Track left with 0 samples | Skipped, with a console warning |

The sanitiser is a pure function with no Cesium import, in its own module, so it
can carry a runnable check.

### Basemap switch

Overlays attach to a specific tileset, and `setBasemap` replaces the tileset —
so an overlay would silently vanish. Scene raises an internal tileset-changed
hook and layers re-attaches every overlay. Invisible to the host.

### Known limitations

- On the **extruded** basemap, an overlay's ground portion sits under the grey
  land fill. Photorealistic, the stage basemap, is unaffected.
- A burst cannot be scrubbed frame-accurately; it replays from its start instead.

### To verify against the live tiles at build time

1. Whether swapping an overlay's image at ~4 Hz flickers. Fallback: the demo
   draws the heatmap once, after the last track lands.
2. Whether `ParticleSystem` advances on the scrubbed clock or on real frame time.
   The burst rules above hold either way.
3. The `ExtrapolationType` member that holds the last position.
4. Whether draped imagery streaks on vertical walls. Expected, since the image is
   georeferenced 2D.
5. Frame rate with 1,000 tracks plus trails, on the demo machine. Headless Chrome
   caps `requestAnimationFrame` at one per second, so it cannot be measured there.

### Deferred — designed, not in step 6

```ts
interface PointDatum extends GeoPoint { color?: string; size?: number; id?: string }
interface PointStyle { color?: string; size?: number; outlineColor?: string; outlineWidth?: number }
interface PolygonStyle { fill?: string; outline?: string; extrudeProperty?: string; extrudeScale?: number }

addPoints(id: string, points: readonly PointDatum[], style?: PointStyle): void;
addModel(id: string, spec: { url: string; position: GeoPoint; orientation?: CameraOrientation; scale?: number }): Promise<void>;
addPolygons(id: string, geojson: GeoJSON.FeatureCollection, style?: PolygonStyle): Promise<void>;
addClipRegion(id: string, ring: readonly GeoPoint[]): void;
```

---

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
- **`pick` is deferred.** Designed as
  `{ layerId; index; datumId?; position } | null`. Click-to-highlight a fragment
  would demo well, but the scenario does not need it.

`on` returns its own unsubscribe. There is no `off(event, handler)` —
identity-matching handlers leaks whenever a caller passes an inline arrow function.

---

## Demo ↔ backend contract — planning-result/1

This section is the **single source of truth for the frontend-facing planning
result**. It supersedes the historical `Scenario` proposal below for this path.
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
The historical `ScenarioSource` proposal below needs frontend adaptation to
consume `planning-result/1`; the new payload does not pretend to satisfy its
fragment-bearing shape.

## Demo ↔ backend contract — historical Scenario proposal (superseded)

The following unagreed proposal is retained as historical design context only.
For the current planning-result path, use `planning-result/1` above. Statements
below about replacing the mock or supplying fragments are not backend promises.

**Not part of the library API.** This is the shape `src/demo/` expects from
whoever computes the intercept — something to take to the backend owner. Nothing
here is confirmed.

```ts
type Sample = { t: string; lon: number; lat: number; height: number };  // t is ISO 8601

interface Scenario {
  start: string;
  end: string;
  missile: Sample[];
  interceptor: Sample[];
  intercept: Sample;
  fragments: { id: string; samples: Sample[] }[];
}
```

**Agree the sample rate first.** The budget is 1,000 fragments. At about 1 Hz over
a 60 s fall that is 60,000 samples, fine as plain JSON; at 10 Hz it is 600,000.
Ballistic arcs are smooth, so 1 Hz plus polynomial interpolation on our side
reproduces them.

The demo reads a scenario through one seam, `ScenarioSource.load(): Promise<Scenario>`.
Today that is a mock generating toy gravity parabolas — a UI stand-in, not a
physics model. The real backend replaces the mock behind the same seam, and a
streaming source can sit behind it later. The heatmap density is computed in the
demo from where fragments have landed by the current clock time, and redrawn at
about 4 Hz during playback.

## New files for step 6

| File | Job |
|---|---|
| `src/lib/time.ts` | The clock |
| `src/lib/layers.ts` | Tracks, paths, bursts, overlays |
| `src/lib/samples.ts` | The input sanitiser — pure, no Cesium |
| `src/demo/scenario.ts` | Contract types, `ScenarioSource`, the mock |
| `src/demo/debris.ts` | Scenario → canvas calls, heatmap density binning |

## Verification

No TDD and no test harness, per `CLAUDE.md`. Verification is loading the page and
looking:

- Fragments appear at the intercept, fall, and hold where they land
- The heatmap blooms during playback and un-blooms on scrub-back
- The burst fires at the intercept and clears on seek-back
- `follow("missile")` pins at the cage edge until the missile enters Singapore
- Switching basemap keeps the heatmap

The one exception is `samples.ts`. A parser at a trust boundary is exactly the
logic that should leave a check behind: one assert-based check, run with plain
`node` using Node 24's built-in TypeScript type stripping (confirmed when built),
with no test framework and no new dependency.
