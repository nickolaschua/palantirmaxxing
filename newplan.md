# Operational Consequence Optimisation and Learning Plan

## 1. Purpose

This document consolidates the current implementation, the project handoff, mentor feedback, and the proposed path from the deterministic static MVP to an operationally relevant, simulation-driven decision-support system.

The refined project objective is:

> Preserve mission and critical-service continuity by identifying feasible response locations whose predicted debris consequences do not disable the capabilities needed to survive and operate after the current threat.

Stopping the threat remains the first requirement. The new contribution is to compare the consequences of otherwise feasible response alternatives. Debris that closes a runway, disrupts command-and-control, disables power or communications, starts a fire at critical infrastructure, or consumes scarce response resources may have consequences beyond the immediate event.

The system should therefore:

1. maintain a versioned view of operationally significant assets and their current state;
2. simulate or otherwise estimate the debris hazard associated with each feasible candidate;
3. translate that hazard into asset-specific operational consequences;
4. reject candidates that violate explicit hard constraints;
5. compare the remaining candidates under a configurable policy profile;
6. preserve the evidence, assumptions, uncertainty, and provenance behind every recommendation;
7. use offline simulation and optimisation results to train a fast supervised surrogate; and
8. reserve reinforcement learning for later sequential problems in which decisions alter future state.

This remains a decision-support prototype. It does not establish operational validity, autonomous authority, real interception performance, or validated debris physics.

---

## 2. Refined project narrative

### 2.1 Primary framing

Stopping a threat is not the only outcome that matters. The location and distribution of resulting debris can determine whether essential capabilities remain available afterward. Debris across a runway can prevent aircraft launch or recovery. Damage to a data centre, power installation, communications facility, command node, fuel site, or access route can interrupt operations even if the original threat is stopped.

The system therefore evaluates consequences in terms of **mission continuity and critical-service availability**, not merely whether a geographic footprint intersects a broad category of land.

### 2.2 Supporting framing

Civilian and population consequences remain visible as an explicit safety dimension, constraint, or lower-tier objective. They should not be erased from the evidence, but the project's principal operational story is the preservation of capabilities required during and after an attack.

### 2.3 Concise pitch

> Debris can disable the capabilities needed to survive the next attack. We simulate those consequences, enforce operational constraints, and learn fast policies that preserve mission and critical-service continuity.

### 2.4 Technical story

> Location-dependent debris risk requires asset-specific consequence modelling. Simulations estimate counterfactual outcomes for feasible response alternatives. An exact policy layer applies hard constraints and operational priorities. Supervised learning distils expensive simulation and optimisation results for low-latency inference. Reinforcement learning is introduced only when decisions affect later resources, asset availability, observations, and response options.

---

## 3. What the repository implements today

The current machine-side flow is:

```text
Supplied threat and interceptor state
    -> 50 uniformly timed future trajectory samples by default
    -> exact bounded-curvature reachability evidence
    -> reachable candidate opportunities
    -> synthetic time-decaying success values
    -> supplied fixed-radius circular footprints
    -> Population Exposure Calculator
    -> complete-coverage eligibility
    -> two-objective Pareto filtering
    -> descriptive representative alternatives
    -> planning-result/1
    -> frontend presentation and human selection
```

### 3.1 Implemented strengths

- Deterministic, immutable domain records with strict validation.
- Configurable trajectory sampling with all reachable and unreachable candidates retained.
- A tested free-terminal-heading, bounded-curvature reachability calculation.
- A reusable, versioned Population Exposure Calculator with provenance and coverage semantics.
- Explicit separation between planning, scenario assumptions, exposure, trade-space processing, presentation, and frontend rendering.
- Pareto evidence rather than a hidden scalar score.
- Human-facing alternatives rather than an automatic final action.
- Reproducible benchmark fixtures, sensitivity studies, and extensive unit/integration coverage.
- A frontend contract that preserves assumptions and evidence.

As verified on 23 September 2026, the existing checks pass:

- 110 Python unit tests;
- 33 Python integration tests; and
- 12 frontend tests.

### 3.2 Current limitations

The current implementation is a deterministic evaluator and trade-space demonstrator, not yet the expensive optimiser described in the project handoff.

