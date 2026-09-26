# Backend integration preparation summary

Status: backend handoff ready for frontend integration review as of 2026-09-26.

The Singapore simulation path is implemented, deterministic, and verified as a
checked-artifact workflow. The frontend can integrate against
`simulation-result/1` now. A live result API, production policy training, and
held-out learned-policy evaluation remain separate follow-up work.

## Integration boundary

Keep the two existing result paths separate:

- `planning-result/1` is the single-threat planning and human-selection demo.
- `simulation-result/1` is the complete eight-threat Singapore rollout.

The simulation frontend currently imports
[`data/results/demo-simulation-result.json`](../data/results/demo-simulation-result.json)
at build time. It does not fetch a live backend result. The checked artifact is
therefore the current integration fixture and contract example.

## Frozen backend contract

The simulation uses these versioned identities:

| Concern | Identity |
| --- | --- |
| Scenario generator | `singapore-scenario/1` |
| Episode | `simulation-episode/2` |
| Simulator | `centralized-event-simulator/2` |
| Consequence provider | `singapore-demo-v2-fixed-rank/2` |
| Objective reference | `full-candidate-universe/1` |
| Rollout record | `rl-rollout/2` |
| Frontend result | `simulation-result/1` |

The fixed scenario contains exactly eight threats, eight one-use interceptors,
and 20 candidate samples for every threat/interceptor pair: 1,280 candidate
opportunities per episode, or a 160-candidate universe for each threat. It uses
EPSG:3414 for calculation, `weekday_midday` consequence inputs, and a supplied
100 m footprint.

`SingaporeScenarioGenerator` and `SingaporeConsequenceProvider` share one
`SingaporeScenarioConfig`. The generator, engine, provider, and exporter reject
radius, condition, objective, or main-island checksum mismatches. The 100 m
circle is a supplied consequence-query area, not a validated blast radius or
debris envelope.

Episode generation is accepted only when a complete consequence-eligible
one-to-one threat/interceptor matching exists. Assignment lock consumes an
interceptor exactly once.

## Consequence objective and failure behavior

For each threat, the provider evaluates and orders its complete 160-candidate
universe once using Emmanuel's existing demo-v2 vetoes, casualty ordering,
10%/0.5 tie band, secondary score, and ordering functions. The provider freezes:

- candidate eligibility and veto evidence;
- normalized ordinal training cost;
- casualty, population, and site evidence; and
- complete rank context and provenance.

Reservations and time progression may later invalidate an action, but they do
not renormalize surviving candidates. The eight selected ordinal costs are
additive and minimized. Physical values such as people potentially exposed,
expected-casualty ranges, and service evidence remain separate diagnostics; the
ordinal objective is not a physical unit.

Reward and termination behavior is explicit:

- assign and cancel actions return zero reward;
- advance emits the signed sum of costs resolved at that timestamp;
- the accumulated reward must equal the signed aggregate episode cost;
- the first unhandled expiry terminates as
  `constraint_violation:unhandled_threat`, applying cost `9.0` once while
  retaining prior resolved costs; and
- provider exceptions and malformed simulator state truncate rather than
  masquerading as normal outcomes.

## Reference policies

`feasible-immediate-matching/1` is the deterministic baseline. It selects the
earliest eligible opportunity for each threat/interceptor pair, breaks ties by
greatest margin and stable IDs, and solves a complete one-to-one matching that
minimizes summed interception time.

`optimal-fixed-rank-assignment/1` selects the lowest immutable-cost candidate
per pair and uses an eight-interceptor bitmask dynamic program to minimize total
ordinal cost. It is exact only for the declared assignment model: immutable
additive candidate costs, one-use interceptors, complete threat coverage, and no
operational update that changes later costs. Its predicted score must equal the
score obtained by replay through the real event engine. It is not a claim of
global physical or operational optimality.

## Export and frontend contract

The exporter permits only a successful complete rollout: eight assignments,
eight distinct consumed interceptors, all threats intercepted, no truncation,
and no constraint violation. Canonical JSON excludes wall-clock runtime values,
so identical inputs produce byte-identical artifacts. Policy comparison runs
the baseline and selected policy in separate engine instances over the same
immutable episode.

`simulation-result/1` supplies:

- eight WGS84 trajectories and their absolute/relative timing;
- detection, assignment, lock, and interception events;
- eight selected and eight terminal-counterfactual supplied footprints;
- snapshotted consequence evidence and the summed ordinal objective;
- policy-versus-baseline identities, scores, and assignment-plan proof scope;
- scenario, geometry, provider, source-data, configuration, and episode
  checksums; and
- explicit modeling limitations and controlled UI wording.

The TypeScript parser validates the schema version, fixed episode shape,
cross-references, IDs, finite values, policy identities, radius, and provenance
before rendering. Required wording is “supplied 100 m area,” “people potentially
exposed,” and “assumption-grade expected casualties.”

