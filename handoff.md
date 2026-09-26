# Project handoff: Singapore simulation and learning demonstrator

Updated 26 September 2026 against the current local working tree at
`/Users/nicko/Desktop/Hackathons/SDTH`.

This is the operational handoff for the implemented Singapore simulation,
Emmanuel consequence integration, learning pipeline, and frontend result. Read
it with [vision.md](vision.md) for the product direction and with
[the canonical integration note](docs/singapore-simulation-integration.md) for
the concise implementation contract.

## 1. Product goal

The project is a Singapore-focused simulation and learning demonstrator. The
target product is an RL agent trained across many connected, multi-threat
Singapore scenarios to recommend interception choices quickly. Earlier choices
consume finite resources and affect later choices in the same episode. The
frontend makes the scenario, trajectories, selected actions, consequence
evidence, uncertainty, and comparison with a fixed baseline inspectable.

That is the target, not the present evidence claim. The current implementation
proves an end-to-end simulator, consequence adapter, masked-RL training path,
result contract, frontend view, and smoke-model reload. It does not yet prove
that a trained policy improves on the baseline. The exact optimizer is only an
assignment-model reference, not a global physical or learned-policy claim.

## 2. Source of truth and repository state

For current behavior, use this order:

1. executable code, versioned contracts, tests, and checked result artifacts;
2. [Singapore simulation integration](docs/singapore-simulation-integration.md);
3. [expanded implementation description](nickolas/singapore-simulation-integration.md);
4. [code-review checklist](nickolas/code-review-checklist.md);
5. this handoff and [vision.md](vision.md) for working context and intent.

Older investigation and planning documents remain useful as history, but they
must not override implemented behavior. In particular,
`docs/emmanuel-integration-implementation.md`, `emmanuel_investigate.md`, and
`newplan.md` include pre-integration assumptions or proposed scope.

Repository facts at this handoff:

- branch: `main`;
- implementation parent commit: `dc82f74`;
- Emmanuel's merged commit: `7bdb1266309e2ea4d7c52ae750f3bcfa28eca252`;
- the Singapore simulation and learning implementation, documentation, tests,
  and reviewed result artifacts are captured together by the RL architecture
  commit that includes this handoff;
- unrelated static-MVP and sensitivity edits may remain local and must be
  reviewed separately.

Do not describe the parent commit alone as containing the system documented
here. Preserve any remaining unrelated working-tree edits when switching
branches or machines.

For codebase questions, follow [AGENTS.md](AGENTS.md): query the existing
Graphify graph first, and run `graphify update .` after code or documentation
changes.

## 3. Implemented end-to-end path

```text
singapore-scenario/1 configuration
  -> derive the Singapore main-island geometry in EPSG:3414
  -> generate 8 threats and 8 one-use synthetic interceptors
  -> generate 20 three-dimensional samples per threat/interceptor pair
  -> evaluate two-dimensional bounded-curvature reachability
  -> require a complete one-to-one feasible matching
  -> build supplied 100 m candidate and terminal footprints
  -> intersect population zones and available sector assets
  -> reuse Emmanuel demo-v2 scoring, vetoes, tie bands, and ordering
  -> convert the ordering to normalized ordinal training costs
  -> execute the event simulator or masked RL environment
  -> export simulation-result/1
  -> parse and display the result in the frontend
```

This path is additive. The existing static evaluator, `planning-result/1`,
`SeededScenarioGenerator`, and `DeterministicToyProvider` remain available as
regression fixtures. They are not evidence for the Singapore learning result.

## 4. Frozen Singapore scenario contract

The `singapore-scenario/1` defaults are:

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
| Deterministic retry limit | 100 |

The main-island polygon is derived from the checked-in planning boundaries by
projecting them to EPSG:3414, repairing invalid geometry, unioning the result,
and selecting the largest connected polygon. The episode records source,
geometry, configuration, and canonical episode checksums.

