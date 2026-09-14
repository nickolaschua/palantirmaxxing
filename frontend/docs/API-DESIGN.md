# Singapore canvas — API design

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

## Demo ↔ backend contract — PROPOSAL, not agreed

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
