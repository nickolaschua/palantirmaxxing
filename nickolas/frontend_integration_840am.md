# Frontend–backend integration plan (8:40 am)

## Current answer on the footprint radius

The intended supplied footprint radius is **100 m**. The checked-in planning and simulation result files both contain 100 m. The stale 500 m sentence in `frontend/docs/API-DESIGN.md` was corrected. The circle is a supplied ground consequence area, **not** a validated blast radius or calculated debris envelope.

Changing a radius in backend code **does not immediately change the frontend today**. Both views import checked-in JSON at build time. A change has to flow through backend evaluation, result export, and a frontend rebuild or reload. A future API can make a newly fetched run reflect the latest backend result; an already displayed run still needs an explicit refresh or update event.

The single-threat planning demo and the eight-threat simulation are separate pipelines. They do not share one runtime variable or one result contract.

| Path | Backend source | Wire field | Frontend behavior | Current limitation |
| --- | --- | --- | --- | --- |
| Single-threat planning | `data/scenarios/demo-singapore.json` → `footprint_radius_m` → evaluated candidate footprint | `candidates[].footprint.radiusM`; also `assumptions.footprintRadiusM` | Candidate circles, history marks, bursts, camera framing, and area wording read the exported values. | The frontend validates that each value is positive, but does not validate that candidate radii and the assumptions radius agree. It reads bundled `demo-planning-result.json`. |
| Eight-threat simulation | `SingaporeScenarioConfig.supplied_footprint_radius_m` and `SingaporeConsequenceProvider.footprint_radius_m` | `selectedFootprints[].radiusM` and `terminalCounterfactualFootprints[].radiusM` | Drawn circles use `radiusM`. | The parser requires exactly 100 m; the exporter, contract, and UI wording contain literal “supplied 100 m area.” It reads bundled `demo-simulation-result.json`. |

The planning backend checks that an enriched candidate's footprint matches the radius passed to its exporter. The simulation exporter reads its radius from episode scenario metadata, while the consequence provider can be constructed with a separate radius. The current export script constructs the provider and generator separately at their 100 m defaults. If only one default changes, assessed consequences and exported circles may disagree; integration should reject that mismatch.

The canvas burst library has a 500 m fallback, but the planning decision view passes each option's `footprint.radiusM` explicitly. That fallback does not determine the current demo radius.

Relevant code and contracts:

- [Planning scenario](../data/scenarios/demo-singapore.json), [backend exporter](../backend/presentation/planning_result.py), [frontend loader](../frontend/src/demo/source.ts), [parser](../frontend/src/demo/decision-model.ts), and [renderer](../frontend/src/demo/decision.ts).
- [Simulation scenario](../backend/simulation/singapore_scenario.py), [consequence provider](../backend/simulation/singapore_provider.py), [backend exporter](../backend/presentation/simulation_result.py), [frontend parser](../frontend/src/demo/simulation-model.ts), and [view](../frontend/src/demo/simulation.ts).
- [Planning contract](../frontend/docs/API-DESIGN.md) and [simulation contract](../contracts/simulation-result.md).

## Integration sequence when the backend pipeline is ready

### 1. Decide which result each screen consumes

Keep `planning-result/1` for the single-threat decision demo and `simulation-result/1` for the eight-threat rollout, or design a new unified result with a new schema version. The existing contracts are intentionally distinct. Planning carries candidate options, a human selection flow, synthetic success probabilities, exposure comparisons, and a 2D trajectory shown at a synthetic height. Simulation carries eight trajectories, assignments, events, selected and terminal-counterfactual footprints, physical consequence evidence, an ordinal objective, and policy comparison. Neither frontend parser can accept the other payload.

Decide whether the simulation view should remain a static overlay or become an episode playback. It currently toggles eight paths and selected circles; it does not replay the backend's event stream or assignments.

### 2. Establish one radius source for each run

Use one scenario radius to build candidate footprints, assess exposure/consequences, generate the result, and supply display wording. Pass the simulation scenario configuration into the provider instead of relying on matching defaults. Before export, assert that the provider's assessed radius, scenario metadata, every footprint `radiusM`, and any top-level assumption agree.

