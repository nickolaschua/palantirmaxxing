# Main pull summary — Jae frontend changes

Pulled `origin/main` into the local `main` branch on 2026-09-26. The branch fast-forwarded from `e12bb11` to `dc82f74` (PR #4, “merging jae's frontend changes with main”). The incoming range contains Jae En's commits `7623684` (hospitals and history), `8332e3b` (`sdth day1`), and `4fe53c8` (panel, history snapshots, type scale), followed by merge commit `dc82f74`. The net pull changed **27 tracked files: 1,122 insertions and 314 deletions**. Its changes are in the frontend, its unit tests, and `.gitignore`; it did not pull backend or scenario-data changes.

## What changes for a demo user

- **Hospitals appear as a red OpenStreetMap layer.** The demo adds 47 hospital-area rings, 42 named, beside the existing purple military areas. Both have building tints, boundaries, labels at closer zoom, and legend entries. The population view hides these layers to keep its own map colours legible. The side inspector also shows both layers.
- **An intercepted threat leaves a map mark.** At outcome, the route, inbound track, fall path, window markers, and other option areas disappear. The chosen supplied footprint remains faintly shaded with an “Intercepted · T+…” marker. This is an intercept location, not a calculated damage area.
- **History survives Restart for the current page session.** A History control lists runs newest first. Fired runs retain individual map marks that can be toggled; expired runs have no mark. Completed decision trays close after the burst and can be reopened as read-only snapshots from History. Reloading the page clears the history.
- **The layout is more compact.** The left controls panel can slide away, Play and Restart sit above History, the decision tray is scaled to 75%, and the UI and map labels share an Alliance/Inter font stack and five text sizes. Camera framing accounts for the controls panel, inspector, and tray.
- **The inspector has a consequence section.** It presents the six H/E/D/X/R/A dimensions, weights, values, uncertainty bands, and a weighted total when supplied. Missing values show as “Unavailable,” distinct from zero. In this demo the loader currently injects deterministic **illustrative** scores when the backend has no consequence values; the section labels them as illustrative, and authorised-capability disruption (`D`) remains unavailable.

## Implementation and file inventory

| File(s) | Incoming change |
| --- | --- |
| `.gitignore` | Ignores `/docs/superpowers/`. |
| `frontend/docs/API-DESIGN.md` | Documents hospital data, the persistent struck-area mark, and in-page History behavior. |
| `frontend/index.html` | Loads the Inter font and adds the left-panel toggle button. |
| `frontend/package.json` | Adds the ground-model unit test to `npm test`. |
| `frontend/package-lock.json` | Refreshes lockfile metadata (platform `libc` and peer flags); no declared package version changed. |
| `frontend/scripts/fetch-ground-detail.mjs` | Adds an Overpass `amenity=hospital` area query and writes the hospital JSON with names. |
| `frontend/src/demo/hospitals.json` | Checks in the hospital polygons used by the demo. |
| `frontend/src/demo/military.ts` → `frontend/src/demo/osm-areas.ts` | Turns the military-only renderer into a configurable OSM area layer shared by military bases and hospitals. |
| `frontend/src/demo/main.ts` | Mounts both OSM layers, their legend entries, and the collapsible panel behavior. |
| `frontend/src/demo/population.ts` | Aligns population map labels with the revised font scale. |
| `frontend/src/demo/decision-model.ts` | Adds optional consequence types, input validation, formatted rows, and camera framing with screen insets. |
| `frontend/src/demo/source.ts` | Centralizes planning-result loading and adds clearly flagged illustrative consequence figures until the backend supplies them. |
| `frontend/src/demo/decision.ts` | Adds persistent intercept marks, per-run History, tray snapshots, outcome cleanup, camera inset use, and the source loader. |
| `frontend/src/demo/inspector.ts` | Lazily creates the second Cesium canvas on first open, mirrors both OSM layers, hides the finished route, and renders consequence rows. |
| `frontend/src/demo/style.css` | Styles the sliding panel, scaled tray, History, snapshots, fonts, inspector, and consequence bars. |
| `frontend/src/lib/coastline.ts` | Replaces always-present vector ground detail with 256 px imagery tiles painted on demand; loads roads and paths at useful zoom levels. |
| `frontend/src/lib/ground-model.ts` | Adds typed-array line packing and a grid index so each imagery tile visits only nearby lines. |
| `frontend/src/lib/index.ts` | Uses Cesium 3D-only and request-render modes with FXAA instead of 4× MSAA. |
| `frontend/src/lib/scene.ts` | Caps OSM building tile cache size, retains the ground imagery layer across basemap changes, and requests renders after scene changes. |
| `frontend/src/lib/burst.ts`, `camera.ts`, `craft.ts`, `labels.ts`, `overlays.ts`, `tint.ts` | Request frames for animation or changed layers under Cesium's new render mode; centralize label font styling and adjust craft placement. |
| `tests/unit/decision-model.test.ts` | Tests consequence validation/formatting and inset-aware camera framing. |
| `tests/unit/ground-model.test.ts` | Tests delta decoding, grid queries, and duplicate avoidance. |

## Review notes

- The pulled API design note described the retained area as **500 m**, while the current local demo result uses **100 m**. That sentence was corrected after review. The implementation reads the radius from the result.
- Hospital coverage follows OSM `amenity=hospital` **area** tags. Point-only hospitals are absent, and the checked data may include other healthcare sites that use that tag. The source and visual treatment should be understood as map context, not a verified hospital registry.
- The consequence total shown by the demo's stand-in source is generated from illustrative dimensions. It is not backend output or a validated consequence estimate.
- History exists only in page memory. Each fired run adds map layers that remain until reload or component disposal; repeated runs can increase memory use.

## Pull integration and checks

The working tree already contained uncommitted backend, simulation, documentation, and frontend work. Those local changes were preserved. Four overlapping text files (`frontend/docs/API-DESIGN.md`, `frontend/package.json`, `frontend/src/demo/main.ts`, and `frontend/src/demo/style.css`) were combined so the pulled features coexist with the local simulation integration. The resulting local `npm test` runs both the new ground test and the existing uncommitted simulation test.

Validation after the pull: **18/18 frontend unit tests passed**, `npm run build` passed, and `git diff --check` passed. Vite reported only its existing large-chunk advisory. `graphify update .` completed after the code integration. These checks cover compilation and unit behavior; they do not establish browser visual quality or map-provider availability.
