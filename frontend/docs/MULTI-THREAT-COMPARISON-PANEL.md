# Multi-threat consequence comparison panel

Status: frontend handoff specification. This describes a synthetic research/demo
view. It is not an operational interception controller, casualty predictor, or
statement of real defence capability.

## Implemented data handoff

The frontend now accepts a validated `multi-threat-comparison/2` result with any
positive number of threats. Data is selected in this order:

1. `?comparisonResult=/path/to/result.json` for a one-off run;
2. `VITE_COMPARISON_RESULT_URL` for a deployed simulation/backend endpoint;
3. the bundled fixture when neither is configured.

The endpoint must return JSON matching `src/demo/comparison-contract.ts`. A
failed request or invalid contract is shown as an unavailable state rather than
silently falling back to demonstration values. The panel identifies whether it
is showing the fixture or a validated simulation result.

For large batches, the map constructs one ordinary moving path per threat and
only one additional highlighted path plus two outcome circles for the selected
threat. The missile selector provides direct access without paging through the
entire batch.

The `All missiles` view provides a scenario-wide comparison and per-missile
drill-down. Until the backend supplies overlap-adjusted aggregate values, it
uses explicit presentation methods: sums for exposure, fatalities and service
service-hours lost; a maximum for response delay; and means for success and H/E/D/X/R/A.
The UI states that exposure totals are not deduplicated across overlapping
outcome areas.

## 1. What exists now

The current Cesium demo already provides:

- a full-screen Singapore map with paths, markers, ground circles, labels, and
  camera framing;
- a single-threat `planning-result/1` reader in
  `src/demo/decision-model.ts`;
- a bottom decision tray in `src/demo/decision.ts` that compares representative
  candidate areas by exposure, supplied success, and intercept time;
- a second Cesium canvas in `src/demo/inspector.ts` for a close-up of one area;
- population and public OpenStreetMap military layers; and
- pure model tests under `../tests/unit/`.

The new presentation should be a separate retrospective comparison mode. The
existing tray models a live choice and a FIRE action; the new mode explains two
already-calculated outcomes for several synthetic threats. Do not put a live
FIRE control in the comparison panel.

## 2. Core comparison

Never call an option merely "unoptimised" in the data. Give the baseline policy
a stable ID and visible definition. Recommended first baseline:

```text
baseline policy: earliest-feasible-v1
display label: Baseline: earliest feasible
rule: choose the first candidate that satisfies the supplied feasibility rules,
      without using the consequence vector
```

The comparison is then auditable:

```text
Baseline: earliest feasible  versus  Optimised: consequence-aware-v1
```

The backend owns both selections and all outcome calculations. The frontend
only validates, formats, compares, and displays supplied values.

## 3. Screen layout

### Map

- Keep all missile/projectile tracks visible at the same time.
- Give each threat a short display ID such as `M-01`, `M-02`, and `M-03`.
- Render the selected threat at full opacity and a slightly greater line width.
- Render other threats at about 25-35% opacity so the multi-threat context
  remains visible without competing with the selected comparison.
- Change the selected threat's outcome display with the current story stage:
  - **Baseline:** show only the baseline point and path emphasis in amber/red;
  - **Optimised:** replace it with the optimised point in teal/green;
  - **Improvement:** show both points and a thin dotted connector labelled
    "alternative outcomes".
- Selecting a threat on the map updates the panel. Using panel Previous/Next
  controls highlights and frames the corresponding map track.
- Do not invent an origin, post-intercept path, physical footprint, or result.
  Any illustrated geometry must be labelled `illustrative`; model-supplied
  geometry must carry its model/version in the payload.

### Three-stage story

The selected missile should progress through three ordered screens:

```text
1  BASELINE  ->  2  OPTIMISED  ->  3  IMPROVEMENT
```

This is stage navigation, separate from the Previous/Next missile controls.
Show a small numbered stepper at the top of the panel and one clear action at
the bottom:

- Baseline: `Show optimised outcome`
- Optimised: `Compare outcomes`
- Improvement: `Next missile`

Users may go back to an earlier stage. Selecting another missile always opens
that missile at Baseline so the audience experiences the same story in order.

### Stage 1: Baseline panel