- Candidate positions are predefined samples along one straight, constant-velocity 2D trajectory.
- There is one interceptor and one generic threat.
- Reachability, success, and footprint assumptions are synthetic.
- The footprint is a fixed circle centred on the candidate point.
- Population is static and uniformly distributed within eligible zones.
- The system does not simulate fragments, debris trajectories, impact energy, ignition, structural damage, service dependencies, repair, or downtime.
- Pareto filtering compares only supplied success and population exposure.
- There is no universal best candidate and no configurable policy profile.
- There is no protected-asset backend catalog.
- The frontend military layer is an OSM-derived visual layer and is not planning evidence.
- There is no backend API implementation, scenario corpus generator, ML pipeline, model registry, or inference contract.
- Dynamic replanning, resource allocation, multiple simultaneous threats, and databases are deferred.

### 3.3 Performance baseline

The checked-in real-population demo benchmark reports a median total of approximately 81.65 ms for 50 candidates, with population prepared outside timing. The smaller synthetic benchmark reports approximately 28.48 ms median, of which footprint exposure assessment is the dominant stage at approximately 26.68 ms; Pareto filtering is approximately 1.30 ms.

The existing system therefore already meets its current sub-100 ms target. Learning is not justified merely to replace the existing Pareto loop. It becomes valuable when the teacher includes substantially richer and more expensive consequence simulation or multi-scenario optimisation.

---

## 4. Decision model

The decision model must keep four concepts separate:

1. **Hazard evidence:** what the simulation predicts will physically occur.
2. **Operational consequence:** how predicted hazard affects specific assets and services.
3. **Hard constraints:** conditions that make a candidate unacceptable.
4. **Policy preferences:** how acceptable candidates are compared.

For candidate \(c\) under scenario \(s\), feasibility is:

\[
\operatorname{Feasible}(s,c) \iff g_i(s,c) \leq 0 \quad \forall i
\]

Each candidate then has a consequence vector:

\[
z(s,c) =
\begin{bmatrix}
1-P(\text{mission success}) \\
\text{runway downtime} \\
\text{critical-service downtime} \\
\text{base capability loss} \\
\text{civilian consequence} \\
\text{resource cost}
\end{bmatrix}
\]

An active policy profile \(\pi\) determines the ordering of feasible candidates:

\[
\operatorname{Recommendations}(s,\pi)
= \operatorname{rank}_{c \in \operatorname{Feasible}(s)} J_{\pi}(z(s,c))
\]

The system should generally return a Pareto set or a small number of representative alternatives rather than imply a universally correct automatic decision.

---

## 5. Hard constraints

Hard constraints are not reward terms and are not optional preferences. They must be checked by deterministic code before ranking.

### 5.1 Physical and timing constraints

- Candidate is reachable under the declared motion model.
- Candidate occurs before the applicable response deadline.
- Required travel time and time margin are finite and valid.
- Scenario and coordinate systems are compatible.

### 5.2 Mission constraints

- Minimum acceptable mission-success estimate.
- Required remaining response margin.
- Permitted response-resource or interceptor class.
- Required reserve or availability level.

### 5.3 Operational-survival constraints

- Minimum remaining runway capability.
- Maximum acceptable probability of losing a critical command, power, communications, fuel, maintenance, or data service.
- Prohibited debris or impact regions.
- Required redundancy for a service or site.
- Maximum acceptable loss of a mission-essential sub-asset.

### 5.4 Evidence-quality constraints

- Complete spatial data coverage for every metric used in selection.
- Supported simulator, asset-catalog, vulnerability-model, and policy versions.
- Prediction uncertainty below an agreed threshold.
- No out-of-distribution warning.
- No failed, incomplete, infeasible, or timed-out teacher solve represented as a successful label.

### 5.5 Civilian safeguards

- Maximum permitted civilian consequence under the chosen validated measure.
- No use of partial population coverage as if it were zero exposure.
- Explicit recording of unknown or excluded geography.

The same measurement can participate in both a constraint and an objective. For example, the system can require that at least one runway remains usable and then minimize expected runway closure time among candidates satisfying that constraint.

---

## 6. Optimisation objectives and priority profiles

### 6.1 Candidate objective dimensions

Potential objective dimensions include:

- maximize mission-success estimate;
- minimize expected runway closure time;
- maximize remaining runway length or throughput;
- minimize expected command-and-control downtime;
- minimize critical power, communications, fuel, maintenance, or data-service disruption;
- minimize aggregate mission-capability loss;
- minimize cleanup and restoration time;
- minimize scarce-resource use;
- minimize civilian consequence; and
- minimize uncertainty or sensitivity to modelling assumptions.

### 6.2 Avoid one unrestricted weighted sum

A single unrestricted weighted score can conceal unacceptable trade-offs. The recommended order is:

1. apply every hard constraint;
2. apply lexicographic priority tiers;
3. use normalized weights only within a tier;
4. retain Pareto evidence and near-equivalent alternatives; and
5. present raw consequence components alongside any aggregate score.

### 6.3 Illustrative policy shape

```yaml
schema_version: policy-profile/1
policy_id: airbase-continuity
policy_version: operator-controlled

hard_constraints:
  minimum_success_probability: operator-defined
  minimum_remaining_runway_capability: operator-defined
  maximum_critical_asset_loss_probability: operator-defined
  require_complete_asset_coverage: true
  maximum_model_uncertainty: operator-defined

objective_tiers:
  - priority: 1
    minimize:
      - runway_closure_minutes
      - command_and_control_downtime
  - priority: 2
    minimize:
      - critical_service_downtime
      - response_resource_cost
  - priority: 3
    minimize:
      - civilian_consequence
      - cleanup_burden
```

Thresholds and weights must come from an authorized stakeholder or scenario specification. The model must not invent them.

### 6.4 Dynamic context

Priority is not purely a static property of an asset. It can change with operational state. A runway becomes more critical if another runway is already unavailable. A data centre becomes more critical if its redundant peer has failed. The policy input must therefore include relevant current availability and dependency state, not only static asset categories.

---

## 7. Protected-asset and operational-state model

The system needs a backend-owned, versioned catalog rather than relying on frontend illustration data.

### 7.1 Asset catalog

Each asset should contain:

- stable asset and sub-asset identifiers;
- geometry and coordinate reference system;
- asset class and functional role;
- source, timestamp, licence, provenance, and confidence;
- parent site and dependency relationships;
- operational state and redundancy group;
- vulnerability-model identifier;
- supported consequence metrics; and
- data-quality and coverage status.

### 7.2 Asset granularity

Broad polygons are insufficient. Examples of meaningful sub-assets include:

- runway strips, taxiways, aprons, and access routes;
- command-and-control nodes;
- fuel, power, cooling, and communications components;
- data-centre buildings and supporting utilities;
- maintenance and launch-support facilities; and
- service dependency links.

Asset categories may overlap. The system must preserve component-level evidence and define aggregation explicitly to avoid double-counting.

### 7.3 Initial storage

Versioned JSON or GeoJSON files are sufficient for the prototype. A database should be introduced only when shared editing, permissions, live operational state, spatial queries, or searchable run history justify it.

The existing OSM military layer can seed a visual demonstration but must not be treated as validated planning evidence without a documented preparation and validation pipeline.

---

## 8. Hazard, vulnerability, and consequence modelling

The required calculation chain is:

```text
Candidate response
    -> debris/hazard simulation
    -> spatial hazard or intensity field
    -> intersection with asset components
    -> asset-specific vulnerability model
    -> functional loss and recovery estimate
    -> candidate consequence vector
```

### 8.1 Hazard model

The current supplied circle should remain available as a transparent baseline. Richer later models may produce:

- fragment landing-point distributions;
- probability or intensity rasters;
- directional or polygonal footprints;
- fragment count or density estimates;
- energy or ignition-relevant classes;
- uncertainty ensembles; and
- wind or state-dependent dispersion.

The Population Exposure Calculator should remain separate. It evaluates supplied geometry and must not silently become a debris-physics model.

### 8.2 Vulnerability models

Hazard overlap alone is not operational consequence. Each asset type needs a documented transformation from hazard to functional effect.

Examples include:

- runway debris coverage, remaining usable length, inspection burden, clearance time, and closure probability;
- data-centre fire, cooling, power, and connectivity interruption probabilities;
- communications or power capacity lost and restoration time;
- probability of losing a mission-essential sub-asset; and
- cleanup time and resource demand.

Every vulnerability function must expose its assumptions, calibration status, uncertainty, and supported input range.

### 8.3 Consequence vector

