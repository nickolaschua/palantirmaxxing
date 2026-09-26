# Structured Imitation Learning

## Executive summary

The structured imitation-learning path is implemented, tested, and has completed
a full 512-case behavior-cloning plus three-round DAgger campaign. The repository
contains all trained artifacts and validation reports, but none passed every
promotion gate. The deterministic naive policy therefore remains the operational
fallback and the learned policies remain experimental.

The canonical result is documented in
`data/results/rl/experiments/structured-imitation-512-seed7/README.md`. The best
candidate, DAgger round 3, achieved an 82.8% validation win rate and 15.0% lower
mean cost, but six of 64 episodes violated constraints and its bootstrap interval
crossed zero. The 256-case held-out suite remains sealed.

For a demo of the learned policy, demonstration generation alone is not enough. The minimum complete workflow is:

1. Generate expert demonstrations from the verified 512-scenario development-training pool.
2. Train the behavior-cloning student and run its mandatory overfit diagnostics.
3. Evaluate it on all 64 frozen validation scenarios.
4. If behavior cloning misses any promotion gate, allow the pipeline to run up to three DAgger rounds.
5. Use the artifact named by `promotion.json` only when `promoted` is `true`. Otherwise, use the deterministic naive policy and describe the imitation model as experimental.

The 256-case held-out suite must remain sealed until the final artifact identity has been frozen. It is not part of normal development or model selection.

## What was implemented

### Generic policy loading

The learning layer now has a common `Policy` contract with:

- `model_version`
- `predict(observation, deterministic, action_masks)`
- `close()`

`load_policy()` automatically dispatches to either PPO or structured imitation based on artifact metadata. Metadata without an `algorithm` field is treated as legacy PPO. The existing explicit PPO loader, `load_normalized_policy()`, is unchanged for existing callers.

### Expert demonstration generation

Demonstrations are generated from the verified `development-training` pool only. Validation, held-out, stress, out-of-distribution, and assignment-reference records are rejected.

The teacher is the exact fixed-rank optimizer. It is privileged, clairvoyant, and offline: it may use future information and must never be presented as the deployable online policy.

For every training episode, the generator:

- computes an exact fixed-rank plan;
- replays that plan through `CentralizedInterceptionEnv`;
- labels every currently valid action consistent with the optimal plan as acceptable;
- uses the lowest acceptable action index only to advance deterministic replay;
- labels `ADVANCE_ACTION` only when no planned assignment is currently visible and valid;
- produces no positive cancellation labels in the initial behavior-cloning dataset;
- rejects duplicate episodes, incompatible provider assumptions, identity mismatches, and plans that cannot be replayed exactly.

The resulting `imitation-demonstrations/1` dataset uses checksummed NPZ shards containing:

- 24 decision-level state features;
- ragged valid-action offsets;
- 44 action-local features;
- environment action indices;
- set-valued acceptable-target flags;
- scenario, profile, and family provenance.

The pool is split deterministically 90/10 by `family_id`, keeping each family entirely within one split. Frozen validation data is never used for normalization, early stopping, or tuning.

### Structured behavior cloning

The observation-only student scores the currently valid actions. Each action combines threat, assignment, interceptor, candidate, and action-type features. Assignment, cancellation, and advance are represented by a three-way type indicator.

The network is permutation-invariant over the valid-action set:

- a shared encoder processes each action;
- a state encoder processes the 24 state features;
- mean and max pooling summarize the valid-action set;
- a shared scalar head scores each valid action.

Continuous normalization statistics are computed from the internal training split only. Training uses set-valued masked cross-entropy, so probability assigned to any acceptable expert action counts as correct.

Default training configuration:

- CPU
- seed `7`
- AdamW
- learning rate `1e-3`
- decision batch size `128`
- maximum `100` epochs
- early-stopping patience `10`
- best internal-validation checkpoint

The saved `policy-artifact/1` contains the model, normalization statistics, dataset and feature checksums, observation-layout checksum, training-pool/provider/generator identities, dependency versions, teacher disclosure, and training metrics.

