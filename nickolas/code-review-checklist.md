# Code review checklist: Singapore simulation integration

Use this list to review the additive Singapore generator, consequence provider,
simulation/RL path, and frontend result. Items are ordered roughly by risk.

## 1. Scope and compatibility

- [ ] Confirm the new path is additive and does not replace
  `planning-result/1`.
- [ ] Confirm existing positional construction of `ThreatState`,
  `TrajectorySample`, and `CandidateOpportunity` remains compatible because the
  new vertical fields were appended with defaults.
- [ ] Confirm `simulation-episode/1` remains accepted where intended.
- [ ] Confirm `DeterministicToyProvider` and the synthetic generator still behave
  as regression fixtures.
- [ ] Review unrelated pre-existing dirty-worktree changes separately; do not
  accidentally attribute them to this integration.

Files to inspect:

- `backend/domain/candidates.py`
- `backend/planning/trajectory.py`
- `backend/planning/reachability.py`
- `backend/simulation/models.py`
- `backend/simulation/provider.py`

## 2. Singapore geometry and deterministic generation

- [ ] Verify boundary input is projected to EPSG:3414, repaired, unioned, and
  reduced to the largest connected polygon.
- [ ] Verify source and derived-geometry checksums are deterministic.
- [ ] Check that detection positions are sampled by arc length on the exterior
  of the 10 km buffer.
- [ ] Check that terminal rejection sampling is uniform over the polygon area,
  not biased toward a centroid or planning-area distribution.
- [ ] Verify all detection times lie in `[0, 10]` and are deterministically
  sorted.
- [ ] Verify triangular altitude parameters are 5,000 / 10,000 / 15,000 m.
- [ ] Verify the parabolic vertical equation uses 9.80665 m/s² and terminates at
  exactly `(terminal x, terminal y, 0)` within tolerance.
- [ ] Confirm all sampled heights are finite and nonnegative.
- [ ] Check that retries do not perturb unrelated threats.
- [ ] Decide whether the current interpretation of the 100-attempt limit matches
  the desired product wording for geometry retries versus matching repairs.
- [ ] Confirm interceptor positions are inside the main island and all synthetic
  values are labelled as such.
- [ ] Review canonical serialization for stable key ordering and exclusion of the
  self-referential episode hash.

Main file:

- `backend/simulation/singapore_scenario.py`

Tests:

- `tests/unit/test_singapore_simulation.py`

## 3. Feasibility and resource behavior

- [ ] Verify graph edges require at least one physically reachable and
  consequence-eligible candidate.
- [ ] Verify accepted episodes always have a complete eight-threat matching with
  eight distinct interceptors.
- [ ] Confirm reservations prevent one interceptor from being assigned to two
  threats.
- [ ] Confirm assignment lock—not tentative assignment—is the consumption point.
- [ ] Confirm consumed interceptors cannot reappear in later masks.
- [ ] Verify late candidates and same-assignment no-ops are masked.
- [ ] Verify current candidate ranks are recomputed after time, reservation, and
  inventory changes.
- [ ] Confirm assignment evaluation uses the saved consequence snapshot rather
  than a later provider-cache entry.
- [ ] Confirm no valid generated episode resolves a threat through the unhandled
  path.
- [ ] Review equal-timestamp event ordering for detection, lock, interception,
  expiry, and episode end.

Files:

- `backend/simulation/engine.py`
- `backend/simulation/baseline.py`
- `backend/simulation/models.py`

## 4. Spatial consequence catalog

- [ ] Verify every required local source exists and startup fails explicitly if
  a required artifact is missing.
- [ ] Check population preparation uses the committed projected population data.
- [ ] Review the military delta-ring decoder and geometry validation.
- [ ] Review locally rebuilt critical-sector assumptions against the committed
  consequence inputs.
- [ ] Confirm the catalog is treated as immutable after construction and the
  STRtree indexes exactly the associated geometry tuple.
- [ ] Verify all source checksums participate in the catalog/provider identities.
- [ ] Confirm unavailable sectors are named explicitly.
- [ ] Confirm transport, healthcare/education, and richer residential-service
  data are not silently represented as zero.

File:

- `backend/simulation/singapore_provider.py`

## 5. Footprint and overlap semantics

- [ ] Confirm the provider and PEC both use a 128-edge supplied circle.
- [ ] Verify the supplied circle is clipped to the main-island polygon before
  population and site queries.
- [ ] Confirm a fully off-island circle reports zero Singapore exposure with
  `outside_singapore` status.
- [ ] Confirm coastal circles preserve partial-coverage evidence.
- [ ] Verify point assets receive an overlap fraction of exactly 1 when
  intersected.
