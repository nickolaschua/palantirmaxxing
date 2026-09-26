# Defence and sensitive dependencies

Two kinds of data: public geography of military areas in Singapore, and abstract evidence about how civil infrastructure failures could degrade defence-relevant functions. Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md). The geography is scored by `military.py` (`pipeline.py military`); the dependency evidence stays data only.

## Geography (`geography/`, output in `../output/defence/`)

- `../output/defence/defence_output_sites.geojson` (git-ignored): 81 polygons in WGS84 (EPSG:4326), decoded from OpenStreetMap `landuse=military` rings used by the frontend (`frontend/src/demo/military.json`). 69 are named (68 distinct names), 12 are unnamed. Properties: `id` (matches the frontend's `military-N`), `name`, `name_contains_air_base`, `centroid_lat`, `centroid_lon`, `area_m2`, `vertices`, `source`.
- `../output/defence/defence_output.csv` (git-ignored): the same rows with the polygon as `geometry_wkt`.
- `geography/build_military_areas.py`: the decoder, which writes the two files above (`python backend/data_sources/consequence/defence/geography/build_military_areas.py` from the repo root). It reads the frontend file and does not modify it.
- The six air-base names are Tengah, Paya Lebar, Sembawang, Changi Air Base (West), Changi Air Base East and a small Changi Airbase piece. `name_contains_air_base` comes from the name only.

## Dependency evidence (abstract)

- `../output/defence/defence_output_reference.json` (git-ignored, moved here by hand; no builder writes it yet): the five tables below joined into one file (`archetypes`, `global_evidence`, `scenarios`, `dependency_input_template`, `authorised_D_contract`), with the scope, warning and vector from the metadata. Checked row for row against the CSVs. The files below are the originals and can be removed once this one is the single source.
- `input_archetypes.csv`: 8 archetypes (`AR-01`..`AR-08`, for example continuity of government, civil-military communications, air mobility) with civil dependencies, consequences and the fields an operator would supply.
- `input_global_evidence.csv`: 8 documented international cases (event, system, consequences, metrics, source, confidence).
- `input_resilience.csv`: scenarios such as external power loss and communications degradation, with what to observe and which dimensions they touch.
- `input_template.csv`: empty template for authorised operator input.
- `input_D_contract.csv`: the allowed fields for supplying the capability dimension (opaque id, capability share band, loss fraction band).
- `input_metadata.json`: scope, vector, weights and the warning. Written by the builder, so it still describes only the abstract evidence.
- `input_evidence.xlsx`: the same five tables as a workbook (plus a Read Me sheet).
- `build_defence_dependencies.mjs`: the builder that produced the files above.

## Scoring (`military.py`, output `../output/defence/military_output*`)

Decided 2026-09-26 (plan: `../doc/plans/2026-09-26-rank-defence-and-critical-sectors.md`): military areas join the cross-sector ranking, using public geometry only.

- Occupancy is one generic assumed density for military land (100/500/2,000 people per km2), the same for every site, times the spec section 9 "Office" time coefficients. Only the share inside the placeholder footprint is scored (areal density, spec section 9.1).
- No civilian service is publicly attributable, so E is the lowest band (10) by assumption. D stays unavailable.
- The six air bases are declared priority assets. `scoring.veto` rejects them as `priority_asset_capability_not_assessed` (a capability reason, separate from civilian reasons) until an authorised D input assesses them. The other 75 areas are ranked on civilian C with essential-site thresholds and show `unknown`, because D is unavailable.

## Limits

- Locations are public map data (OpenStreetMap). They say where a military area is drawn, not what it does. Nothing here infers capability, readiness, vulnerabilities or single points of failure; a military area's rank reflects only assumed civilian presence and the precautionary air-base veto. OSM outlines can be incomplete or out of date.
- The archetype, evidence, scenario and template tables carry no site locations and no scores.
- D stays unavailable until supplied through an authorised interface (`input_D_contract.csv`). `score_profile` takes D as a ready 0-100 estimate on the profile and does not compute it from the contract fields.

## Rebuild

`node build_defence_dependencies.mjs` needs `@oai/artifact-tool` and writes back into this folder. The geography files are rebuilt separately by `build_military_areas.py` and, like `defence_output_reference.json`, live in the git-ignored `output/` folder, so a fresh clone must run it once.
