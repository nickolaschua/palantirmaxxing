# PEC contracts — version 1

Implemented by `backend/exposure/` and `scripts/population_exposure.py`. All JSON numbers must be finite; booleans are not numbers. Identifiers are nonempty strings, compared exactly (no trimming or coercion). Additional object properties are ignored unless explicitly checked below. JSON files reject duplicate object keys and nonstandard NaN/Infinity constants. No coordinate conversion occurs.

## Population inputs

Canonical envelope (`schema_version: "pec-population/1"`):

| Required field | Meaning |
|---|---|
| `dataset_id`, `version` | Nonempty strings identifying the supplied eligible population dataset |
| `coordinate_reference_system` | String declaring EPSG:3414 or a pyproj-equivalent CRS; projected, two metre axes |
| `zones` | Array, possibly empty, of zone objects |

Each zone requires unique `zone_id`, finite nonnegative `population` (people), and `geometry`: an object with `type: "Polygon"` or `"MultiPolygon"` and nested `coordinates` arrays. This is projected geometry inside a custom envelope, **not RFC 7946 geographic GeoJSON**. Positions are exactly `[easting, northing]` in metres. Rings must be explicitly closed and contain at least four positions. Geometry must be nonempty, valid and positive-area. Holes and disconnected multipolygons are supported. No zone interiors may overlap, even by a positive-area sliver; shared boundaries are allowed. An optional `pec_eligible` must be true; nonempty `exclusion_reasons` are rejected. Area and density are derived, never trusted from supplied convenience fields.

The existing [population-zones-wkt/1 contract](population-dataset.md) is also accepted directly. Its adapter defines the logical `dataset_id` as **`sg-residents-2020-mp2019`**, maps `metadata.dataset_version` to `version` and `crs` to `coordinate_reference_system`, and reads authoritative `geometry_wkt`. Its `units` must be `metre` and `axis_order` must be `["easting", "northing"]`. Every zone must have matching `dataset_version`, `pec_eligible: true`, `exclusion_reasons: []`, `population_status` of `known` or `known_zero`, `geometry_status: "valid"`, and `join_status: "matched"`. PEC validates the prepared subset again; it never selects a replacement dataset or modifies eligibility. The full display artifact is unsupported.

