# Footprint assessment — version 1

`backend.orchestration.footprint_assessment.assess_footprints(prepared_population, request)` accepts a decoded JSON-compatible request and returns a JSON-compatible result. The caller prepares population once with `backend.exposure.prepare_population`. This adapter performs no file I/O, population acquisition, footprint prediction, action generation, policy filtering, ranking or selection. It adds no dependencies.

## Input contract: footprint-assessment-request/1

Required envelope properties:

| Property | Type / rule |
|---|---|
| `schema_version` | Exact string `footprint-assessment-request/1` |
| `assessment_id` | Nonempty string; whitespace-only invalid; no trimming/coercion |
| `mode` | Exact string `alternatives` or `episode`; mandatory, no default |
| `population_dataset_id` | Nonempty string matching prepared dataset ID |
| `population_dataset_version` | Nonempty string matching prepared dataset version |
| `coordinate_reference_system` | Exactly `EPSG:3414`, including case |
| `records` | Array of record objects; empty permitted |

Optional `geometry_settings` is an object allowing only `circle_edges`: integer 128 or 256. Omission or `{}` uses 128. Floating-point 128.0, booleans, null and other settings are invalid. PEC's fixed coverage tolerance is not configurable here.

Every record requires `record_id` (unique nonempty string) and `footprint`, an object requiring exactly `footprint_id` (nonempty string), `center_x_m`, `center_y_m`, `radius_m`. Coordinates are finite numbers in metres; radius is finite and nonnegative. Booleans are not numbers. Reused footprint IDs must have numerically identical centre/radius throughout the request, including alternatives. Different records may have identical geometry.

Only episode records may contain `time_from_episode_start_s`: finite nonnegative number. Omit unknown time; explicit null is invalid. Time remains descriptive, not a simulation input.

Only alternatives requests may contain `comparisons`, an array of objects requiring exactly `reference_record_id` and `comparison_record_id`. Both must identify distinct existing records. Duplicate ordered pairs are invalid; reverse pairs are distinct. Omission or `[]` requests no comparisons. Episode requests reject the property even if empty or null.

Unknown properties are rejected at every request object level, including arbitrary metadata. Population documents follow their existing PEC contract independently. The adapter receives decoded objects; strict rejection of duplicate JSON object keys is the responsibility of the caller's parser, as in the existing PEC file runner.

The checked-in runnable request is `tests/fixtures/footprint-assessment.json`, paired with `tests/fixtures/pec-population.json`.

## Validation and calculation failures

Structural validation runs before geometry. It enforces the adapter envelope, nested shapes and comparison rules, then delegates mapped event validation to `backend.exposure.validation.validate_episode`. This existing module-level helper is outside PEC's public exports; its reuse avoids duplicating PEC numeric and event validation. No cross-record geographic calculation occurs during validation.

A structurally invalid request returns request-level `invalid_input`. PEC numerical/geometry calculation failure also invalidates the whole request, discarding any already calculated records. Partial coverage is a valid calculation outcome. Validation may stop after a validation phase; it does not promise an exhaustive list of all errors in malformed input.

Invalid output contains `schema_version: footprint-assessment-result/1`, `status: invalid_input`, `errors`, and `diagnostics`. Valid assessment ID and mode are echoed when available. Each error has `code`, `field`, `message`, and optional `record_id`. It contains no records, comparisons, summaries, provenance or PEC result. Dataset preparation failures remain the caller's existing `PECValidationError`; callers must supply a valid prepared population object.

PEC error fields are translated back to adapter paths (`records[i].footprint.radius_m`, for example). Error paths reference submitted input positions; they need not remain identical when malformed inputs are reordered. Programmer errors are not silently recast as invalid input.

## Alternatives result

Required properties: `schema_version: footprint-assessment-result/1`, `assessment_id`, `mode: alternatives`, `status`, `records`, `comparisons`, `summary`, `provenance`, `diagnostics`.

Records are mutually exclusive hypothetical footprints. Each exposure result is equivalent to standalone PEC assessment. No union, unique exposure, person-exposure total or multiple-event exposure is calculated across alternatives, exposed, or used to obtain individual results. PEC call count is an implementation detail.

Each sorted output record contains:

- `record_id`.
- `exposure`: unchanged PEC event result, mapping record ID to event ID. Includes footprint ID/geometry, status, footprint area, covered fraction, uncovered area, people potentially exposed, known-area exposure and zone breakdown.
- `warnings`: empty for complete results; partial coverage produces `partial_population_coverage` with field, factual message and record ID.

