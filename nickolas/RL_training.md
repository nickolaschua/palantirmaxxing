# RL training plan: diverse Singapore scenarios to an evaluated policy

Updated 26 September 2026 against the current repository state.

## 1. Purpose and immediate execution boundary

This document is the implementation and evaluation plan for moving from the
current deterministic Singapore simulator to a trained reinforcement-learning
policy whose performance can be compared honestly with naive interception.

The immediate work boundary is deliberately limited to the first three steps:

1. freeze the policy question and supported claim;
2. define and implement a judge-readable scenario-diversity model; and
3. build the scenario audit that proves the generated cases occupy a useful
   middle ground between a toy problem and an impossible problem.

Training should not begin until those three steps have produced an accepted,
versioned scenario distribution and audit report. The remainder of this document
records the full path so early design choices do not make later training or
evaluation invalid.

The project is a simulation and decision-support demonstrator. Its threat,
interceptor, footprint, casualty, and service-effect parameters are synthetic or
assumption-grade unless separately identified. A learned policy can demonstrate
optimization inside this versioned environment. It cannot validate the physical
or operational realism of the environment that generated its feedback.

## 2. Executive decision

The first policy claim will be:

> Given only threats detected so far, select feasible interception assignments
> using finite one-use interceptor resources, handle every threat when the
> episode is declared fully feasible, and minimize the versioned assumption-grade
> consequence objective relative to a naive launch-on-detection policy.

The main comparison is the naive online policy, because it receives the same
information available to the learned agent. The existing full-episode feasible
matching and exact fixed-rank optimizer remain reference methods:

- the naive online baseline answers whether learning improves on an obvious
  launch-immediately strategy;
- the full-episode feasible matcher checks whether a complete assignment exists;
- the exact fixed-rank optimizer supplies a clairvoyant lower cost bound within
  its declared mathematical scope;
- the learned policy is judged on what it can do online, without future threat
  details in its observation.

This distinction must appear in code, reports, frontend wording, and the demo.
An offline optimizer with access to the whole episode is not a fair online
baseline, although it is useful for measuring regret.

## 3. What is already implemented

The repository already contains the major architectural pieces:

- `SingaporeScenarioGenerator` creates reproducible seeded episodes;
- `SimulationEngine` processes detection, tentative assignment, cancellation,
  assignment lock, resource consumption, interception, expiry, and termination;
- `SingaporeConsequenceProvider` supplies fixed candidate assessments and the
  normalized ordinal training cost;
- `CentralizedInterceptionEnv` exposes the simulator as a masked Gymnasium
  environment;
- MaskablePPO training, normalization persistence, model loading, rollout replay,
  and evaluation utilities exist;
- `FeasibleImmediateMatchingPolicy` supplies the existing full-episode matching
  comparator;
- `OptimalFixedRankAssignmentPolicy` exactly minimizes the frozen additive
  ordinal objective within its documented scope;
- fixed validation, held-out, stress, bounded-oracle, and assignment-reference
  seed partitions exist in code;
- `simulation-result/1`, HTTP publication, run jobs, and the frontend can render
  a generated eight-threat episode.

The current Singapore generator varies detection positions, terminal positions,
detection times, altitudes, interceptor positions, and interceptor headings by
seed. It nevertheless fixes eight threats, eight interceptors, 20 candidates per
pair, one speed per class, one consequence condition, a 100 m supplied area, and
complete matchability. It resamples unmatched threats until a complete
consequence-eligible matching exists.

The current Singapore MaskablePPO artifact contains only 16 training steps. It is
a save/load/inference smoke test, not an optimized policy.

### 3.1 Preliminary learnability evidence

A diagnostic run over validation seeds 10000 through 10019 compared the existing
naive-time full-episode matcher with the exact fixed-rank optimizer:

| Measure | Result |
| --- | ---: |
| Episodes | 20 |
| Exact optimizer strictly better | 20/20 |
| Equal outcomes | 0/20 |
| Mean absolute ordinal-cost reduction | 0.9221 |
| Mean relative reduction | 46.63% |
| Minimum absolute reduction | 0.1886 |
| Maximum absolute reduction | 2.3785 |

This is encouraging because the current scenarios contain consequence trade-offs.
It is not evidence that an online learned policy can obtain the same improvement:
the exact optimizer sees the complete future episode, while the learned policy
does not. The scenario audit and online baseline are required to answer that
question.

## 4. Step 1: freeze the policy question

### 4.1 Decision point

The first policy is an online resource-allocation policy. At each decision epoch
it observes detected threats, available resources, current assignments, feasible
candidate opportunities, and consequence features. It may assign, cancel a
tentative assignment, or advance the event clock.

It does not observe future threat content before detection. The current
environment already zero-fills scheduled future threats and marks their presence
as false. This behavior must remain covered by regression tests.

### 4.2 Primary constraint and optimization objective

For core training, validation, and held-out suites:

1. every generated episode is certified as completely matchable;
2. handling all threats without constraint violations is mandatory;
3. among valid complete episodes, lower summed ordinal consequence cost is better;
4. expected casualties, population exposure, site effects, and ordinal training
   cost remain separately reported and are never presented as one physical unit.