The SHA-256 in results hashes the entire accepted input envelope, encoded as UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=False`, and no trailing newline. This is a normalized-envelope checksum, not the on-disk file checksum. Whitespace-only changes do not affect it; provenance/metadata content changes do. The existing source-derived dataset version remains independently recorded.

## Episode input

Required envelope: `schema_version: "pec-episode/1"`, `episode_id`, `population_dataset_id`, `population_dataset_version`, `coordinate_reference_system`, and `events` array. Dataset identity/version must match preparation. CRS follows the population rules; coordinates are easting/northing metres, without CRS inference.

Each event requires `event_id` (unique within the episode), `footprint_id`, finite `center_x_m`, finite `center_y_m`, and finite nonnegative `radius_m`. Optional `time_from_episode_start_s` must be finite and nonnegative; null is invalid when supplied. Time is descriptive only. Repeated geometry is permitted. Reusing a footprint ID requires exactly equal centre/radius values; different footprint IDs can describe identical circles. Input order does not change results. There is no hard 100-event limit; v0.1 is intended and measured for approximately 100 events.

See [runnable episode](../data/scenarios/pec-example.json) and its [population fixture](../tests/fixtures/pec-population.json).

## Valid calculation output

The result has `schema_version: "pec-result/1"`, `episode_id`, `status` (`complete` or `partial_coverage`), `events`, the totals below, `uncovered_area_m2`, and `metadata`.

| Episode field | Meaning |
|---|---|
| `unique_people_potentially_exposed` | People in the event union; null for partial episode coverage |
| `total_person_exposures` | Sum over events; null for partial episode coverage |
| `people_exposed_to_multiple_events` | People in at least two distinct events; null for partial episode coverage |
| `known_area_unique_exposure` | Union exposure within eligible population coverage |
| `known_area_person_exposures` | Sum of known-area event exposures |
| `known_area_multiple_exposure` | At-least-two-event exposure within eligible coverage |
| `uncovered_area_m2` | Area of the episode union outside eligible coverage |

Each event result contains supplied `event_id`, `footprint_id`, `center_x_m`, `center_y_m`, `radius_m`, optional supplied `time_from_episode_start_s`, `status`, `footprint_area_m2`, `uncovered_area_m2`, `covered_area_fraction`, `people_potentially_exposed`, `known_area_exposure`, and `zone_breakdown`. `people_potentially_exposed` is null for partial event coverage. `covered_area_fraction` is null only for zero-area footprints. `footprint_area_m2` is the approximating polygon's area, not ideal πr².

`zone_breakdown` contains zones with positive overlap, including known zero-population zones. Each row has `zone_id`, `zone_population`, `zone_density_people_per_m2`, `overlap_area_m2`, and `estimated_people_exposed`. Boundary-only touches produce no row. Events and zones are sorted by their identifiers. Numbers are unrounded calculation values.

Metadata contains `input_schema_versions` (population and episode), `output_schema_version`, `population_dataset_id`, `population_dataset_version`, `dataset_checksum_sha256`, `checksum_encoding`, `coordinate_reference_system`, `calculator_version`, `libraries` (Shapely, GEOS, pyproj), `circle_approximation` (method, edges, quad_segs), `numerical_tolerances`, and `assumptions`. No timestamps, durations, local paths, or retrieval-time fields are copied into deterministic results. A separate benchmark report contains timings.

A valid empty episode is complete with empty events and zero totals. A zero-radius event is complete even outside coverage, with zero area/exposure, no contributing zones, and null coverage fraction. Entirely uncovered positive-area footprints have zero known exposure and normally partial coverage, subject to the explicit absolute numerical tolerance below.

## Invalid-input output

Population preparation raises `PECValidationError(errors)` in Python; the file command converts it to the same error result used for invalid episodes:

```json
{
  "schema_version": "pec-result/1",
  "episode_id": "example",
  "status": "invalid_input",
  "errors": [{
    "code": "invalid_number",
    "record_type": "event",
    "record_id": "event-1",
    "field": "events[0].radius_m",
    "message": "Expected finite number in permitted range; booleans forbidden"
  }]
}
```

`episode_id` and `record_id` are omitted if unavailable or invalid. `record_type` is `population`, `zone`, `episode`, or `event`; `field` identifies an input path (or the aggregate operation for numerical failures). Codes include `invalid_type`, `invalid_identifier`, `duplicate_identifier`, `invalid_number`, `invalid_geometry`, `ineligible_zone`, `overlapping_zones`, `unsupported_schema`, `incompatible_crs`, `incompatible_coordinates`, `dataset_mismatch`, `inconsistent_footprint`, `invalid_json`, `invalid_population`, `numerical_range`, and `numerical_calculation`. Human messages provide context; consumers should branch on codes. Invalid results contain no event calculations, aggregates, or success metadata. Population failure prevents calculation, and any invalid event prevents all episode aggregation.

## Numerical policy

128 edges by default, optionally 256; Shapely buffer uses 32 or 64 segments per quadrant. Coverage is partial when measured missing area is **greater than 0.000001 m²**, with no relative tolerance. Measured area is retained even below that threshold. Thus tiny positive footprints wholly outside coverage can be classified complete only when their whole area is below that explicit noise threshold. Zone-overlap tolerance is zero. A coverage ratio excursion within `1e-12` of [0,1] may be clamped; larger excursions invalidate calculation. Geometry is never repaired or snapped. Unrepresentable derived geometry/areas/exposures invalidate the calculation instead of producing NaN or Infinity.

See [PEC specification](../docs/specifications/pec.md) for mathematics, measured sensitivity, execution and limitations, and [example output](examples/pec-result.json).