Threat motion is parabolic in height and constant-velocity in the horizontal
plane. Every path terminates at its sampled `(x, y, 0)` destination. Current
interceptor reachability intentionally receives only candidate `x`, `y`, and
time; no interceptor-altitude model exists.

Generation accepts an episode only when a bipartite maximum matching covers all
eight threats with eight distinct interceptors. A matching edge requires at
least one reachable and consequence-eligible candidate. Assignment lock is the
one-time resource-consumption point.

Primary implementation:

- `backend/simulation/singapore_scenario.py`
- `backend/domain/candidates.py`
- `backend/planning/trajectory.py`
- `backend/planning/reachability.py`
- `backend/simulation/engine.py`
- `backend/simulation/baseline.py`

## 5. Consequence bridge and objective

`SingaporeConsequenceProvider` constructs an indexed catalog from:

- prepared Singapore population zones;
- checked-in parks and civic point sites;
- military polygons reconstructed from the checked-in frontend geometry; and
- critical-facility geometry with locally rebuilt scenario rows.

Transport, healthcare/education, and richer residential-service sectors are
explicitly unavailable in v1. Missing data is not converted to zero.

The supplied 100 m circle is the candidate query geometry. It is not a
validated blast or debris radius. The implemented overlap rules are:

- population uses PEC area-density overlap;
- intersected point assets receive a full direct effect;
- polygon occupancy and beneficiary estimates scale by intersection area
  divided by site area;
- loss fraction, outage, alternatives, and recovery duration remain unchanged;
- no physical damage, whole-site shutdown, aircraft downtime, or recovery
  transition is inferred.

PEC population is the authoritative aggregate human-exposure quantity. Site
casualty calculations remain diagnostics and are not added to it.

The adapter calls Emmanuel's existing `score_profile`, `flag_table`, `veto`,
and `rank_sites` functions. It preserves the demo-v2 casualty ordering, 10% / 0.5
casualty tie band, secondary score, veto evidence, and low/central/high values.
All 160 candidates for a threat are ordered once after veto filtering. Their
positions are normalized to `[0, 1]`; this immutable ordinal value is the
per-threat training cost. Reservations and time can invalidate actions without
renormalizing survivors. The eight event costs are summed and minimized. No
second set of consequence weights was introduced.

No persistent operational consequence update exists in v1. Interceptor
inventory is the only persistent state change.

Primary implementation:

- `backend/simulation/singapore_provider.py`
- `backend/exposure/`
- `backend/data_sources/consequence/`

## 6. Learning, evaluation, and baseline

The learning environment uses `centralized-observation/2`. Candidate rows carry
reachability and timing, horizontal position and altitude, travel geometry,
normalized consequence rank, casualty bounds, secondary score, veto and
unknown flags, and population-coverage state.

Training artifacts use `maskable-ppo-centralized/2` and validate provider,
generator, scenario configuration, geometry, source-data, cache, dependency,
and observation-layout identities when loaded. Runtime CLI choices are:

```text
--provider toy|singapore-demo-v2
--generator synthetic|singapore-v1
```

`feasible-immediate-matching/1` is an offline full-episode comparator. It
chooses the earliest eligible candidate per pair (then greatest margin and
stable IDs) and finds a complete one-to-one assignment minimizing total time.
`optimal-fixed-rank-assignment/1` minimizes immutable additive ordinal cost by
bitmask DP and replays the plan through the real engine. Its exactness scope is
explicitly limited to this fixed-rank assignment model.

Assign and cancel return zero reward. Advance emits signed resolved costs;
constraint violations emit the signed 9.0 penalty once. Rollout replay verifies
per-step costs and rewards, and evaluation reports violation count/rate.

The suite manifest is `rl-scenario-suites/4`, with non-overlapping seed ranges
for training, validation, held-out, stress, generic bounded-oracle work, and a
separate full-size Singapore assignment reference. The full
Singapore policy gates have not been run. The checked 16-step PPO artifact only
verifies training, persistence, normalization reload, and valid masked
inference.

Primary implementation:

