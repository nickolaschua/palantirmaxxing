# Emmanuel consequence integration implementation plan

Status: originally implemented as `singapore-demo-v2/1`, now superseded by
`singapore-demo-v2-fixed-rank/2`; retained as the historical plan
and acceptance-gate record.

This document starts **after** the evidence-gathering checklist in
[`emmanuel_investigate.md`](../emmanuel_investigate.md) has been completed. It
lists the code, tests, benchmarks, artifacts and claim gates required to replace
the deterministic toy provider with Emmanuel's consequence model.

Do not begin by copying values out of Emmanuel's example or reimplementing his
formula. First reproduce his code unchanged and freeze its interface, semantics
and example outputs.

## Non-negotiable constraints

- [ ] Keep the existing static evaluator and `planning-result/1` behavior unchanged.
- [ ] Keep candidate generation in `backend.planning.generate_candidate_opportunities()`.
- [ ] Keep the 8-threat, 8-interceptor, 20-candidate action encoding unchanged.
- [ ] Keep the immediate-interception baseline definition unchanged.
- [ ] Use Emmanuel's declared aggregate score directly; do not add another set of reward weights.
- [ ] Preserve the raw score in rollouts and reports even if training normalizes rewards internally.
- [ ] Freeze one objective direction (`minimize` or `maximize`) for a complete run.
- [ ] Define explicit scoring behavior for an unhandled threat.
- [ ] Reject nonfinite scores, missing required fields, ambiguous units and silent fallbacks.
- [ ] Do not present toy-provider artifacts as project results.
- [ ] Do not use “optimal” in the frontend unless bounded-oracle evidence passes.

## Existing integration points

| Existing location | Role | Expected integration work |
|---|---|---|
| `backend/simulation/provider.py` | `ConsequenceProvider` and `ProviderEvaluation` contract | Add Emmanuel adapter; change the protocol only if his required inputs cannot be represented safely. |
| `backend/simulation/engine.py` | Calls assigned, unhandled and aggregate evaluations; applies operational updates | Add a separate transition adapter if Emmanuel does not return persistent state; define timeout/cancellation behavior if calls are external. |
| `backend/learning/environment.py` | Adds at most 16 provider features to the observation | Map only decision-time-visible Emmanuel features; preserve padding and prevent future-information leakage. |
| `backend/learning/training.py` | Currently constructs the toy provider and uses toy-specific filenames/labels | Make provider, scenario generator, artifact prefix and metadata configurable. |
| `backend/learning/evaluation.py` | Can accept a provider factory, but still emits toy-specific report labels | Generalize labels and validate provider/model compatibility before evaluation. |
| `scripts/train_rl.py` | Toy smoke-training entry point | Add an explicit provider/config selection without changing the safe toy default. |
| `scripts/evaluate_rl.py` | Fixed-suite evaluator | Load the provider/config recorded with the model and refuse mismatches. |
| `backend/simulation/recording.py` | Versioned rollout JSONL and replay | Add Emmanuel input/output checksums and any data/model snapshot identifiers required for exact replay. |
| `backend/simulation/scenarios.py` | Synthetic seeded episode generator | Add or adapt a versioned generator that supplies Emmanuel's required Singapore-specific inputs. |
| `backend/simulation/suites.py` | Frozen validation, test, stress and oracle seeds | Preserve seed partitions; version a new manifest if scenario semantics change. |

## Phase 0 — capture and reproduce Emmanuel's delivery

- [ ] Record branch, exact commit, merge base and dirty-worktree status.
- [ ] Save the file list and dependency diff before modifying his code.
- [ ] Preserve his original example input and output byte-for-byte under a test fixture directory.
- [ ] Run his documented setup, example and tests unchanged.
- [ ] Record one successful call and every documented unavailable/failure case.
- [ ] Identify network calls, credentials, local services, caches and mutable global state.
- [ ] Repeat the same seeded call at least twice and compare full outputs.
- [ ] Confirm whether the implementation is safe for repeated, concurrent or batched calls.
- [ ] Complete every finding field in `emmanuel_investigate.md`.