- [ ] Verify polygon overlap is `intersection area / site area`.
- [ ] Confirm only occupancy and beneficiaries are scaled for polygon sites.
- [ ] Confirm loss fraction, outage, alternatives, recovery duration, and
  capability estimates are not scaled.
- [ ] Confirm the implementation does not infer physical damage, whole-site
  shutdown, downtime, or recovery transitions.
- [ ] Check evidence retains each intersected site, overlap fraction, inputs,
  low/central/high scores, missing dimensions, assumptions, and source identity.

## 6. Emmanuel scoring equivalence

- [ ] Confirm no Emmanuel constants, weights, thresholds, or formulas were
  changed.
- [ ] Trace population and site profiles through the original `score_profile`,
  `flag_table`, `veto`, and `rank_sites` functions.
- [ ] Confirm PEC population is the only aggregate human-harm population source.
- [ ] Confirm site casualty scores are diagnostic only and cannot be added to PEC
  casualties.
- [ ] Review missing-vulnerability behavior and casualty uncertainty bounds.
- [ ] Verify candidate veto is the union of population human-harm and site
  service/capability vetoes.
- [ ] Confirm `unknown` remains eligible when the primary result is computable.
- [ ] Inspect the frozen direct-scoring test that compares adapter evidence with
  the original Emmanuel functions.
- [ ] Verify the 10% / 0.5 casualty tie band and secondary-score ordering using
  the test fixture.

Files:

- `backend/simulation/singapore_provider.py`
- `backend/data_sources/consequence/scoring.py`
- `tests/unit/test_singapore_simulation.py`

## 7. Scalar training objective

- [ ] Confirm vetoed candidates are excluded before ranking.
- [ ] Confirm ranking only considers candidates valid in the current resource and
  timing context.
- [ ] Confirm ordinal costs run from 0 to 1 and lower is better.
- [ ] Confirm event costs are summed across eight resolved threats.
- [ ] Confirm expected casualties and population exposure remain separate from
  the training cost.
- [ ] Confirm no new weighted combination of consequence dimensions was added.
- [ ] Confirm `evaluate_unhandled()` returns an explicit failure and cannot
  create a successful zero-cost outcome.
- [ ] Confirm provider outputs reject NaN or infinity.
- [ ] Review whether an exact equality/tie should share a dense rank or whether
  the current deterministic ordered position is the intended interpretation.

## 8. Observation and action-mask correctness

- [ ] Verify `centralized-observation/2` dimensions and offsets are stable.
- [ ] Confirm candidate rows include altitude, rank cost, casualty bounds,
  secondary score, veto/unknown state, and coverage state.
- [ ] Confirm unavailable values use documented sentinels rather than zero.
- [ ] Confirm no scheduled future threat contributes nonzero observation data.
- [ ] Confirm action masks and encoded observations are based on the same
  refreshed assessment context.
- [ ] Confirm invalid external actions still fail explicitly.
- [ ] Check that float32 conversion cannot turn finite source values into
  infinities without triggering truncation.
- [ ] Confirm Gymnasium and MaskablePPO expectations remain satisfied.

File:

- `backend/learning/environment.py`

## 9. Model identity, persistence, and evaluation

- [ ] Confirm saved metadata contains model, observation layout, provider,
  generator, geometry, source-data, configuration, cache, and dependency
  identities.
- [ ] Confirm model loading rejects old layout/model versions.
- [ ] Confirm provider or generator mismatch fails before inference.
- [ ] Confirm normalization statistics are loaded in inference mode and reward
  normalization is disabled.
- [ ] Verify CLI selections construct the intended provider/generator pair.
- [ ] Confirm training seeds remain separate from validation, held-out, stress,
  and oracle ranges.
- [ ] Review canonical duplicate detection in `build_suite_manifest`.
- [ ] Check that evaluation reports use the Singapore assumption-grade label
  instead of the toy-provider label.
- [ ] Review bounded-oracle behavior with the exact 8/8/20 Singapore generator;
  the current full Singapore evaluation gates have not been executed.
- [ ] Confirm the PyTorch distribution-validation workaround is narrowly scoped
  and backed by independent finite observation/provider validation.

Files:

- `backend/learning/training.py`
- `backend/learning/evaluation.py`
- `backend/simulation/factories.py`
- `backend/simulation/suites.py`
- `data/scenarios/rl/suites.json`
- `scripts/train_rl.py`
- `scripts/evaluate_rl.py`

## 10. Result exporter and frontend

- [ ] Validate `simulation-result/1` independently from `planning-result/1`.
- [ ] Confirm there are exactly eight trajectories, assignments, selected
  footprints, and terminal-counterfactual footprints.