Changing radius is a **new evaluation**, not a styling update. It can change population exposure, consequence scores, candidate eligibility, Pareto choices, representative IDs, comparisons, and the visible area. Regenerate all of those together. If 100 m is a fixed rule, retain a clear fixed-radius contract and reject other values. If it is configurable, remove the simulation parser's exact-100 check and derive labels from the payload.

### 3. Freeze and test the API contracts

Agree on field names, units, null/omission rules, IDs, ordering, and versions before connecting a live data source. Important translations include:

| Backend concept | Frontend wire field | Decision to document/test |
| --- | --- | --- |
| `footprint_radius_m` or `supplied_footprint_radius_m` | `footprint.radiusM` or `selectedFootprints[].radiusM` | Metres; same value used in assessment and drawing. |
| `time_from_start_s` | `timeFromStartS` | Seconds relative to the planning clock. |
| Simulation detection and episode time | `detectionTimeS`, `timeFromDetectionS`, `timeFromEpisodeStartS`, absolute `time` | State which clock drives playback and deadlines. |
| EPSG:3414 projected coordinates | WGS84 `lon`/`lat` | Backend performs conversion; frontend receives degrees. |
| Planning synthetic visualization height | `position.height` | Presentation only; backend planning calculation is 2D. |
| Simulation vertical trajectory | `position.heightM` | Height above the synthetic terminal ground plane; different meaning from planning height. |
| Backend candidate/opportunity identity | `id`, `opportunityId`, `threatId` | Keep references stable and validate all cross-links. |
| Missing or unavailable evidence | omitted field or explicit `null` | Preserve the distinction from a numerical zero. |

The planning contract currently lives in `frontend/docs/API-DESIGN.md`; the simulation contract lives in `contracts/simulation-result.md`. Maintain generated examples and Python/TypeScript contract tests against the same exported artifacts. Introduce a new schema version for incompatible changes rather than silently reinterpreting fields. The simulation contract and parser currently require eight trajectories, eight assignments, and 20 samples per trajectory; changing episode shape also needs a contract decision.

### 4. Reconcile consequence evidence

The planning inspector currently injects deterministic, clearly labelled illustrative H/E/D/X/R/A scores because `planning-result/1` does not export candidate consequence rows. The backend simulation exports a different structure: candidate assessment snapshots, population and expected-casualty evidence, intersected sites, physical components, and an ordinal training objective. These are **not** directly interchangeable with the inspector's `Consequence` type.

Define a presentation adapter for the actual backend output. For each displayed figure, specify its unit, scenario/condition, confidence or range, provenance, availability rule, and whether it is a score, physical estimate, or training objective. Remove the illustrative injection once the real field is supplied. Do not present ordinal objective cost as people exposed or expected casualties. Confirm the dimension naming: the current frontend uses `H` for human exposure, whereas the provider's candidate assessment uses `C` for casualty evidence and site-level `C/E/D/X/R/A` scores. That mapping needs an explicit product and model decision.

### 5. Connect delivery and refresh

Add a versioned result delivery path for each chosen contract, with stable run/episode IDs, schema version, status/error response, and provenance. Replace the frontend's JSON imports with fetches at a defined point in the UI lifecycle. Validate each response before rendering and show a clear unavailable state on contract failure.

Decide what “immediate” means:

- **New run fetch:** the next run loads the newest backend result. This is the simplest integration.
- **Explicit refresh or polling:** a displayed view can load a newer completed result.
- **Pushed update:** the backend notifies the browser when a new result is ready.

Keep history snapshots tied to the result/run that produced them; do not silently apply new radius or consequence values to a past run. Define caching and stale-result behavior so a regenerated artifact cannot be mistaken for the result currently on screen.

### 6. Verify the full loop

Run the backend pipeline, export or serve the result, parse it in the frontend, and compare the rendered radius, centre, wording, time, option IDs, consequence values, and provenance with that exact backend run. Include a changed-radius test **if configurability is supported**, plus a mismatched-radius case that must fail. Test missing and null evidence, unknown schema versions, invalid coordinates/times, and stale run identity.

The frontend's Cesium circle is a visual approximation; backend PEC exposure uses a polygonal circle approximation for calculation. If exact boundary correspondence becomes important, export the calculated polygon or define an explicit geometry tolerance in the contract.

## Current status

No live planning or simulation result API is connected. The backend pipeline can be completed independently before starting these integration changes. The 100 m documentation correction has been made; the integration work above remains to be done.