The current maximum valid complete cost is eight: eight resolved events, each
with a normalized cost in `[0, 1]`. The unhandled-threat cost of 9.0 therefore
makes any constraint failure worse than any valid complete outcome. This ordering
must be tested whenever the objective or episode capacity changes.

### 4.3 Information boundary

The learned policy and primary naive baseline must have identical information:

- detected threats only;
- current simulation time;
- currently available interceptors;
- tentative and locked assignments;
- feasible candidate geometry, timing, and consequence features;
- current provider summary features;
- no future threat positions, detection times, terminal locations, or candidate
  assessments.

The exact optimizer and full-episode matching reference may see the full episode,
but reports must label them `offline` or `clairvoyant`.

### 4.4 Supported claim

If the final gates pass, the supported claim is:

> Across a frozen set of reproducible synthetic Singapore scenarios, the learned
> online policy completed feasible episodes without constraint violations and
> achieved lower assumption-grade ordinal consequence cost than the defined
> naive online interception policy. Performance was also measured against a
> clairvoyant exact fixed-rank reference.

The claim does not cover real interception performance, validated casualty
prediction, physical optimality, or operational deployment.

### 4.5 Judge-ready answer

If judges ask what the agent learns, the short answer is:

> It learns when and where to commit finite interceptors as threats arrive. An
> immediate locally attractive launch can consume the resource needed by a later
> threat. The agent is rewarded for completing the episode while reducing the
> simulator's versioned consequence rank relative to a naive launch-immediately
> strategy.

## 5. Step 2: scenario-diversity model

### 5.1 Principle: structured diversity, not random noise

The generator must describe a distribution of decision problems, rather than a
single fixture with different random coordinates. Each dimension below needs:

- a name a judge can understand;
- a precise sampling rule;
- a value recorded in episode metadata;
- an audit metric;
- an explicit statement of whether it is included in training, reserved for
  stress/OOD evaluation, or deferred.

The first two-day implementation should change the decision structure without
claiming new physical realism. Timing, geometry, contention, and consequence
placement are appropriate first dimensions. Detailed physics, failures, and
uncertain sensing are later environment versions.

### 5.2 Dimensions considered

This table is the canonical answer to “what dimensions did you consider?”

| Dimension | What varies | Why it affects the decision | First two-day scope | Audit evidence |
| --- | --- | --- | --- | --- |
| Active threat count | Number of active threats within the fixed maximum of eight | Changes episode length and resource competition | Include 2–8 for curriculum; final benchmark retains full 8-threat cases | Count histogram and profile coverage |
| Active interceptor count | Number of available resources within the fixed maximum of eight | Controls scarcity and matching flexibility | Include counts sufficient for complete core episodes; reserve true shortage for later | Resource/threat ratio and complete-matching result |
| Detection cadence | Spaced, mixed, burst, and near-simultaneous detections | Determines how much can be committed before later threats become visible | Include | Detection gaps, burst sizes, maximum concurrent active threats |
| Ingress position | Detection point around the 10 km buffered Singapore boundary | Changes heading, reachability, and which interceptors have useful geometry | Include | Angular-sector coverage and spatial entropy |
| Terminal position | Destination within the main island | Changes time-to-impact and consequence geography | Include stratified geographic and consequence sampling | Grid/region coverage and consequence-band counts |
| Ingress pattern | Distributed, clustered corridor, and opposing directions | Creates different forms of resource contention | Include as named profiles | Pairwise bearing concentration and profile identity |
| Flight duration | Derived from detection-to-terminal distance and scenario speed | Controls the available reaction window | Include short/medium/long strata using geometry; keep the current speed assumption initially | Duration quantiles and band counts |
| Altitude | Initial height sampled within the declared synthetic range | Changes the displayed 3D trajectory and vertical timing | Retain existing range; do not claim altitude-aware interception | Altitude histogram and terminal invariant |
| Interceptor position | Resource launch position within Singapore | Changes which threats each resource can reach | Include distributed and clustered layouts | Spatial coverage and per-resource feasible-edge count |
| Interceptor heading | Initial heading | Changes bounded-curvature path length and reachability | Include | Circular distribution and turn-path statistics |
| Reachability margin | Time margin after required travel | Distinguishes forgiving from time-critical assignments | Include easy, mixed, and low-slack bands | Margin quantiles and proportion near zero |
| Matching redundancy | Number and structure of complete threat-resource matchings | Measures whether one poor assignment can block the episode | Include high, medium, and low redundancy while keeping core suites feasible | Edge density, degree distribution, critical edges, matching-removal tests |
| Consequence separation | Difference between good and bad candidate costs | Determines whether location choice materially matters | Include weak, medium, and strong trade-off bands | Baseline–optimizer gap and candidate-cost spread |
| Population/site context | Whether candidates intersect population or available site layers | Produces varied consequence evidence | Include through stratified terminal/candidate geography | Exposure bands, intersected-site counts, unavailable-data counts |
| Time condition | Weekday/weekend and time-of-day profile | Changes site occupancy and consequence assumptions | Defer until every selected sector has coherent profiles | Condition coverage and provider identity |
| Footprint geometry | Radius and shape of the supplied affected area | Changes exposure and site intersections | Keep the supplied 100 m circle fixed for the first trained policy | Contract equality and geometry checksum |
| Threat speed/class | Kinematics and trajectory family | Changes time pressure and feasibility | Keep one synthetic class initially; reserve varied classes for OOD/later versions | Configuration identity |
| Interceptor class | Speed, turn rate, and resource cost | Introduces heterogeneous resource choice | Defer; current policy uses one synthetic class | Configuration identity |
| Sensor uncertainty | Position, velocity, and timing noise | Tests robustness to imperfect observations | Defer until noise semantics and truth/observation separation are designed | Calibration and perturbation report |
| Trajectory updates | Course changes after detection | Requires dynamic candidate regeneration and replanning | Defer to a new simulator version | Update/replanning tests |
| Resource failure | Failed launch, failed lock, or unavailable resource | Requires recovery and new termination semantics | Defer to a new simulator version | Failure-injection suite |
| Infeasible episodes | Fewer usable resources than threats or no complete matching | Changes the objective from completion to prioritization | Exclude from core v2; design separately after priority semantics are approved | Explicit infeasible-suite label and reason |