Do not collapse consequences early. Store raw asset-level and aggregate components so policies can change without rerunning physical simulation or retraining the consequence model.

---

## 9. Proposed repository architecture

The current module separation should be preserved and extended:

```text
backend/
  assets/
    catalog.py              # validation and versioned asset preparation
    operational_state.py    # availability and dependency state
  consequence/
    hazard.py               # hazard-provider interface
    vulnerability.py        # asset-specific consequence interfaces
    evaluator.py            # candidate consequence vectors
  policy/
    constraints.py          # deterministic constraint evaluation
    profiles.py             # versioned configurable priorities
    pareto.py               # generalized multi-objective evidence
    ranking.py              # lexicographic/within-tier ranking
  learning/
    features.py             # versioned feature contract
    provider.py             # learned outcome-provider interface
    validation.py           # model identity, OOD, uncertainty gates
  orchestration/
    static_scenario.py      # existing exact MVP retained
    operational_scenario.py # new extended pipeline

contracts/
  protected-assets.md
  operational-state.md
  consequence-result.md
  policy-profile.md
  training-example.md
  recommendation-result.md

scripts/
  generate_scenario_corpus.py
  train_consequence_surrogate.py
  evaluate_consequence_surrogate.py
  benchmark_operational_pipeline.py
```

### 9.1 Integration seam

Introduce a replaceable candidate-outcome provider after exact reachability and before policy/Pareto processing:

- `ExactOutcomeProvider`: runs detailed hazard, vulnerability, and consequence models.
- `LearnedOutcomeProvider`: predicts the same consequence contract with uncertainty and model provenance.

Exact trajectory, reachability, hard constraints, policy logic, and presentation remain outside the learned model.

### 9.2 Contract evolution

Keep `planning-result/1` stable for the existing demo. Introduce `planning-result/2` or `recommendation-result/1` containing:

- active policy ID and version;
- constraint names, thresholds, observed values, and pass/fail evidence;
- raw consequence dimensions;
- affected assets and sub-assets;
- Pareto and ranking evidence;
- simulator, vulnerability, asset-catalog, population, and model versions;
- uncertainty and out-of-distribution evidence;
- assumptions and limitations; and
- deterministic reasons for inclusion or exclusion.

---

## 10. Offline scenario and dataset pipeline

### 10.1 Teacher pipeline

```text
Versioned scenario generator
    -> exact trajectory and reachability
    -> detailed hazard simulation
    -> asset vulnerability and consequence evaluation
    -> hard-constraint evaluation
    -> exact optimisation or Pareto/policy processing
    -> versioned training records
```

### 10.2 Scenario generation

Sample across meaningful ranges for:

- threat position, direction, speed, time-to-go, and uncertainty;
- interceptor position, heading, speed, turn-rate, class, and availability;
- candidate-sampling resolution;
- debris-model parameters, footprint shapes, and environmental conditions;
- asset operational state and redundancy;
- policy profile; and
- model and data uncertainty.

Use a structured sampling method such as stratified, Latin-hypercube, or low-discrepancy sampling rather than relying only on naive independent random draws. Deliberately oversample decision boundaries, rare critical-asset interactions, infeasible cases, partial-coverage cases, and near-tied alternatives.

### 10.3 Training-record contents

For every scenario and candidate, retain:

- stable scenario, episode, and candidate IDs;
- random seed and generator version;
- complete scenario inputs;
- exact reachability evidence;
- hazard and consequence outputs;
- asset-level contributions;
- constraint evaluations;
- policy profile and resulting ranks or Pareto membership;
- teacher solver status, gap, runtime, timeout, and failure reason;
- simulator, dataset, vulnerability, policy, and software versions; and
- checksums for material inputs and outputs.

Failed, incomplete, infeasible, or timed-out cases must not be silently converted into successful labels.

### 10.4 Data partitions

The proposed 10,000 training and 10,000 testing scenarios are reasonable only if scenario identity is preserved.

- All candidates and snapshots from one underlying scenario stay in one partition.
- A validation partition is used for model and hyperparameter selection.
- The final same-distribution test set remains locked until the model is frozen.
- A separate challenge set contains withheld geographies, parameter ranges, asset states, rare combinations, and altered modelling assumptions.
- Near-duplicate scenarios and related trajectories must not cross partitions.

