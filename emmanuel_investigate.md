# Emmanuel integration investigation

Use this checklist when Emmanuel pushes his work. The goal is to determine quickly whether it supplies the simulation and consequence interface needed for RL training, what can be integrated directly, and what remains undefined.

## Target demo claim

The intended claim is:

> We built an RL agent, trained on many simulations of different Singapore-specific interception scenarios, to quickly identify the most optimal interception point.

To support this claim, the integrated system must make the following concrete:

- what the agent observes;
- which interception choices are available;
- what “optimal” means and how it is calculated;
- how one choice changes the rest of an episode;
- how the Singapore-specific scenarios are generated;
- how many distinct scenarios and episodes are used;
- how evaluation scenarios are kept separate from training;
- how the agent compares with the immediate-interception baseline; and
- the measured inference time of the complete decision path.

Record the final supported wording after the investigation. If the environment remains a one-step scenario evaluator, record that clearly because it changes what kind of learning experiment has actually been built.

## Working hypothesis to verify

The working hypothesis is that Emmanuel's component already converts an interception scenario or resulting geographic effect into operational consequences, including aircraft downtime and other factors. If so, it may supply the missing consequence and reward inputs directly.

Do not rebuild this mapping before checking his implementation. Verify whether it:

1. Accepts an interception point, candidate record, debris or hazard footprint, or some other input.
2. Produces the geographic effect itself or expects a footprint supplied by another component.
3. Maps the effect to named assets, operational capability, downtime, civilian outcomes, or aggregate scores.
4. Produces raw quantities with units, only normalized scores, or both.
5. Updates persistent state for later events or evaluates only one event independently.
6. Models uncertainty or alternative outcomes.
7. Preserves the source, version, and assumptions behind every consequence value.

The current healthcare and education examples were mentioned because those are runnable sectors in the checked-in `backend/data_sources/consequence/` package. They are not requirements for the interception or RL demonstration. Use them only if they are part of the intended objective. If Emmanuel's work supplies the relevant runway, aircraft, defence, infrastructure, or operational consequences, those outputs should drive the first integration slice.

## 1. Capture the delivered revision

Record before changing anything:

| Item | Finding |
|---|---|
| Branch | |
| Commit | |
| Merge base with `main` | |
| Files added or changed | |
| Dependency changes | |
| Data or generated artifacts | |
| Documented run command | |
| Expected runtime environment | |

Preserve Emmanuel's original example input and output so later adapters can be checked against them.

## 2. Reproduce the component

- [ ] Install only the declared dependencies.
- [ ] Run the documented example unchanged.
- [ ] Run its unit and integration tests.
- [ ] Record any external services, credentials, caches, or network calls it needs.
- [ ] Save one successful output and one failure or unavailable case.
- [ ] Confirm whether a fixed random seed reproduces the same result.
- [ ] Confirm whether repeated runs mutate shared state or cached inputs.

Record the exact commands and results:

```text
Setup command:
Run command:
Test command:
Successful artifact:
Failure or unavailable artifact:
```

## 3. Document the interface

### Inputs

For every input field, record:

- name and type;
- unit and coordinate reference system;
- valid range;
- whether it is required, optional, inferred, or assumed;
- whether it is known at decision time;
- source and version; and
- missing or invalid behavior.

Pay particular attention to the join with the existing records:

- `scenario_id`
- `candidate_id`
- interception position and time
- threat state
- interceptor state and remaining resources
- supplied or generated hazard footprint
- current asset and operational state
- random seed

### Outputs

For every output field, record:

- name and type;
- physical meaning and unit;
- applicable time horizon;
- whether it is measured, simulated, derived, assumed, or normalized;
- lower, central, and upper values if available;
- source or model version;
- whether it can be combined across assets or events; and
- unavailable, invalid, and timeout behavior.

Determine whether one invocation returns:

- consequences for one candidate;
- consequences for every candidate in a scenario;
- the chosen candidate;
- a state transition for a later event; or
- several of these as separate layers.

## 4. Establish what “optimal” means

Write the exact objective before using Emmanuel's outputs as an RL reward.

| Decision | Answer |
|---|---|
| Hard feasibility constraints | |
| Outcome dimensions to minimize | |
| Outcome dimensions to maximize | |
| Resource-preservation term | |
| Time or urgency term | |
| Consequences carried into later events | |
| Priority order or weights | |
| Treatment of uncertainty | |
| Treatment of missing outputs | |
| Episode terminal conditions | |

Check whether Emmanuel's aggregate score already embeds priorities or weights. If it does, record them and avoid silently adding a second set of weights in the RL reward.

## 5. Determine RL environment readiness

The planned environment needs an interface equivalent to:

```text
reset(seed, episode_spec) -> observation, metadata
step(candidate_action) -> next_observation, reward_components, terminated, truncated, metadata
```

Investigate whether Emmanuel's work provides the following pieces:

| Environment need | Supplied? | Location or adapter needed |
|---|---:|---|
| Consequence for a selected candidate | | |
| Outcome uncertainty or stochastic sampling | | |
| Resource consumption | | |
| Aircraft or asset downtime update | | |
| Other persistent operational-state update | | |
| State passed into the next event | | |
| Multiple events in one episode | | |
| Deterministic seeded replay | | |
| Batched or parallel evaluation | | |
| Explicit failure and timeout status | | |

If it evaluates one event only, define an adapter that applies its outputs to a separate episode-state object. Do not hide state-transition logic inside the training loop.

## 6. Decide the integration contract

After inspecting the real interface, decide whether to call Emmanuel's component as:

- an in-process Python function;
- a command-line process;
- a local service; or
- an offline batch generator.

The preferred boundary should accept a versioned scenario and candidate and return a versioned consequence result. Record:

| Contract item | Decision |
|---|---|
| Input schema and version | |
| Output schema and version | |
| Candidate identity mapping | |
| Error and timeout representation | |
| Simulator/model identity | |
| Data snapshot identity | |
| Seed and replay metadata | |
| Cache key | |
| Owner | |

Do not finalize the frontend result schema until these actual outputs are known.

## 7. Benchmark the delivered workload

Benchmark Emmanuel's component rather than extrapolating from the current static evaluator.

Measure separately:

1. data loading and preparation;
2. candidate generation, if included;
3. one candidate consequence evaluation;
4. all candidates for one scenario;
5. one complete multi-event episode, if supported;
6. serialization or inter-process overhead; and
7. warm-cache versus cold-cache behavior.

For each benchmark, record:

| Item | Result |
|---|---|
| Commit and command | |
| Hardware and dependency versions | |
| Scenario and candidate count | |
| Warm-up count | |
| Measured run count | |
| p50 / p95 / p99 runtime | |
| Peak memory | |
| Failures or timeouts | |
| Included and excluded stages | |

Use a small representative Singapore scenario set before estimating how many simulations can be generated within the remaining time.

## 8. Define the immediate-interception baseline

The agreed baseline is to intercept as soon as the missile is detected. Turn that into a deterministic policy:

1. Generate the feasible candidate opportunities known at detection time.
2. Select the earliest feasible opportunity.
3. Define a stable tie-break rule.
4. Define behavior when no opportunity is feasible.
5. Run the same consequence and state-transition model used for the RL policy.
6. Compare complete episodes rather than comparing only the first action.

Record whether “earliest” refers to earliest intercept time, earliest decision time, smallest time-to-go, or another field. This definition must remain fixed across training and evaluation.

## 9. Check training-data suitability

For each simulated transition, confirm that the rollout record can preserve:

- episode, scenario, event, and candidate IDs;
- generator version and random seed;
- observation before the action;
- feasible actions and action mask;
- selected action;
- raw consequence outputs;
- separate reward components and final scalar reward;
- resource and operational state before and after;
- termination or truncation reason;
- simulator, data, and software versions;
- runtime, failure, timeout, and unavailable status; and
- checksums for material inputs and outputs.

All candidates and transitions from one episode must remain in the same training, validation, or test partition.

## 10. Integration and claim gates

Answer these gates after the investigation:

| Gate | Evidence | Result |
|---|---|---|
| Emmanuel's example runs reproducibly | Command, artifact, seed | |
| Candidate consequences have defined meanings and units | Interface table | |
| Geographic effects and operational consequences are connected | Code path and example | |
| Persistent state transitions are defined | Before/after episode state | |
| Runtime permits the planned rollout volume | Benchmark | |
| RL reward uses visible, agreed components | Reward specification | |
| Immediate-interception baseline is executable | Baseline replay | |
| Training and held-out evaluation can be separated | Dataset manifest | |
| Demo claim is supported | Final evaluation report | |

## Work that can proceed before Emmanuel pushes

These pieces can be prepared without guessing his output semantics:

- a seeded Singapore scenario and episode specification;
- a versioned rollout-record format;
- an environment shell with replaceable consequence and transition providers;
- action masking based on the existing candidate and reachability code;
- the deterministic immediate-interception baseline;
- episode replay and train/validation/test manifest tooling;
- an evaluation harness for cumulative reward components, constraint failures, resource use, and latency; and
- tests for reset, step, seeded reproducibility, invalid actions, termination, and recording.

Leave the reward weights, consequence adapter, persistent-effect equations, and final result schema open until Emmanuel's actual interface has been inspected.

## Investigation summary template

```text
Revision inspected:
Component purpose:
Reproduction result:
Accepted input:
Produced output:
Consequence meaning and units:
Geographic-to-consequence mapping:
Persistent state behavior:
Determinism and randomness:
Per-candidate runtime:
Per-scenario runtime:
Per-episode runtime:
Integration approach:
RL-ready pieces:
Missing pieces:
Decisions required from Emmanuel:
Supported demo claim:
```