### 5.3 Named scenario profiles

Named profiles make the distribution explainable and allow failures to be traced
to a recognizable case family. Proposed profiles are:

| Profile | Purpose | Characteristics | Split use |
| --- | --- | --- | --- |
| `warmup` | Teach valid actions and episode completion | 2–3 threats, extra resources, spaced detections, high matching redundancy | Curriculum training only |
| `balanced` | Typical online allocation | 4–6 threats, mixed cadence, distributed geometry, medium redundancy | Training and validation |
| `full-standard` | Current product-shaped case | 8 threats, 8 resources, mixed cadence, complete matching | Training, validation, held-out |
| `burst-contention` | Make early resource commitment matter | 6–8 threats, clustered detection times, overlapping reachability, medium/low redundancy | Training, validation, stress |
| `low-slack` | Test time-critical choices | 8 threats, short margins, few interchangeable assignments, complete matching retained | Limited training; prominent stress coverage |
| `consequence-contrast` | Ensure a useful optimization signal | Candidates deliberately span consequence bands while remaining feasible | Training and validation |
| `geographic-shift` | Test spatial generalization | Reserved ingress or terminal sectors, or held-out spatial strata | OOD only |
| `cadence-shift` | Test temporal generalization | Detection patterns outside the training mixture | OOD only |

Profile names describe the decision structure, not real threat doctrine.

### 5.4 Goldilocks-zone definition

The desired distribution lies between two failure modes.

#### Too easy

- almost every interceptor can serve every threat;
- earliest interception is also lowest consequence;
- naive and exact policies produce nearly identical costs;
- detection timing has no effect on later choices;
- action masks contain many interchangeable actions;
- the learned policy can succeed by always selecting the first valid action.

#### Too hard or impossible

- core episodes lack a complete matching;
- almost all actions are invalid;
- one unavoidable early decision determines failure before the agent has useful
  information;
- time margins are so short that only one action is ever available;
- reward is dominated by the 9.0 failure penalty;
- scenario rejection or repair consumes most generation attempts.

#### Useful learning region

- every core episode has at least one complete matching;
- multiple actions are initially feasible, but they are not interchangeable;
- naive launching completes most or all core episodes;
- a measurable consequence gap exists between naive and exact reference policies;
- some choices consume resources needed by later detected threats;
- the policy can infer better choices from observable state;
- no single geographic cell, cadence pattern, or consequence band dominates the
  training corpus;
- low-slack episodes are present but do not overwhelm early learning.

### 5.5 Provisional acceptance bands

The first large audit will calibrate and then freeze exact thresholds. Before
training, the following provisional requirements should be replaced by observed,
reviewed values rather than silently weakened:

- 100% of core training/validation/held-out scenarios are certified completely
  matchable;
- 100% deterministic regeneration by seed/profile/version/hash;
- zero duplicate canonical episode hashes across frozen evaluation splits;
- a positive naive-to-exact cost gap in at least half of full-size core cases;
- median relative naive-to-exact improvement of at least 10% in the full-size
  audit, ensuring a nontrivial optimization opportunity;
- each named core profile contributes enough cases to report its own results;
- stress cases may have lower redundancy and shorter margins but remain feasible;
- OOD cases are generated by a declared held-out dimension, not by arbitrary
  hand selection after seeing policy results;
- generator retries, profile failures, and exclusions are reported rather than
  discarded invisibly.

The preliminary 20-seed result exceeds the two cost-gap thresholds, but the full
audit must cover many more seeds and profile strata.

### 5.6 Versioning and implementation design

Do not mutate the meaning of `singapore-scenario/1`. Preserve it as the checked
seed-7 frontend fixture and regression path.

Implement a new distribution and generator identity, tentatively:

- `singapore-scenario-distribution/1` for the profile mixture and sampling rules;
- `singapore-scenario/2` for generated episodes;
- `simulation-episode/3` only if the episode schema must gain required fields;
  otherwise retain the episode schema and record additive profile metadata;
- a distribution checksum covering every range, categorical weight, profile
  definition, source checksum, and generator version.

The current observation capacity already supports up to eight threats,
eight interceptors, and 20 candidates per pair, including explicit presence
masks. Variable active counts should use those masks rather than changing model
dimensions.