Stop here if his example cannot be reproduced. Do not hide a reproduction failure
inside the provider adapter.

## Phase 1 — freeze the consequence contract

Create a short, versioned interface decision record before writing the adapter.

- [ ] Assign a provider identity and immutable semantic version.
- [ ] Declare exactly one objective direction.
- [ ] Define whether the returned value is a per-event score, episode aggregate, or both.
- [ ] List every score component and its unit, range, source and interpretation.
- [ ] State whether components are additive across candidates, events and assets.
- [ ] Record all built-in priorities and weights so RL does not duplicate them.
- [ ] Define the consequence time horizon for each output.
- [ ] Define required versus optional fields and missing-value behavior.
- [ ] Define unavailable, timeout and internal-error statuses.
- [ ] Define deterministic seeding and any stochastic sampling behavior.
- [ ] Define the input/output schema versions and compatibility policy.
- [ ] Define the model, code, data-snapshot and configuration identifiers used in provenance.
- [ ] Define the cache key from all material inputs and versions.

### Required input mapping

Document the exact source of every Emmanuel input. The adapter will normally
need to map at least:

- episode/scenario ID and seed;
- threat ID, state, detection time and expiry time;
- interceptor ID and state;
- opportunity ID and sample index;
- absolute interception time and assignment lock time;
- interception position and coordinate reference system;
- reachability evidence and required travel time;
- current consumed/reserved resources;
- current operational/asset state;
- hazard or footprint input, including who generates it;
- consequence-data snapshot and model configuration.

No input may be derived from future scheduled threats or other information that
is unavailable at the decision time.

### Required output mapping

Map Emmanuel's output to `ProviderEvaluation` without changing its meaning:

- `raw_score`: the finite, unrounded source score;
- `components`: optional finite diagnostic components, not a second reward;
- `operational_state_update`: a versioned persistent-state update, if supplied;
- `provenance`: provider, model, data, configuration and input identities;
- `runtime_ms`: measured provider runtime with a stated boundary;
- `failure_status`: explicit failure/unavailable/timeout state.

## Phase 2 — implement the provider adapter

Preferred new location: `backend/simulation/providers/emmanuel.py`, with a
package-level public export only after tests pass.

- [ ] Implement `EmmanuelConsequenceProvider` against the reproduced interface.
- [ ] Validate all identifiers, types, units, ranges and coordinate systems before calling Emmanuel's code.
- [ ] Translate `ScheduledThreat`, `AbsoluteCandidate` and operational state into his input without mutating them.
- [ ] Preserve `opportunity_id`, `threat_id`, `interceptor_id`, episode ID and seed through the call.
- [ ] Implement `decision_features()` with at most 16 finite values.
- [ ] Document the order, scale, unit and meaning of all 16 feature positions.
- [ ] Pad unused feature positions in the existing environment; do not expose future threats.
- [ ] Implement `evaluate_assigned()` using the selected candidate's exact absolute time and position.
- [ ] Implement `evaluate_unhandled()` from Emmanuel's explicit rule.
- [ ] Implement `aggregate()` using Emmanuel's aggregate operation exactly once.
- [ ] Reject a changed provider identity, version or objective direction during an episode.
- [ ] Convert returned values to `ProviderEvaluation` without rounding or silent defaults.
- [ ] Retain source component names and units in provenance or the contract document.
- [ ] Add an in-process, CLI or service boundary only as established in Phase 1.

If Emmanuel evaluates every candidate in one batch, add a provider-owned cache
or batch adapter keyed by the complete scenario/model identity. Do not move
provider-specific caching into the Gymnasium environment.

## Phase 3 — implement persistent operational transitions

First determine whether Emmanuel returns the complete next operational state,
a patch/delta, or only a single-event score.

### If Emmanuel returns state updates

- [ ] Specify whether updates replace state, shallow-merge keys or apply a typed patch.
- [ ] Replace the current implicit shallow `dict.update()` behavior if nested state exists.
- [ ] Validate state schema and version before and after every update.
- [ ] Preserve immutable audit evidence for the pre-state, update and post-state.
- [ ] Test recovery/downtime timestamps across multiple later events.