Top-level status is `partial_coverage` if any record is partial; otherwise `complete`. Summary contains `number_records_supplied`, `number_complete`, `number_partial_coverage`, and `complete_exposure_range: {count, minimum, maximum}`. Only complete values contribute to the range. With no complete records its count is zero and bounds are null. This range is not a population total.

Empty alternatives produce complete status, empty records/comparisons, zero counts, null range bounds and full provenance. Metadata is obtained from PEC without retaining episode aggregates.

## Pairwise factual evidence

Each requested pair contains:

| Field | Meaning |
|---|---|
| `reference_record_id`, `comparison_record_id` | Requested ordered pair |
| `reference_coverage_status`, `comparison_coverage_status` | PEC event statuses |
| `coverage_comparable` | True exactly when both statuses are complete |
| `people_exposure_delta` | Comparison minus reference, using unrounded complete exposure; otherwise null |
| `people_exposure_ratio` | Comparison divided by reference, when complete and reference nonzero; otherwise null |
| `footprint_area_delta_m2` | Comparison minus reference PEC polygon area; available even for partial coverage |
| `reasons` | Stable structured explanations for unavailable values |

Reason objects contain `code`, `field`, `message`, and optional `record_id`. Partial coverage yields `reference_partial_coverage` and/or `comparison_partial_coverage`, in reference/comparison order. Exposure values are never compared to known-area subtotals. For complete records with zero reference exposure, delta remains available and ratio is null with `zero_reference_exposure`. This also applies when both exposures are zero.

Nonfinite derived arithmetic sets the affected field to null with `numeric_range_exceeded`, identifying the field. It does not change coverage comparability. Numeric checks are processed in area-delta, exposure-delta, ratio order. No NaN or Infinity is emitted. Identical complete positive-exposure footprints yield zero deltas and ratio one. No qualitative preference labels or recommendations are produced.

## Episode result

Required properties: `schema_version: footprint-assessment-result/1`, `assessment_id`, `mode: episode`, `status`, `pec_result`, `diagnostics`.

Map assessment ID to PEC episode ID and record ID to PEC event ID. `pec_result` is the unchanged existing `pec-result/1` returned by a normal PEC episode calculation, including all event results, unique people potentially exposed, total person-exposures, multiple-event exposure, known-area totals, coverage, errors where applicable to PEC, and metadata. Invalid PEC results are instead surfaced through the adapter invalid-output envelope described above. Top-level status mirrors PEC. No comparisons or alternative summary are added.

## Provenance, determinism and numerical semantics

Alternatives `provenance` preserves the entire PEC metadata object; episodes preserve it in `pec_result.metadata`. This includes dataset ID/version/checksum and checksum encoding, CRS, calculator version, library versions, input/output PEC schema versions, circle approximation, numerical tolerances and assumptions. These are PEC's schema identifiers and wording, not the adapter's. Footprint identifiers remain on each event result.

Valid records sort lexicographically by record ID; comparisons sort by `(reference_record_id, comparison_record_id)`. PEC retains its event/zone ordering. Valid evidence is identical under input reordering, excluding latency. Retain unrounded numbers and serialize with `allow_nan=False`; presentation rounding is outside this adapter.

PEC circles use inscribed polygons; area is polygon area, not ideal pi*r². Default resolution is 128 edges, optional 256. Coverage status follows PEC's fixed 1e-6 m² uncovered-area tolerance, including tiny positive uncovered footprints classified complete below this tolerance. Zero-radius footprints are complete with zero exposure and null covered fraction. The adapter does not change these semantics.

Population is fixed and uniform within supplied zones. Footprint geometry is a supplied assumption. Results describe people potentially exposed geographically; physical hazard validity is not established.

`diagnostics.evaluation_latency_ms` uses `perf_counter_ns`, spanning adapter validation, PEC calculation and result packaging. It excludes population preparation, external serialization and file I/O. PEC internally calls `json.dumps` for validity checking; its cost necessarily remains included.

## Reproduce the engineering benchmark

Run from the repository root. No output files are created. The same prepared synthetic population is reused for both sizes. Distinct fixed circles lie within coverage; requested comparisons use the first record as reference. There is one warm-up and seven measured runs per size. Profiling is separate from reported timing.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import copy, cProfile, json, platform, pstats, statistics, sys
from pathlib import Path
from time import perf_counter_ns
import shapely, pyproj
from backend.exposure import prepare_population
from backend.orchestration.footprint_assessment import assess_footprints