Proposed code organization:

```text
backend/simulation/
  scenario_distribution.py       # profile definitions and deterministic selection
  singapore_scenario.py           # preserve v1 behavior
  singapore_scenario_v2.py        # v2 generation and profile-aware validation
  suites.py                       # frozen split/profile manifests
scripts/
  audit_scenarios.py              # distribution and learnability report
```

The final file layout can be consolidated if that reduces duplication, but v1
behavior and identity must remain stable.

## 6. Step 3: scenario audit and learnability report

### 6.1 Purpose

The audit is the evidence that the generator produces varied, solvable, and
decision-relevant scenarios. It must run before significant RL training and be
re-runnable from the repository.

The audit should answer:

1. Are scenarios reproducible and unique?
2. Do the selected profiles cover the intended dimensions?
3. Are core episodes solvable?
4. Do they contain multiple meaningful choices?
5. Does naive launching leave room for improvement?
6. Are stress and OOD cases difficult for the reason their labels claim?
7. Is generation fast enough for the planned training budget?

### 6.2 Proposed command and outputs

```sh
.venv-rl/bin/python scripts/audit_scenarios.py \
  --distribution singapore-scenario-distribution/1 \
  --episodes 1000 \
  --output data/results/rl/scenario-audit-v2.json \
  --summary docs/specifications/rl-scenario-audit.md
```

The JSON is the machine-readable evidence. The Markdown summary is the
judge-readable explanation and must contain the canonical dimensions table,
profile definitions, observed distributions, exclusions, and limitations.

### 6.3 Per-episode audit record

Each audited episode should record at least:

- scenario reference;
- seed;
- profile identity;
- generator and distribution versions/checksums;
- canonical episode hash;
- threat and interceptor counts;
- detection times and gap statistics;
- ingress-sector and terminal-region identifiers;
- duration and altitude summaries;
- feasible threat-interceptor edge count;
- per-threat and per-interceptor graph degrees;
- complete-matching status;
- matching redundancy proxy;
- minimum/median candidate time margins;
- candidate consequence-cost spread;
- unavailable or partial-coverage counts;
- naive baseline termination, cost, and latency;
- exact reference termination, predicted cost, replayed cost, exactness, and
  latency;
- absolute and relative naive-to-exact gap;
- generator attempts and repair count.

### 6.4 Matching-difficulty metrics

Counting feasible edges alone is inadequate. Two graphs can contain the same
number of edges while having very different allocation difficulty. The audit
should calculate:

- threat degree distribution;
- interceptor degree distribution;
- whether any threat or resource has degree one;
- critical assignment edges whose removal destroys complete matchability;
- the number of single-edge removals the graph tolerates;
- an exact matching count when cheap, otherwise a capped count or deterministic
  redundancy proxy;
- the cost gap between the best and second-best complete assignments where
  tractable;
- whether the naive first commitment removes every optimal completion.

These measures describe the resource-allocation problem more directly than raw
coordinate randomness.

### 6.5 Spatial and temporal coverage

The audit should use fixed, versioned bins rather than bins chosen after results
are observed:

- angular sectors around the buffered detection boundary;
- a coarse Singapore grid or planning-area grouping for terminal points;
- detection-gap bands;
- flight-duration bands;
- time-margin bands;
- consequence-cost-spread bands;
- matching-redundancy bands.

Report raw counts, percentages, and empty bins. Do not hide sparse cells behind a
single entropy score.

### 6.6 Learnability checks before PPO

The exact reference makes several cheap tests possible before training:

- measure how often exact cost is strictly lower than naive cost;
- measure the size and distribution of that improvement;
- group improvement by scenario profile;
- verify improvement is not confined to one geographic region;
- test whether an online consequence-greedy baseline captures most of the gap;
- identify cases where future hidden information makes the offline optimum
  unattainable online;
- confirm the observation contains the features needed to distinguish better
  currently available actions.

If naive and exact are usually equal, increase resource contention or consequence
contrast. If exact is dramatically better but all useful decisions require hidden
future information, adjust the scenario timing or define realistic prior/context
features. Do not interpret an impossible information gap as an RL failure.

### 6.7 Tests required for Steps 1–3

- same seed + profile + version produces byte-identical episode JSON and hash;
- different seeds produce different canonical hashes across an audited sample;
- named profiles satisfy their declared structural predicates;
- all core profiles produce complete matchings;
- stress profiles remain feasible unless explicitly labelled infeasible;
- variable active counts populate presence masks correctly;
- future threats remain zero-filled and absent before detection;
- generator repair changes only the documented threat stream;
- audit metrics are deterministic;
- naive and exact replayed costs match their reported costs;
- report aggregation counts every generated, rejected, and repaired episode;
- v1 seed-7 output remains unchanged.

### 6.8 Completion gate for the current work boundary

Steps 1–3 are complete only when:

- this policy claim is accepted;
- the dimensions and initial profile set are accepted;
- v2 scenarios are reproducible and versioned;
- a 1,000-episode audit report exists;
- provisional Goldilocks thresholds are replaced by frozen observed thresholds;
- every exclusion and generator retry is visible;
- v1 regression artifacts remain unchanged;
- no RL training result is being used to tune the held-out distribution.

