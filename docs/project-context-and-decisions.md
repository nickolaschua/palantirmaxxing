# Project context and decision workbook

Prepared 25 September 2026. Inspected main-branch baseline: `93ebb72`.

Companion: [Training considerations](training-considerations.md).

## 1. Purpose, scope, and how to use this workbook

This is a consolidated record of what the repository contains, what today's commits contributed, what you have already decided, and what remains unresolved. It is designed to let you work through the project without repeating the earlier conversation or rereading every sector guide.

The implementation guidance here concerns civilian-consequence data, interpretation, reproducibility, and presentation. Existing interception-related components are described factually. This workbook does not provide a design for weapon-interception optimization, engagement logic, resource allocation, or an autonomous weapon-policy training environment.

Labels used throughout:

- **Confirmed:** supported by inspected code, Git history, or a completed check.
- **Documented:** asserted by a repository guide but not independently exercised in full during this session.
- **Proposed:** a suggested next decision, not an agreement or implemented feature.
- **Open:** information not established by the inspected repository or conversation.

The workbook deliberately distinguishes a software gap from a modeling decision and a research claim. They need different kinds of evidence.

## 2. Your intended project, recorded accurately

Your clarification changed the emphasis of the discussion. You are not primarily asking for a static data dashboard or for a small frontend-only integration. You see today's sector work as a collection of parameters and considerations for a broader simulation and optimization system. You want generated examples to support a learned final product.

Your stated ambitions are:

1. Combine the existing work into a complete working pipeline.
2. Represent consequences across multiple kinds of civilian infrastructure and activity.
3. Produce a learned model whose eventual interface gives one recommendation.
4. Address the concern that many events may interact rather than behave independently.
5. Demonstrate improved outcomes against an immediate-response baseline.
6. Work within hackathon/MVP constraints instead of treating every refinement as a release blocker.

These are user-stated goals. They are not statements that the current code already implements them or that the requested optimization system is covered by this workbook.

### 2.1 Corrections to earlier summaries

- The frontend is not wholly disconnected from backend results: it imports a precomputed `planning-result/1` artifact.
- The new consequence package is not yet connected to that existing result calculation or frontend contract.
- Today's commits do contain consequence dimensions and demonstration weights. It was inaccurate to imply there was no proposed objective information at all.
- Consequence scoring does not itself supply debris physics or establish an overall decision rule.
- Passing all automated tests does not mean the live data pipeline has completed successfully for every sector.

## 3. Today's commits and attribution

All times below are Singapore time on 25 September 2026.

| Commit | Git author | Time | Confirmed contribution |
|---|---|---|---|
| `f84c158` | `jiajun-19` | 03:29 | Added Singapore consequence evidence datasets, builders, spreadsheets, and raw geographic downloads. |
| `3b58d22` | `tzcemman` | 10:38 | Added/consolidated the consequence package, Python sector pipelines, shared model and source handling, tests, and guides; relocated evidence tables and removed tracked raw parks downloads. |
| `93ebb72` | `Emman` | 10:42 | Merge of the consolidation into main. |

The two Emman author names use the same Git email identity. This attribution is based on Git records, not a claim about who performed every part of the underlying work. No separate commit attributed to “Jian” was identified in today's inspected main-branch history. Work on other branches or machines remains open.

The pull advanced main from `891c1b5` to `93ebb72` without conflicts. Relative to the earlier main, the final change added 47 files under the consequence package. The intermediate deletion of raw geographic files was cleanup of material added earlier that day, not deletion of the existing population subsystem.

## 4. Architecture as it exists today

There are several connected and partially separate strands of work:

| Strand | Current role | Evidence |
|---|---|---|
| Population preparation | Creates versioned Singapore population geography and provenance. | [Data-source guide](../backend/data_sources/data_sources.md) |
| Population exposure | Calculates exposure for caller-supplied footprints. | [PEC contract](../contracts/pec.md) |
| Existing static evaluator | Processes one synthetic scenario and reports trade-space alternatives. | [Static evaluator](../backend/orchestration/static_scenario.py) |
| Result presentation | Serializes existing scenario results for the demo. | [Presenter](../backend/presentation/planning_result.py) |
| Frontend demo | Loads a precomputed result and presents it with visualization. | [Decision entry point](../frontend/src/demo/decision.ts) |
| New consequence package | Produces sector profiles and demonstration scores. | [Package guide](../backend/data_sources/consequence/consequence.md) |
| Learning system | Proposed in planning documents; no completed training pipeline established in this review. | [Existing plan](../newplan.md) |

