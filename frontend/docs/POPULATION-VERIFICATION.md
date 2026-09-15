# Population milestone verification

Verified on 14 September 2026. No exposure calculations or event/optimisation components were implemented.

## Automated checks

- Seven Python unit tests cover hierarchy (including `Changi- Total`), qualified/missing/zero/invalid values, conservative names, duplicate/ambiguous/bidirectional joins, projected area/density units and geometry exclusions.
- One offline integration test exercises the complete fixture pipeline, byte-identical reproduction, preserved geographic geometry, projected WKT/area agreement, cached acquisition without network, failed/truncated-refresh protection and checksum rejection.
- Three Node tests cover filter/ranking agreement, unknown versus numeric zero, stable colors, density conversion and payload guards.
- The full official cached dataset was prepared twice: all five processed outputs were byte-identical. A separate all-pairs spatial-index check found all 275 projected candidates valid, positive-area and non-overlapping.
- `npm run build` and `npm run build:lib` pass TypeScript and Vite. The demo retains the existing roughly 6.3 MB JavaScript chunk caused largely by bundled map assets; Vite warns about its size. No performance budget is claimed.

Commands are in the [root README](../../README.md). Tests require no network. Official acquisition was performed separately through the supplied population API and documented boundary poll-download workflow.

## Browser inspection and limits

The Vite development preview was opened in Safari through native UI automation. Observed:

- Correct title, all 332 zones, 4,044,340 known residents and 46 unknown populations in the controls.
- Count/density toggles update the fixed-unit legend and rankings; density ranking starts with Jurong West Central at about 45,396 people/km².
- Selecting Tampines East from the chart pins population 130,980, area about 4.344 km² and density about 30,154 people/km².
- Search for Semakau reports one unknown-population zone and no known ranked value. A non-matching search shows the explicit empty state; clearing it restores the full dataset.
- Disabling/re-enabling the population layer updates visibility state while retaining the chart/data.
- The remote terrain/OSM basemap request completed successfully. The Google photorealistic path was attempted, but successful rendering was not established.
- Temporarily withholding the generated display artifact produced the loading/failure/retry UI. Restoring the same artifact and selecting Retry loaded all 332 zones again. The final error handling also recognises HTML fallback responses as a missing/non-JSON artifact.
- Source links, dates, population interpretation, details and attribution were present.

The available Safari automation window reported `document.visibilityState = hidden`, and its normal animation loop did not advance after reload. Temporary explicit redraw diagnostics established that WebGL and colored population polygons render, and exposed the original ground-primitives overpainting issue. The implementation preserves that renderer and temporarily hides its custom land/road surfaces while a polygon overlay is enabled, restoring them when disabled. Diagnostic timers, debug status and forced redraws were removed before delivery; the application uses Cesium's normal render loop.

Coordinate-based interaction failed with `noWindowsAvailable` / `cgWindowNotFound` in this environment. Consequently, **normal foreground animation, hover/click picking directly on the map, all multipart/offshore visual details, final direct basemap-select interaction, successful Google rendering and mobile layout are not browser-verified**. Planning-area filtering is covered by selector tests, but its native dropdown could not be exercised reliably here. The library implements picking/visibility lifecycles, and all final code is type-checked; these limits are not presented as passed runtime tests.

For a foreground follow-up, check count and density maps, filter and clear a planning area, hover/click mainland and multipart offshore zones, toggle the layer in each configured basemap, and confirm attribution remains visible. Unknown zones must stay grey and show their original `-` qualification; excluded geometry must never be represented as PEC-eligible.