### If Emmanuel returns only single-event scores

- [ ] Add a separate, versioned transition-provider protocol.
- [ ] Implement an adapter that derives only transitions explicitly agreed with Emmanuel.
- [ ] Keep transition equations out of the training loop and policy code.
- [ ] Record transition ownership, assumptions, units and provenance separately from score provenance.
- [ ] Test that the same transition adapter is used for RL, baseline and oracle evaluation.

Do not infer aircraft recovery, downtime accumulation, asset loss or replacement
behavior from a score alone.

## Phase 4 — failure, timeout and cache behavior

- [ ] Establish a measured provider timeout rather than choosing one arbitrarily.
- [ ] Convert timeouts to explicit truncation and failure records.
- [ ] Never turn a provider failure into a zero score.
- [ ] Reject NaN, infinity, missing required values and unknown enum values.
- [ ] Reject objective-direction changes within or across a model artifact.
- [ ] Include all material inputs, model/data versions and seed in cache keys.
- [ ] Verify cold-cache and warm-cache outputs are identical.
- [ ] Ensure failed or partial calls are not cached as successful outputs.
- [ ] Verify cache concurrency and corruption behavior if rollouts run in parallel.
- [ ] Record provider runtime separately from candidate generation, encoding and policy inference.

## Phase 5 — make training and loading provider-agnostic

The current training path deliberately hardcodes the toy provider. Generalize it
without removing the toy smoke path.

- [ ] Add a provider factory/config argument to `train_maskable_ppo()`.
- [ ] Add a scenario-generator/config argument compatible with Emmanuel's inputs.
- [ ] Replace `maskable_ppo_toy` with a provider/model-specific artifact name.
- [ ] Replace the hardcoded `plumbing validation only` metadata for non-toy runs.
- [ ] Record provider identity, version, objective direction and config checksum in training metadata.
- [ ] Record scenario generator and data snapshot versions.
- [ ] Save the exact observation layout/version and normalization statistics.
- [ ] Make `load_normalized_policy()` validate model/provider/layout compatibility.
- [ ] Keep raw scores out of normalization artifacts and available in evaluation records.
- [ ] Add explicit CLI configuration for toy versus Emmanuel providers.
- [ ] Fail closed if the requested provider cannot be constructed.

## Phase 6 — generate compatible scenarios

- [ ] Identify which Emmanuel inputs vary across episodes and which are fixed data snapshots.
- [ ] Add the minimum scenario fields necessary to supply those inputs.
- [ ] Preserve continuous detections, simultaneous threats, scarcity and later arrivals.
- [ ] Keep all candidates and transitions from an episode in one data partition.
- [ ] Freeze training, validation, held-out test, stress and oracle manifests before final training.
- [ ] Prevent duplicate scenarios across partitions using canonical input hashes, not seed comparison alone.
- [ ] Record the generator version and material source-data versions in every episode.
- [ ] Check generated distributions for impossible or degenerate scenarios.
- [ ] Confirm all decision-time observation features are available without leakage.

If Emmanuel's component accepts only a static footprint rather than a candidate,
implement and validate the candidate-to-footprint stage as its own versioned
adapter. Do not imply that Emmanuel's model generated the footprint if it did not.

## Phase 7 — adapter and equivalence tests

Add focused unit tests and fixtures before retraining.

- [ ] Original example input through Emmanuel's original entry point equals the frozen output.
- [ ] The same example through `EmmanuelConsequenceProvider` has the same raw aggregate score.
- [ ] Every mapped identifier, time, position and unit reaches the original component unchanged.
- [ ] Assigned-candidate scoring matches the original implementation.
- [ ] Unhandled-threat scoring matches the agreed rule.
- [ ] Aggregate scoring neither drops nor double-counts event results.
- [ ] Operational updates produce the expected before/after state.
- [ ] Seeded stochastic output reproduces exactly where promised.
- [ ] Missing required values fail explicitly.
- [ ] NaN and infinity fail explicitly.
- [ ] Ambiguous or wrong units fail explicitly.
- [ ] Provider identity/version/direction changes fail explicitly.
- [ ] Timeout and unavailable responses truncate with the correct reason.
- [ ] Decision features never include hidden future-threat data.
- [ ] Result provenance and input/output checksums survive JSONL serialization and replay.