The new package and existing static evaluator are separate calculation paths. A successful sector CSV export does not imply those consequences appear in the frontend's comparisons.

### 4.1 Existing interception-related code: factual status only

The inspected evaluator works with one supplied threat/interceptor scenario, synthetic success assumptions, and supplied circular footprints. It reports multiple representative alternatives. It does not establish calibrated real-world physical performance.

No multi-event sequential learning environment, trained policy, or model registry was established in this review. These absence statements apply to inspected main-branch code, not unseen teammate work.

The existing benchmark is an engineering fixture. Its synthetic values should not be promoted to operational specifications. This workbook does not reproduce those values or turn them into an implementation plan.

### 4.2 Existing frontend integration

[decision.ts](../frontend/src/demo/decision.ts) imports `data/results/demo-planning-result.json`. The frontend [result types and parser](../frontend/src/demo/decision-model.ts) describe population exposure, supplied assumptions, alternatives, and comparisons. They do not currently carry the full new sector consequence profiles.

This means a frontend exists and a file-based handoff exists. A live backend API and a generalized consequence presentation are different pieces of work. Neither should be assumed complete merely because the animation runs.

## 5. What each new sector actually supplies

| Sector | Supplied material | Current calculation status | Main qualification |
|---|---|---|---|
| Transport | Roads and MRT/LRT code; optional DataMall reader. | Shared Python scoring pipeline. | Rail defaults to category estimates without supplied passenger volumes; live rail run failed in this session. |
| Residential | HDB and private-housing allocation/profile code. | Shared Python scoring pipeline. | Census allocation and occupancy assumptions; full live run not completed here. |
| Healthcare | Public acute hospitals. | Shared Python scoring pipeline. | Nine hospitals described; public-data coverage is narrower than all healthcare. |
| Education | MOE schools, grouped inside healthcare pipeline. | Shared Python scoring pipeline. | School-level occupancy derives from level aggregates and assumptions. |
| Parks/civic | Sites, scenarios, source metadata, workbook, builder. | Evidence tables; not routed through the shared scorer. | Catalog coverage does not establish measured occupancy for every venue. |
| Critical sectors | Energy, water, aviation, port system profiles. | Evidence tables, including selected populated dimensions. | System-level aggregates are not facility-level observations. |
| Defence dependencies | Abstract archetypes, public evidence, input templates. | Evidence material only. | No site-level operational capability data supplied by this work. |

Sector guides: [transport](../backend/data_sources/consequence/transport/transport.md), [residential](../backend/data_sources/consequence/residential/residential.md), [healthcare](../backend/data_sources/consequence/healthcare/healthcare.md), [parks/civic](../backend/data_sources/consequence/parks_civic/parks_civic.md), [critical sectors](../backend/data_sources/consequence/critical_sectors/critical_sectors.md), [defence](../backend/data_sources/consequence/defence/defence.md).

The taxonomy in the specification is broader than implemented coverage. A named category in that taxonomy is not evidence of a complete dataset or runnable model for that category.

## 6. What the consequence model already defines

The profile contract includes identifiers, geography, condition, occupancy, service beneficiaries, disruption assumptions, alternative capacity, recovery, vulnerability, hazard information, and provenance-bearing estimates.

The score vector is:

| Symbol | Meaning in the project | Current qualification |
|---|---|---|
| H | Human exposure with vulnerability considerations. | A normalized model output, not a casualty forecast. |
| E | Essential civilian-service loss. | Relies on beneficiaries, duration, loss, and substitute-capacity assumptions. |
| D | Authorized abstract capability continuity. | Unavailable in the scored civilian sectors without a supplied input. |
| X | Cascading consequences. | Shared scorer currently leaves this unavailable. |
| R | Functional recovery. | Derived from modeled time to restoration. |
| A | Additional hazard potential. | Potential at a site, not a probability of activation. |

The shared scorer has a versioned `demo-v1` blend and separate flags. The specification labels the blend as a demonstration policy. This establishes that some preference information exists; it does not establish empirical calibration or agreement on a complete downstream decision policy.

Sources: [profile contract](../backend/data_sources/consequence/profile.py), [scorer](../backend/data_sources/consequence/scoring.py), and [model specification](../backend/data_sources/consequence/docs/singapore-consequence-model.md).

### 6.1 What the six time conditions mean

