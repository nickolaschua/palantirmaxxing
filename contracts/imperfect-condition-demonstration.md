# Imperfect-condition imitation sidecar

`imperfect-condition-demonstration/1` is a simulation-only sidecar for one
decision in an imitation-learning demonstration. It does not control the
simulator and does not define operational thresholds.

## Scope

The contract intentionally contains only six retained conditions:

| Feature location | Feature |
|---|---|
| State | `heavy_rain` |
| State | `mist` |
| State | `strong_wind` |
| State | `sensor_outage` |
| State | `communication_delay` |
| Candidate/action | `building_path_intersection` |

State features describe what the student may observe at a decision. Building
intersection is candidate-specific, so it belongs beside each valid action.
The binary classifications are supplied by a scenario generator or labelled
dataset. This contract does not derive “heavy,” “strong,” or “delayed” from a
measurement.

Optional source-native values preserve rainfall rate, visibility, wind speed,
communication delay, unavailable sensor IDs, intersected building IDs, and
source IDs. No fixed multiplier converts these measurements into trajectory or
success changes.

## Imitation-learning join

Each sidecar is joined to the structured imitation dataset by `episode_id` and
zero-based `decision_index`. `selected_action_index` must belong to the
set-valued `acceptable_action_indices`. Candidate rows use the same action index
as the environment's current valid-action set.

The existing checked policy artifact was trained without these features. It
must not be described as condition-aware. Integration requires:

1. Append the five state flags to the student state features.
2. Append `building_path_intersection` to assignment-action features.
3. Regenerate demonstrations and feature checksums.
4. Retrain the imitation policy.
5. Evaluate normal, single-condition, combined-condition, and missing-data
   splits separately.

Do not label the expert action as “earlier because of rain” by rule. The expert
must select from the complete simulated case. A rain explanation is valid only
when the observation records heavy rain and the expert-labelled option has a
measured increase in replanning margin.

## Required validation

- All numbers are finite and nonnegative.
- Condition, candidate, action, building, sensor, and source IDs are explicit.
- `sensor_outage` agrees with the unavailable-sensor list.
- A building-exclusion reason requires at least one intersecting candidate.
- Rain or communication margin wording requires a recorded nonnegative margin
  delta.
- Explanation codes cannot claim a condition that is absent.
- The feature schema and checksum must match the reader exactly.

## Research basis

- FAA documentation explains that precipitation can absorb or scatter radar
  energy and that buildings can create blockage and reflections:
  https://www.faa.gov/sites/faa.gov/files/FAA-H-8083-28B.pdf
- GPS.gov identifies building blockage and reflected signals (multipath) as
  causes of degraded positioning accuracy:
  https://archive.gps.gov/systems/gps/performance/accuracy/
- NIST treats measurement uncertainty as incomplete knowledge represented by a
  probability distribution, rather than a single deterministic correction:
  https://www.nist.gov/itl/sed/topic-areas/measurement-uncertainty
- Singapore rainfall observations are available at station level every five
  minutes, but the publisher warns that gaps and local effects can occur:
  https://data.gov.sg/datasets/d_6580738cdd7db79374ed3152159fbd69/view

These sources justify modelling degraded observations and preserving
uncertainty. They do not provide interception-performance coefficients.

## Scenario matrix

The checked [imperfect-condition matrix](../data/imperfect_conditions/imperfect-condition-scenario-matrix-v1.json)
is an overlay for the existing base scenario families. It contains one control,
all six single-condition cases, all 15 two-condition combinations, six balanced
three-condition severe cases, and one all-condition stress case.

The control has sampling weight six and every other archetype has weight one.
This yields 34 weighted slots, with every retained condition active in exactly
10 slots. The weights are dataset-composition guidance, not probabilities of
real-world weather or system failures. All expert-label fields remain explicitly
unlabelled until the imitation teacher evaluates the joined base scenario.

The complete teammate handoff, including field definitions and source notes,
lives in [`data/imperfect_conditions`](../data/imperfect_conditions/README.md).
