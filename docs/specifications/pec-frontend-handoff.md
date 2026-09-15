# PEC frontend handoff

Repository inspection: 15 September 2026. This document gives the Singapore Canvas owner integration context and suggested outcomes. Layout, styling, animation and interaction design are theirs to decide. Suggestions below are not implemented features or new payload contracts.

## 1. Purpose and current status

The Population Exposure Calculator (PEC) v0.1 calculates **people potentially exposed within supplied circular event footprints**, using population density derived from eligible zones. It returns per-event exposure, three whole-episode measures, coverage information and reproducibility metadata.

Implemented: standalone Python validation/calculation, reusable prepared geometry, strict JSON file execution, population preparation, examples, tests and numerical investigations. See the [calculator](../../backend/exposure/calculator.py), [dataset preparation](../../backend/exposure/dataset.py), [validation](../../backend/exposure/validation.py), [PEC specification](pec.md) and [contract](../../contracts/pec.md).

Not implemented: PEC frontend integration/result loading, HTTP endpoints, application orchestration, database, footprint prediction, simulation, casualty estimation or optimisation. Historical [frontend API design](../../frontend/docs/API-DESIGN.md) describes proposed playback, tracks, overlays and follow behaviour; these are not available PEC integration APIs. Older milestone statements about PEC being absent are superseded by the current calculator and contract.

Existing [Singapore Canvas capabilities](../../frontend/frontend.md):

- CesiumJS/TypeScript/Vite viewer with camera presets, flight/orbit, lighting, and plain, terrain/OSM (`extruded`) and Google (`photorealistic`) basemaps.
- Population count/density map, fixed legend, unknown-data styling, search, planning-area filtering, ranking, hover/pinned details and loading/error/retry states.
- Public [`canvas.addPolygonLayer(data, callbacks)`](../../frontend/src/lib/index.ts): geographic GeoJSON Polygon/MultiPolygon features with unique string IDs; hover/click callbacks return an ID or null. Returned layer supports `setVisible`, `setStyles` and `destroy`. [Implementation](../../frontend/src/lib/polygons.ts) preserves feature IDs across multipart entities and uses ground-clamped polygons.
- The polygon loader replaces feature properties with internal ID tagging. Keep result rows and domain details in application state keyed by ID; do not expect arbitrary properties back from picking. Multiple visible polygon layers are supported, but overlapping PEC/population selection behaviour has not been verified.

## 2. Integration entry points and files

### Generate an example

From the repository root, using the existing Python 3.9–3.12 PEC environment with the [pinned dependencies](../../backend/data_sources/requirements.txt) already available:

```sh
.venv/bin/python scripts/population_exposure.py \
  --population tests/fixtures/pec-population.json \
  --episode data/scenarios/pec-example.json \
  --output data/results/pec-example.json
```

This uses a [synthetic population fixture](../../tests/fixtures/pec-population.json) and [two-event episode](../../data/scenarios/pec-example.json). Compare the generated [result](../../data/results/pec-example.json) with the checked-in [reference result](../../contracts/examples/pec-result.json). The synthetic coordinates around `(0, 0)` metres are not a meaningful Singapore hazard location; use this for payload/number checks, not a Singapore map demonstration.

For a supplied Singapore-coordinate workload, with the matching prepared dataset available:

```sh
.venv/bin/python scripts/population_exposure.py \
  --population data/processed/population-projected.json \
  --episode data/scenarios/pec-coverage-benchmark.json \
  --circle-edges 256 \
  --output data/results/pec-coverage-256.json
```

The [archived 100-event input](../../data/scenarios/pec-coverage-benchmark.json) is a numerical benchmark, not a hazard scenario prediction. Its [256-edge result](../../data/results/pec-coverage-256.json) has partial episode coverage. The input requires dataset ID `sg-residents-2020-mp2019` and version `sg-residents-2020-mp2019-cbb1c395f60918c1`; another version must not be silently substituted. General episodes must declare the exact `metadata.dataset_version` of their projected population input.