The scored sectors share weekday morning peak, weekday midday, weekday evening peak, weekday night, weekend day, and weekend night conditions. The current shared conditions describe normal operation. Closed, degraded, and other operational modes mentioned in the broader specification are not all implemented by that list.

Time-conditioned profiles are useful, but they do not constitute a dynamic simulation. Six different static estimates do not alone describe transitions from one state to another.

### 6.2 What “unavailable” means

The intended contract is that unsupported values remain unavailable, rather than becoming zero. This is especially important when combining datasets with different evidence quality.

Some current implementation details fall short of that intent, as recorded in section 10. The relevant MVP choice is whether a particular unsupported field is excluded, displayed with its qualification, or corrected before use. Silently interpreting it as absence of consequence is not justified by the data.

## 7. The missing scientific connection

The sector work mainly answers questions of the form: “Who or what is present here, under this condition, and what would a declared disruption mean?” It does not by itself answer: “What damage will a particular physical event cause?”

Three claims therefore require separate support:

1. **Spatial association:** a supplied event footprint overlaps or relates to some civilian assets.
2. **Functional consequence:** the event produces a stated loss of service or recovery burden.
3. **Learning validity:** a model predicts those consequences adequately beyond its development examples.

An overlap is not automatically damage, and damage is not automatically complete loss of service. Treating them as identical can be an explicit synthetic assumption, but it must remain visible as such.

This is a modeling-definition issue, not something solved by a different CSV format or more training epochs. The civilian-model decision to resolve is the meaning and evidence behind each reported outcome for a supplied disruption.

## 8. Evidence from testing in this session

| Check | Result | What it does not establish |
|---|---|---|
| New consequence test suite | 88 passed. | Real-world model calibration. |
| Existing backend unit suite | 110 passed. | Full live acquisition across all new sectors. |
| Existing backend integration suite | 33 passed. | A trained model or multi-event environment. |
| Dependency consistency | `pip check` reported no broken requirements. | All network/runtime paths succeed. |
| Three sector CLI help paths | Passed. | Completion of a production run. |
| Hospital/school fixture exports | Passed. | Complete live healthcare/education generation. |
| MOH workbook acquisition/parsing | Passed for both checked feeds. | Clinical outcome accuracy. |
| School directory acquisition | 337 rows returned. | Individual school headcounts. |
| OneMap single-hospital lookup | Passed. | Full geocoding coverage. |
| Committed evidence table format checks | Passed. | Factual verification of every cell. |
| Live rail pipeline | Failed on Overpass SSL connection and subsequent OSMnx error handling. | The failure does not by itself identify the root cause as local versus remote. |

The local environment emitted an urllib3 warning about its LibreSSL build. That warning is relevant to investigation, but the session did not prove that it caused the rail failure.

No source changes were made while running those checks. Missing declared dependencies were installed in the existing `.venv`. Generated check outputs were written under `outputs/consequence-validation/`, and live downloads created package-local cache files.

The frontend test suite was not rerun in this session. Historical frontend test counts in planning documents should not be reported as newly verified results.

## 9. Decisions to settle for the civilian-consequence subsystem

These are proposed decision records, not hidden requirements for completing an interception system.

| ID | Open decision | Why it matters | Suggested MVP disposition |
|---|---|---|---|
| C1 | What counts as a reported civilian outcome? | Exposure, service disruption, and recovery have different meanings. | Keep named quantities and units visible. |
| C2 | Which sectors have comparable evidence? | A system aggregate and a building estimate cannot be treated as the same resolution. | Preserve native resolution and evidence state. |
| C3 | Which inputs are observed versus assumed? | A generated number can otherwise look measured. | Carry source/method/state alongside outputs. |
| C4 | How are overlapping populations interpreted? | Residents, commuters, patients, and beneficiaries can overlap. | Report separate quantities unless a defensible combination is available. |
| C5 | What does an uncertainty range claim? | Plausibility bounds and statistical intervals differ. | Describe the construction instead of assigning an unsupported confidence level. |
| C6 | How is unavailable data displayed? | Missing information can be confused with no impact. | Use an explicit unavailable status. |
| C7 | How is data age interpreted? | Source vintage and download date are different. | Show both where known. |
| C8 | What happens if acquisition fails? | A demo may be blocked by a remote service. | Preserve verified snapshots and report their vintage. |
| C9 | What is the demonstration claim? | The same visualization can imply very different levels of validity. | State a scoped consequence-model or prediction claim. |
| C10 | Who owns each unresolved assumption? | Unowned assumptions become accidental defaults. | Assign a person and an evidence link. |