Ten thousand scenarios with 50 candidates create up to 500,000 candidate rows, but the independent sample count remains 10,000 scenarios.

Generate a smaller pilot corpus first to validate schemas, coverage, storage, runtime, label quality, and failure handling before spending compute on the full dataset.

---

## 11. Supervised learning plan

### 11.1 Recommended target

Train the model to predict inspectable consequence components for each reachable candidate rather than directly outputting a candidate index.

Recommended targets include:

- asset-specific functional impact;
- runway availability and closure-time measures;
- critical-service downtime;
- aggregate capability-loss components;
- civilian consequence where supported;
- consequence uncertainty; and
- data-validity or out-of-distribution indicators.

Do not learn cheap exact functions such as current trajectory sampling or bounded-curvature reachability.

### 11.2 Input features

Inputs may include:

- threat and interceptor state;
- candidate position, time, path length, required travel time, and time margin;
- hazard-model parameters;
- local raster or engineered summaries of nearby assets;
- asset operational state and dependencies;
- environmental or uncertainty variables; and
- declared model/data versions.

Policy priorities should normally remain outside the physical consequence model. If a direct ranking model is later added, it must be explicitly conditioned on the policy profile.

### 11.3 Model progression

Compare increasingly complex approaches:

1. deterministic heuristic;
2. precomputed consequence surface or spatial lookup;
3. nearest-neighbour or cached-scenario retrieval;
4. gradient-boosted trees for per-candidate tabular outcomes;
5. small multilayer perceptron;
6. set/list model only if cross-candidate context materially helps; and
7. direct policy or listwise ranker only after consequence prediction is credible.

For the current static, fixed-radius population problem, a precomputed spatial consequence surface may be faster, more accurate, and easier to audit than ML. It must be included as a baseline.

### 11.4 Training losses

Possible losses include:

- robust regression for consequence components;
- classification for validity or coverage states;
- quantile or ensemble objectives for uncertainty;
- listwise or regret-weighted loss for optional ranking; and
- calibration losses where probabilities are reported.

### 11.5 Runtime behaviour

Online inference should:

1. calculate trajectory and reachability exactly;
2. reject physically infeasible candidates;
3. predict consequence vectors for remaining candidates;
4. reject unsupported, uncertain, or out-of-distribution predictions;
5. apply deterministic hard constraints;
6. compute policy/Pareto evidence;
7. return a small set of alternatives with raw evidence; and
8. fall back to exact evaluation or human-only alternatives when confidence is insufficient.

---

## 12. Role of reinforcement learning

### 12.1 Why RL is not the first step

The present static problem is a one-step selection over a finite candidate set. In learning terms it is close to a contextual bandit. Supervised imitation, learning-to-rank, or consequence-surrogate modelling is simpler, more data-efficient, and easier to validate.

Running an RL algorithm on the current one-step environment would add complexity without creating a meaningful sequential decision problem.

### 12.2 When RL becomes justified

RL becomes relevant when an episode contains repeated decisions and current choices alter future state, for example:

- updated threat observations and trajectories;
- uncertain success or failure followed by replanning;
- multiple simultaneous or arriving threats;
- depleted or reserved response resources;
- degraded runways, sites, or critical services;
- changing asset priorities or redundancy; and
- long-term trade-offs between immediate response and future capability.

At that stage the environment becomes:

```text
current world and operational state
    -> choose among feasible response alternatives
    -> simulator samples outcome
    -> resources and asset availability change
    -> new observation arrives
    -> next decision
```

Hard constraints should still be enforced by the environment or an external safety layer rather than represented only as reward penalties.

### 12.3 Defensible language

Until the sequential environment exists, describe the work as:

- simulation-driven policy learning;
- supervised policy distillation;
- learning a fast surrogate for expensive consequence simulation; or
- offline learning from optimised counterfactual scenarios.

Do not claim RL merely because simulated data are available.

---

## 13. Evaluation and acceptance criteria

The central research question is:

> Can a learned approximation meet a meaningful decision-time budget while retaining acceptable consequence quality, constraint validity, robustness, and auditability relative to the exact teacher?

### 13.1 Baselines

Compare against:

- current exact pipeline;
- simple operational heuristics;
- precomputed spatial consequence surfaces;
- cached or nearest-neighbour results;
- exact optimisation when available; and
- ablations without asset state, policy context, or uncertainty handling.