## 7. Frozen scenario splits

Split design follows Steps 1–3, but it is recorded now because scenario identity
and frontend auditability must be designed together.

### 7.1 Split roles

| Split | Proposed size | Used for | May influence development? |
| --- | ---: | --- | --- |
| Training | Procedural/unbounded seeds | PPO interaction | Yes |
| Validation | 64+ frozen scenarios | Checkpoints, curriculum promotion, hyperparameters | Yes |
| Held-out | 256 frozen scenarios | One final generalization assessment | No |
| Stress | 32+ frozen scenarios | Burst, low-slack, low-redundancy robustness | Not for model selection |
| OOD geography | 64 frozen scenarios | Held-out spatial sectors/regions | No |
| OOD cadence | 64 frozen scenarios | Held-out arrival patterns | No |
| Bounded oracle | 32 small scenarios | Exhaustive online-action reference | No |
| Full assignment reference | 64 eight-threat scenarios | Exact fixed-rank regret | No |

Exact sizes should be confirmed against generation and evaluation runtime. Split
roles must not change after seeing model outcomes.

### 7.2 Scenario reference

Every frozen scenario must receive an immutable reference such as:

```text
sg2:validation:000017
sg2:held-out:000203
sg2:stress:burst-contention:000011
```

The manifest entry resolves that reference to:

- seed;
- profile;
- generator version;
- distribution version and checksum;
- provider/configuration identity;
- canonical episode hash;
- split and ordinal index;
- expected feasibility classification.

Regeneration must verify the hash before simulation. A hash mismatch is a hard
failure, not a warning.

### 7.3 Leakage discipline

The frontend and backend may technically load any scenario reference. Process
discipline still matters:

- use training and validation references during development;
- use stress cases for robustness diagnosis without selecting the final
  checkpoint around one favorable stress result;
- do not inspect held-out outcomes while tuning the generator, reward,
  hyperparameters, or checkpoint;
- open held-out results only after the final policy identity is frozen;
- if held-out results cause any change, version a new experiment and treat the
  previous held-out suite as development data.

## 8. Frontend scenario auditability

The user must be able to open a specific generated scenario, inspect it, and
reproduce what the policy and baselines did.

### 8.1 Required workflow

1. Choose or enter a scenario reference.
2. Backend resolves it through the frozen manifest.
3. Backend regenerates the episode and verifies its canonical hash.
4. Choose `naive`, `learned`, or a labelled offline reference policy.
5. Run the episode and publish an immutable result snapshot.
6. Frontend loads the exact result ID, not `latest`.
7. Frontend displays scenario identity, split, profile, seed, generator version,
   episode hash, policy identity, and publication identity.
8. The map shows trajectories, detections, assignments, selected areas,
   consequences, and termination evidence.

### 8.2 Minimal two-day interface

The smallest useful interface is a “Scenario audit” section containing:

- scenario-reference input;
- policy selector limited to installed named policies;
- Run button;
- visible validation/hash failure;
- exact result identity;
- profile and split badge;
- links or buttons for the naive and learned results for the same scenario.

The backend should accept a manifest scenario reference, not arbitrary paths or
arbitrary configuration JSON. This preserves the existing fixed-command security
boundary and makes every run reproducible.

### 8.3 Result requirements

The result payload or delivery metadata must include:

- scenario reference;
- split and profile;
- seed;
- generator/distribution identities;
- canonical episode hash;
- policy and model identities;
- naive baseline cost;
- learned policy cost;
- exact reference cost when available;
- relative improvement and regret;
- limitations and whether the comparator is online or clairvoyant.

The current `simulation-result/1` seed-7 artifact remains stable. Additive audit
metadata may fit a new result version if required fields or comparison semantics
change.

## 9. Reward and environment audit

Before training:

- verify assignment and cancellation remain zero-reward state changes;
- emit consequence cost only when an outcome resolves;
- preserve the 9.0 constraint penalty ordering for an eight-threat episode;
- reject nonfinite observations, rewards, and provider outputs;
- confirm invalid actions are masked and still rejected if submitted externally;
- confirm a policy cannot obtain a better return by causing truncation;
- confirm episode reward equals signed aggregate replayed cost;
- report raw physical components separately from the ordinal learning objective;
- freeze observation layout, normalization, provider, generator, and dependency
  identities in every model artifact.

Do not change reward weights because one trained run looks disappointing. A
reward change creates a new experiment version and invalidates comparisons with
earlier models.

## 10. Primary baseline: naive online interception

The main baseline should be simple, online, deterministic, and use the same
information as the agent.

Proposed identity: `naive-launch-on-detection/1`.

At each event epoch:

1. inspect detected active threats in stable detection/ID order;
2. for each unassigned threat, find currently valid candidates using only
   currently unconsumed resources;
3. select the earliest interception time;
4. break ties by greater time margin, then stable interceptor/candidate IDs;
5. assign immediately;
6. do not cancel or revise the assignment unless the environment forces a
   failure transition in a later simulator version;
7. advance when no immediate assignment remains.

It does not inspect future threats and does not use consequence cost to choose an
action. This is the intuitive “detect and launch the first feasible interceptor”
story the learned agent must beat.