### 9.1 Questions to bring to the team

- Is there additional simulation work outside the inspected main branch?
- Which sector authors have already generated usable outputs, and can they identify the input versions?
- Which reported quantities have been checked against independent observations?
- Which assumptions are intentional demonstration simplifications?
- Does the team agree that the current total is provisional?
- Which external dependencies are essential during the presentation, and which can use saved artifacts?
- Who owns the final wording of uncertainty, data coverage, and evidence quality?
- What is the actual deadline for the combined civilian-consequence demonstration?

These questions avoid asking teammates to repeat the sector inventory. They ask for evidence and ownership that are not established by the commit messages.

## 10. Refinements, ranked for an MVP rather than a production release

You explicitly said not every rough edge is a major issue. The following separates interpretation problems from polish.

### 10.1 Address before presenting the affected result as trustworthy

**Unknown flags can read as false.** A reproduced example with missing occupancy produced `False` for the high-exposure flag. A reader can mistake that for evidence of low exposure. Clarify or correct this if the flag is displayed.

**Validation permits impossible ranges.** Negative occupancy passed validation and then failed during scoring; alternative capacity above 100% also passed. If inputs are externally supplied, this can cause either confusing failures or misleading output. The issue is in the [profile validation](../backend/data_sources/consequence/profile.py).

**Some exports remove warning fields.** Housing, hospital, and school CSVs are trimmed after `total_status`. Transport exports retain more diagnostic information. This is documented behavior, but consumers must know that missing columns do not mean there were no warnings. See [pipeline.py](../backend/data_sources/consequence/pipeline.py).

These are concrete reproductions from the earlier review, not newly fixed behavior.

### 10.2 Document or defer when outside the demonstrated scope

- Dependency-cascade scoring is unavailable in the shared scorer. A current demo can state that limitation.
- More comprehensive healthcare coverage can be a later data milestone.
- Uncalibrated occupancy and recovery assumptions can remain visible as assumptions for a synthetic demonstration.
- Inconsistent comments should be corrected when touched, but do not justify redesigning the package.
- Performance work should follow measurement; the session did not identify a model-training bottleneck.

### 10.3 Specific confusing points worth knowing

The rail module's opening comment says missing passenger volumes make stations unrankable, while the implementation and guide use category priors by default. The guide is the more accurate description of current behavior.

The residential guide explicitly says census-derived `source_date` values are omitted to avoid marking every row stale under the shared threshold. The vintage is retained elsewhere. A consumer using only the stale flag will therefore miss that age information.

The export path scores before it validates and can short-circuit validation for an unrankable profile. A malformed profile with unavailable occupancy was reproduced as exportable. That is a boundary-validation issue, rather than evidence that all existing generated rows are malformed.

The capability-breach flag has no positive evaluation path in the current shared flag function. This documents incompleteness; it does not justify inferring a capability threshold or filling one in without a defined source.

## 11. Reproducible civilian data handoff

The team can make the current work materially easier to combine without inventing new physics or decision logic. For each civilian-sector artifact, collect:

| Handoff item | Expected answer |
|---|---|
| Artifact location | Exact CSV/GeoJSON/JSON files. |
| Producing version | Git commit and producing component. |
| Input snapshot | Source identifiers, dates, and checksums where available. |
| Geographic meaning | Coordinate system and point/polygon/system resolution. |
| Time meaning | Applicable condition and source observation period. |
| Units | People, hours, rates, scores, or another explicit quantity. |
| Unavailable values | How absence is encoded and why. |
| Assumptions | Parameters that were not observed directly. |
| Coverage | Included, skipped, unmatched, and unsupported records. |
| Verification | What was checked against fixtures or independent evidence. |
| Owner | Who can explain and regenerate the artifact. |

This is the immediate handoff I recommend for the civilian data work. It lets you tell which outputs are ready to consume and which are only conceptual evidence, without rebuilding every sector during integration.

### 11.1 Avoid accidental loss of outputs

The package guide says sector runs overwrite their outputs. In particular, transport road-only and rail-only runs use the same default filenames. Preserve separate run artifacts or explicitly record that a transport directory contains only one half.

Cache and generated output directories are ignored by Git. Pulling the latest code therefore does not mean the machine contains the teammates' processed results. A shared artifact handoff is a distinct task from a successful Git pull.

## 12. What “the whole pipeline works” can mean

There are several levels of completion. Use one explicit definition rather than allowing each teammate to assume a different one.