### 13.2 Core metrics

- Hard-constraint violation rate after the deterministic validator.
- Objective regret relative to the teacher under each policy profile.
- Pareto-set precision/recall and dominated-recommendation rate.
- Top-k recall of teacher-optimal or teacher-representative candidates.
- Error for each raw consequence component.
- Probability calibration and prediction-interval coverage.
- Out-of-distribution detection performance.
- End-to-end p50, p95, and p99 latency including preprocessing and validation.
- Failure and fallback rates.
- Result stability under small input perturbations.

### 13.3 Slice and challenge evaluation

Report results separately for:

- asset type and criticality;
- runway and service redundancy state;
- dense versus sparse asset environments;
- reachable-set size and near-boundary reachability;
- partial or degraded data coverage;
- policy profile;
- ordinary versus rare hazard configurations; and
- same-distribution versus deliberately withheld challenge cases.

### 13.4 System-level acceptance

The learned model should not be accepted solely because its candidate-index accuracy is high. Acceptance requires:

- deterministic constraints continue to hold;
- raw consequence predictions are sufficiently accurate and calibrated;
- policy regret is acceptable on locked and challenge sets;
- latency improves at the complete-system boundary;
- failures trigger explicit fallback;
- every result retains model and data provenance; and
- the frontend can explain why a candidate was excluded, retained, or preferred.

Quantitative thresholds must be agreed before final model selection rather than selected after inspecting final-test performance.

---

## 14. Delivery phases

### Phase 0: Preserve and benchmark the current baseline

- Keep the current static MVP and `planning-result/1` unchanged.
- Re-run existing tests and benchmarks on the target demonstration hardware.
- Confirm the actual latency budget and identify the future expensive component.
- Document whether the intended teacher optimiser exists inside or outside this repository.

**Exit evidence:** reproducible baseline quality, timing, scope, and limitations.

### Phase 1: Define operational semantics

- Define asset, sub-asset, operational-state, consequence, constraint, and policy contracts.
- Agree which requirements are hard constraints.
- Agree which metrics are objectives and their direction.
- Specify lexicographic tiers and within-tier weighting semantics.
- Define units, missing-data behaviour, uncertainty, and provenance.

**Exit evidence:** reviewed versioned contracts with no ambiguous definition of “ideal.”

### Phase 2: Build protected-asset and consequence baselines

- Implement the versioned backend asset catalog.
- Add a small validated demonstration set containing runway and critical-service sub-assets.
- Implement exact geometry overlap and simple transparent vulnerability baselines.
- Retain population exposure as a separate consequence component.
- Add deterministic hard-constraint evaluation.
- Generalize Pareto evidence beyond two fixed objectives.

**Exit evidence:** exact candidate consequence vectors and auditable policy results without ML.

### Phase 3: Build the offline teacher and corpus generator

- Introduce the hazard-provider interface.
- Add richer simulated hazard outputs when available.
- Generate deterministic, versioned scenarios with stable seeds.
- Record all candidates, outcomes, constraints, solver statuses, failures, runtimes, and provenance.
- Produce a small pilot corpus and audit it before scaling.

**Exit evidence:** reproducible pilot dataset with documented coverage and failure modes.

### Phase 4: Establish non-ML and supervised baselines

- Build heuristic and precomputed-surface baselines.
- Train a simple per-candidate tabular consequence model.
- Add uncertainty and out-of-distribution handling.
- Reuse exact constraints and policy/Pareto processing.
- Benchmark complete online inference.

**Exit evidence:** locked validation results showing whether learning is actually useful.

### Phase 5: Scale and independently evaluate

- Generate the full training, validation, final-test, and challenge corpora.
- Freeze data and evaluation protocols before final tuning.
- Compare model classes, teacher quality, latency, regret, calibration, and failures.
- Preserve replayable failure cases.

**Exit evidence:** measured claims such as inference latency, regret, validity, calibration, and challenge robustness.

### Phase 6: Integrate decision-support presentation

- Add a versioned `planning-result/2` or `recommendation-result/1` adapter.
- Show asset impacts, operational-state effects, constraints, alternatives, uncertainty, and provenance.
- Keep the current visual demo available as a regression baseline.
- Preserve human supervisory authority.

**Exit evidence:** a reproducible end-to-end demonstration whose claims match backend evidence.

