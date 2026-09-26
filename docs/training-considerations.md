# Training considerations: supervised learning, RL, evidence, and local hardware

Prepared 25 September 2026. Repository baseline: `93ebb72`.

Companion: [Project context and decision workbook](project-context-and-decisions.md).

## 1. What this document answers

You want a learned model as the final product, rather than stopping at a collection of datasets or a visualization. You have an Apple M5 Pro MacBook Pro, and you want to understand supervised learning versus reinforcement learning, what either approach requires, whether many interacting events change the answer, and what would make a convincing hackathon demonstration.

This document provides general learning-method guidance and a concrete decision workbook for **civilian-consequence prediction**. RL examples concern benign environments such as games or public-service restoration. It does not specify an interception policy, weapon-control environment, action representation, reward, or training procedure for weapon employment. The requested weapon-recommendation system is outside this document's implementation scope.

Read sections 2–5 for the learning choice, sections 6–9 for data and evaluation, and sections 10–14 for hardware and decisions. The companion document records the repository evidence and the issues already settled in the conversation.

## 2. Direct answers before the detail

| Your question | Answer |
|---|---|
| Do I need RL because the output is one recommendation? | No. The output format does not determine the learning method. |
| Does processing one event at a time make it independent? | No. Shared conditions or persistent effects can couple events even when processing is sequential. |
| Do 100 simultaneous events automatically require RL? | No. Input size, interaction, time dependence, and learning method are different questions. |
| Can supervised learning handle complex inputs? | Yes in principle, but complexity and generalization must be demonstrated rather than assumed. |
| Is the current dataset already a training dataset? | It is evidence and profile data. A learning dataset also needs a clearly defined prediction target, examples, provenance, and an evaluation split. |
| Is RL cooler? | The name may sound more ambitious. A convincing live result, honest comparison, and clear technical contribution matter more than the label. This is a presentation judgment, not a benchmark result. |
| Is the Mac a blocker? | Nothing observed establishes that it is a blocker for a modest civilian-prediction prototype. No training workload has been benchmarked on it yet. |
| What is the most defensible first learning target within this document's scope? | Predict civilian consequences for supplied disruption scenarios, without choosing an intervention. This can be evaluated separately from any decision system. |

The last answer is a recommendation for a bounded learning demonstration. It does not assert that it fulfills your broader desired product.

## 3. Separate the scientific questions

Several different questions have been bundled into the phrase “physics engine.” Keeping them separate makes the work easier to assess.

**Physical or scenario model:** Given specified conditions and an externally supplied event, what happens? Its output depends on the assumptions represented by that model. A table of location importance is not a physical simulation.

**Consequence model:** Given the event and the affected civilian systems, what follows for exposure, service availability, and recovery? This is where much of today's new code belongs.

**Preference model:** How does a person or institution value different consequences? A weight is a preference or design assumption, not a physical constant.

**Learning model:** What relationship should be approximated from examples? Predicting a numerical consequence, predicting a category, and imitating a choice are different targets.

**Evaluation model:** What evidence would establish that the learned relationship is useful? It may be prediction accuracy, runtime, calibration, or transfer to held-out conditions. These are not interchangeable.

For example, a model can reproduce a simulator accurately while the simulator itself poorly represents the world. A model can also be fast but inaccurate. Neither success should be reported as the other.

## 4. Supervised learning: what you would need

