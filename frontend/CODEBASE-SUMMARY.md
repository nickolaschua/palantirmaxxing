# Singapore Canvas — complete codebase summary

Population milestone update (14 September 2026): the viewer now has an independent `addPolygonLayer` capability, population explorer and offline data-preparation tests. See the [current implementation and verification](docs/POPULATION-VERIFICATION.md). The original review/design below is retained as historical context; planned playback, tracks and camera-follow features remain unimplemented.

Reviewed on 14 September 2026 against commit `6850b79` on `main`.

The application was subsequently moved into `frontend/`. Unless stated otherwise, file paths and shell commands below are relative to that directory. The repository root contains the project README and shared Git configuration.

## 1. What this project is

This repository contains **Singapore Canvas**, a browser-based 3D viewer of Singapore built with CesiumJS, TypeScript, and Vite. It is the visual foundation for the Singapore Defense Tech Hackathon project in the GitHub repository [nickolaschua/palantirmaxxing](https://github.com/nickolaschua/palantirmaxxing).

The working implementation provides a reusable map library and a small demo application. Users can navigate Singapore, fly to town presets, orbit a location, switch between Google photorealistic tiles and OSM building extrusions, and change lighting. The extruded view adds locally stored coastline, inland water, road, and pedestrian-path geometry.

The intended next feature is an intercept/debris visualization with moving objects, playback, a particle burst, and a ground heatmap. **That scenario is documented but not implemented.** There is no backend, physics engine, database, authentication system, scenario loader, or simulation API in the current source tree.

## 2. Implementation status

| Capability | Current state |
|---|---|
| Asynchronous viewer creation and cleanup | Implemented |
| Google photorealistic 3D tiles | Implemented; requires a configured key |
| Cesium terrain and OSM Buildings | Implemented; intended to use a supplied ion token |
| Singapore land clipping | Implemented for the two bundled land polygons |
| Land, coast, inland water, roads, pedestrian paths | Implemented as ground primitives |
| Town camera presets, direct flights, orbit, stop | Implemented |
| Geographic camera bounds and altitude limits | Implemented; temporarily suspended during library flights and orbit |
| Midday and blue-hour lighting | Implemented with fixed clock dates/times |
| Camera, globe tile-progress, and boundary events | Implemented |
| Camera following | Method exists but throws an explicit not-implemented error |
| Playback clock API, moving tracks, paths, bursts, heatmaps | Planned in `docs/API-DESIGN.md` |
| Point/model/polygon layers, arbitrary clip regions, picking | Deferred |
| Automated tests and CI | No checked-in test suite or CI configuration |

## 3. Architecture and execution flow

```text
index.html
  └─ src/demo/main.ts + style.css
       └─ createSingaporeCanvas(container, options)
            ├─ Cesium Viewer
            ├─ scene.ts
            │    ├─ streamed Google or Cesium/OSM tiles
            │    └─ coastline.ts → four bundled geographic JSON datasets
            ├─ camera.ts → presets.ts
            └─ events.ts + types.ts
```

The demo owns DOM controls and presentation. The library owns Cesium rendering and camera behavior. Public positions use plain longitude/latitude/height objects; Cesium vectors and viewer objects stay internal.

Startup proceeds as follows:

1. Vite loads `index.html`, which provides a full-screen scene container and a control panel.
2. `src/demo/main.ts` reads the two `VITE_*` environment values and awaits `createSingaporeCanvas`.
3. The factory assigns supplied credentials to Cesium's global configuration, resolves defaults, and creates a viewer with most stock widgets disabled.
4. The scene constructs ground primitives, loads the selected remote tileset, clips buildings to the bundled land polygons, and sets lighting.
5. The camera module registers its controls, boundary clamp, and camera-change listener.
6. Globe tile-progress notifications are connected to the typed event emitter.
7. An immediate flight places the camera at the whole-island preset.
8. The factory returns the API, after which the demo creates its controls and event subscription.

Resolving the factory promise is the application-ready signal. It does **not** mean every visible streamed tile has finished downloading.

## 4. Files and responsibilities

| File | Purpose |
|---|---|
| `index.html` | Main Vite entry point; scene, panel, title, startup status |
| `src/demo/main.ts` | Creates the canvas, generates buttons, handles status and boundary feedback |
| `src/demo/style.css` | Full-screen layout, dark translucent panel, buttons, focus states, orange boundary indicator |
| `src/lib/index.ts` | Public factory, public exports, viewer ownership, module wiring, disposal |
| `src/lib/types.ts` | Geographic types, options, event payloads, default bounds, cancellation error |
| `src/lib/camera.ts` | Flights, orbit, pose reporting, input bindings, camera cage, follow stub |
| `src/lib/presets.ts` | Whole-island and town targets with heading, pitch, and range |
| `src/lib/scene.ts` | Basemap loading/switching, tileset ownership, lighting, ground visibility |
| `src/lib/coastline.ts` | Dataset decoding, coordinate preparation, ground rendering, land clipping |
| `src/lib/events.ts` | Generic synchronous typed event emitter |
| `src/lib/coastline.json` | Two flat longitude/latitude rings for land geometry |
| `src/lib/water.json` | Flat longitude/latitude rings for inland water |
| `src/lib/roads.json` | Delta-encoded road polylines |
| `src/lib/paths.json` | Delta-encoded pedestrian/cycle/path polylines |
| `src/vite-env.d.ts` | Type declarations for optional Vite credential variables |
| `package.json` | Package metadata, scripts, dependency ranges |
| `package-lock.json` | Reproducible dependency resolution |
| `tsconfig.json` | Strict TypeScript settings, JSON imports, browser types, no emitted TS output |
| `vite.config.ts` | Demo build and development server with Cesium integration |
| `vite.lib.config.ts` | Separate ES-module library build with Cesium externalized |
| `.env.example` | Empty credential configuration template |
| `.gitignore` | Excludes credentials, dependencies, build artifacts, editor files, and local assistant notes |
| `singapore-3d.html` | Earlier independent JavaScript prototype using CDN-hosted Cesium |
| `docs/API-DESIGN.md` | Existing API description and future scenario/layer design |
| `docs/baseline/*.png` | Four reference screenshots: MBS, whole island, Toa Payoh, and Merlion |

The repository-root `README.md` provides the frontend entry point and quick-start commands. `CODEBASE-SUMMARY.md` is the detailed frontend overview added by this review. `.gitignore` remains at the repository root and applies to the frontend subtree.

## 5. Public library API

### Construction and options

```ts
const canvas = await createSingaporeCanvas(element, options);
canvas.camera;
canvas.scene;
const unsubscribe = canvas.on("cameraChange", pose => console.log(pose));
unsubscribe();
canvas.destroy();
```

| Option | Default / behavior |
|---|---|
| `ionToken` | Optional string assigned to `Ion.defaultAccessToken` when truthy |
| `googleApiKey` | Optional string assigned to `GoogleMaps.defaultApiKey` when truthy |
| `basemap` | `photorealistic` when a Google key is supplied; otherwise `extruded` |
| `lighting` | `midday` |
| `bounds` | West `103.56`, south `1.13`, east `104.14`, north `1.52` |
| `maxHeight` | `80_000` metres above the ellipsoid |
| `minHeight` | `60` metres above the ellipsoid |

`bounds: null` removes the longitude/latitude constraint; the altitude clamp still operates. Both credential settings are Cesium module-level globals shared across canvas instances. Omitted credentials do not clear values set by a previous instance.

`GeoPoint` has `lon`, `lat`, and optional `height`. Angles are degrees and heights are metres. `CameraPose` adds optional `heading`, `pitch`, and `roll`; negative pitch points downward. Camera height limits are ellipsoid-based, not a measured distance above each building or terrain surface.

The entry point exports geographic/options/event types, `CameraPreset`, `PRESETS`, `SINGAPORE_BOUNDS`, `FlightCancelled`, `SingaporeCanvas`, and the factory. `CameraModule`, `SceneModule`, and `OrbitOptions` are defined in their own modules rather than directly re-exported as named types from the entry point.

### Camera methods

| Member | Behavior |
|---|---|
| `flyToPreset(name, { duration? })` | Flies to a named subject using a bounding sphere and viewing offset; rejects unknown names |
| `flyTo(pose, { duration? })` | Flies to an explicit camera position and orientation |
| `orbit({ centre, radius, pitch?, degreesPerSecond? })` | Starts continuous motion around a target |
| `follow(pathId, opts?)` | Declared API only; always throws because layers are not implemented |
| `stop()` | Cancels an active flight and removes an active orbit callback |
| `pose` | Getter returning current geographic camera position/orientation |
| `presets` | Names of available presets |

Flights default to 2.5 seconds and quadratic easing. Direct flights default to height 1,000 m, heading 0°, pitch −30°, and roll 0°. Starting another flight or orbit stops existing movement; cancelled flights reject with `FlightCancelled`.

Orbit defaults to pitch −20° and 6°/second. It advances its own heading using elapsed real time and calls `lookAt` before rendering. Stopping restores the identity camera transform.

The cage clamps the camera before rendering and emits a boundary event when the detected edge changes. Latitude or altitude checks can supersede a longitude edge in the emitted payload when several limits are exceeded together. Flights suspend clamping until settlement; orbit suspends it until stopped. A destination outside the box can therefore be clamped after a flight finishes.

Input bindings explicitly make middle-drag, wheel, and pinch zoom; right-drag and configured Ctrl-drag combinations tilt. Other interactions inherit Cesium behavior.

### Presets

There are **17 presets**: Whole island, Jurong West, Jurong East, Bukit Batok, Clementi, Queenstown, Toa Payoh, Bishan, Ang Mo Kio, Serangoon, Hougang, Sengkang, Punggol, Yishun, Woodlands, Tampines, and Bedok.

Town presets share heading 30°, pitch −35°, and range 2,800 m. Whole island targets `(103.8198, 1.3521)` at heading 0°, pitch −60°, and range 42,000 m. Targets represent subjects; framing is expressed separately as viewing offsets. The source attributes town centroids to OSM/Nominatim, but extraction tooling is not included.

### Scene and events

`scene.setBasemap(kind)` asynchronously replaces the active city tileset. `scene.setLighting(preset)` updates lighting settings and the Cesium clock. `scene.basemap` reports the last successfully loaded selection.

| Event | Payload and source |
|---|---|
| `cameraChange` | Current `CameraPose`, from Cesium's camera-change event; threshold set to `0.1` |
| `tileLoadProgress` | `{ pending }`, forwarded from the **globe's** tile-progress event |
| `boundsHit` | `{ edge }`, one of west/south/east/north/ceiling/floor |

The emitter stores handlers in sets and invokes a snapshot synchronously. Subscribing returns an unsubscribe closure. There is no `ready`, `pick`, or generic error event. Listener exceptions are not caught by the emitter.

## 6. Basemaps, lighting, and geographic data

### Basemap rendering

**Photorealistic:** Uses `createGooglePhotorealistic3DTileset`, applies the land clipping polygons, and hides the globe and custom ground primitives. Google's mesh supplies its ground surface. The loader passes `onlyUsingWithGoogleGeocoder: true`, while the viewer's geocoder widget is disabled.

**Extruded:** Loads Cesium world terrain and OSM Buildings ion asset `96188`. It removes imagery layers, paints the globe blue for open water, clips buildings to the land polygons, and shows the custom ground primitives.

The main library chooses extruded mode when no Google key is supplied, but it does **not** automatically retry extruded mode when a requested Google load fails. The older standalone prototype does have that retry behavior.

### Ground geometry

All four geographic datasets are bundled into the application. Coast and water contain flat degree coordinates. Roads and paths encode the first coordinate as integers scaled by `100_000`; subsequent pairs are deltas from the previous point.

At module initialization, the code decodes data, removes consecutive duplicate vertices and repeated closing vertices, and converts coordinates to Cesium `Cartesian3` arrays. Road/path lines with fewer than two remaining points are dropped. Deduplication avoids zero-length polyline segments that can break rendering.

Measured from the actual checked-in JSON, before runtime deduplication:

| Dataset | Rings / lines | Coordinate pairs | File bytes |
|---|---:|---:|---:|
| Coastline | 2 | 1,576 | 28,048 |
| Water | 21 | 3,212 | 57,107 |
| Roads | 162,905 | 343,832 | 4,086,852 |
| Paths | 80,523 | 183,104 | 2,096,457 |

Together these files contain 531,724 coordinate pairs and about 6.27 MB of raw JSON. These are source-file sizes, not compressed network or production-bundle measurements.

Source comments identify the land as Pulau Ujong and Sentosa from OSM/Nominatim, and water/transport geometry as OSM data fetched through Overpass. No download, generation, or refresh scripts are checked in. Two land rings do not constitute complete coverage of every Singapore offshore island; clipping follows this data, separately from the larger rectangular camera bounds.

Drawing order is land → inland water → paths → roads → coast. All ground primitives classify terrain only, avoiding coloring building surfaces. Land/water use polygon fills; roads, paths, and coast use ground polylines. Roads are width 2.5, paths 1, coast 2.

The palette is sea `#1d4e6b`, water `#2a6788`, land `#8f9194`, coastline `#c2c6cb`, roads `#5f6469`, and paths `#7c8188`. Inverse clipping removes tiles outside the land polygons.

### Lighting

Both presets enable globe lighting, atmosphere when available, fog, and HDR; both disable globe translucency. Midday sets `2026-03-15T04:30:00Z` (12:30 Singapore time); blue hour sets `2026-03-15T11:20:00Z` (19:20). These are fixed presentation choices, not current weather or live time. Lighting currently shares the viewer clock that the planned playback module would also need to manage.

## 7. Demo behavior

The demo is plain DOM TypeScript without React or another UI framework. It generates preset buttons from library data, then adds basemap, lighting, and orbit controls.

- Basemap switching disables its button during loading, reports a key-related failure message on rejection, and resets the label from `scene.basemap` afterward.
- The orbit button targets `(103.8607, 1.2834)` with radius 1,200 m, pitch −22°, and rate 5°/second.
- Boundary events briefly draw an orange viewport border and display the edge or zoom-limit message for 900 ms.
- Expected flight cancellation is ignored by both error class and error name to accommodate Vite hot-reload module identity differences.
- `window.__canvas` exposes the API for manual browser debugging.

The panel scrolls on smaller viewports. Buttons include keyboard focus styling, and reduced-motion CSS disables UI transitions. That preference does not disable camera flight/orbit animation. Cesium's attribution area remains visible.

## 8. Older standalone prototype

`singapore-3d.html` is a separate inline HTML/CSS/JavaScript implementation loading Cesium 1.145 from its CDN. It uses empty inline credential constants rather than Vite environment values.

It offers whole-island, Marina Bay Sands, Merlion, ArtScience Museum, and CBD camera positions; starts on the island and schedules a flight to MBS; supports a simpler orbit; and falls back to terrain/OSM when Google loading fails. It also defines an unused `insetModel` helper that cuts a circular hole in a tileset and inserts a model entity. No corresponding `.glb` is supplied.

This prototype does not use the current library's camera cage, custom ground datasets, typed API, or town preset model. It is not configured as an additional production entry point in the Vite build. Its screenshots and comments are historical context, not proof of current behavior.

## 9. Build and local setup

The package is private, version `0.0.0`, and uses ES modules. Locked direct dependency versions are Cesium `1.145.0`, TypeScript `5.9.3`, Vite `8.3.0`, and `vite-plugin-cesium` `1.2.23`.

The lockfile's engine declarations require Node >=22 for Cesium, and `^20.19.0 || >=22.12.0` for Vite; Node 22.12+ satisfies both. There is no checked-in Node version pin.

```sh
cd frontend # From the repository root.
npm ci
cp .env.example .env.local
# Fill in VITE_CESIUM_ION_TOKEN and optionally VITE_GOOGLE_MAPS_API_KEY.
npm run dev
```

The development server is configured for port 5173. Credentials are passed by the browser application to its remote providers. `VITE_*` values are embedded in frontend code by the build, so ignoring `.env.local` prevents committing the source file but does not make its values server-side secrets.

| Command | Effect |
|---|---|
| `npm run dev` | Starts Vite with the Cesium plugin |
| `npm run build` | Type-checks, then builds the demo into `dist/` |
| `npm run build:lib` | Type-checks, then builds an ES library into `dist-lib/` |
| `npm run preview` | Serves the built demo locally |

The library build externalizes `cesium`; the consuming application must supply it and arrange the necessary Cesium runtime assets/styles. No declaration-file generation, package export map, publishing workflow, deployment config, lint command, or test command is configured. TypeScript uses strict checking, unused-variable/parameter checks, unchecked-index checks, JSON imports, and an ES2022 target.

## 10. Planned intercept/debris features

`docs/API-DESIGN.md` marks the current code as steps 1–5 and describes a scoped step 6. The planned library remains domain-neutral; missile/interceptor vocabulary belongs in the demo.

| Planned module | Responsibilities |
|---|---|
| `src/lib/time.ts` | Range, play/pause, seek, multiplier, current time, playing state |
| `src/lib/layers.ts` | ID-addressed moving tracks, single paths, bursts, ground overlays, visibility/removal |
| `src/lib/samples.ts` | Pure input sanitization and timestamp ordering |
| `src/demo/scenario.ts` | Proposed scenario types, loading seam, mock data |
| `src/demo/debris.ts` | Scenario-to-canvas integration and landing-density heatmap |

None of these files exists yet.

The design proposes roughly 1,000 primitive-backed moving tracks, selective entity-backed trails, single-path entities, particle bursts, and tileset imagery overlays. Tracks would hide before their first sample and hold their final position afterward. Samples would be sorted, duplicate times removed, invalid coordinates dropped, and empty tracks skipped. The planned `follow(layerId, trackId?, opts?)` would follow either a path or an individual track while respecting the camera cage.

The proposed backend payload contains start/end timestamps, missile and interceptor samples, an intercept sample, and fragment tracks. A `ScenarioSource.load()` seam would allow a mock and eventual backend implementation. Around 1 Hz sampling and approximately 4 Hz heatmap redraw are design targets, not measured behavior of running code.

Ground overlays would need to reattach when basemaps change. Burst seek behavior, overlay flicker, wall streaking, interpolation, and frame rate remain planned validation topics. General point/model/polygon layers, custom clip regions, and picking are deferred beyond that scope.

## 11. Important implementation gaps and review observations

These observations come from source inspection; runtime failure cases have not been reproduced in this review.

1. **Documentation includes future behavior written in the present tense.** The design's mock scenario, loading seam, heatmap, time module, and layer registry do not exist. Its expanded `follow` signature also differs from the current throwing stub.
2. **Dataset comments are stale.** `coastline.ts` describes 30 water bodies and about 1,800 points; the file actually has 21 rings and 3,212 coordinate pairs. Its road-size comment also understates the current raw JSON size. Counts above come from the files.
3. **Cesium is not exactly pinned in the manifest.** The design calls the version pinned, but `package.json` uses `^1.145.0`. The lockfile currently resolves 1.145.0; `npm ci` preserves that resolution.
4. **Basemap replacement is not transactional.** It destroys the old tileset before the replacement finishes loading. Failure can leave no city tileset while `scene.basemap` still names the previous successful mode. The library does not serialize or cancel concurrent switches, though the demo disables its own button.
5. **Startup failure does not clean up partial initialization.** The factory has no catch/finally to destroy a viewer/ground setup if scene creation rejects. The demo's initial top-level await also has no startup error UI handler.
6. **Tile-progress reporting is limited.** It observes globe tiles, not the active city's 3D tileset, so it is not a complete indicator of photorealistic/building loading.
7. **Input validation is minimal.** Camera positions, orbit settings, bounds, and height relationships are trusted. The planned sample sanitizer is not yet available.
8. **Demo orbit state can become inaccurate.** Selecting a preset stops library orbit, but does not reset the demo's separate `orbiting` boolean or button label.
9. **Large geometry is prepared eagerly.** Hundreds of thousands of points are decoded at module load, and ground primitives are constructed even when the initial basemap is photorealistic and they will be hidden. Startup, memory, and rendering costs have not been benchmarked here.
10. **Lifecycle handling is stronger in the library than in the demo.** Library destruction removes its listeners, primitives, and viewer, but the demo does not call it on teardown or register a Vite HMR disposer. Its boundary timer/subscription are not explicitly disposed by demo code.
11. **Lighting and future simulation time need coordination.** Lighting currently writes directly to the viewer clock. A later simulation clock could overwrite the presentation time, or vice versa.
12. **Several delivery pieces are absent.** There is no test harness, CI, geodata regeneration pipeline, backend integration, package publishing setup, or dedicated license file in the tracked tree. The API document references local `CLAUDE.md` instructions, but that file is ignored and is not part of the checked-in codebase.

## 12. Review coverage and verification limits

This summary covers all tracked application source, the standalone prototype, build/configuration files, environment template, API design document, and lockfile dependency metadata. Geographic JSON was parsed to verify array/coordinate counts and file sizes. Baseline images were inventoried as reference assets; they were not used to establish current visual correctness.

This was a documentation review. Dependencies were not installed, builds were not run, and live Cesium/Google rendering was not tested. No application code was changed. Successful credential loading, browser compatibility, visual quality, and performance therefore remain unverified by this review.

After the subsequent move to `frontend/`, `npm ci`, `npm run build`, and `npm run build:lib` all completed successfully from that directory, including TypeScript checks. Vite reported a large demo JavaScript chunk (about 6.28 MB, 2.21 MB gzip). Live rendering was not tested during the move.
