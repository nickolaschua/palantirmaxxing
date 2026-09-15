# Population Exposure Calculator v0.1

PEC is implemented as a standalone deterministic Python calculator for **people potentially exposed** within externally supplied circular footprints. It prepares a reusable eligible population dataset, validates an episode, and returns per-event and complete-episode results. It has no frontend connection, API service, database, footprint prediction, trajectory model, weapon model, optimisation, simulation, casualty model, or hazard validation.

## Interpretation and mathematics

Population remains fixed throughout an episode and is uniformly distributed within each eligible zone. Everyone within a footprint is counted equally. Optional event time does not change calculation, and complete-episode totals are not simultaneous exposure. Counts can remain fractional; there is no integer rounding in JSON.

All geometry uses declared EPSG:3414 easting/northing metre coordinates. Area is m² and density is people/m². No coordinate conversion, magnitude-based CRS inference, geometry repair, clipping of source zones, or population imputation occurs. Zero-population zones still extend known coverage; unknown and excluded zones do not.

For eligible zone Z with count N, density ρ = N / area(Z). For calculation footprint F, each zone contributes ρ × area(F ∩ Z). Sum those terms for known-area event exposure. Known population coverage C is the union of eligible zones. Missing event area is area(F \\ C); positive-area coverage fraction is area(F ∩ C) / area(F).

For episode union U = union(F), known unique exposure is Σ ρ × area(Z ∩ U). Known person-exposures are the sum of event exposures. Construct M as the union of Fᵢ ∩ Fⱼ over distinct event pairs i < j; known multiple-event exposure is Σ ρ × area(Z ∩ M). Triple overlap counts once in M. In particular, three identical events covering 100 people produce 100 unique, 300 person-exposures, and 100 multiple-event exposure. Subtracting unique from person-exposures is not the multiple-event formula.

Episode missing area is area(U \\ C), not the sum of event missing areas. Missing area above `1e-6 m²` makes that event/episode partial. Partial events retain known exposure and zone rows but have null complete exposure. A partial episode has all three complete totals null, even if some events are complete. A valid empty episode is complete with zero totals. Zero-radius footprints use empty geometry, are complete with zero exposure, and have undefined/null coverage fraction.

## Implementation and public interface

```python
from backend.exposure import prepare_population, calculate_episode, CalculationSettings

prepared = prepare_population(population_document)  # may raise PECValidationError
result = calculate_episode(prepared, episode_document, CalculationSettings(circle_edges=128))
```

Input documents are decoded Python dictionaries following the [contracts](../../contracts/pec.md). Preparation performs full validation, derives density, sorts zones, builds an STRtree, and computes coverage once. Reuse the prepared object across episodes; treat its contents as read-only. The calculator does not read files or acquire data. Settings permit 128 or 256 edges; the coverage tolerance is fixed in v0.1.

Circles use Shapely `Point.buffer(radius, quad_segs=edges//4)`. Positive-x starting vertices and clockwise order give consistently oriented, nested 128/256 approximations to numerical precision. The same polygon is used for footprint area, intersection, union, coverage and exposure. Zero radius is handled explicitly. No πr² area is mixed into the exposure arithmetic. STRtrees filter zone and event-pair candidates; repeated geometries reuse circle construction, but repeated events retain their full person-exposure contribution. Sorted events/zones and `math.fsum` stabilize output. Repeated runs in the same pinned environment produce byte-identical command output. Cross-platform GEOS bitwise equivalence is not promised; library versions are recorded.

The validator rejects invalid records before aggregation, including every positive-area zone overlap (zero tolerance), nonfinite or boolean numbers, invalid polygon geometry, incompatible CRS and inconsistent reused footprint IDs. Very large or tiny finite values may still make derived geometry unrepresentable; these return a numerical validation error. Invalid results never present partial aggregates as success. Detailed fields and error semantics are in the contract.

## Execution and tests

From repository root, use the existing environment and dependency pins:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/data_sources/requirements.txt
.venv/bin/python scripts/population_exposure.py \
  --population tests/fixtures/pec-population.json \
  --episode data/scenarios/pec-example.json \
  --output data/results/pec-example.json