Supervised learning uses examples with known targets. Classification predicts a category; regression predicts a quantity. “Classifier” therefore describes only one possible form of supervised learning. The official [scikit-learn supervised-learning overview](https://scikit-learn.org/stable/supervised_learning.html) lists both families and their supported estimators.

For a civilian-consequence example, the target might be independently observed restoration duration or the output of a documented consequence calculation. The first targets an observed quantity; the second targets an approximation of an existing calculation. The evidence behind those two labels is different.

A usable problem statement needs these answers:

| Decision | Why it matters | Your answer |
|---|---|---|
| What exact quantity is predicted? | Prevents a vague “good outcome” target. | |
| What is one example? | Defines the unit of prediction and evaluation. | |
| What information exists when prediction is requested? | Prevents future information from leaking into inputs. | |
| Where does the target come from? | Determines what agreement with the target establishes. | |
| What units and time horizon apply? | Makes numerical errors interpretable. | |
| How is a missing target represented? | An unknown consequence must not become a zero label. | |
| What population of future examples matters? | Defines the intended generalization claim. | |

**Strengths for a bounded demonstration:** inputs and labels can be inspected together, a prediction can be compared directly with its reference, and a failed example can be investigated without reconstructing an entire interaction history.

**Limitations:** a model learns from the examples and targets supplied. It does not independently resolve incorrect assumptions, omitted mechanisms, or value judgments embedded in those targets. More copies of closely related synthetic cases do not create independent empirical evidence.

### 4.1 Predicting consequences versus copying decisions

A consequence predictor estimates an outcome. A decision-imitation model reproduces choices made by another process. The latter inherits that process's preferences and errors.

In a benign example, a model estimating a building's restoration duration is predicting an outcome. A model copying a maintenance manager's chosen work category is imitating a decision. Either can be useful, but an evaluation must say which claim it supports.

For the civilian-consequence work here, the proposed first claim is deliberately narrow: agreement with a named reference on supplied scenarios, accompanied by a measured runtime comparison. There is no claim of autonomous decision quality.

## 5. Reinforcement learning: what changes conceptually

RL learns from interactions and their consequences rather than only a fixed list of input–target pairs. An environment supplies observations, accepts actions, and returns feedback as an episode progresses. Gymnasium's [basic usage documentation](https://gymnasium.farama.org/introduction/basic_usage/) explains this interface and distinguishes environment reset, interaction steps, and episode endings.

RL therefore requires more than converting CSV rows into tensors. It requires a coherent account of how a world evolves after a choice, what the learner can observe, and how outcomes are assessed. Those definitions can be harder to validate than the learning algorithm.

In a benign building-restoration study, the research question could be whether earlier maintenance choices affect later service availability. Merely displaying the buildings on a map would not supply those dynamics. Likewise, a history of outcomes does not automatically provide a trustworthy interactive environment.

### 5.1 Questions an RL study must be able to answer

These are general research questions, not a weapon-policy specification:

- What makes the task sequential rather than repeated prediction?
- Which effects persist over time?
- What information is hidden, delayed, or uncertain?
- Does the feedback actually reflect the stated outcome of interest?
- Could a learner receive favorable feedback while exploiting a modeling mistake?
- What distinguishes task completion from a run stopped by a time or compute limit?
- What evidence supports the transition behavior of the environment?
- What simpler explanation could account for an apparent improvement?

If these questions are unanswered, selecting an RL algorithm does not remove the underlying uncertainty.

### 5.2 A fixed dataset is not automatically an RL environment

There is a distinction between supervised examples, recorded sequences, and an interactive simulator. They support different analyses. Historical sequences can omit outcomes that were never observed. An interactive simulator can generate those outcomes, but only under its assumptions.

This document does not prescribe an RL algorithm or training configuration for the interception project. If learning RL itself is a goal, a standard benign reference environment can demonstrate the mechanics without entangling them with the validity of this project's consequence models.

## 6. Understanding “100+ things at once”

There are at least three different problems hidden inside that phrase:

| Problem | Benign example | What it establishes |
|---|---|---|
| Many independent predictions | Predict restoration duration for many unrelated buildings. | Throughput and predictive generalization. |
| Many related observations | Several facilities depend on the same electricity supply. | Correlation and shared context matter. |
| Sequentially coupled outcomes | A restoration decision changes later public-service availability. | Earlier choices can affect later outcomes. |

Counting objects does not identify which problem exists. Processing order also does not establish physical independence.

Two useful questions for the civilian model are: “Would this site's predicted outcome change if another site's condition changed?” and “Would the same visible conditions have different outcomes because of earlier history?” These expose missing context without assuming a particular learning method.

Generalizing from a small setting to a larger one remains an empirical claim. A model that behaves correctly on familiar small examples has not, by that fact alone, demonstrated behavior on large, interacting systems. The current repository's single-scenario tests do not establish that broader claim.

## 7. What the current data can and cannot teach

Today's package contains useful structure: site identifiers, time conditions, uncertainty bounds, information states, source references, and consequence estimates. These are assets for an auditable prediction study.

But three distinctions matter:

1. **Repeated conditions are not independent observations.** Six rows for one site may share the same census allocation, coefficients, and source vintage.
2. **Assumption bounds are not automatically calibrated confidence intervals.** A lower and upper value can describe a declared plausible range without having a known probability of containing a real outcome.
3. **A normalized score is not a physical measurement.** A score on a 0–100 scale does not become a casualty count, outage probability, or number of people simply because it is numerical.

Preserve the difference between a measured quantity, an aggregate allocated to a site, a derived estimate, and an assumption. Otherwise a downstream model can make guessed quantities look more authoritative than their source.

### 7.1 Suggested record audit for civilian prediction

Before treating any table as learning-ready, review these fields:

| Item | Question to answer |
|---|---|
| Example identity | Can this record be traced back to its source site and scenario? |
| Target definition | Is the target one quantity with explicit units and horizon? |
| Evidence state | Is the target measured, derived, assumed, or unavailable? |
| Dates | Are observation date and retrieval date distinguished? |
| Shared ancestry | Which records use the same underlying source or generated scenario? |
| Version | Which data snapshot and calculation produced the target? |
| Missingness | Is absence preserved instead of becoming a numeric zero? |
| Quality notes | Can a reviewer see known allocation and coverage limitations? |

This is an audit of civilian outcome data, not a training-record schema for interception actions.

## 8. Evaluation that supports an honest claim

For civilian-outcome prediction, separate three comparisons:

- **Prediction versus reference:** How far is the model's estimated quantity from the named observation or calculation?
- **Runtime versus reference:** Does the approximation save meaningful time on the actual workload?
- **Reference versus reality:** What independent evidence supports the calculation used to generate labels?

The first two can be measured without establishing the third. A hackathon presentation can be strong while explicitly limiting its claim to the first two.

Keep untouched evaluation examples separate from the development process. Preprocessing learned from data belongs to the training portion; test information must not influence it. This is the central leakage warning in the official [scikit-learn common-pitfalls guide](https://scikit-learn.org/stable/common_pitfalls.html).

Where records share facilities, scenario ancestry, or time periods, a random row split can make evaluation too easy. Grouped and time-aware splits address different dependence patterns; the appropriate choice depends on the intended future use. See [scikit-learn's cross-validation guide](https://scikit-learn.org/stable/modules/cross_validation.html).

### 8.1 Report sheet for a civilian predictor

| Evidence | Result | Limitation |
|---|---|---|
| Target and units | | |
| Reference source and version | | |
| Number of genuinely distinct evaluation cases | | |
| Typical prediction error | | |
| Large-error cases | | |
| Results by sector and evidence quality | | |
| Behavior with unavailable inputs | | |
| Runtime including input preparation | | |
| Peak process memory | | |
| Conditions outside evaluated scope | | |

Report failures as well as successes. A small clear result with visible limitations is easier to defend than a large aggregate improvement that hides where it breaks down.

### 8.2 Avoid circular evidence

If labels are produced by an existing formula, reproducing those labels demonstrates approximation of the formula. It does not validate the formula's social or physical meaning. If the formula is inexpensive already, a learned approximation also needs a reason to exist beyond its name.

The checked-in project benchmarks predate today's consequence integration. They are useful historical engineering measurements, but they are neither a new training benchmark nor evidence that a learned model improves real-world outcomes.

## 9. What makes the demonstration compelling

Your question about what “sounds cooler” has a practical answer: the strongest story explains a difficulty, shows a measurable contribution, and survives follow-up questions.

A civilian-prediction demonstration can show:

- the source evidence and assumptions for a supplied disruption;
- the reference consequence estimate;
- the learned estimate beside it;
- error and runtime on examples excluded from development;
- a difficult example where uncertainty or missing information matters.

That presentation makes the engineering visible. Adding “RL” to a slide without a demonstrated sequential problem and an evaluated environment is a weaker claim, even if the term attracts attention.

Useful wording when supported by results: “We approximate this versioned consequence calculation and report its error on held-out scenarios.” Avoid claiming “learned physics” when the target is a hand-built score.

## 10. Your actual Mac and what is known

A read-only inspection during this session reported:

| Property | Observed |
|---|---|
| Machine | MacBook Pro |
| Chip | Apple M5 Pro |
| CPU cores | 15 |
| Installed memory | 24 GB |
| Existing repository virtual environment | Python 3.9.6 |
| Training performance | Not measured |
| PyTorch/MPS readiness in a learning environment | Not verified |

Hardware identifiers are intentionally omitted. The memory figure is installed system memory, not an assertion that all of it is available to a training process.

PyTorch provides the `mps` backend for GPU computation on supported macOS systems. Its documentation distinguishes a build with MPS support from MPS availability on the running machine. Support must be checked for the actual installation and workload; the chip name alone is insufficient. See the official [MPS backend documentation](https://docs.pytorch.org/docs/stable/notes/mps.html).

The repository's working Python environment should not be assumed compatible with whichever learning-library versions are selected later. Use the current official [PyTorch installation selector](https://docs.pytorch.org/get-started/locally/) when preparing a separate learning environment; no learning stack was installed during this documentation task.

### 10.1 Practical feasibility assessment

My engineering expectation is that this machine is suitable for exploring modest tabular civilian predictors and small learning demonstrations. That is a provisional assessment, not a measured throughput guarantee.

The limiting factor could be raw-data acquisition, geometry processing, example generation, memory duplication, or model computation. A GPU does not automatically accelerate Python loops or geographic operations. Treat “simulation time,” “dataset preparation time,” and “training time” as separate measurements.

There is no evidence yet supporting a claim such as “a million cases will take one hour” or “RL needs a cloud GPU.” Neither estimate should be made without a representative workload.

### 10.2 Local-workload worksheet

For a benign civilian-prediction experiment, record:

| Measurement | Observed value |
|---|---|
| Data acquisition time, excluding cache hits | |
| Preparation time for one representative dataset | |
| Dataset size on disk | |
| Peak memory while loading and processing | |
| Reference calculation time | |
| Model fitting time | |
| Prediction time including preprocessing | |
| Whether accelerator use is verified | |
| Whether the browser/demo runs simultaneously | |

Do not purchase external compute merely because the algorithm name suggests it. First identify a measured bottleneck and the type of resource it needs. That avoids paying for a GPU when the slow component is elsewhere.

## 11. Current-session evidence

The following were completed before these documents were written:

- 88 new consequence tests passed after declared dependencies were installed.
- 110 existing backend unit tests and 33 existing integration tests passed.
- The three consequence command-line help paths loaded successfully.
- Hospital and school fixture exports produced six condition rows each with ordered score bounds and readable GeoJSON.
- Live MOH workbooks, the 337-row school directory, and a single-hospital OneMap lookup succeeded.
- The committed parks/civic, critical-sector, and defence CSV/JSON files passed basic structural checks.

The live rail run failed during an OpenStreetMap/Overpass SSL connection, followed by an OSMnx error-handler exception. Full live residential, road, and healthcare runs were not completed in this session. No training experiment, GPU benchmark, or learned-model evaluation has been performed.

These checks support software execution claims. They do not establish calibrated prediction accuracy or generalization.

## 12. Decisions that actually block a civilian learning study

| ID | Decision | Proposed position, not yet agreed | Owner / answer |
|---|---|---|---|
| L1 | Learning claim | Predict civilian consequences for supplied disruptions. | |
| L2 | Target | Select an outcome with explicit units and reference evidence. | |
| L3 | Label authority | Distinguish observed outcomes from simulator-derived targets. | |
| L4 | Generalization claim | Name the facilities, periods, and conditions to which the claim applies. | |
| L5 | Primary evidence | Report predictive error and runtime separately. | |
| L6 | Missing data | Preserve unavailable targets and inputs explicitly. | |
| L7 | Hardware budget | Measure local memory/time before selecting external compute. | |
| L8 | Method choice | Begin with supervised prediction for this bounded target; RL remains a separate research question. | |
| L9 | Demonstration format | Show held-out examples with provenance and limitations. | |
| L10 | Definition of done | A reproducible result another teammate can rerun. | |

The recommendation in L8 follows the bounded prediction target in L1. It is not a universal statement that supervised learning is better than RL.

## 13. Meeting worksheet

Complete these sentences before choosing a library or architecture:

> The model predicts ______ for ______ using information available at ______.

> Our reference target comes from ______ and has the following known limitations: ______.

> A successful result means ______ on evaluation examples that differ from development examples in ______.

> We will report these two things separately: ______ and ______.

> We will not claim the result establishes ______.

> Our time budget is ______, our available memory budget is ______, and the person responsible for reproducing the result is ______.

If the team cannot fill in the target or reference sentences, that is the immediate research blocker. Choosing RL first would move that ambiguity into an environment and feedback signal rather than resolve it.

## 14. Decisions captured from the conversation

Already stated by you:

- A learned model is the intended final product.
- The desired product output is one recommendation.
- Many interacting events matter to the eventual ambition.
- The current priority is combining the work, rather than polishing every edge case.
- You want comparative evidence of improvement over an immediate-response baseline.
- The available personal hardware is the M5 Pro MacBook Pro.

Still open:

- Whether civilian-consequence prediction is acceptable as a bounded learning deliverable.
- Which target has adequate evidence to support a learning claim.
- What existing simulator work, if any, exists outside the inspected main branch.
- Whether the project has a validated sequential environment; none was established in this review.
- Deadline, available experiment time, and ownership.

This document does not turn the desired interception recommendation into a training objective. It records the ambition while providing usable guidance for the civilian-prediction and general-learning portions.
