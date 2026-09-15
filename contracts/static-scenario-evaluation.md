# Static scenario evaluation — machine-side MVP

Implemented by `backend/orchestration/static_scenario.py`. This is a reusable
Python interface and deterministic structured view, not an API transport or an
automatic action selector.

## Inputs

```python
evaluate_static_scenario(
    threat,
    interceptor,
    synthetic_success_profile,
    footprint_radius_m,
    prepared_population,
    number_of_samples=50,
)
```

`threat` and `interceptor` use the existing Phase A-C domain records.
`prepared_population` is the existing PEC `PreparedPopulation`. The success
profile and footprint radius are explicit scenario assumptions. Values must be
finite numbers and booleans are forbidden. Radius may be zero, consistently
with PEC, but may not be negative.

The immutable `SyntheticSuccessProfile` defaults to `p0=0.97`,
`alpha=0.004/s`, `minimum=0.70`, and `maximum=1.00`. Every probability must lie
in `[0,1]`, decrease must be nonnegative, and
`minimum <= initial <= maximum`. Evaluation is:

```text
clip(initial_success_probability - decrease_per_second * time_from_start_s,
     minimum_success_probability,
     maximum_success_probability)
```

These defaults are synthetic inputs chosen to exercise the trade-space. They
are not calibrated to any interceptor.

## Evaluation and exposure

All generated `CandidateOpportunity` records remain in the result. Only
reachable opportunities receive success and footprint assumptions or enter the
footprint-assessment adapter. Footprint IDs are:

```text
{opportunity_id}__footprint
```

The center equals the candidate coordinates exactly and the scenario radius is
copied unchanged. The orchestration submits one adapter request in
`alternatives` mode and joins its independently assessed records by candidate
ID. It does not reproduce PEC geometry. PEC event evidence is copied into
immutable downstream records without rounding; common adapter provenance is
retained once on the result.

An evaluated candidate is eligible exactly when its original opportunity is
reachable and PEC status is `complete`. A reachable `partial_coverage`
candidate retains `known_area_exposure`, `covered_area_fraction`, and its zone
evidence but has `people_potentially_exposed: null`, is excluded from Pareto
analysis, and carries `partial_population_coverage` as its ineligibility reason.

## Pareto semantics

Eligible candidates compare higher supplied success and lower people
potentially exposed. The probability comparison uses absolute tolerance
`1e-12`. Exposure comparison uses:

```text
max(1e-9 people, 1e-12 * max(abs(first), abs(second)))
```

Candidate A dominates B when success is no worse, exposure is no worse, and at
least one comparison is strict outside tolerance. Exact duplicates and values
equivalent within both tolerances remain Pareto-efficient unless a third
candidate dominates them. Every eligible candidate records all dominator IDs
and all directly pairwise-equivalent IDs in canonical order. Pairwise evidence
is used because tolerance equivalence need not be transitive.

Canonical order is `(time_from_start_s, sample_index, opportunity_id)`.

## Descriptive representatives

The Pareto frontier supplies three category assignments in stable order:

1. `earliest_viable`;
2. `highest_success`;
3. `lowest_exposure`.

Tolerance ties retain canonical order. The category mapping may assign one
candidate to several categories. `representative_candidate_ids` lists unique
IDs in first-category appearance order; it never manufactures additional
choices. An empty frontier returns null category values and no representatives.

These categories describe evidence. They do not identify a universally best
choice or authorize an action.

## Structured result

`trade_space_result_to_dict` returns `static-scenario-evaluation/1` with:

- total, reachable, complete-coverage, and eligible counts;
- every original candidate opportunity, including unreachable records;
- every reachable evaluated candidate with supplied success, footprint, PEC
  evidence, eligibility, Pareto, dominance, equivalence, and category evidence;
- Pareto candidate IDs;
- category assignments and unique representative IDs;
- unchanged population-exposure provenance;
- optional timing diagnostics.

Timing diagnostics use `perf_counter_ns` and are inherently variable.
Deterministic comparisons must omit `diagnostics`; no calculation evidence
contains timestamps or rounded numbers.