population = prepare_population(json.loads(Path('tests/fixtures/pec-population.json').read_text()))
base = json.loads(Path('tests/fixtures/footprint-assessment.json').read_text())
print(dict(python=sys.version.split()[0], platform=platform.platform(),
           shapely=shapely.__version__, geos=shapely.geos_version_string, pyproj=pyproj.__version__))
for count in (5, 100):
    request = copy.deepcopy(base)
    request['records'] = [dict(record_id=f'R{i:03}', footprint=dict(
        footprint_id=f'F{i:03}', center_x_m=-8+16*i/(count-1), center_y_m=0, radius_m=1))
        for i in range(count)]
    request['comparisons'] = [dict(reference_record_id='R000', comparison_record_id=f'R{i:03}')
                              for i in range(1, count)]
    assess_footprints(population, request)
    times = []
    for _ in range(7):
        start = perf_counter_ns()
        result = assess_footprints(population, request)
        times.append((perf_counter_ns()-start)/1e6)
        assert result['status'] == 'complete'
    print(dict(records=count, comparisons=count-1, circle_edges=128, measured_ms=times,
               median_ms=statistics.median(times), minimum_ms=min(times), maximum_ms=max(times)))
profiler = cProfile.Profile()
profiler.runcall(assess_footprints, population, request)
pstats.Stats(profiler).sort_stats('cumulative').print_stats(18)
PY
```

Seven runs are a small engineering benchmark, not a statistically rigorous performance characterization. Runtime depends on zone geometry, record locations, circle resolution and requested comparisons; this benchmark is not a real-time guarantee.

## Measured implementation benchmark

Measured on Python 3.9.6, macOS 26.5.1 ARM64, Shapely 2.0.7 / GEOS 3.11.4, pyproj 3.6.1. Both batches used 128 edges and the method above.

| Records | Comparisons | Seven measured times (ms) | Median | Minimum | Maximum |
|---|---|---|---|---|---|
| 5 | 4 | 3.233375, 3.124833, 3.460333, 3.129709, 3.110125, 3.484291, 3.208916 | 3.208916 | 3.110125 | 3.484291 |
| 100 | 99 | 55.069416, 55.094125, 55.244959, 54.899542, 54.834750, 55.720583, 54.899875 | 55.069416 | 54.834750 | 55.720583 |

A separate cProfile run took approximately 60 ms. Repeated PEC CRS validation dominated: 101 CRS checks made 202 CRS constructions, with about 34 ms in CRS construction and 36 ms cumulative in `compatible_crs`. Shapely wrappers accounted for about 14 ms cumulative. The adapter validation and comparison work did not dominate. These nested profiling figures must not be summed. PEC is unchanged; no caching or batching optimization was introduced.

## Executed examples

The following are full requests and results from the implementation. Diagnostics are illustrative measured values and vary between runs; all remaining evidence is deterministic in the recorded environment.

### Complete-coverage alternatives

Request:

```json
{
  "schema_version": "footprint-assessment-request/1",
  "assessment_id": "synthetic-footprints",
  "mode": "alternatives",
  "population_dataset_id": "pec-example-population",
  "population_dataset_version": "1",
  "coordinate_reference_system": "EPSG:3414",
  "geometry_settings": {
    "circle_edges": 128
  },
  "records": [
    {
      "record_id": "A",
      "footprint": {
        "footprint_id": "footprint-A",
        "center_x_m": -5,
        "center_y_m": 0,
        "radius_m": 1
      }
    },
    {
      "record_id": "B",
      "footprint": {
        "footprint_id": "footprint-B",
        "center_x_m": 5,
        "center_y_m": 0,
        "radius_m": 1
      }
    }
  ],
  "comparisons": [
    {
      "reference_record_id": "A",
      "comparison_record_id": "B"
    }
  ]
}
```

Result:

```json
{
  "schema_version": "footprint-assessment-result/1",
  "assessment_id": "synthetic-footprints",
  "mode": "alternatives",
  "status": "complete",
  "records": [
    {
      "record_id": "A",
      "exposure": {
        "event_id": "A",
        "footprint_id": "footprint-A",
        "center_x_m": -5,
        "center_y_m": 0,
        "radius_m": 1,
        "status": "complete",
        "footprint_area_m2": 3.140331156954754,
        "uncovered_area_m2": 0.0,
        "covered_area_fraction": 0.9999999999999997,
        "people_potentially_exposed": 6.280662313909506,
        "known_area_exposure": 6.280662313909506,
        "zone_breakdown": [
          {
            "zone_id": "west",
            "zone_population": 400,
            "zone_density_people_per_m2": 2.0,
            "overlap_area_m2": 3.140331156954753,
            "estimated_people_exposed": 6.280662313909506
          }
        ]
      },
      "warnings": []
    },
    {
      "record_id": "B",
      "exposure": {
        "event_id": "B",
        "footprint_id": "footprint-B",
        "center_x_m": 5,
        "center_y_m": 0,
        "radius_m": 1,
        "status": "complete",
        "footprint_area_m2": 3.140331156954754,
        "uncovered_area_m2": 0.0,
        "covered_area_fraction": 0.9999999999999997,
        "people_potentially_exposed": 12.561324627819012,
        "known_area_exposure": 12.561324627819012,
        "zone_breakdown": [
          {
            "zone_id": "east",
            "zone_population": 800,
            "zone_density_people_per_m2": 4.0,
            "overlap_area_m2": 3.140331156954753,
            "estimated_people_exposed": 12.561324627819012
          }
        ]
      },
      "warnings": []
    }
  ],
  "comparisons": [
    {
      "reference_record_id": "A",
      "comparison_record_id": "B",
      "reference_coverage_status": "complete",
      "comparison_coverage_status": "complete",
      "coverage_comparable": true,
      "people_exposure_delta": 6.280662313909506,
      "people_exposure_ratio": 2.0,
      "footprint_area_delta_m2": 0.0,
      "reasons": []
    }
  ],
  "summary": {
    "number_records_supplied": 2,
    "number_complete": 2,
    "number_partial_coverage": 0,
    "complete_exposure_range": {
      "count": 2,
      "minimum": 6.280662313909506,
      "maximum": 12.561324627819012
    }
  },
  "provenance": {
    "input_schema_versions": {
      "population": "pec-population/1",
      "episode": "pec-episode/1"
    },
    "output_schema_version": "pec-result/1",
    "population_dataset_id": "pec-example-population",
    "population_dataset_version": "1",
    "dataset_checksum_sha256": "6638c2ec33825294cd4a08d5554ced16a505a36528467e79e6a72dcc3c7cde20",
    "checksum_encoding": "UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False, entire input envelope",
    "coordinate_reference_system": "EPSG:3414",
    "calculator_version": "0.1.0",
    "libraries": {
      "shapely": "2.0.7",
      "geos": "3.11.4",
      "pyproj": "3.6.1"
    },
    "circle_approximation": {
      "method": "inscribed regular polygon; clockwise from positive x axis",
      "edges": 128,
      "quad_segs": 32
    },
    "numerical_tolerances": {
      "coverage_area_m2": 1e-06,
      "population_overlap_area_m2": 0,
      "coverage_fraction_clamp": 1e-12
    },
    "assumptions": [
      "Population is fixed throughout the episode and uniformly distributed within each eligible zone.",
      "Supplied circles are scenario inputs, not predictions; everyone within a footprint is counted equally.",
      "Episode totals describe the complete episode, not simultaneous exposure; time is descriptive only.",
      "No injury, casualty, shelter, movement, uncertainty, or hazard-validity modelling.",
      "Unknown and excluded population zones do not extend known population coverage."
    ]
  },
  "diagnostics": {
    "evaluation_latency_ms": 3.061625
  }
}
```

### Partial-coverage alternatives comparison

Request:

```json
{
  "schema_version": "footprint-assessment-request/1",
  "assessment_id": "synthetic-partial",
  "mode": "alternatives",
  "population_dataset_id": "pec-example-population",
  "population_dataset_version": "1",
  "coordinate_reference_system": "EPSG:3414",
  "geometry_settings": {
    "circle_edges": 128
  },
  "records": [
    {
      "record_id": "A",
      "footprint": {
        "footprint_id": "footprint-A",
        "center_x_m": -5,
        "center_y_m": 0,
        "radius_m": 1
      }
    },
    {
      "record_id": "B",
      "footprint": {
        "footprint_id": "footprint-B",
        "center_x_m": 10,
        "center_y_m": 0,
        "radius_m": 1
      }
    }
  ],
  "comparisons": [
    {
      "reference_record_id": "A",
      "comparison_record_id": "B"
    }
  ]
}
```

Result:

```json
{
  "schema_version": "footprint-assessment-result/1",
  "assessment_id": "synthetic-partial",
  "mode": "alternatives",
  "status": "partial_coverage",
  "records": [
    {
      "record_id": "A",
      "exposure": {
        "event_id": "A",
        "footprint_id": "footprint-A",
        "center_x_m": -5,
        "center_y_m": 0,
        "radius_m": 1,
        "status": "complete",
        "footprint_area_m2": 3.140331156954754,
        "uncovered_area_m2": 0.0,
        "covered_area_fraction": 0.9999999999999997,
        "people_potentially_exposed": 6.280662313909506,
        "known_area_exposure": 6.280662313909506,
        "zone_breakdown": [
          {
            "zone_id": "west",
            "zone_population": 400,
            "zone_density_people_per_m2": 2.0,
            "overlap_area_m2": 3.140331156954753,
            "estimated_people_exposed": 6.280662313909506
          }
        ]
      },
      "warnings": []
    },
    {
      "record_id": "B",
      "exposure": {
        "event_id": "B",
        "footprint_id": "footprint-B",
        "center_x_m": 10,
        "center_y_m": 0,
        "radius_m": 1,
        "status": "partial_coverage",
        "footprint_area_m2": 3.140331156954753,
        "uncovered_area_m2": 1.5701655784773758,
        "covered_area_fraction": 0.4999999999999998,
        "people_potentially_exposed": null,
        "known_area_exposure": 6.280662313909503,
        "zone_breakdown": [
          {
            "zone_id": "east",
            "zone_population": 800,
            "zone_density_people_per_m2": 4.0,
            "overlap_area_m2": 1.5701655784773758,
            "estimated_people_exposed": 6.280662313909503
          }
        ]
      },
      "warnings": [
        {
          "code": "partial_population_coverage",
          "field": "exposure.people_potentially_exposed",
          "message": "Known-area exposure is a subtotal; complete exposure is unavailable.",
          "record_id": "B"
        }
      ]
    }
  ],
  "comparisons": [
    {
      "reference_record_id": "A",
      "comparison_record_id": "B",
      "reference_coverage_status": "complete",
      "comparison_coverage_status": "partial_coverage",
      "coverage_comparable": false,
      "people_exposure_delta": null,
      "people_exposure_ratio": null,
      "footprint_area_delta_m2": -8.881784197001252e-16,
      "reasons": [
        {
          "code": "comparison_partial_coverage",
          "field": "comparison_record_id",
          "message": "Complete exposure is unavailable because population coverage is partial.",
          "record_id": "B"
        }
      ]
    }
  ],
  "summary": {
    "number_records_supplied": 2,
    "number_complete": 1,
    "number_partial_coverage": 1,
    "complete_exposure_range": {
      "count": 1,
      "minimum": 6.280662313909506,
      "maximum": 6.280662313909506
    }
  },
  "provenance": {
    "input_schema_versions": {
      "population": "pec-population/1",
      "episode": "pec-episode/1"
    },
    "output_schema_version": "pec-result/1",
    "population_dataset_id": "pec-example-population",
    "population_dataset_version": "1",
    "dataset_checksum_sha256": "6638c2ec33825294cd4a08d5554ced16a505a36528467e79e6a72dcc3c7cde20",
    "checksum_encoding": "UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False, entire input envelope",
    "coordinate_reference_system": "EPSG:3414",
    "calculator_version": "0.1.0",
    "libraries": {
      "shapely": "2.0.7",
      "geos": "3.11.4",
      "pyproj": "3.6.1"
    },
    "circle_approximation": {
      "method": "inscribed regular polygon; clockwise from positive x axis",
      "edges": 128,
      "quad_segs": 32
    },
    "numerical_tolerances": {
      "coverage_area_m2": 1e-06,
      "population_overlap_area_m2": 0,
      "coverage_fraction_clamp": 1e-12
    },
    "assumptions": [
      "Population is fixed throughout the episode and uniformly distributed within each eligible zone.",
      "Supplied circles are scenario inputs, not predictions; everyone within a footprint is counted equally.",
      "Episode totals describe the complete episode, not simultaneous exposure; time is descriptive only.",
      "No injury, casualty, shelter, movement, uncertainty, or hazard-validity modelling.",
      "Unknown and excluded population zones do not extend known population coverage."
    ]
  },
  "diagnostics": {
    "evaluation_latency_ms": 2.989459
  }
}
```

### Episode

Request:

```json
{
  "schema_version": "footprint-assessment-request/1",
  "assessment_id": "synthetic-episode",
  "mode": "episode",
  "population_dataset_id": "pec-example-population",
  "population_dataset_version": "1",
  "coordinate_reference_system": "EPSG:3414",
  "geometry_settings": {
    "circle_edges": 128
  },
  "records": [
    {
      "record_id": "A",
      "footprint": {
        "footprint_id": "footprint-A",
        "center_x_m": -5,
        "center_y_m": 0,
        "radius_m": 1
      },
      "time_from_episode_start_s": 0
    },
    {
      "record_id": "B",
      "footprint": {
        "footprint_id": "footprint-B",
        "center_x_m": 5,
        "center_y_m": 0,
        "radius_m": 1
      },
      "time_from_episode_start_s": 1
    }
  ]
}
```

Result:

```json
{
  "schema_version": "footprint-assessment-result/1",
  "assessment_id": "synthetic-episode",
  "mode": "episode",
  "status": "complete",
  "pec_result": {
    "schema_version": "pec-result/1",
    "episode_id": "synthetic-episode",
    "status": "complete",
    "events": [
      {
        "event_id": "A",
        "footprint_id": "footprint-A",
        "center_x_m": -5,
        "center_y_m": 0,
        "radius_m": 1,
        "time_from_episode_start_s": 0,
        "status": "complete",
        "footprint_area_m2": 3.140331156954754,
        "uncovered_area_m2": 0.0,
        "covered_area_fraction": 0.9999999999999997,
        "people_potentially_exposed": 6.280662313909506,
        "known_area_exposure": 6.280662313909506,
        "zone_breakdown": [
          {
            "zone_id": "west",
            "zone_population": 400,
            "zone_density_people_per_m2": 2.0,
            "overlap_area_m2": 3.140331156954753,
            "estimated_people_exposed": 6.280662313909506
          }
        ]
      },
      {
        "event_id": "B",
        "footprint_id": "footprint-B",
        "center_x_m": 5,
        "center_y_m": 0,
        "radius_m": 1,
        "time_from_episode_start_s": 1,
        "status": "complete",
        "footprint_area_m2": 3.140331156954754,
        "uncovered_area_m2": 0.0,
        "covered_area_fraction": 0.9999999999999997,
        "people_potentially_exposed": 12.561324627819012,
        "known_area_exposure": 12.561324627819012,
        "zone_breakdown": [
          {
            "zone_id": "east",
            "zone_population": 800,
            "zone_density_people_per_m2": 4.0,
            "overlap_area_m2": 3.140331156954753,
            "estimated_people_exposed": 12.561324627819012
          }
        ]
      }
    ],
    "unique_people_potentially_exposed": 18.841986941728532,
    "total_person_exposures": 18.841986941728518,
    "people_exposed_to_multiple_events": 0.0,
    "known_area_unique_exposure": 18.841986941728532,
    "known_area_person_exposures": 18.841986941728518,
    "known_area_multiple_exposure": 0.0,
    "uncovered_area_m2": 0.0,
    "metadata": {
      "input_schema_versions": {
        "population": "pec-population/1",
        "episode": "pec-episode/1"
      },
      "output_schema_version": "pec-result/1",
      "population_dataset_id": "pec-example-population",
      "population_dataset_version": "1",
      "dataset_checksum_sha256": "6638c2ec33825294cd4a08d5554ced16a505a36528467e79e6a72dcc3c7cde20",
      "checksum_encoding": "UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False, entire input envelope",
      "coordinate_reference_system": "EPSG:3414",
      "calculator_version": "0.1.0",
      "libraries": {
        "shapely": "2.0.7",
        "geos": "3.11.4",
        "pyproj": "3.6.1"
      },
      "circle_approximation": {
        "method": "inscribed regular polygon; clockwise from positive x axis",
        "edges": 128,
        "quad_segs": 32
      },
      "numerical_tolerances": {
        "coverage_area_m2": 1e-06,
        "population_overlap_area_m2": 0,
        "coverage_fraction_clamp": 1e-12
      },
      "assumptions": [
        "Population is fixed throughout the episode and uniformly distributed within each eligible zone.",
        "Supplied circles are scenario inputs, not predictions; everyone within a footprint is counted equally.",
        "Episode totals describe the complete episode, not simultaneous exposure; time is descriptive only.",
        "No injury, casualty, shelter, movement, uncertainty, or hazard-validity modelling.",
        "Unknown and excluded population zones do not extend known population coverage."
      ]
    }
  },
  "diagnostics": {
    "evaluation_latency_ms": 1.75025
  }
}
```