### Mandatory diagnostics

Training must pass both diagnostics before frozen validation:

1. Single-scenario overfit: 100% acceptable-action agreement, identical terminal score to the teacher, normal termination, and zero constraint violations.
2. Fixed 16-scenario overfit: at least 95% acceptable-action agreement, valid actions only, normal termination for every episode, and zero constraint violations.

The diagnostics use dedicated probe models trained to overfit the reserved scenarios. A failure means the pipeline should stop and investigate feature extraction, masks, targets, or capacity instead of proceeding to frozen validation.

### Evaluation and promotion

Evaluation reports use schema `policy-evaluation/3`.

The primary comparator is the online, detected-threat-only `NaiveLaunchOnDetectionPolicy`. Feasible immediate matching and exact fixed-rank optimization are reported separately as offline references. Reports identify the policy algorithm and artifact, comparator scope, offline reference scope, completion and constraint outcomes, score differences, regret, latency, and profile-level results.

Behavior cloning or DAgger is promoted only if all five frozen-validation gates pass:

- zero constraint violations;
- win rate against the naive policy of at least 60%;
- mean improvement over the naive policy of at least 5%;
- 95% bootstrap interval for favorable mean difference excludes zero;
- decision-path p95 is below 100 ms.

### Conditional DAgger fallback

DAgger runs only when the initial behavior-cloning artifact fails at least one validation gate.

Its privileged residual expert solves the remaining optimization problem from each student-visited simulator state. It keeps locked assignments fixed, creates cancellation targets for inconsistent tentative assignments, excludes expired or invalid candidates, optimizes remaining active and future threats over remaining resources, and retains tied optimal next actions as a set.

Each round rolls the student over the training pool, deduplicates visited states by observation-plus-mask hash, unions tied targets, aggregates the new labels with the original dataset, and fine-tunes from the previous checkpoint at learning rate `3e-4`. At most three rounds are permitted.

If no round passes every validation gate, no learned model is promoted. `NaiveLaunchOnDetectionPolicy` remains the deterministic fallback and the imitation results must be described as experimental.

## Commands to produce a demo artifact

Use the repository's RL virtual environment and run from the repository root.

### 1. Generate demonstrations

```bash
.venv-rl/bin/python scripts/generate_imitation_dataset.py \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-512-seed7/demonstrations \
  --seed 7
```

This produces a manifest and checksummed NPZ shards. It is training input, not a deployable policy.

For a quick pipeline smoke test only, add `--diagnostic-limit 2`. Do not use a limited dataset as the final demo model.

### 2. Train, validate, and conditionally run DAgger

```bash
.venv-rl/bin/python scripts/train_imitation.py \
  --dataset data/results/rl/experiments/structured-imitation-512-seed7/demonstrations \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-512-seed7/pipeline \
  --seed 7 --epochs 500 --diagnostic-limit 16 \
  --validation-and-dagger
```

This is the recommended end-to-end command. It trains behavior cloning, runs the mandatory diagnostics, evaluates all 64 frozen validation cases, and invokes DAgger only if needed.

Inspect:

```text
data/results/rl/experiments/structured-imitation-512-seed7/pipeline/promotion.json
```

If `promoted` is `true`, use `selected_artifact_dir` as the model directory. The selected directory contains the runtime files:

- `model.pt`
- `normalization.npz`
- `policy-metadata.json`

If `promoted` is `false`, use `naive-launch-on-detection/1` for the demo and label the learned result experimental.

### 3. Evaluate the selected artifact

For validation or a repeatable CLI demonstration, pass the promoted artifact directory as `--model-dir`, along with the Singapore provider, generator, and original training pool:

```bash
.venv-rl/bin/python scripts/evaluate_rl.py \
  --model-dir /absolute/path/from/selected_artifact_dir \
  --suite validation \
  --provider singapore-demo-v2 \
  --generator singapore-v2 \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output data/results/rl/experiments/structured-imitation-512-seed7/repeat-validation.json
```

