# Frontend

Singapore Canvas remains the CesiumJS/TypeScript/Vite viewer and demo in `src/lib/` and `src/demo/`. The population milestone adds `src/lib/polygons.ts` for reusable polygon rendering/picking, and `src/demo/population-model.ts` / `population.ts` for population controls, map styles, chart and details.

It consumes the prepared `public/population.geojson`; no official sources are fetched or joined in the browser. Count/density, a fixed legend, qualified-unknown styling, search, area filtering, rankings and hover/pinned details share the same artifact. Camera presets, orbit, lighting and remote basemap switching remain; a plain globe supports use without credentials. No exposure calculations are implemented here.

See [verification](docs/POPULATION-VERIFICATION.md), [current dataset contract](../contracts/population-dataset.md) and the [root commands](../README.md). The existing [codebase summary](CODEBASE-SUMMARY.md) and [API design](docs/API-DESIGN.md) remain historical references; population additions supersede their statements that polygon support and all automated tests are absent. Their planned playback, tracks and follow features remain unimplemented.

Future assessment presentation belongs here; population preparation belongs in `backend/data_sources/`, and future PEC calculations in `backend/exposure/`. Existing map JSON, standalone prototype and baseline screenshots remain preserved.