Keep the map dominant and use a fixed right panel around 420-460 px wide.
Display only the baseline result:

1. `Missile 2 of 5` navigator and scenario condition.
2. `Baseline (unoptimised)` heading and its exact policy rule, such as
   `Earliest feasible intercept`.
3. Baseline headline outcomes: exposure, simulated casualties when supplied,
   service disruption, capability continuity, and recovery.
4. Baseline H/E/D/X/R/A vector.
5. Top affected categories and active hard flags.
6. Data confidence and assumptions.
7. `Show optimised outcome` action.

The purpose is to let the audience understand the consequence of the simple
rule before seeing any green improvement figures.

### Stage 2: Optimised panel

Keep exactly the same metric order, labels, units, and scales as Baseline. This
makes visual comparison possible from memory without moving information around.
Display:

1. `Optimised` heading and policy/version.
2. Optimised headline outcomes.
3. Optimised H/E/D/X/R/A vector.
4. Ranked affected categories and evidence quality.
5. `Compare outcomes` action.

Do not explain why it was selected or reveal accepted trade-offs on this screen;
those belong to the Improvement stage, where the supporting comparison is
visible. A brief transition may animate each bar from its baseline value to its
optimised value, but it must settle quickly and respect reduced-motion settings.

### Stage 3: Improvement table

Expand the panel to roughly 720-840 px on desktop so the map remains visible
behind it. Include an expand icon for an optional full-screen table; on mobile,
this stage is full-screen by default. The table is the primary content:

| Measure | Baseline | Optimised | Improvement | Interpretation |
|---|---:|---:|---:|---|
| People potentially exposed | 10,400 | 4,000 | 6,400 fewer (61%) | Lower residential occupancy exposure |
| Essential-service disruption | 830k service-hours | 240k service-hours | 71% lower | Avoids major water dependency |
| `H` Human exposure | 78 | 42 | 36 lower | Improvement remains under high estimate |
| `D` Capability continuity | 35 | 41 | 6 worse | Accepted capability trade-off |

Use two table groups: **Outcome metrics** followed by **H/E/D/X/R/A**. Directly
below the table, add two clearly separated sections in this order:

1. **Why this was selected**: the two to four strongest benefits, each linked
   to a row in the comparison table.
2. **Accepted trade-offs**: every material metric that became worse, plus any
   timing, success-probability, uncertainty, or constraint cost.

Place robustness and the evidence summary after these sections. Keep active hard
flags above the table. If no material trade-off was supplied, display
`No material trade-off identified in the supplied comparison` rather than
hiding the section.

The third stage compares only the selected missile. After the final missile,
an optional `All missiles` summary may aggregate compatible metrics, but it must
state how overlap and double counting were handled.

### Persistent right-panel rules

The panel or expanded analysis view should scroll independently of the map.
Keep content as full-width sections separated by rules, avoid cards inside
cards, and use tabular numerals for every metric. Use distinct labels for
`Previous missile`/`Next missile` and `Previous stage`/`Next stage`; do not show
two unexplained pairs of arrow buttons.

## 4. Headline metrics

Display four to six metrics by default. Recommended order:

| Metric | Display rule |
|---|---|
| People potentially exposed | Low-central-high people; always show coverage status |
| Simulated estimated fatalities | Show only when explicitly supplied by a versioned casualty model; use a range, never a single certain count |
| Serious injuries | Same rule as fatalities |
| Essential-service disruption | Service-hours lost: people affected multiplied by hours without the service |
| Capability continuity | `D` score; optionally a supplied synthetic response-delay range |

The frontend must not estimate fatalities from `peoplePotentiallyExposed` or
turn a `D` score into delay minutes. If those fields are unavailable, show
`Not modelled`, not zero.

An improvement should be presented as a reduction, so the sign is easy to
understand:

```text
reduction = baseline.central - optimised.central
reduction_percent = reduction / baseline.central
```

Use "reduced by 68%" instead of displaying a negative number. If the optimised
value is worse, label it "increased by" and style it as an accepted trade-off.

## 5. H/E/D/X/R/A display

Use the existing 0-100 consequence-vector definitions:

| Code | Label | What the panel should reveal |
|---|---|---|
| `H` | Human exposure | People present, vulnerability, and occupancy condition |
| `E` | Essential services | Loss of healthcare, water, power, transport or other essential services |
| `D` | Capability continuity | Authorised abstract value; never infer sensitive capacity in the frontend |
| `X` | Cascading effects | Top dependency contributions and double-counting status |
| `R` | Recovery effort | Relative difficulty and resources required to restore normal operations |
| `A` | Additional hazards | Hazard bands and whether each value is sourced or assumed |

Each row should contain:

```text
H  Human exposure       Baseline 78 [72-84]   Optimised 42 [36-50]   36 lower
```

- Keep the baseline and optimised bars on the same 0-100 scale.
- Show low/high as a whisker or text range around the central value.
- Lower is better for all six consequence dimensions.
- Add a tooltip with the full factor name and unit/method summary.
- Preserve `null` as `Not available`; do not draw it as zero.
- Add an assumption marker to values whose information state is `assumption`.
- If a weighted total is displayed, show the active policy ID, weight values,
  and supported-weight coverage beside it. Never let the total replace the
  six-factor vector or active hard flags.

Suggested compact weights for a demo fixture, not a deployment policy:

```json
{
  "H": 0.30,
  "E": 0.18,
  "D": 0.20,
  "X": 0.12,
  "R": 0.10,
  "A": 0.10
}
```

These weights must arrive in the result payload with a policy/version. They
should not be hard-coded into the panel.

## 6. Twelve affected categories

Use the taxonomy already documented in
`docs/specifications/singapore-consequence-model.md`:

1. Aviation zones (`aviation`)
2. Defence and security (`defence_security`)
3. Energy and fuel (`energy_fuel`)
4. Water and drainage (`water_drainage`)
5. Healthcare and emergency services (`health_emergency`)
6. Transport networks (`transport`)
7. Port and maritime (`port_maritime`)
8. Dense residential (`residential`)
9. Commercial and civic (`commercial_civic`)
10. Industrial and logistics (`industrial_logistics`)
11. Green, open and recreation (`green_recreation`)
12. Water bodies and coastal areas (`water_coastal`)

Show only categories contributing materially to the selected outcome, sorted by
their supplied contribution. A row should explain the main mechanism, for
example `Residential: occupancy exposure` or `Water: downstream service loss`.
The category is an explanation, not a permanent priority rank.

## 7. Why-this-changed section

Generate this section from structured backend explanation codes and evidence
references. The frontend resolves each reference against the supplied baseline
and optimised values, calculates the difference, and writes consistent display
text. A good result contains both benefits and costs:

```text
Why the optimised outcome was selected

- Reduces simulated people potentially exposed by 6,400 (61%).
- Avoids the highest-ranked water-service dependency in this scenario.
- Lowers cascading consequence X from 58 to 24.

Accepted trade-off

- Intercept occurs 3.2 s later and supplied success is 1.8 percentage points lower.
```

Recommended reason codes:

- `human_exposure_reduced`
- `essential_service_avoided`
- `capability_continuity_preserved`
- `cascade_reduced`
- `recovery_shortened`
- `additional_hazard_avoided`
- `success_probability_tradeoff`
- `intercept_time_tradeoff`
- `hard_constraint_applied`
- `uncertainty_preference`

## 8. Additional useful information

These items make the panel more honest and more useful than another large total
score:

- **Uncertainty width**: whether the result still improves under low/high bounds.
- **Robustness**: percentage of sampled scenarios in which the optimised option
  has lower total consequence than the baseline.
- **Data coverage**: share of active policy weight supported by sourced,
  assumed, restricted, and unavailable inputs.
- **Binding constraint**: the feasibility or hard-policy rule that eliminated
  nearby alternatives.
- **Sensitivity**: the one factor or weight whose plausible change could reverse
  the recommendation.
- **Top affected services**: at most three service/dependency contributions,
  with units rather than another score.
- **Candidate rank**: selected candidate rank and number of feasible candidates.
- **Scenario condition**: day/night, weekday/weekend, event state, operating
  state, and degraded-system state.
- **Aggregate scenario summary**: optional collapsed footer for all missiles.
  Aggregate only compatible quantities and state whether cross-threat overlap
  was removed; otherwise show per-missile values only.