Keep Emmanuel's original tests unchanged. Adapter tests are additional tests, not
replacements.

## Phase 8 — end-to-end simulator regression tests

Run both the toy provider and Emmanuel provider through the same simulator tests.

- [ ] Gymnasium environment checker passes.
- [ ] Action masks remain correct for reachability, reservations, locks, expiry and padding.
- [ ] No duplicate, invalid or post-lock assignment occurs.
- [ ] One-use interceptors remain consumed.
- [ ] Simultaneous events keep deterministic ordering.
- [ ] Future threats remain absent from observations and provider features.
- [ ] Raw score and direction-derived terminal reward are both correct.
- [ ] Provider failures and event-limit exhaustion truncate explicitly.
- [ ] Rollout replay reproduces observations, masks, actions, state and score.
- [ ] Immediate baseline and RL policy use the same provider and transition behavior.
- [ ] Existing backend unit/integration suites remain unchanged and pass.
- [ ] Existing static evaluator output remains byte-for-byte or semantically unchanged as appropriate.

## Phase 9 — benchmark before selecting a training budget

Benchmark on the target machine with the exact Emmanuel commit and data snapshot.

- [ ] One candidate, cold cache.
- [ ] One candidate, warm cache.
- [ ] All candidates for one scenario, cold and warm cache.
- [ ] One complete episode, cold and warm cache.
- [ ] Full 8-threat by 8-interceptor stress episode.
- [ ] Serialization or service-call overhead, if applicable.
- [ ] Candidate generation, observation encoding, action masking and inference together.
- [ ] Peak memory, failure count and timeout count.
- [ ] p50, p95 and p99 with warm-up count and measured-run count recorded.

Keep p95 environment-step time as a diagnostic. Calibrate completed PPO timesteps
with the same provider, environment, normalization, seed and rollout configuration
as the real training run. Use measured PPO milliseconds per timestep to estimate
a whole-rollout count for a 60% training allocation, reserving 20% for held-out
evaluation and 20% for reruns and demo integration. This is a best-effort estimate,
not a deadline; calibration/setup cost is additional. Record requested/effective
steps, calibration throughput, estimated/actual duration and allocation overrun
or underrun in the training metadata.

## Phase 10 — train and evaluate

- [ ] Run the toy smoke path once to confirm plumbing still works.
- [ ] Train a fresh Emmanuel-provider policy; do not reuse toy normalization statistics or weights as final evidence.
- [ ] Save model, normalization statistics, configuration and dependency versions together.
- [ ] Evaluate deterministically on 64 fixed validation episodes.
- [ ] Make tuning decisions using validation only.
- [ ] Evaluate once on 256 held-out episodes after tuning is frozen.
- [ ] Run the 32 full-capacity stress episodes.
- [ ] Run the 32 bounded-oracle episodes, capped at three threats, three interceptors, five candidates and 100,000 sequences.
- [ ] Replay the immediate-interception baseline on the identical episode specs.
- [ ] Record invalid-action, duplicate-assignment, post-lock and truncation counts.
- [ ] Calculate bootstrap confidence intervals from episode-level favorable differences.
- [ ] Calculate normalized regret only where the oracle is exact and strictly better than the baseline; retain ineligibility reasons and leave the gate false if no episodes qualify.

## Phase 11 — artifacts and reporting

Every final model, rollout and report must record:

- episode/scenario/event/candidate IDs;
- scenario seed and canonical scenario hash;
- action mask and selected action;
- assignments before and after;
- raw event and aggregate scores;
- diagnostic components without treating them as extra reward;
- operational state before, update and after;
- provider/model/config/data versions;
- score direction;
- simulator, scenario-generator and policy versions;
- input/output checksums;
- provider and complete decision-path timings;
- failure, timeout, termination and truncation reasons.

