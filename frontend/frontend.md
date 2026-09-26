# Frontend

Singapore Canvas remains the CesiumJS/TypeScript/Vite viewer and demo in
`src/lib/` and `src/demo/`. The population view uses reusable polygon
rendering/picking. Planning and simulation results load from the same-origin
local API with explicit fixture mode, immutable result identities, refresh and
retry behavior, and lifecycle-safe replacement of Cesium resources.

It consumes the prepared `public/population.geojson`; no official sources are fetched or joined in the browser. Count/density, a fixed legend, qualified-unknown styling, search, area filtering, rankings and hover/pinned details share the same artifact. Camera presets, orbit, lighting and remote basemap switching remain; a plain globe supports use without credentials. No exposure calculations are implemented here.

The simulation controls preserve legacy seed runs and add a frozen-scenario
mode. The browser fetches the checked manifest, filters by split/profile or
reference text, submits one of three fixed policies, and loads the job's exact
published result ID. Version 2 renders the actual 2–8 trajectories, selected
and unhandled footprints, visible provenance badges, online/offline scope,
naive/exact costs, regret, and constraint failures. Unhandled paths and terminal
areas are visibly red. Human-readable policy labels distinguish the naive online
policy from the offline exact and feasible comparators; the selected policy's
disclosure is visible before run.

See [verification](docs/POPULATION-VERIFICATION.md), [current dataset contract](../contracts/population-dataset.md), [HTTP contract](../contracts/frontend-backend-api.md), and the [root commands](../README.md). The existing [codebase summary](CODEBASE-SUMMARY.md) and [API design](docs/API-DESIGN.md) remain historical references.

Population preparation belongs in `backend/data_sources/`, and PEC calculations
belong in `backend/exposure/`. Existing map JSON, standalone prototype and
baseline screenshots remain preserved.