Keep the existing methods under distinct labels:

- `naive-launch-on-detection/1`: primary fair online baseline;
- `feasible-immediate-matching/1`: offline full-episode feasibility/time
  comparator;
- `optimal-fixed-rank-assignment/1`: offline clairvoyant consequence optimum
  under fixed-rank assumptions;
- bounded exhaustive oracle: exact online action-sequence reference only for
  reduced-capacity episodes.

## 11. Training throughput preparation

The current training path uses one `DummyVecEnv`. Before allocating a long
budget, record:

- complete episodes per minute;
- environment steps per second;
- cold and warm provider timings;
- scenario-generation and candidate-assessment time;
- PPO update time separately from environment time;
- peak memory;
- time spent in geometry operations;
- unique episodes observed per 10,000 steps.

Potential improvements, in order:

1. reuse immutable consequence catalogs;
2. cache deterministic candidate assessments by full scenario/provider identity;
3. pre-materialize frozen validation scenarios;
4. parallelize independent training environments if process memory remains
   acceptable;
5. avoid recomputing static geometry at every step;
6. only then consider model or observation compression.

Cache keys must include every scenario, provider, data, configuration, and
geometry identity. A cache collision or stale result is worse than slower
training.

## 12. Curriculum design and why it is meaningful

### 12.1 Why use a curriculum

The full environment has a flat observation of roughly 23,000 values and 1,289
discrete actions before masking. Rewards are sparse and mostly arrive when events
resolve. Starting only with low-slack eight-threat episodes can make early PPO
updates dominated by failures, without showing whether the implementation can
learn simpler relationships.

A curriculum is useful only if every stage teaches part of the final task under
the same objective and observation semantics. It must not replace evaluation on
the full distribution.

### 12.2 Proposed curriculum

| Stage | Scenario mixture | What it teaches | Promotion evidence |
| --- | --- | --- | --- |
| C0: mechanics | `warmup`, 2–3 threats, abundant resources, spaced arrivals | Valid assign/advance behavior and completion | Near-perfect completion, zero invalid actions |
| C1: local consequence choice | Small feasible episodes with strong consequence contrast | Prefer a lower-cost valid candidate when resource coupling is weak | Beats naive cost on validation while completing episodes |
| C2: resource coupling | `balanced`, 4–6 threats, medium redundancy | Preserve useful resources across multiple detected threats | Completion plus reduced regret versus exact reference |
| C3: temporal contention | Mixed/burst arrivals, 6–8 threats | Avoid commitments that block later likely needs | Beats naive online baseline by profile |
| C4: full task | `full-standard`, `burst-contention`, limited `low-slack` | Eight-threat performance | Meets provisional full-task gates |
| C5: mixed retention | Mixture of all prior core stages | Prevent catastrophic forgetting and over-specialization | No material regression on earlier validation profiles |

Earlier profiles should remain in later mixtures. Otherwise the policy may forget
basic completion while adapting to low-slack cases.

### 12.3 Why these stages are relevant to the final goal

- C0 tests whether the agent can interact with the simulator at all.
- C1 tests whether the reward and observation expose consequence preference.
- C2 introduces the core sequential reason for using RL: assignments consume
  resources and change later options.
- C3 tests partial observability and arrival timing, where naive launching should
  be vulnerable.
- C4 matches the final eight-threat product claim.
- C5 tests whether success reflects a general policy rather than a narrow stage.

If C1 cannot beat a naive policy on deliberately clear trade-offs, increasing
scenario count will not fix the underlying problem. If C1 succeeds but C2 fails,
the likely issue is resource-coupling representation or credit assignment. If C2
succeeds but C3 fails, hidden-future uncertainty or cadence diversity is the
primary difficulty.

### 12.4 Promotion and stopping

Promotion should use validation episodes, not training return alone. Candidate
gates are:

- 100% completion on guaranteed-feasible warmup/standard validation;
- zero constraint violations;
- improvement over naive in a majority of scenarios;
- positive mean improvement with uncertainty reported;
- decreasing normalized regret against the exact reference;
- stable results across more than one algorithm seed.

Use wall-clock and evidence limits rather than promising a fixed step count.
Initial diagnostic runs at approximately 10k, 50k, and 100k steps are useful for
learning curves, but each report must also state how many complete and unique
episodes those steps represent.

## 13. Pilot training protocol

1. Freeze scenario-distribution, provider, observation, action, and reward
   versions.
2. Run an overfit diagnostic on a tiny fixed set of scenarios.
3. Run at least three algorithm seeds on a short curriculum.
4. Evaluate every checkpoint on validation scenarios only.
5. Compare against naive online, offline feasible matching, and exact reference.
6. Record learning curves by profile rather than only aggregate reward.
7. Select a provisional model and repeat with a larger budget.

### 13.1 Mandatory tiny-set overfit test

Before judging generalization, confirm the implementation can learn a small fixed
set, such as 8–16 scenarios with clear cost contrast. This is a diagnostic, not a
publishable result.

- If the policy cannot overfit the tiny set, suspect reward, mask, observation,
  normalization, action representation, or optimizer configuration.
- If it overfits but does not generalize, suspect scenario coverage, model
  capacity, permutation sensitivity, or training diversity.