- [ ] Confirm every trajectory has 20 ordered samples, WGS84 coordinates,
  absolute timestamps, nonnegative height, and a zero-height terminal sample.
- [ ] Confirm selected consequences come from assignment snapshots.
- [ ] Confirm terminal consequences are clearly counterfactual.
- [ ] Confirm event output includes detections, locks, and interceptions.
- [ ] Confirm provenance includes the canonical episode, geometry, source,
  scenario, generator, simulator, and provider identities.
- [ ] Confirm all exported numbers are finite JSON values.
- [ ] Confirm the frontend parser rejects a legacy planning result.
- [ ] Confirm UI wording uses “supplied 100 m area,” “people potentially
  exposed,” and “assumption-grade expected casualties.”
- [ ] Search the new view for accidental “blast radius,” “validated casualty,”
  or unsupported “optimal” wording.
- [ ] Confirm “optimal” is emitted only with exact bounded-oracle evidence.
- [ ] Check whether selected-only circles are sufficient for the desired initial
  UX or whether terminal-counterfactual visibility should be added later.

Files:

- `backend/presentation/simulation_result.py`
- `contracts/simulation-result.md`
- `data/results/demo-simulation-result.json`
- `frontend/src/demo/simulation-model.ts`
- `frontend/src/demo/simulation.ts`
- `tests/unit/simulation-model.test.ts`

## 11. Reproducibility and performance evidence

- [ ] Regenerate seed 7 twice and compare canonical episode hashes.
- [ ] Regenerate `demo-simulation-result.json` and inspect the diff.
- [ ] Run the benchmark once from a cold process and compare results with the
  checked evidence without treating one run as a universal performance claim.
- [ ] Confirm cold and warm candidate scoring are measured separately.
- [ ] Confirm the baseline and environment both terminate normally.
- [ ] Confirm the smoke model reloads and its predicted action is allowed by the
  mask.
- [ ] Remember that the 16-step policy is only a plumbing test.
- [ ] Do not approve a learned-policy improvement claim until all validation,
  held-out, stress, oracle, and constraint gates pass.

Artifacts:

- `data/results/singapore-simulation-benchmark.json`
- `data/results/demo-simulation-result.json`
- local ignored artifacts under `data/results/rl/singapore-smoke/`

## 12. Commands to run before approval

```bash
# Backend
.venv-rl/bin/python -m pytest -q

# Singapore-specific tests
.venv-rl/bin/python -m pytest -q tests/unit/test_singapore_simulation.py

# Frontend parser and existing frontend unit tests
npm --prefix frontend test

# TypeScript and production bundle
npm --prefix frontend run build

# Reproducible benchmark and baseline result
.venv-rl/bin/python scripts/benchmark_singapore_simulation.py
.venv-rl/bin/python scripts/export_simulation_result.py --seed 7

# Whitespace and JSON checks
git diff --check
.venv-rl/bin/python -m json.tool \
  data/results/demo-simulation-result.json >/dev/null
.venv-rl/bin/python -m json.tool \
  data/results/singapore-simulation-benchmark.json >/dev/null
```

Expected current results:

- backend: 308 passed;
- frontend: 18 passed;
- frontend production build: passed with a bundle-size advisory;
- Singapore baseline: eight intercepted threats, no truncation;
- smoke artifact: reload and masked prediction passed.

## 13. Known limits to acknowledge in review

- [ ] The 100 m circle is supplied scenario input, not a validated blast or
  debris radius.
- [ ] Casualty constants are uncalibrated demonstration assumptions.
- [ ] There is no interceptor-altitude model.
- [ ] There is no debris, terrain, wind, drag, aircraft-downtime, or recovery
  transition model.
- [ ] The consequence condition remains fixed at `weekday_midday` for the whole
  episode.
- [ ] Transport, healthcare/education, and richer residential-service sectors
  remain unavailable in v1.
- [ ] The checked frontend result is a baseline comparison with 0% measured
  improvement, not a trained-policy result.
- [ ] The 64 validation, 256 held-out, 32 stress, and 32 bounded-oracle suites
  have not been run for a trained Singapore policy.

## 14. Final approval questions

- [ ] Is the synthetic scenario contract acceptable for the MVP?
- [ ] Are the typed overlap rules exactly the intended product semantics?
- [ ] Is normalized ordered position the approved scalar objective derived from
  Emmanuel's ranking?
- [ ] Is an empty persistent operational update correct for v1?
- [ ] Is the current baseline-only frontend result acceptable until evaluation
  gates pass?
- [ ] Are the explicit unavailable sectors and all modeling limitations visible
  enough for reviewers and demo users?
- [ ] Has every supported claim been tied to an artifact or test, with stronger
  claims withheld?