Store generated artifacts under ignored `data/results/rl/` paths. Check in only
small contracts, manifests, fixtures and reviewed summary evidence that the team
intends to version.

## Phase 12 — acceptance and frontend integration

Do not present the policy as an improvement until all applicable gates pass:

- [ ] Zero invalid, duplicated or post-lock assignments.
- [ ] Policy wins on at least 60% of 256 held-out episodes.
- [ ] Mean raw aggregate score improves by at least 5% in the declared direction.
- [ ] Bootstrap 95% confidence interval for favorable improvement excludes zero.
- [ ] Median normalized regret is at most 10% of the baseline-to-oracle gap on eligible oracle episodes.
- [ ] Candidate generation, encoding, masking and inference together have p95 below 100 ms on the target M5 Pro.
- [ ] Every result has complete scenario, model, provider, direction and simulator provenance.
- [ ] Emmanuel equivalence tests pass against his unchanged examples and tests.

Only after those gates:

- [ ] Define the frontend result schema from actual provider outputs.
- [ ] Export the selected policy's result with provider and model provenance.
- [ ] Display raw consequence meaning, units and limitations.
- [ ] Use “optimal” only if bounded-oracle evidence supports it; otherwise state that the policy improves cumulative simulated outcomes over the fixed immediate-interception baseline.
- [ ] Keep a visible “simulated” qualification and do not imply observed real-world validation.

## Questions that must be answered with Emmanuel

1. What exact object does his component accept: candidate, point, footprint, scenario or batch?
2. Does it generate geographic effects or require them as input?
3. What does every output mean, in what unit and over what time horizon?
4. Is there one aggregate score, and is lower or higher better?
5. Which weights or priorities are already embedded in that score?
6. How is an unhandled threat scored?
7. Does a result include persistent downtime or operational-state transitions?
8. If not, who owns and approves the transition equations?
9. What randomness exists and how is it seeded?
10. What does missing, unavailable, partial or timeout output look like?
11. Which model, dataset and configuration versions identify a result?
12. Are calls deterministic, thread-safe, batchable and cacheable?
13. Which features are genuinely known to the policy at decision time?
14. What are the expected cold/warm runtimes and memory requirements?
15. Which original examples and tests are authoritative for adapter equivalence?

## Suggested pull-request sequence

1. **Reproduction evidence:** frozen fixtures, interface decision record and unchanged original tests.
2. **Provider adapter:** exact input/output mapping, validation, equivalence tests and failure behavior.
3. **State transitions:** provider updates or a separately owned transition adapter.
4. **Generic pipeline:** configurable training/loading/evaluation and provenance-complete recording.
5. **Scenario compatibility:** versioned inputs and frozen split manifests.
6. **Performance evidence:** cold/warm benchmarks and wall-clock training budget.
7. **Training and evaluation:** model artifacts, held-out report, oracle regret and constraint audit.
8. **Demo integration:** frontend schema and claim language gated by the final evidence.

Each pull request should leave the toy provider runnable as a regression fixture
and should pass the existing static evaluator tests.

## Final handoff record

Complete this before demo integration:

```text
Emmanuel branch and commit:
Adapter version:
Provider identity/version:
Objective direction:
Input/output schema versions:
Data/model/config snapshots:
Unhandled-threat rule:
Persistent-state owner:
Cold/warm benchmark artifact:
Training command and budget:
Model and normalization artifacts:
Validation report:
Held-out report:
Stress report:
Oracle report:
Constraint-audit result:
Supported frontend claim:
Known limitations:
```

## Implemented MVP status — 2026-09-26

The additive implementation now uses adapter version `singapore-demo-v2-fixed-rank/2`,
provider identity `singapore-consequence-provider`, minimize direction,
`simulation-episode/2`, `centralized-observation/2`, and `simulation-result/1`.
Unhandled threats are explicit constraint failures and persistent operational
updates remain empty; interceptor lock/consumption is the only persistent state
change. The current checked frontend result is a baseline episode, not a trained
policy claim.

See `docs/singapore-simulation-integration.md` for the exact schema behavior,
commands, checksums, benchmark values, smoke artifact, test totals, and remaining
evaluation gates.