- If it generalizes on balanced cases but fails on bursts, focus on timing,
  memory, and resource-coupling features.

### 13.2 Diagnostics when learning is flat

Do not respond to a flat learning curve by immediately increasing compute or
changing the reward. Follow this order:

1. **Verify opportunity:** confirm naive-to-exact gaps remain nonzero in the
   training and validation profiles.
2. **Verify behavior:** ensure episodes actually contain multiple valid actions
   and the policy is not always advancing or selecting the first mask entry.
3. **Verify reward:** replay returns and confirm step costs sum to terminal cost.
4. **Verify observation:** confirm good and bad candidates produce distinguishable
   normalized inputs and future data remains hidden.
5. **Verify masks:** measure valid-action counts and ensure the optimal current
   action is never accidentally masked.
6. **Verify normalization:** inspect clipping rates and nonfinite/constant
   features.
7. **Run tiny-set overfit:** distinguish implementation failure from
   generalization failure.
8. **Inspect PPO diagnostics:** entropy, value loss, explained variance, KL,
   clipping fraction, and action distribution.
9. **Tune minimally:** learning rate, rollout length, batch size, entropy
   coefficient, and network width, one controlled change at a time.
10. **Reconsider representation:** only after the preceding checks, consider a
    shared candidate encoder, attention, recurrent state, or factorized action
    policy.

Every change receives a new experiment identity. Keep unsuccessful runs and their
diagnostics; they explain why the final configuration was chosen.

### 13.3 When to move beyond the flat MLP

MaskablePPO with the current flat observation is the first implementation because
it already works end to end. A structured model becomes justified if:

- tiny-set learning succeeds but sample efficiency remains unacceptable;
- results change materially under harmless threat/interceptor slot permutations;
- the network cannot generalize across active counts;
- action probabilities collapse because the 1,280 assignment choices are too
  weakly related in the flat representation.

The next architecture would share encoders across threats, interceptors, and
candidates, then score valid assignment triples. It should preserve the existing
Gymnasium contract so simulator and evaluation evidence remain reusable.

## 14. Final training

After pilots:

- freeze the chosen distribution, curriculum, hyperparameters, code revision,
  dependencies, and data identities;
- use at least three independent algorithm seeds;
- retain checkpoints, normalization state, metadata, and learning curves;
- report requested and effective timesteps, complete episodes, unique scenarios,
  and wall-clock time;
- choose the final checkpoint using validation only;
- lock its model hash before opening held-out results.

If compute permits, report the distribution across algorithm seeds rather than
only the best seed. The best-of-many run alone is selection-biased.

## 15. Final evaluation and acceptance gates

### 15.1 Required comparisons

For each applicable suite, run:

- learned online policy;
- `naive-launch-on-detection/1`;
- offline feasible full-episode matching;
- exact fixed-rank optimizer;
- bounded exhaustive oracle on reduced episodes.

### 15.2 Primary gates

- 100% normal termination on guaranteed-feasible validation and held-out cases;
- zero invalid actions and zero constraint violations;
- no NaN, infinity, schema drift, identity mismatch, or replay mismatch;
- learned policy has positive held-out improvement over naive online interception;
- the 95% confidence interval for mean favorable difference excludes zero;
- learned normalized regret against the exact reference is lower than naive
  normalized regret;
- inference p95 meets the frozen interactive latency target;
- results remain acceptable across named scenario profiles rather than being
  carried by one easy profile;
- saved model reload reproduces the evaluated behavior with frozen normalization.

### 15.3 Secondary evidence

- win/tie/loss count against naive;
- mean and median cost difference;
- confidence interval and effect size;
- completion and violation rates;
- regret distribution against exact reference;
- latency distribution;
- performance by threat count, cadence, geography, matching difficulty, time
  margin, and consequence contrast;
- worst cases with scenario references that can be opened in the frontend.

If the learned policy does not pass the primary gates, the demo should show the
working training/evaluation system and the measured negative or inconclusive
result. It must not replace the checked baseline comparison with a success claim.

## 16. Frontend and demo handoff

After acceptance:

1. generate immutable naive and learned result snapshots for selected validation,
   stress, OOD, and held-out examples;
2. show both policies on the same scenario reference;
3. display online/offline labels prominently;
4. display consequence components and ordinal objective separately;
5. include a representative success, a difficult near-tie, and a failure or
   limitation case;
6. allow judges to enter a scenario reference and reproduce the result;
7. retain seed, profile, hashes, model identity, and exact publication ID.

The strongest demo sequence is:

1. load one frozen scenario;
2. show threats appearing over time;
3. run naive launch-on-detection;
4. replay the learned policy on the same episode;
5. compare completion, consequence cost, and regret;
6. open the provenance panel and show the exact scenario/model identities;
7. switch to a stress case and explain where performance degrades.

## 17. Two-day hackathon schedule

This schedule assumes the current simulator and MaskablePPO path remain intact.

### Day 1 morning: Steps 1–2

- approve the policy claim and baseline definition;
- implement scenario distribution/profile records;
- preserve v1 and add v2 identities;
- implement deterministic profile selection and variable active counts;
- add core profile invariant tests.

### Day 1 afternoon: Step 3