| Level | Evidence of completion | Current session status |
|---|---|---|
| Imports and tests | Declared dependencies resolve and checked test suites pass. | Demonstrated for the checked Python suites. |
| Sector execution | Each chosen live source can produce its documented outputs. | Partially demonstrated; full runs remain open. |
| Civilian data consistency | Units, identity, condition, missingness, and provenance are understood across artifacts. | Not established end to end. |
| Consequence interpretation | Reported effects have explicit assumptions and support. | Partially specified; no independent calibration established. |
| Presentation | Viewer displays the intended artifact with correct meaning. | Existing static result is integrated; new sector results are not. |
| Learning demonstration | A model has a defined target, reproducible training evidence, and untouched evaluation. | Not implemented or evaluated in this session. |

Completing one row does not establish the next. This table is a way to give progress updates without overstating the result.

## 13. Proposed next civilian-data deliverables

These are deliberately narrower than the requested weapon-recommendation system and can be worked on independently:

1. **Evidence inventory:** one table identifying the exact usable output for every civilian sector and its owner.
2. **Shared interpretation sheet:** definitions of quantities, time conditions, uncertainty, and missingness, with exceptions listed.
3. **Saved demonstration snapshot:** a reproducible set of supplied civilian disruption examples and their consequence outputs.
4. **Consequence viewer:** display of those outputs with source vintage, assumptions, and incomplete coverage visible.
5. **Civilian-prediction study:** a separately scoped learning experiment described in the companion document, if accepted by the team.

The purpose is to make existing evidence inspectable and reusable. None of these deliverables selects an interception point or directs weapon employment.

## 14. Decision register to fill in

Use one entry per decision. An empty answer remains open; it does not silently adopt the suggested default.

```text
Decision ID:
Question:
Confirmed facts:
Options being considered:
Chosen answer:
Reason:
Assumptions retained:
Evidence link:
Owner:
Date:
What would make us revisit this:
```

Starter register:

| ID | Decision | Status | Owner | Evidence / answer |
|---|---|---|---|---|
| D01 | Exact civilian outcome definitions for the demonstration | Open | | |
| D02 | Sector artifacts available from each teammate | Open | | |
| D03 | Treatment of unavailable and assumption-only fields | Open | | |
| D04 | Interpretation of overlapping populations and beneficiaries | Open | | |
| D05 | Named reference for a civilian-prediction target | Open | | |
| D06 | Coverage and uncertainty language in the viewer | Open | | |
| D07 | Reproducible saved data snapshot | Open | | |
| D08 | Deadline and integration ownership | Open | | |
| D09 | Learning demonstration scope from the companion document | Proposed; not agreed | | |
| D10 | Additional relevant work on other branches | Unknown | | |

## 15. Reading map

| Need | Read |
|---|---|
| Understand the new package | [Consequence overview](../backend/data_sources/consequence/consequence.md) |
| Understand intended semantics | [Consequence specification](../backend/data_sources/consequence/docs/singapore-consequence-model.md) |
| Check implemented data fields | [Profile definitions](../backend/data_sources/consequence/profile.py) |
| Check implemented scoring behavior | [Scoring implementation](../backend/data_sources/consequence/scoring.py) |
| Check export behavior | [Pipeline](../backend/data_sources/consequence/pipeline.py) |
| Understand current population exposure | [PEC contract](../contracts/pec.md) |
| Locate existing static evaluator | [Static scenario contract](../contracts/static-scenario-evaluation.md) |
| Understand current frontend consumption | [Decision entry point](../frontend/src/demo/decision.ts) |
| Understand broader proposed direction | [Existing operational-consequence plan](../newplan.md) |
| Work through the learning choice | [Training considerations](training-considerations.md) |

Planning documents can contain intended behavior beyond the current implementation. Where a guide conflicts with code, record the discrepancy rather than assuming either that the feature is complete or that the entire guide is obsolete.

## 16. What remains unknown after this review

This workbook covers the inspected main branch and the conversation. It cannot establish unseen teammate work, the credibility of an external physical simulator, the evidence behind every source row, the final deadline, or an agreed multi-event operational policy.

The concrete work already demonstrated is useful: versioned population data, tested exposure calculations, a static result viewer, and a broader set of civilian-consequence profiles and evidence. The immediate civilian-data task is to make those artifacts consistent, interpretable, and reproducible. The learning decision can then be discussed against an explicit prediction claim rather than an ambiguous promise to train “an AI.”
