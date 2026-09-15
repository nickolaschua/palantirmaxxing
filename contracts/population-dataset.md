# Population dataset contract — version 1

This milestone produces files, not an API. Preparation is implemented in `backend/data_sources/`; the browser consumes only the prepared geographic artifact. The standalone [PEC contracts](pec.md) define a compatible adapter for the eligible projected output; this preparation format is unchanged.

## Artifacts

| File | Format and consumers |
|---|---|
| `data/processed/population-display.geojson` | RFC 7946 FeatureCollection, full-resolution source geometry in WGS84 `[longitude, latitude]` degrees. All 332 zones, including unknown population and invalid geometry flagged in properties. Display/reference only. |
| `frontend/public/population.geojson` | Byte-identical copy of the display artifact, served by Vite. Never independently joined in the browser. |
| `data/processed/population-projected.json` | Custom `population-zones-wkt/1` JSON envelope, **not GeoJSON**. `crs: EPSG:3414`, `axis_order: [easting, northing]`, `units: metre`; each eligible zone has `geometry_wkt` (Polygon/MultiPolygon WKT). |
| `data/processed/validation-report.json` | Counts, all aggregate source rows, bidirectional join findings, exclusions, geometry/overlap findings and reconciliation. |
| `data/processed/provenance.json` | Dataset version, source references/checksums, source/retrieval dates, transformation/settings and software versions. |
| `data/processed/validation-summary.md` | Generated readable validation findings, including every planning-area reconciliation. |

Both dataset envelopes carry `metadata`: population year 2020, boundary vintage 2019, dataset version, source references, acquisition time and meaning, settings, library versions and partial-coverage counts/totals. A dataset version hashes source checksums, transformation version, settings and geometry-library versions. Retrieval/runtime timestamps do not define substantive identity.

## Zone properties

- `zone_id`: URA `SUBZONE_C`, stable within MP2019; do not assume stability across boundary vintages. Display feature `id` equals this code.
- `planning_area_code`: URA `PLN_AREA_C`. `planning_area` and `subzone` retain original boundary names; corresponding `*_normalised` names support auditing.
- `population_planning_area_original`, `population_subzone_original`, `population_source_row`: original population labels and 1-based ordered source row.
- `population`: non-negative integer people or `null`; `population_raw` preserves the original value. No unknown value is coerced to zero.
- `population_status`: `known`, `known_zero`, `qualified_nil_or_negligible`, `missing`, `not_available_or_applicable`, `qualified_uninterpreted`, `invalid`, `unmatched` or `ambiguous`. Only the first two qualify as known counts. The inspected full dataset uses `known` and `qualified_nil_or_negligible`.
- `join_status`: `matched`, `unmatched`, or `ambiguous`. Duplicate composite names/IDs make involved joins ambiguous, never first-match-wins.
- `geometry_status`: `valid` or `invalid`; `zone_area_m2` is positive supplied-zone area in square metres, or `null` for invalid geometry. `population_density_people_per_m2` is population divided by that area, or `null` if population/valid area is unavailable. Frontend converts the density unit by multiplying by 1,000,000.
- `pec_eligible`, `exclusion_reasons`: eligibility in the candidate subset only. Every invalid geometry, unknown population, ambiguous/unmatched join and participant in any positive-area overlap is excluded. The whole dataset is **not PEC-ready**.
- `outside_viewer_bounds`: whether any geometry extends outside the existing rectangular camera bounds. This is independent of coastline/tileset clipping.
- `source_references`: population/boundary dataset IDs and original boundary OBJECTID; source URLs and SHA-256 values are in metadata.
- `dataset_version`: identical to the envelope version, to prevent accidental mixing.

Projected zones contain the same properties, with known population, positive area and valid, non-overlapping projected WKT. Shared zero-area boundaries are allowed. Invalid and unknown zones remain in display/reference data but never extend known-population coverage. Source geometry is not repaired, simplified or clipped.

UI colors, filtering, chart ranking and pinned/hover state are presentation choices, not additional population measures. See [interpretation and processing specification](../docs/specifications/population-data.md).