- implement scenario-audit metrics;
- run the first 1,000-episode audit;
- adjust only declared profile ranges to reach the Goldilocks zone;
- freeze thresholds and produce judge-readable summary;
- generate draft split manifests and scenario references.

### Day 2 morning: baseline, frontend audit, pilots

- implement naive online launch-on-detection;
- implement manifest-reference loading and exact frontend audit workflow;
- benchmark throughput;
- run tiny-set overfit and short curriculum pilots;
- diagnose flat learning using the ordered checklist.

### Day 2 afternoon: train, evaluate, present

- freeze the experiment;
- run the largest defensible multi-seed training budget;
- select by validation;
- run held-out, stress, OOD, and reference evaluations;
- publish frontend comparisons only if gates pass;
- prepare success, difficult, and limitation scenarios for the demo.

If time compresses, preserve evidence quality in this order:

1. deterministic scenario profiles and audit;
2. fair naive baseline;
3. tiny-set learning proof;
4. one frozen trained policy with held-out evaluation;
5. frontend scenario selector;
6. broader OOD and architecture experiments.

## 18. Implementation backlog

### Milestone A — current scope: policy and scenarios

- [ ] Approve the policy claim in Section 4.
- [ ] Approve the dimensions table in Section 5.2.
- [ ] Approve core profile names and predicates.
- [ ] Add versioned scenario-distribution records.
- [ ] Add `singapore-scenario/2` without changing v1.
- [ ] Support variable active counts inside fixed observation maxima.
- [ ] Record profile and distribution identities in every episode.
- [ ] Add deterministic profile and regeneration tests.

### Milestone B — current scope: audit

- [ ] Implement `scripts/audit_scenarios.py`.
- [ ] Implement matching difficulty, spatial coverage, temporal coverage, and
  consequence-gap metrics.
- [ ] Count rejected and repaired generations.
- [ ] Produce JSON and Markdown audit artifacts.
- [ ] Run at least 1,000 audited episodes.
- [ ] Freeze Goldilocks thresholds.
- [ ] Confirm v1 seed-7 regression remains byte-identical.

### Milestone C — splits and auditability

- [ ] Update the suite-manifest version and checked manifest.
- [ ] Create validation, held-out, stress, OOD, bounded-oracle, and full-reference
  manifests with no duplicate episode hashes.
- [ ] Define immutable scenario references.
- [ ] Regenerate and hash-verify scenarios by reference.
- [ ] Add backend manifest-reference execution.
- [ ] Add frontend scenario-audit controls and provenance display.

### Milestone D — baseline and environment gates

- [ ] Implement `naive-launch-on-detection/1`.
- [ ] Verify identical information boundaries for naive and learned policies.
- [ ] Run reward, mask, truncation, normalization, and replay audits.
- [ ] Benchmark environment and PPO throughput.

### Milestone E — curriculum and pilots

- [ ] Implement curriculum mixtures without changing reward semantics.
- [ ] Run tiny-set overfit diagnostic.
- [ ] Run short multi-seed pilots.
- [ ] Record profile-specific learning curves.
- [ ] Follow the flat-learning diagnostic tree before redesigning the model.

### Milestone F — final policy

- [ ] Freeze all experiment identities.
- [ ] Train at least three algorithm seeds.
- [ ] Select using validation only.
- [ ] Lock the model hash.
- [ ] Run held-out, stress, OOD, oracle, and assignment-reference suites.
- [ ] Apply the acceptance gates without weakening them after results are known.
- [ ] Publish the learned frontend comparison only if supported.

## 19. Decision register

Decisions already accepted for this plan:

- the policy acts online using detected threats only;
- the goal is complete feasible handling followed by lower assumption-grade
  consequence cost;
- scenario diversity is structured and documented by named dimensions;
- the immediate implementation stops after Steps 1–3 are complete;
- data splits are frozen before model selection;
- every frozen scenario is reproducible and frontend-loadable by immutable
  reference;
- the primary baseline is naive online interception;
- the existing MaskablePPO path is tried before a more complex policy network;
- flat learning triggers diagnostics before more compute or reward changes;
- final claims require held-out improvement, constraint compliance, replay, and
  provenance evidence.

Decisions intentionally deferred:

- heterogeneous interceptor classes;
- varying physical footprint geometry;
- dynamic target-course updates;
- sensor uncertainty;
- resource failure and replanning;
- infeasible episodes that require prioritizing unhandled threats;
- a structured attention/factorized policy architecture.

Each deferred item changes the environment semantics and should receive a new
version, tests, scenarios, and evaluation claim rather than being inserted into a
running experiment.

## 20. Canonical implementation references

- `backend/simulation/singapore_scenario.py`
- `backend/simulation/engine.py`
- `backend/simulation/assignment_planning.py`
- `backend/simulation/baseline.py`
- `backend/simulation/suites.py`
- `backend/simulation/singapore_provider.py`
- `backend/learning/environment.py`
- `backend/learning/training.py`
- `backend/learning/evaluation.py`
- `backend/learning/oracle.py`
- `scripts/train_rl.py`
- `scripts/evaluate_rl.py`
- `scripts/verify_singapore_backend.py`
- `contracts/simulation-result.md`
- `contracts/frontend-backend-api.md`