## 9. Proposed wire contract

Add a new contract instead of overloading `planning-result/1`, whose current
shape represents one threat and candidate opportunities.

```ts
type DimensionCode = "H" | "E" | "D" | "X" | "R" | "A";
type InformationState =
  | "measured" | "official_aggregate" | "derived"
  | "operator_input" | "restricted_input" | "assumption" | "unavailable";

interface RangeValue {
  unit: string;
  low: number | null;
  central: number | null;
  high: number | null;
  informationState: InformationState;
  confidence: "A" | "B" | "C" | "D" | "E" | null;
  sourceIds: string[];
  modelId?: string;
  modelVersion?: string;
}

interface OutcomeMetric extends RangeValue {
  id: string;
  label: string;
  description: string;
  unit: "people" | "person-hours" | "days" | "minutes";
}

interface DimensionValue {
  low: number | null;
  central: number | null;
  high: number | null;
  informationState: InformationState;
  confidence: "A" | "B" | "C" | "D" | "E" | null;
  evidenceIds: string[];
}

interface Outcome {
  candidateId: string;
  policyId: string;
  policyVersion: string;
  position: { lon: number; lat: number; height: number };
  timeFromStartS: number;
  suppliedSuccessProbability: number | null;
  displayArea?: {
    kind: "circle";
    radiusM: number;
    modelId: string;
    modelVersion: string;
  };
  metrics: {
    peoplePotentiallyExposed: RangeValue;
    simulatedEstimatedFatalities?: RangeValue;
    seriousInjuries?: RangeValue;
    essentialServicePersonHours?: RangeValue;
    simulatedCapabilityDelayMinutes?: RangeValue;
  };
  vector: Record<DimensionCode, DimensionValue>;
  weightedTotal?: DimensionValue;
  flags: Array<{ id: string; active: boolean; basis: string }>;
  categoryContributions: Array<{
    category: string;
    contribution: DimensionValue;
    mechanism: string;
  }>;
  dataCoverage: {
    sourcedWeight: number;
    assumedWeight: number;
    restrictedWeight: number;
    unavailableWeight: number;
  };
}

interface ThreatComparison {
  threatId: string;
  displayId: string;
  samples: Array<{ time: string; lon: number; lat: number; height: number }>;
  baseline: Outcome;
  optimised: Outcome;
  explanations: Array<{
    code: string;
    kind: "benefit" | "tradeoff" | "constraint";
    references: Array<{
      type: "metric" | "dimension" | "success_probability" | "intercept_time" | "category" | "constraint";
      id?: string;
    }>;
    sourceIds: string[];
  }>;
  robustness: {
    lowerConsequenceSamples: number;
    sampleCount: number;
    method: string;
    sourceIds: string[];
  };
}

interface MultiThreatComparisonResult {
  schemaVersion: "multi-threat-comparison/2";
  scenarioId: string;
  generatedAt: string;
  synthetic: true;
  condition: {
    localTime: string;
    dayType: string;
    operatingState: string;
    eventState: string;
    systemState: string;
  };
  scorePolicy: {
    id: string;
    version: string;
    weights: Record<DimensionCode, number>;
  };
  threats: ThreatComparison[];
  provenance: { sourceIds: string[]; limitations: string[] };
}
```

Contract validation should reject duplicate threat IDs, non-finite geometry,
out-of-order samples, scores outside 0-100, invalid low/central/high ordering,
fractions outside 0-1, unknown selected candidate IDs, and missing reason metric
references. It should preserve unknown category and reason codes for forward
compatibility.

## 10. Frontend state

Keep one small UI state object:

```ts
interface ComparisonState {
  selectedThreatIndex: number;
  stage: "baseline" | "optimised" | "improvement";
  comparisonExpanded: boolean;
  expandedSections: Set<string>;
}
```

Required actions:

- `selectThreat(index)` wraps or disables at the ends; choose one behaviour and
  make the disabled state visible, and reset `stage` to `baseline`;
- `selectThreatById(id)` is used by map picking;
- `setStage(stage)` changes panel content and map emphasis without recalculating
  data;
- `setComparisonExpanded(value)` controls the wide/full-screen table;
- URL query state such as `?threat=M-02&stage=improvement` is optional but useful for
  sharing a demo state.

