# Unit

`test_population.py` checks ordered hierarchy parsing (including Changi's heading), missing/qualified/zero values, exact composite joins and ambiguity, coordinate/area/density units and geometry exclusions. `population-model.test.ts` checks frontend filtering/ranking, unit display conversion, fixed colors and payload validation.

These are offline, isolated checks; they use `tests/fixtures/` and small synthetic geometries. Full cache-to-artifact checks belong in `tests/integration/`, not these selectors/parsers.

`test_exposure.py` verifies standalone PEC validation, coverage, exposure mathematics, circle approximation, reproducibility and invariants with synthetic known-answer geometry. Existing population tests remain unchanged.

`test_exposure_boundary.py` adds six focused boundary regressions: inside, tangent, slight extension, small internal gap, resolution-sensitive excluded corner with translation check, and unchanged production settings.

The machine-side static MVP adds `test_synthetic_success.py`,
`test_candidate_enrichment.py`, `test_pareto.py`, and
`test_representatives.py`. They cover strict synthetic-profile and footprint
validation, input immutability, complete-coverage eligibility, numerical
tolerance boundaries, direct equivalence evidence, dominance, canonical
ordering and duplicate-free descriptive categories.
