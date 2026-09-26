# Singapore generator and Emmanuel consequence integration

Status: implemented and smoke-verified on 2026-09-26.

This document describes the additive Singapore simulation path implemented
alongside the existing static demo. The old `planning-result/1` path, synthetic
scenario generator, and `DeterministicToyProvider` remain available as regression
fixtures.

## End-to-end flow

```text
singapore-scenario/1 configuration
  -> project and derive the Singapore main-island polygon
  -> generate 8 synthetic threats and 8 one-use interceptors
  -> generate 20 three-dimensional samples per threat/interceptor pair
  -> evaluate two-dimensional bounded-curvature reachability
  -> require a complete one-to-one feasible matching
  -> build supplied 100 m candidate and terminal footprints
  -> intersect population and sector data
  -> reuse Emmanuel demo-v2 scoring, vetoes, tie bands, and ordering
  -> convert the order to normalized ordinal training costs
  -> execute the event simulator / masked RL environment
  -> export simulation-result/1
  -> parse and display the result in the frontend
```

## Scenario contract

The frozen `singapore-scenario/1` defaults are:

| Property | Value |
| --- | --- |
| Threats | Exactly 8 |
| Interceptors | Exactly 8, one use each |
| Candidate samples | 20 per threat/interceptor pair |
| Detection window | Independently sampled in `[0, 10]` seconds, then sorted |
| Horizontal CRS | EPSG:3414 |
| Detection boundary | Exterior of a 10,000 m main-island buffer |
| Detection sampling | Uniform by boundary arc length |
| Terminal sampling | Uniform by area inside the main island |
| Detection altitude | Triangular 5,000 / 10,000 / 15,000 m |
| Threat horizontal speed | 250 m/s |
| Gravity | 9.80665 m/s² |
| Supplied footprint radius | 100 m |
| Consequence condition | `weekday_midday` |
| Vertical reference | Height above the synthetic terminal ground plane |
| Synthetic interceptor speed | 500 m/s |
| Synthetic interceptor turn rate | 15°/s |
| Retry limit | 100 deterministic attempts |

The main-island geometry is derived from the checked-in planning boundaries by
projecting them to EPSG:3414, repairing invalid geometry, unioning the result,
and selecting the largest connected polygon. Both the boundary-source checksum
and normalized derived-geometry checksum are recorded.

Randomness is deterministic and isolated by seed, component, entity, and retry
attempt. Retrying one threat does not alter the sampled values of unrelated
threats. Each episode also receives a canonical SHA-256 hash over its stable JSON
representation.

The generated threat path is parabolic in height and constant-velocity in the
horizontal plane. Every generated path must contain finite, nonnegative altitude
samples and terminate at the sampled `(x, y, 0)` position. Interceptor
reachability intentionally receives only candidate `x`, `y`, and time; there is
no interceptor-altitude model.

Primary implementation:

- `backend/simulation/singapore_scenario.py`
- `backend/domain/candidates.py`
- `backend/planning/trajectory.py`
- `backend/planning/reachability.py`

## Complete feasibility guarantee

Generation constructs a bipartite graph from threats to interceptors. An edge
exists when at least one candidate is both physically reachable and consequence
eligible. The episode is accepted only when a maximum matching covers all eight
threats using eight distinct interceptors.

During a rollout, the engine masks candidates that are vetoed, unreachable,
late, reserved by another threat, or dependent on a consumed resource. Ordinal
candidate ranks are refreshed over the candidates valid under the current time,
reservations, and inventory. The chosen consequence assessment and its complete
rank context are snapshotted when the assignment is made.

The interceptor is consumed exactly once, at assignment lock. A malformed
rollout can still reach the defensive unhandled path, but the Singapore provider
returns an explicit `constraint_failure:unhandled_threat`; it never reports a
normal zero consequence.

Primary implementation:

- `backend/simulation/engine.py`
- `backend/simulation/models.py`
- `backend/simulation/baseline.py`

## Consequence catalog

`SingaporeConsequenceProvider` prepares an indexed catalog at startup using:

- population zones from `data/processed/population-projected.json`;
- parks and civic point sites from the checked-in consequence input tables;
- military polygons reconstructed from `frontend/src/demo/military.json`;
- critical-facility geometry and locally rebuilt critical-sector scenario rows.

The v1 catalog intentionally reports transport, healthcare/education, and richer
residential-service sectors as unavailable. Missing data is not converted to
zero.

Every footprint uses the same 128-edge supplied-circle representation as the
Population Exposure Calculator. Consequence queries are clipped to the main
island. A circle wholly outside it has zero Singapore exposure and is labelled
`outside_singapore`, rather than being misreported as partial population
coverage.

Overlap semantics are:

- population: area-density overlap through PEC;
- point assets: full direct effect when intersected;
- polygon assets: occupancy and beneficiaries scale by intersection area divided
  by site area;
- loss fraction, outage duration, alternatives, and recovery duration remain
  unchanged;
- no whole-site shutdown, physical damage, downtime, or recovery transition is
  inferred.

PEC population is the authoritative aggregate human-exposure population. Site
casualty calculations are retained as diagnostics but are not added to the PEC
population result, preventing double counting.

Primary implementation:

- `backend/simulation/singapore_provider.py`
- `backend/exposure/`
- `backend/data_sources/consequence/`

## Emmanuel scoring and the scalar objective

The adapter calls Emmanuel's existing demo-v2 functions without modifying their
formulas:

- `score_profile` for `C`, `E`, `D`, `X`, `R`, `A`, and secondary scores;
- `flag_table` and `veto` for civilian and capability veto evidence;
- `rank_sites` for casualty tie bands and secondary ordering.

The population exposure is converted into a demo-v2 population profile. Missing
vulnerability remains explicit and produces the existing low/central/high
uncertainty treatment.

Currently valid candidates are ordered by:

1. excluding vetoed candidates;
2. central expected casualties;
3. the existing 10% / 0.5 casualty tie band;
4. the existing secondary score inside the band.

The ordered positions are normalized from `0` to `1`. This ordinal value is the
per-threat training cost and adds no new consequence weights. Eight event costs
are summed and minimized. Expected casualties, people potentially exposed, site
evidence, and other physical values remain separate diagnostics.

`CandidateAssessment` records eligibility, veto status and reasons, casualty
bounds, secondary bounds, population coverage, every intersected site, decision
features, rank context, and provider/data/config/cache identities.

No persistent operational-state updates are applied in v1. Interceptor
inventory is the only persistent state change.

## Simulation and RL integration

The environment uses `centralized-observation/2`. Candidate rows now contain:

- reachable state and time-to-interception/lock;
- horizontal position and altitude;
- travel time, margin, and path length;
- normalized consequence rank cost;
- low/central/high expected casualties;
- secondary score;
- veto and unknown status;
- population-coverage status.

Training and loading accept provider and scenario factories. CLI choices are:

```text
--provider toy|singapore-demo-v2
--generator synthetic|singapore-v1
```

`maskable-ppo-centralized/2` artifacts record and validate the provider,
generator, geometry, consequence data, observation layout, dependency, cache,
and configuration identities. Old model or normalization artifacts are rejected
when those identities do not match.

The immediate-interception baseline remains deterministic: earliest eligible
interception time, then greatest reachability margin, interceptor ID, and
opportunity ID.

The suite manifest is `rl-scenario-suites/3`. Canonical episode hashes can be
materialized with `build_suite_manifest`, which rejects duplicates across
partitions.

Primary implementation:

- `backend/learning/environment.py`
- `backend/learning/training.py`
- `backend/learning/evaluation.py`
- `backend/simulation/factories.py`
- `backend/simulation/suites.py`
- `scripts/train_rl.py`
- `scripts/evaluate_rl.py`

## Result and frontend

`simulation-result/1` is independent from `planning-result/1`. It contains:

- eight WGS84 trajectories with absolute time, height, and vertical velocity;
- detection, assignment, lock, and interception events;
- eight selected and eight terminal-counterfactual supplied footprints;
- population and sector consequence summaries;
- raw physical evidence and summed ordinal objective cost;
- policy-versus-baseline comparison;
- generator, geometry, provider, data, configuration, and episode provenance;
- explicit limitations.

The frontend uses a separate parser and view. The checked result is the seed-7
immediate-interception baseline. It deliberately displays:

- “supplied 100 m area”;
- “people potentially exposed”;
- “assumption-grade expected casualties.”

It does not call the supplied area a validated blast radius and does not claim
that the smoke-trained policy is improved or optimal.

Primary files:

- `backend/presentation/simulation_result.py`
- `scripts/export_simulation_result.py`
- `contracts/simulation-result.md`
- `data/results/demo-simulation-result.json`
- `frontend/src/demo/simulation-model.ts`
- `frontend/src/demo/simulation.ts`
- `frontend/src/demo/main.ts`

## Verification performed

Backend verification:

```text
308 passed
```

Frontend verification:

```text
18 passed
TypeScript/Vite production build passed
```

The build reports the existing large-bundle advisory but has no compilation or
build error.

The seed-7 reproducible benchmark records:

| Check | Result |
| --- | ---: |
| Catalog/provider cold start | 2041.70 ms |
| Complete 1,280-candidate episode generation | 510.25 ms |
| First 160-candidate consequence set, cold | 15.61 ms |
| Same set, warm cache | 1.11 ms |
| Immediate-baseline full episode | 168.76 ms |
| Environment step p95 | 28.11 ms |
| Smoke-policy masked inference p95 | 0.19 ms |
| Peak traced benchmark memory | 70,460,713 bytes |

Both the baseline and deterministic environment terminated normally with all
eight threats resolved. The saved 16-step Singapore MaskablePPO smoke artifact
trained, reloaded with its normalization statistics, and produced a valid masked
action. This verifies plumbing only.

Useful commands:

```bash
.venv-rl/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
.venv-rl/bin/python scripts/benchmark_singapore_simulation.py
.venv-rl/bin/python scripts/train_rl.py \
  --provider singapore-demo-v2 --generator singapore-v1 \
  --output-dir data/results/rl/singapore-smoke --steps 16 --seed 7
.venv-rl/bin/python scripts/export_simulation_result.py --seed 7
graphify update .
```

## Claims not yet supported

The following evaluation suites are versioned but have not been run for a
trained Singapore policy:

- 64 validation episodes;
- 256 held-out episodes;
- 32 full-capacity stress episodes;
- 32 bounded-oracle episodes.

Therefore the current work does not support claims of learned-policy
improvement, optimality, calibrated casualty prediction, a validated blast or
debris radius, interceptor-altitude behavior, aircraft downtime, service
recovery, terrain interaction, wind, or drag.

The checked frontend result must remain the baseline until the equivalence,
performance, held-out, stress, oracle, and constraint gates pass.