These commands need no frontend or network. Generated geometry/results may be absent in a fresh checkout because they are ignored. The checked-in synthetic reference remains available; [root setup/preparation instructions](../../README.md) explain how to obtain the larger artifacts. No dependencies were installed or results regenerated for this documentation task.

### File relationships

| Artifact | Role and correspondence |
|---|---|
| [PEC contract](../../contracts/pec.md) | Authoritative `pec-population/1`, `pec-episode/1` and `pec-result/1` fields and validation rules; also accepts the prepared WKT envelope. |
| [Population contract](../../contracts/population-dataset.md) / [projected input](../../data/processed/population-projected.json) | Eligible calculation zones only; authoritative `geometry_wkt` in `population-zones-wkt/1`. Required with an episode to calculate. Never feed the full display dataset to PEC. |
| Episode + result | Retain the input alongside its result. Match `episode_id`, exact `event_id` and `footprint_id`, centres/radii and dataset identity. Results sort events by ID, not input order or time. |
| [Display GeoJSON](../../data/processed/population-display.geojson) / [public copy](../../frontend/public/population.geojson) | Full 332-zone geographic reference and byte-identical Vite-served copy. Join result `zone_breakdown[].zone_id` to feature `id` / `properties.zone_id` only with the matching dataset version. Synthetic `east`/`west` IDs do not join to Singapore subzones. |
| [Provenance](../../data/processed/provenance.json), [validation report](../../data/processed/validation-report.json), [summary](../../data/processed/validation-summary.md) | Source dates/checksums, exclusions and reconciliation. Needed for richer provenance and coverage explanations, not calculator arguments. |

Valid results repeat event centre/radius and optional time, but contain **no footprint vertices, zone geometries, intersection geometries or missing-area polygons**. Result-only metrics are possible; geographic details require matching geometry/reference files and a transformation step. The result's `metadata.dataset_checksum_sha256` hashes the normalized entire population envelope, not file bytes or the episode. Preserve the input episode separately for an auditable run.

### Suggested first loading path — not implemented

Start with one saved result, loaded through a file chooser or a static asset fetched by the demo. Either is a proposed browser integration, not an existing endpoint; there is no `/api` route to assume. Static files would need to be deliberately made available to Vite, as the population artifact already is. Files under `data/results/` are not automatically browser URLs.

Validate the result schema/status and expected IDs/version before binding metrics to map features. Retain nulls. Load matching population display/provenance separately if needed. Report missing files, malformed/non-JSON content and version mismatch explicitly; do not silently show a prior result as current. A later service can reuse `prepare_population(document)` and `calculate_episode(prepared, episode, CalculationSettings())` from [backend.exposure](../../backend/exposure/__init__.py); no service transport is selected.

### Actual payload excerpts

Selected fields from the [input example](../../data/scenarios/pec-example.json), without renaming or rounding:

```json
{
  "event_id": "event-2",
  "footprint_id": "footprint-2",
  "center_x_m": 5,
  "center_y_m": 0,
  "radius_m": 1,
  "time_from_episode_start_s": 30
}
```

Selected top-level fields from the [reference output](../../contracts/examples/pec-result.json):

```json
{
  "episode_id": "pec-example",
  "schema_version": "pec-result/1",
  "status": "complete",
  "unique_people_potentially_exposed": 50.245298511276054,
  "total_person_exposures": 50.24529851127604,
  "people_exposed_to_multiple_events": 0.0,
  "uncovered_area_m2": 0.0
}
```

One actual `zone_breakdown` row for `event-1`:

```json
{
  "estimated_people_exposed": 25.122649255638017,
  "overlap_area_m2": 6.280662313909504,
  "zone_density_people_per_m2": 4.0,
  "zone_id": "east",
  "zone_population": 800
}
```

## 3. What the numbers mean

For each eligible zone, density is population / full supplied zone area. Its event contribution is density × intersected area. These are estimated, potentially fractional people.