### Phase 7: Add sequential RL only if justified

- Introduce dynamic observations, uncertain outcomes, resource consumption, and asset-state transitions.
- Define a constrained sequential environment.
- Compare RL against model-predictive control, repeated optimisation, heuristics, and supervised policies.
- Evaluate full episodes and long-term capability preservation, not isolated action accuracy.

**Exit evidence:** proof that sequential policy learning adds value beyond supervised or repeated deterministic planning.

---

## 15. Demonstration plan

A credible demonstration should show two or more feasible response alternatives with similar supplied mission-success estimates but materially different operational consequences.

Example narrative:

1. A threat trajectory creates several reachable candidate locations.
2. The earliest candidate produces a simulated debris field that crosses a runway or critical service component.
3. Another candidate remains feasible while preserving the required runway or service capability.
4. The system shows the constraint evidence, consequence deltas, active policy, uncertainty, and provenance.
5. The learned provider reproduces the teacher's outcome or ranking with substantially lower latency.
6. An out-of-distribution or high-uncertainty case visibly falls back instead of presenting false confidence.

The UI should avoid implying that broad purple military polygons are sufficient evidence. It should show the specific operational component affected and the functional metric that changes.

---

## 16. Research claims the project can responsibly make

Potential defensible claims include:

- Different feasible response locations can produce materially different simulated operational consequences.
- Explicit operational constraints change which candidates remain acceptable.
- Configurable policy profiles change trade-offs without changing the underlying physical consequence estimates.
- A supervised surrogate can approximate an expensive consequence model within a measured latency, regret, calibration, and validity envelope.
- Challenge testing reveals where recommendations are sensitive to geography, asset state, priorities, or modelling assumptions.
- Sequential RL is useful only if later experiments show value under dynamic state and resource constraints.

Claims the project should not make without additional validation include:

- real debris prediction;
- real interception probability;
- real casualty, fire, structural-damage, or downtime prediction;
- autonomous operational readiness;
- guaranteed generalisation outside the training and challenge distributions; or
- independent validation merely because a large simulated dataset was generated.

---

## 17. Open decisions

Resolve these before implementing the extended architecture:

1. What exact teacher optimiser exists, and is it in this repository?
2. What does one teacher run consume and produce?
3. Which debris or hazard model will generate asset-level effects?
4. Which assets and sub-assets are in the first demonstration?
5. What operational consequence is credible for each asset type?
6. Which requirements are hard constraints rather than objectives?
7. Who defines thresholds, priority tiers, and policy profiles?
8. How is operational state supplied and versioned?
9. What uncertainty representation is required?
10. What inference hardware and end-to-end latency budget matter?
11. When must the system fall back to exact evaluation or abstain?
12. What is the deadline, storage budget, and compute budget for corpus generation?
13. Is the intended first deliverable supervised policy distillation, consequence-surrogate learning, or a truly sequential RL environment?

---

## 18. Immediate recommended milestone

Build **Operational Consequence Baseline v0** before adding RL.

The milestone should deliver:

- `protected-assets/1` and `policy-profile/1` contracts;
- a small versioned runway and critical-infrastructure demonstration dataset;
- one transparent consequence model per selected asset type;
- deterministic hard-constraint evaluation;
- generalized consequence vectors and Pareto evidence;
- a seeded scenario generator and training-record contract;
- a precomputed-surface or heuristic latency baseline;
- a supervised per-candidate consequence surrogate;
- exact-versus-learned evaluation on validation and challenge scenarios; and
- a frontend view explaining operational effects, constraints, uncertainty, and provenance.

Only after this milestone should the team decide whether a sequential environment and RL add meaningful technical value.

---

## 19. Final framing

The project should be presented as a progression:

```text
Debris creates location-dependent operational risk
    -> operational risk depends on the affected asset and its current state
    -> hard requirements remove unacceptable response alternatives
    -> simulations estimate counterfactual consequences
    -> optimisation exposes the feasible trade space
    -> supervised learning distils expensive evaluation for low latency
    -> challenge testing measures robustness and failure
    -> sequential RL is added only when decisions change future state
```

The technically meaningful contribution is not merely “we trained a model.” It is a versioned, testable and auditable bridge from simulation to operational consequence, from consequence to explicit policy, and from expensive offline evaluation to measured low-latency decision support.