.venv/bin/python -m unittest discover -s tests/unit -p 'test_*.py'
.venv/bin/python -m unittest discover -s tests/integration -p 'test_*.py'
.venv/bin/python scripts/benchmark_exposure.py
```

The example uses synthetic metre coordinates with two adjacent 200 m² zones containing 400 and 800 people. A radius-2 circle straddles their shared boundary equally; its exposure is 3 × its polygon area. A disjoint radius-1 circle in the eastern zone contributes 4 × its polygon area. Multiple-event exposure is zero. The example has complete coverage. Coordinates are intentionally synthetic and do not describe a real Singapore location. A checked-in result lives at `contracts/examples/pec-result.json`; local runtime results are ignored by Git.

For the actual dataset, supply `--population data/processed/population-projected.json` and an episode declaring ID `sg-residents-2020-mp2019` with the exact `metadata.dataset_version` from that file. The benchmark derives this identity directly and supplies 100 deterministic circles without network access. Missing local prepared artifacts must be supplied or produced by the existing population pipeline; PEC never falls back to the display dataset. Integration tests explicitly skip the real-data case if its ignored artifacts are absent; synthetic checks still run.

The file command strictly loads JSON, validates, calculates, and writes atomically with nonfinite serialization forbidden. It refuses to overwrite input paths, including aliases. Exit codes: 0 for complete or partial valid results; 2 for invalid inputs/arguments; 1 for file execution errors. Invalid input JSON is written as an error result when an output can be written. File I/O failures are printed to stderr and do not claim successful calculation. Timing is excluded from result JSON.

## Numerical settings and sensitivity

Coverage tolerance is absolute `1e-6 m²`, without a relative term; measured missing area is never erased. This tolerates only one square millimetre of area noise, including the explicit tiny-footprint edge case in the contract. Zone-overlap tolerance is zero. Coverage fraction roundoff may be clamped only within `1e-12` of [0,1]. Test assertions use approximately `1e-7` absolute exposure/area accuracy on small known-answer fixtures and `1e-9` for invariant noise; these do not change coverage rules.

A regular n-edge unit polygon has area n/2 × sin(2π/n), independently checked in tests. At 128 edges the ideal-circle area deficit is 0.040154685%; at 256 it is 0.010039578%. For uniform density and full coverage, 256-edge exposure increases about 0.030127% relative to 128. These percentages are not universal exposure-error bounds: boundary location and density variation matter. Coverage classifications can change near a boundary.

Measured real-data timings and sensitivity are in [PEC benchmark findings](pec-benchmark.md). Tests cover empty/zero events, known zero population, full/cross-zone coverage, uncovered areas, shared boundaries, invalid geometry/overlaps/numbers/identities/CRS/time, footprint reuse, disjoint/nested/identical/triple overlap, holes/multipolygons, event-order invariance, repeat runs, exposure inequalities, radius monotonicity, and approximation sensitivity. Integration tests cover file success/failure, strict JSON, output protection and the actual eligible population dataset.

## Dataset and model limitations

The inspected prepared version `sg-residents-2020-mp2019-cbb1c395f60918c1` contains 275 zones and 3,982,190 residents. Its 57 exclusions are omitted from WKT zones; their IDs/reasons remain in the validation report and full display properties. There are 46 qualified unknown counts, six invalid geometries and seven overlap pairs affecting 11 zones; these categories overlap. PEC preserves these exclusions without repairing geography or inventing counts.

The source describes historical Census 2020 residents, not all people physically present. Rounded known display counts exceed the published national total by 130; no reconciliation adjustment is applied. Uniform density uses all supplied zone area, including any water. Existing reports remain authoritative for preparation provenance and limitations. A locally complete footprint means complete coverage by the eligible subset within numerical tolerance; it does not certify full national coverage or a validated hazard prediction.

The [coverage-status investigation](pec-coverage-investigation.md) reproduces the event-090 boundary change, explains its excluded-zone geometry, records 64–1024-edge convergence and an event-only higher-resolution reference, and audits all 57 exclusions. Production defaults and tolerances remain unchanged.
