# Structured imitation diagnostic, 32 episodes, seed 7

**Status:** passed after a controlled diagnostic-epoch extension.

## Question

Can the shared valid-action scorer pass the mandatory single-scenario and
fixed-16 overfit gates before we spend time on the complete 512-case campaign?

## Configuration

- Source pool: `sg2-pilot-512-v1`
- Pool manifest checksum:
  `sha256:c76f63f056f1dffbba090d720c48f3d2a1953d446e8e55c2f7c183b32d810495`
- Seed: 7
- Demonstration episodes: 32
- Training/internal-validation episodes: 26/6
- Exact teacher: privileged offline fixed-rank optimizer
- Student information scope: observation only

```bash
.venv-rl/bin/python scripts/generate_imitation_dataset.py \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-diagnostic-32-seed7/demonstrations \
  --seed 7 --diagnostic-limit 32

.venv-rl/bin/python scripts/train_imitation.py \
  --dataset data/results/rl/experiments/structured-imitation-diagnostic-32-seed7/demonstrations \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-diagnostic-32-seed7/artifact \
  --seed 7 --diagnostic-limit 16

# Controlled follow-up after the 100-epoch probe stopped short
.venv-rl/bin/python scripts/train_imitation.py \
  --dataset data/results/rl/experiments/structured-imitation-diagnostic-32-seed7/demonstrations \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-diagnostic-32-seed7/artifact-epochs500 \
  --seed 7 --diagnostic-limit 16 --epochs 500
```

## Gate

The single scenario requires 100% acceptable-action agreement, an exact
teacher score, normal termination, and zero invalid actions or violations. The
fixed 16 scenarios require at least 95% agreement, normal termination, and zero
invalid actions or violations. The full campaign starts only if both pass.

## Result and significance

The default 100-epoch attempt failed narrowly. Its fixed-16 probe passed with
98.11% rollout agreement and zero invalid actions or violations, while its
single-scenario probe reached 93.75% rollout agreement and a slightly worse
terminal score than the teacher. The failure metrics are preserved in
`artifact/overfit-diagnostics.json`.

The controlled 500-epoch-ceiling attempt passed both gates. The single probe
reached 100% agreement at epoch 115 and exactly replayed the teacher score. The
fixed-16 probe reached 100% agreement at epoch 110; every rollout terminated
normally with zero invalid actions and zero violations. The main 32-case model
selected epoch 14 and achieved 85.58% agreement on its six-episode internal
validation split. This is not a promotion result, but it establishes that the
structured representation can fit the mandatory training probes and permits
the full 512-case experiment.