Keyboard support can use Left/Right for missile navigation when focus is not in
a form control. The visible icon buttons remain the primary controls.

## 11. File-level implementation plan

Recommended additions:

| File | Responsibility |
|---|---|
| `src/demo/comparison-contract.ts` | Wire types and strict result validation |
| `src/demo/comparison-model.ts` | Pure deltas, formatting, ranges, coverage, and navigator state |
| `src/demo/comparison-panel.ts` | Right-panel DOM and accessible interactions |
| `src/demo/multi-threat-map.ts` | One set of Cesium layers per threat and selected-state styling |
| `../data/results/demo-multi-threat-comparison.json` | Clearly synthetic integration fixture |
| `../tests/unit/comparison-model.test.ts` | Pure contract and calculation tests |

Recommended modifications:

- `src/demo/main.ts`: mount the comparison mode and pass the existing canvas.
- `src/demo/style.css`: reserve right-panel width, add responsive bottom-sheet
  rules, fixed metric columns, range bars, and focus states.
- `package.json`: include `comparison-model.test.ts` in `npm test`.
- `src/demo/decision.ts`: leave intact initially; select comparison mode via a
  local feature flag or separate demo entry, then retire the old tray only after
  the new flow is verified.

Reuse `canvas.addPath`, `canvas.addMarkers`, `canvas.addGroundCircles`,
`framePose`, and the existing basemap/lighting synchronisation. Do not create a
second Cesium canvas for the new right panel; the close-up inspector is costly
and the comparison needs room for evidence, not another map.

## 12. Calculation and formatting rules

- Deltas are pure functions and must be unit-tested.
- The frontend never recomputes H/E/D/X/R/A from raw observations.
- Display at most two significant decimals for percentages and one for scores.
- Format people as whole numbers and time using the largest readable unit.
- If either compared central value is null, the delta is `Not comparable`.
- A low/high range is shown only when all three values are present and ordered.
- Probability differences use percentage points, not percent change.
- The robustness percentage must include its sample count.
- Active hard flags sit above the weighted total and cannot be hidden in an
  accordion.
- Never label people exposed as deaths. The casualty field has its own model,
  provenance, and uncertainty.

## 13. Acceptance checks

1. Five synthetic threats can animate simultaneously without the selected
   threat navigation changing simulation time.
2. Clicking a track and using Previous/Next produce the same selected state.
3. Selecting a new missile opens Baseline; the user can progress Baseline ->
   Optimised -> Improvement and return without losing the selected missile.
4. Baseline shows only the baseline map outcome, Optimised only the optimised
   outcome, and Improvement shows both unambiguously; all other threats remain
   visible.
5. Baseline and optimised panels keep metrics in the same order and use the same
   units, scale, and range rules.
6. Every H/E/D/X/R/A row supports low/central/high, null, confidence, and an
   assumption marker.
7. Improvement contains a table with baseline, optimised, improvement, and
   interpretation columns for headline metrics and all six vector factors.
8. The panel explains at least one benefit and every material accepted trade-off.
9. Unknown categories/reasons render readable fallback labels without failure.
10. Missing casualty or capability-delay fields display `Not modelled`.
11. Data coverage totals to 1 within a documented tolerance and is visible.
12. Active hard flags remain visible in all three stages.
13. The layout fits at 1440x900 and 390x844 without text overlap or map controls
    becoming unreachable.
14. `npm test` and `npm run build` pass, and desktop/mobile screenshots confirm
    the Cesium scene is nonblank.

## 14. Suggested demo story

1. Begin with the whole island and all synthetic inbound tracks visible.
2. Select `M-01`; the panel opens at Baseline.
3. Explain the baseline rule and let the audience see its outcomes and vector.
4. Choose `Show optimised outcome`; the map and panel change to the optimised
   result using the same metric layout.
5. Choose `Compare outcomes`; the panel expands into the improvement table.
6. Explain the largest gains, then the accepted timing/success trade-off and
   uncertainty.
7. Choose `Next missile`; `M-02` opens at Baseline so the story repeats under a
   different condition and category mix.
8. End on the optional all-missiles summary, while stating that values are synthetic
   model outputs and not observed outcomes.
