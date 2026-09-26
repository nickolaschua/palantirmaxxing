# Imperfect-condition imitation data

This folder is the self-contained handoff for adding imperfect conditions to
the imitation-learning dataset. It prepares training inputs and validation
rules; it does not select an action or provide operational thresholds.

## Contents

- `imperfect-condition-scenario-matrix-v1.json`: 29 balanced condition
  archetypes covering a control, each condition alone, every two-condition
  pair, six severe triples, and one all-condition stress case.
- `imperfect-condition-demonstration-example.json`: one contract-valid
  synthetic demonstration showing the final joined record shape.
- `condition-data-dictionary.json`: field meanings, units, scope, null rules,
  and whether each value is observed, derived, or expert-labelled.
- `source-registry.json`: public Singapore inputs and research references,
  with limitations and intended uses stated explicitly.

The executable record contract is documented in
`contracts/imperfect-condition-demonstration.md`. Runtime validation lives in
`backend/domain/imperfect_conditions.py`; matrix generation and validation live
in `backend/domain/imperfect_condition_matrix.py`.

## How to use it

1. Apply every matrix row as an overlay to each selected base scenario family.
2. Keep all overlays of a base family in the same train, validation, or test
   split to prevent leakage.
3. Populate source-native measurements where available. Do not invent a value
   solely to fill a nullable field.
4. Compute candidate-local building intersections against the same mapped
   geometry version for every candidate in an episode.
5. Run the existing simulation or teacher over the complete joined scenario.
6. Add the teacher's acceptable action set, selected action, outcome, and only
   those explanation codes supported by recorded evidence.
7. Regenerate the imitation demonstrations and feature checksum, retrain, and
   report results separately for control, single, pair, severe, and stress
   groups.

The matrix contains 34 weighted slots: six control slots and 28 degraded
slots. Every retained condition appears in exactly 10 weighted slots. These
weights balance a training set; they are not claims about real-world frequency.

## Important limits

- The checked imitation model does not yet consume these features and must not
  be described as condition-aware.
- All matrix rows are unlabelled. The example label is synthetic and only
  demonstrates the data shape.
- Public weather observations describe environmental conditions, not their
  effect on a simulated system. Performance changes must come from the chosen
  simulator or a documented teacher, with uncertainty retained.
- `building_path_intersection` is action-local. It must not be copied into the
  global state vector.
- Missing measurements remain `null`; missingness should be tested explicitly
  instead of silently replacing it with zero.

Rebuild the deterministic matrix with:

```sh
python3 scripts/build_imperfect_condition_matrix.py
```