The checked seed-7 artifact uses the baseline on both sides of the comparison,
so it correctly reports no improvement. A separately exported seed-7 optimizer
run records:

| Policy | Ordinal cost |
| --- | ---: |
| `feasible-immediate-matching/1` | 1.5541121832713964 |
| `optimal-fixed-rank-assignment/1` | 0.9006223779753162 |

## Verification evidence

Verified on 2026-09-26:

- backend test suite: **318 passed**;
- frontend test suite: **19 passed**;
- TypeScript/Vite production build: passed, with the existing bundle-size
  advisory;
- validation plus stress reference sweep: 64 validation and 32 stress episodes
  per policy;
- baseline: 96/96 normal terminations and zero constraint violations;
- optimizer: 96/96 normal terminations and zero constraint violations;
- optimizer cost no worse than baseline: 96/96 episodes;
- optimizer predicted cost equals replayed actual cost: 96/96 episodes;
- regression seeds 7, 17, and 10020 passed;
- repeated baseline exports were byte-identical; repeated optimizer exports
  were byte-identical; and
- the locally regenerated 16-step PPO smoke artifact reloaded its normalization
  state and produced a valid masked action. This proves plumbing only, not
  learned improvement.

Useful reproduction commands:

```bash
.venv-rl/bin/python -m pytest -q

.venv-rl/bin/python scripts/verify_singapore_backend.py \
  --suite validation --include-stress \
  --output /tmp/singapore-backend-verification.json

.venv-rl/bin/python scripts/verify_singapore_backend.py \
  --seeds 7 17 10020 \
  --output /tmp/singapore-regressions.json

.venv-rl/bin/python scripts/export_simulation_result.py \
  --seed 7 --policy baseline --output /tmp/result-a.json
.venv-rl/bin/python scripts/export_simulation_result.py \
  --seed 7 --policy baseline --output /tmp/result-b.json
cmp /tmp/result-a.json /tmp/result-b.json

.venv-rl/bin/python scripts/export_simulation_result.py \
  --seed 7 --policy optimal --output /tmp/result-optimal.json

(cd frontend && npm test && npm run build)
```

## Known limits

- No live planning or simulation result API is connected yet.
- The frontend consumes checked JSON and needs a rebuild/reload to display a
  newly exported run.
- The supplied 100 m area is not a validated blast or debris model.
- Reachability is two-dimensional; there is no interceptor-altitude model.
- Terrain, drag, wind, physical debris, aircraft downtime, and recovery
  transitions are not modeled.
- Casualty assumptions are uncalibrated demonstration inputs.
- Transport, healthcare, education, and richer residential-service evidence is
  unavailable in v1 and must not be treated as zero.
- Exact optimizer wording applies only to the fixed-rank assignment scope.
- No production-trained Singapore PPO policy or learned-policy improvement claim
  exists yet. The 256 held-out and learned-policy acceptance gates remain to be
  run after meaningful training.
- Starting the Vite development server was blocked by socket-bind `EPERM` in the
  managed sandbox; socket-free frontend tests, transform, and production build
  passed. This is an environment limitation, not a demonstrated app defect.

## Integration checklist

1. Treat [`contracts/simulation-result.md`](../contracts/simulation-result.md)
   and the checked seed-7 JSON as the frontend source of truth.
2. Keep the result schema versioned and reject incompatible payloads instead of
   silently reinterpreting fields.
3. Preserve one radius/configuration source through scenario generation,
   consequence evaluation, export, and rendering.
4. Preserve stable episode, threat, interceptor, opportunity, policy, provider,
   geometry, and source-data identities end to end.
5. Validate the payload before rendering and show an explicit unavailable state
   on contract failure.
6. If a live API is added, define run IDs, completion/error states, refresh and
   stale-result behavior, caching, and schema-version negotiation.
7. Keep past results immutable: do not apply a new radius, consequence model, or
   provider identity to an already displayed episode.
8. Replace the baseline-only checked comparison only after a trained policy has
   passed validation, held-out, stress, constraint, latency, and reproducibility
   gates.

## Primary references

- [`docs/singapore-simulation-integration.md`](../docs/singapore-simulation-integration.md)
- [`handoff.md`](../handoff.md)
- [`backend/simulation/singapore_scenario.py`](../backend/simulation/singapore_scenario.py)
- [`backend/simulation/singapore_provider.py`](../backend/simulation/singapore_provider.py)
- [`backend/simulation/assignment_planning.py`](../backend/simulation/assignment_planning.py)
- [`backend/simulation/engine.py`](../backend/simulation/engine.py)
- [`backend/presentation/simulation_result.py`](../backend/presentation/simulation_result.py)
- [`scripts/verify_singapore_backend.py`](../scripts/verify_singapore_backend.py)
- [`frontend/src/demo/simulation-model.ts`](../frontend/src/demo/simulation-model.ts)
