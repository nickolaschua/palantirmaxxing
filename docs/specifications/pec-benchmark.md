# PEC benchmark findings

Measured 2026-09-14 with `scripts/benchmark_exposure.py`; no network or source regeneration. Timing is separate from deterministic calculation JSON. This is a local scenario measurement, not a real-time performance guarantee.

## Dataset and environment

- Dataset: `sg-residents-2020-mp2019`, version `sg-residents-2020-mp2019-cbb1c395f60918c1`.
- Normalized input-envelope SHA-256: `4fa83ffefec87ddeb85e77d9b77d41fd8aea6beb9068eaaf926e9e79352054c4`.
- 275 eligible zones; 3,982,190 residents; 100 supplied circles.
- Python 3.9.6; macOS-26.5.1-arm64-arm-64bit; processor `arm`.
- Shapely 2.0.7, GEOS 3.11.4, pyproj 3.6.1; existing pinned environment.

Scenario: sort eligible zones by ID, select zone index floor(i × zone_count / 100) for i = 0…99, and use its representative point. Radii cycle through 250, 750, 1500 and 2500 metres. This creates overlapping and boundary-crossing footprints. It is a numerical workload, not a footprint-prediction model. Input generation and file I/O are excluded from timing.

## Runtime

| Operation | Run 1 (s) | Run 2 (s) | Run 3 (s) | Median (s) |
|---|---:|---:|---:|---:|
| Dataset validation, geometry/index/coverage/checksum | 0.123590 | 0.093396 | 0.093422 | 0.093422 |
| 100 events, 128 edges | 0.161569 | 0.154115 | 0.153977 | 0.154115 |
| 100 events, 256 edges | 0.209419 | 0.203964 | 0.201957 | 0.203964 |

Each preparation and each resolution is measured three times in one process with `time.perf_counter`. Prepared geometry is reused during calculation measurements. The benchmark also checks exact repeat-result equality within each resolution. No distributed processing, workers, or incremental state are used.

## Circle approximation sensitivity

Both episode results are `partial_coverage`; all complete episode exposure totals remain null. Values below are known-area exposures and union missing area. Displayed values are rounded only in this report.

| Quantity | 128 edges | 256 edges | Increase | Relative increase |
|---|---:|---:|---:|---:|
| `known_area_multiple_exposure` | 1852697.710434 | 1853324.461541 | 626.751107 | 0.033829% |
| `known_area_person_exposures` | 6606352.867766 | 6608112.877215 | 1760.009450 | 0.026641% |
| `known_area_unique_exposure` | 3391618.301752 | 3391906.001199 | 287.699448 | 0.008483% |
| `uncovered_area_m2` | 89468378.605519 | 89501828.213443 | 33449.607924 | 0.037387% |

Per-event known exposure increased between 0.000016578 and 97.596535733 people potentially exposed. One event, `event-090`, changed from complete at 128 edges (zero uncovered area) to partial at 256 edges (0.011656080615 m² uncovered). This exceeds the fixed 0.000001 m² tolerance; it is not clamped away.

The independent synthetic unit-circle formula gives polygon areas 3.140331156954753 at 128 edges and 3.141277250932773 at 256. Relative to ideal πr², deficits are approximately 0.040154685% and 0.010039578%. In constant density with full coverage, exposure increases approximately 0.030127% between these resolutions. Nested/oriented geometry and increasing-radius exposure are verified in tests. These results do not establish an error bound for every footprint: local population density and coverage boundaries can amplify or change the practical effect.

## Reproduce

```sh
.venv/bin/python scripts/benchmark_exposure.py
```

The command uses the local `data/processed/population-projected.json` and writes `data/results/pec-benchmark.json`. If that ignored artifact is unavailable, obtain the existing prepared output or run the documented population pipeline using verified cached sources. Do not replace it with the full display dataset. Environment and geometry-library changes may alter timings and floating-point results; the report records identity and versions.

Current population limitations remain: 57 excluded zones (including 46 qualified unknown counts and geometry exclusions), historical Census 2020 residents, uniform density over supplied geometry, and unadjusted reconciliation differences. See the [PEC specification](pec.md) and original population validation report.

The [coverage-status investigation](pec-coverage-investigation.md) reproduces the event-090 boundary change, explains its excluded-zone geometry, records 64–1024-edge convergence and an event-only higher-resolution reference, and audits all 57 exclusions. Production defaults and tolerances remain unchanged.