The original training pool must remain available at inference/loading time because artifact loading verifies its identity and provenance.

### 4. Open held-out only after promotion

Do this once, only after `promotion.json` has frozen an accepted artifact:

```bash
.venv-rl/bin/python scripts/evaluate_rl.py \
  --model-dir /absolute/path/from/selected_artifact_dir \
  --suite held-out-test \
  --provider singapore-demo-v2 \
  --generator singapore-v2 \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --promotion-record data/results/rl/experiments/structured-imitation-512-seed7/pipeline/promotion.json \
  --output data/results/rl/experiments/structured-imitation-512-seed7/held-out-evaluation.json
```

The evaluator verifies the promotion record and artifact identity, then marks the held-out suite as opened. Do not use the held-out result to tune and rerun the same development cycle.

## What is needed for the actual presentation

For a learned-policy CLI or recorded demo, prepare:

- the verified `sg2-pilot-512-v1` training pool;
- the generated demonstration dataset while training;
- a successful `promotion.json`;
- the selected artifact's three runtime files;
- a `policy-evaluation/3` report showing the five promotion gates;
- a clear disclosure that the teacher and exact optimizer are clairvoyant/offline references while the student is observation-only.

The demonstration shards are not used directly for inference after training, but should be retained for reproducibility. The original scenario pool is required by the current strict artifact loader.

The learned policy is usable through the Python loader and evaluation CLI. It is not yet wired into the frontend/API live-run controls. A browser-based live demo therefore needs a separate backend endpoint and frontend selection/display integration. Until that is added, the safe demo format is CLI output, a saved evaluation report, or a pre-recorded run.

## Expected training time

These are planning estimates from local smoke tests and existing machine measurements, not a full 512-case benchmark:

| Stage | Rough time |
|---|---:|
| Demonstration generation over 512 cases | 10–25 minutes |
| Initial behavior cloning and diagnostics | 15–30 minutes |
| Frozen 64-case validation | A few minutes |
| Total if behavior cloning passes | About 30–60 minutes |
| Each DAgger round | About 30–60 minutes |
| Worst case with all three DAgger rounds | About 2–4 hours total |

For demo-day planning, budget four hours and run the pipeline ahead of time. Do not rely on training live during the presentation.

## Verification already completed

The implementation has been exercised with:

- the complete Python unit/integration suite: 267 tests passed;
- the focused learning suite: 40 tests passed;
- Python compilation and whitespace validation;
- deterministic dataset-generation smoke tests producing identical dataset and shard checksums;
- generic imitation loading and `policy-evaluation/3` report generation;
- DAgger aggregation smoke testing;
- a tiny two-episode training CLI run that passed its reduced diagnostic setup;
- a refreshed project knowledge graph.

The full 512-case generation, training, and 64-case validation campaign is now
also complete. Behavior cloning and all three DAgger rounds failed at least the
zero-violation and bootstrap-confidence gates, so no production imitation
artifact was promoted. The one-time 256-case held-out evaluation was not run.

## Relevant code

- `backend/learning/imitation.py`: features, dataset generation/loading, model, training, diagnostics, residual expert, and DAgger.
- `backend/learning/policy.py`: common policy protocol.
- `backend/learning/training.py`: generic and PPO-specific policy loading.
- `backend/learning/evaluation.py`: online comparator, offline references, reports, metrics, and gates.
- `scripts/generate_imitation_dataset.py`: demonstration generation CLI.
- `scripts/train_imitation.py`: behavior cloning and conditional DAgger CLI.
- `scripts/evaluate_rl.py`: generic artifact evaluation and held-out guard.
- `tests/unit/test_imitation_learning.py`: structured imitation regression tests.

## Recommended demo decision

Use the deterministic naive policy for the operational demo. The completed
`promotion.json` has `promoted: false`; the structured imitation artifacts may
be shown only as experimental comparisons. Round 3 is the strongest learned
comparison, but its six validation violations prevent promotion. Describe the
exact fixed-rank optimizer as an offline teacher/reference, not as the online
deployed policy.