- `backend/learning/environment.py`
- `backend/learning/training.py`
- `backend/learning/evaluation.py`
- `backend/learning/oracle.py`
- `backend/simulation/factories.py`
- `backend/simulation/suites.py`
- `scripts/train_rl.py`
- `scripts/evaluate_rl.py`

## 7. Result and frontend

`simulation-result/1` is independent from `planning-result/1`. It contains
eight WGS84 trajectories, simulation events, selected and terminal-
counterfactual footprints, consequence summaries, raw evidence, summed ordinal
cost, policy-versus-baseline comparison, provenance, and limitations.

The frontend has a separate parser and view for this schema. The checked seed-7
result is the feasible full-episode baseline on both sides of the comparison.
The UI deliberately says:

- “supplied 100 m area”;
- “people potentially exposed”; and
- “assumption-grade expected casualties.”

It does not claim a validated physical footprint, learned improvement, or
optimality. There is still no live application API; the frontend imports a
checked result artifact.

Primary files:

- `backend/presentation/simulation_result.py`
- `scripts/export_simulation_result.py`
- `contracts/simulation-result.md`
- `data/results/demo-simulation-result.json`
- `frontend/src/demo/simulation-model.ts`
- `frontend/src/demo/simulation.ts`
- `frontend/src/demo/main.ts`

## 8. Verified evidence

Current verified checks:

- backend: **318 passed**;
- frontend: **19 passed**;
- TypeScript/Vite production build: passed with the existing large-bundle
  advisory;
- seed-7 baseline and deterministic environment: terminated normally with all
  eight threats resolved;
- baseline and optimizer: **96/96** validation-plus-stress episodes terminated
  normally, with zero constraint violations and optimizer cost no worse on all
  96 episodes;
- smoke artifact: reloaded with normalization statistics and produced a valid
  masked action.

The checked seed-7 benchmark records:

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

These are reproducible engineering measurements for seed 7, not universal
performance guarantees.

## 9. Claims not supported yet

Do not claim any of the following from the current evidence:

- learned-policy improvement over the feasible full-episode baseline;
- physical/global optimal interception decisions beyond the fixed-rank scope;
- calibrated casualty prediction;
- a validated blast or debris radius;
- interceptor-altitude behavior;
- aircraft downtime or persistent service recovery;
- terrain, wind, drag, or physical debris behavior; or
- operational suitability for real-world decisions.

The 64 validation, 256 held-out, 32 stress, and 32 bounded-oracle suites are
versioned but have not been completed for a trained Singapore policy.

## 10. Immediate next work

1. Review the integration against
   [nickolas/code-review-checklist.md](nickolas/code-review-checklist.md), with
   special attention to compatibility, matching, overlap semantics, scoring
   equivalence, masks, artifact identity, and frontend wording.
2. Decide whether the frozen synthetic scenario, typed overlap rules,
   normalized ordinal objective, empty operational-state update, and
   baseline-only frontend result are approved for the MVP.
3. Review and commit the intended dirty-working-tree changes so the implemented
   state is reproducible outside this machine.
4. Choose and record a meaningful Singapore training budget.
5. Train a non-smoke policy, then run the validation, held-out, stress, oracle,
   and constraint gates without changing scenario semantics between policies.
6. Replace the checked frontend baseline comparison only if the trained policy
   passes those gates. Report measured improvement, uncertainty, failures, and
   latency; qualify any exact wording with the fixed-rank assignment scope.

## 11. Collaboration and evidence discipline

- Keep desired product behavior, implemented behavior, and validated claims
  separate.
- Do not turn unknown or unavailable consequence data into zero.
- Do not combine people potentially exposed, expected casualties, service
  effects, and ordinal training cost into one unlabeled number.
- Preserve episode, threat, interceptor, candidate, geometry, provider, data,
  configuration, model, and result identities across the pipeline.
- Work through material product choices with the user rather than silently
  changing the frozen scenario or objective.
- Preserve unrelated dirty-worktree changes.