| Measure | Complete field | Meaning |
|---|---|---|
| Per-event exposure | `events[].people_potentially_exposed` | Sum of contributions within that event's calculation polygon. |
| Unique people potentially exposed | `unique_people_potentially_exposed` | Population in the union of all event footprints; each location counted once. |
| Total person-exposures | `total_person_exposures` | Sum of per-event exposures; repeated exposure counts again for each event. This is not a unique-person count. |
| People exposed to multiple events | `people_exposed_to_multiple_events` | Population covered by at least two distinct events; triple overlap still counts once here. |

Illustrative overlap example, not the bundled example: three identical footprints each covering 100 estimated people give **100 unique people, 300 person-exposures, and 100 people exposed to multiple events**. Per-event exposure is 100 each. `total_person_exposures - unique_people_potentially_exposed` would be 200, so that subtraction is not the multiple-event metric. The bundled two-event example is disjoint and correctly has zero multiple exposure.

Repeated footprint IDs require exactly identical centre/radius values; different IDs may also describe identical geometry. Distinct events still contribute separately to person-exposures. Do not deduplicate events by `footprint_id` when presenting totals.

## 4. Geographic integration

**Calculation:** EPSG:3414 (SVY21 / Singapore TM), `[easting, northing]` metres. PEC validates the declared CRS but performs no conversion or coordinate inference. Area is m²; density is people/m².

**Frontend:** [`GeoPoint`](../../frontend/src/lib/types.ts) uses `{ lon, lat, height? }`, WGS84 degrees with optional height in metres. Geographic GeoJSON uses `[longitude, latitude]`. Never pass PEC metre coordinates directly to Canvas or GeoJSON loading.

Transformation is required in both directions if map-authored events are introduced: WGS84 map centre → EPSG:3414 before calculation; calculated polygon vertices → WGS84 for display. The [population pipeline](population-data.md) uses pyproj with `always_xy=True` and no ballpark transform for source reprojection. A PEC footprint export/browser transformation adapter is not implemented.

To preserve correspondence, the proposed adapter should construct the same projected polygon as [PEC's `footprint`](../../backend/exposure/calculator.py), then transform its vertices. Use the result's recorded settings: Shapely `Point.buffer(radius, quad_segs=edges//4)`, **128 edges / 32 segments per quadrant by default; 256 / 64 supported**. Polygons are inscribed, clockwise from the positive x axis. All calculation areas, intersections and unions use that polygon, not ideal πr². Exporting those calculation vertices alongside a run is a possible future approach; no such output field exists today.

A browser geodesic circle, a circle drawn directly in degree coordinates, or another tessellation is not established as the same footprint. Verify transformed vertices and projected round-trip geometry before claiming a match; any renderer interpolation remains a display approximation. Preserve episode/event/footprint identity and settings with the rendered representation. `event_id` is unique within an episode and is a suitable selection key; scope it by episode if multiple runs are shown.

Clipping/simplification for display must never change PEC inputs, eligible coverage or result values. The existing city/coastline clip omits some offshore zones; population polygons are independent of it. All inspected population extents fit the rectangular camera bounds. Keep holes and multipart/offshore geometry. Visible layers, filters, basemap extent and camera view do not define population coverage. With polygon overlays enabled, Canvas shows the globe and hides custom land/road surfaces to prevent overpainting; verify this with the added layer.

## 5. Status, missing data and edge cases

| Status | Implemented meaning | Suggested communication |
|---|---|---|
| `complete` | Missing calculation-polygon area is at most `1e-6 m²`; complete metrics are numbers. | Complete coverage of this calculation geometry, not a claim of national completeness or ideal-circle coverage. |
| `partial_coverage` | Missing area exceeds `1e-6 m²`. | Complete estimate unavailable; show clearly labelled known-area subtotals and missing area. |
| `invalid_input` | Validation/numerical failure; no event calculations, aggregates or success metadata. | Calculation failed; show structured errors and relevant input IDs/fields, not empty success metrics. |

Per-event `known_area_exposure` remains available when `people_potentially_exposed` is null. Episode equivalents are `known_area_unique_exposure`, `known_area_person_exposures` and `known_area_multiple_exposure`. A partial episode has all three complete totals null even if some events are complete. Use each returned status; episode coverage is computed on the union. Episode `uncovered_area_m2` is union missing area, not the sum of event missing areas.

`covered_area_fraction` is an area fraction, not the fraction of people known. Do not extrapolate population by dividing known exposure by this fraction. Status must not be inferred from its rounded display: a partial event may round to 100% coverage.

- **Null is unavailable/undefined, not zero.** An entirely uncovered positive-area event normally has zero known exposure and null complete exposure. Unknown/excluded zones do not extend coverage; valid zero-population zones do.
- **Empty episode:** complete, empty events and zero totals. Communicate “no events,” without implying a populated assessment occurred.
- **Zero-radius event:** complete, zero area/exposure, empty zone breakdown and null coverage fraction, even outside coverage. No area polygon exists; an optional selection marker must not imply positive coverage.
- **Numerical exception:** a wholly uncovered positive footprint no larger than the absolute area tolerance can be complete. Measured missing area remains in the result; the tolerance is not a relative percentage.
- **Zone rows:** positive-area overlaps only, including known-zero zones; boundary-only touches have no row. Rows do not describe missing regions.
- **Errors:** branch on `errors[].code`; `record_type`, optional `record_id`, `field` and `message` supply context. Any invalid event prevents all aggregation. The file command exits 0 for complete/partial, 2 for invalid inputs/arguments, and 1 for file errors. File errors go to stderr and may leave no new result.

For unavailable population, preserve the source qualification and exclusion reason. For unavailable result/geometry files, distinguish “cannot load/display” from a valid zero exposure. Never convert missing fields, nulls or failed calculations to zero.

## 6. Suggested experience — design remains open

- Make footprints discoverable and selectable, with a clear relationship between map selection and event details. Overlaps and repeated footprints need a way to reach each event; the owner chooses the interaction.
- Event details could show IDs, supplied centre/radius/time, status, polygon area, missing area, coverage fraction and complete or known-area exposure. Contributing zones can show name/ID, population, density, overlap area and contribution from `zone_breakdown`; resolve names through the matching display artifact.
- Present the three episode metrics with distinct labels/units and a whole-episode scope. Map filters or selected events should not silently relabel the saved totals as filtered totals.
- Make missing coverage visible through status/text and, if geometry becomes available, a map treatment. Excluded-zone reference shapes can help explain gaps, but are not a complete missing-area layer: footprints may also extend beyond all supplied zones. Exact missing geometry would require a new derived artifact/adapter; PEC currently returns only areas/fractions.
- Make dataset provenance and assumptions accessible: Census year, boundary vintage, version, source references, retrieval meaning, eligibility/exclusions, calculator/library versions, checksum and circle resolution. The result metadata lacks retrieval timestamps; obtain those from matching population provenance.

These are information needs, not a prescribed layout, palette, animation or component structure.

## 7. Scientific interpretation

The [population reports](population-data.md) describe Census 2020 residents (citizens and permanent residents) on Master Plan 2019 subzones. This is historical residential population, not live occupancy or everyone physically present. Density is uniform over supplied zone geometry, including any water; there is no independent land-only mask, movement or shelter model.

The inspected dataset has 332 display zones, 46 qualified unknown populations and 275 eligible zones containing 3,982,190 residents. There are 57 distinct exclusions; six invalid geometries and seven overlap pairs affecting 11 zones overlap with the unknown-count category. No repairs or imputation occur. Known display counts total 4,044,340, 130 above the published national total; no reconciliation adjustment is applied. A source dash is qualified unknown, not exact zero.

Footprints are supplied scenario inputs, **not predicted or validated hazard boundaries**. Everyone inside is counted equally. Exposure is not casualty, injury or fatality estimation. Optional `time_from_episode_start_s` is descriptive only; population stays fixed and whole-episode totals are neither simultaneous nor playback-time totals. A future timeline requires separately specified calculation semantics.

JSON retains fractional, unrounded values. Rounding for readability is reasonable, but numerical precision, reproducibility or higher circle resolution does not establish real-world population or hazard accuracy. Library versions are recorded; cross-platform bitwise equality is not promised.

## 8. Verification checklist and unresolved evidence

This is a checklist for integration, **not a record of completed frontend checks**. This handoff was checked against source, payloads and existing reports; no application tests or browser verification were rerun.

- [ ] Match episode/event/footprint IDs, centres/radii, dataset ID/version and calculation settings between input, result and map. Join zones by ID, never array position or name alone; reject mismatched references.
- [ ] Verify displayed polygon vertices correspond to the projected calculation polygon after transformation; check axis order, holes, multipart/offshore zones and 128/256 settings. Clipping, simplification, filtering and terrain changes must not redefine coverage.
- [ ] Exercise complete, partial and invalid results, absent files, empty episodes, zero radii and true zero population. Unknown values never display as zero; known-area values retain their labels.
- [ ] Check disjoint, overlapping, identical and triple-overlap footprints. Confirm all three totals and units; map selection/visibility must not silently change whole-episode scope.
- [ ] Exercise picking with population and event layers together, including overlapping events, multipart zones, hidden layers and layer removal. Confirm the selected IDs and details correspond.
- [ ] Switch among plain and configured remote basemaps, including failure/retry. Confirm footprints/population remain visible and pickable, custom ground surfaces restore correctly, and attribution remains visible.
- [ ] Verify foreground rendering/animation, planning-area filter/clear, offshore details and mobile layout in a real interactive browser.

**Recorded frontend limits:** the [14 September verification report](../../frontend/docs/POPULATION-VERIFICATION.md) records passing population tests/builds and observed controls, chart selection, search, layer visibility and missing-file retry. Safari automation reported a hidden document; temporary redraw diagnostics established polygon rendering, then were removed. Normal foreground animation, direct map hover/click, all multipart/offshore details, final direct basemap selection, successful Google rendering and mobile layout were **not browser-verified**. The planning-area selector had test coverage but its native dropdown was not reliably exercised. The large roughly 6.3 MB demo JavaScript chunk remains a build warning; there is no established performance budget. Historical codebase observations may predate fixes; the current source/report takes precedence.

**Recorded PEC coverage finding:** the [15 September investigation](pec-coverage-investigation.md), [comparison snapshot](pec-coverage-comparison.json) and [diagnostic figure](pec-coverage-diagnostic.png) reproduce `event-090` becoming partial at 256 edges: uncovered area rises from zero at 128 to approximately `0.011656080615 m²`, within excluded Bidadari (`TPSZ10`, qualified unknown population). This is a genuine supplied-geometry gap revealed by finer approximation, not a floating-point status bug. Its fraction `0.9999999983508352` would round to 100%. The whole benchmark episode is partial at every tested resolution.

The investigation reports 30 unit and three integration tests passing, including real-data checks; it did not test frontend integration. Production still supports only 128/256 edges. Diagnostic resolutions up to 16384 are not production settings or exact-circle proof. Neither supported resolution guarantees ideal-circle completeness; conservative boundary classification/refinement would need a separate specification. Source-boundary fidelity, historical counts, exclusions and reconciliation remain unresolved. Local [benchmark timings](pec-benchmark.md) are not end-to-end or real-time guarantees.

## Open integration questions

- Which initial result-loading workflow should the frontend offer, and how will matching population/provenance artifacts be distributed and versioned?
- Where should projected footprint construction and WGS84 conversion run, and should a future export include exact footprint and missing-area geometry?
- How should selection distinguish coincident events and overlapping population/event layers?
- Is resolution-labelled polygon coverage sufficient for the product, or is conservative ideal-circle classification a separate future requirement?
- If event editing or playback is added, who defines recalculation, time-dependent metric semantics and the eventual service contract?

The repository does not settle these decisions; frontend visual and interaction design remains with its owner.

## Explanation-record planning

The [explanation-record plan](pec-explanation-record.md) tracks unresolved demo questions, output forms, geometry needs, identity, persistence and performance decisions for a future deterministic adapter. The suggested experience above remains illustrative; no explanation feature or frontend integration is implemented.
