# Structured imitation, 512 episodes, seed 7

**Status:** complete; experimental and not promoted. The held-out suite remains
sealed.

See [VIOLATIONS_AND_NEXT_STEPS.md](VIOLATIONS_AND_NEXT_STEPS.md) for the exact
meaning and distribution of constraint violations and the recommended
safety-shield experiment.

## Question

Can a shared scorer over currently valid actions learn an observation-only
policy that is safe and materially better than the online naive policy across
the frozen 64-case validation suite?

## Configuration

- Source pool: `sg2-pilot-512-v1`
- Pool manifest checksum:
  `sha256:c76f63f056f1dffbba090d720c48f3d2a1953d446e8e55c2f7c183b32d810495`
- Demonstration checksum:
  `sha256:0c68a045671707ea0903cf48952ac2691b28df712f79ea94a0d7425a4043f71b`
- Episodes: 512 total, 420 training, 92 internal validation
- Decisions: 13,144
- Valid action examples: 397,450
- Shards: 8
- Seed: 7
- Maximum epochs: 500; early-stopping patience: 10
- Conditional DAgger: enabled, at most three rounds
- Teacher: privileged offline exact fixed-rank optimizer
- Student: observation-only structured valid-action scorer

```bash
.venv-rl/bin/python scripts/generate_imitation_dataset.py \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-512-seed7/demonstrations \
  --seed 7

.venv-rl/bin/python scripts/train_imitation.py \
  --dataset data/results/rl/experiments/structured-imitation-512-seed7/demonstrations \
  --pool data/scenarios/rl/pools/sg2-pilot-512-v1 \
  --output-dir data/results/rl/experiments/structured-imitation-512-seed7/pipeline \
  --seed 7 --epochs 500 --diagnostic-limit 16 \
  --validation-and-dagger
```

## Promotion gates

Promotion requires zero constraint violations, at least 60% wins against
`naive-launch-on-detection/1`, at least 5% mean improvement, a favorable 95%
bootstrap interval excluding zero, and decision-path p95 below 100 ms. Failure
of behavior cloning invokes up to three DAgger rounds. If no round passes,
`naive-launch-on-detection/1` remains the operational fallback.

## Results

| Candidate | Completion | Violations | Win rate | Mean improvement | 95% favorable-difference CI | Decision p95 | Result |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| Behavior cloning | 89.1% | 7/64 | 82.8% | +11.4% | [-0.4697, 0.9564] | 21.0 ms | Failed safety and CI gates |
| DAgger 1 | 81.2% | 12/64 | 76.6% | -12.9% | [-1.2434, 0.4891] | 16.7 ms | Regressed |
| DAgger 2 | 73.4% | 17/64 | 68.8% | -42.2% | [-2.0951, -0.1874] | 19.4 ms | Regressed further |
| DAgger 3 | 90.6% | 6/64 | 82.8% | +15.0% | [-0.3277, 1.0164] | 15.8 ms | Best cost result; failed safety and CI gates |

Every artifact passed the single-scenario and fixed-16 training probes after
the diagnostic probe optimizer was decoupled from DAgger's lower fine-tuning
rate. No validation candidate passed all five promotion gates.

`pipeline/promotion.json` records `promoted: false`, selects
`naive-launch-on-detection/1` as the deterministic fallback, and confirms
`held_out_suite_opened: false`.

## Significance

The structured representation is a substantial improvement over flat PPO. It
can exactly fit the mandatory probes and produces high validation win rates,
lower mean cost, and fast decisions. This demonstrates that learned policy
selection is viable enough to continue investigating.

It is not operationally safe yet. Rare action errors cause unhandled threats,
and the cost advantage is not statistically conclusive on 64 validation cases.
Naive DAgger aggregation was unstable: the first two rounds worsened safety and
mean cost, while the third recovered performance without reaching zero
violations. The next work should target safety-aware decoding or a deterministic
feasibility shield and improve residual-expert coverage before another model
selection campaign. More PPO steps or a larger scenario pool are not supported
by these results.

## Preserved interruptions and pipeline fixes

The archive retains three interrupted logs:

- `train-interrupted-dagger-path-bug.log`: missing parentheses in DAgger output
  path construction.
- `train-interrupted-dagger1-diagnostics.log`: the dedicated probe incorrectly
  inherited DAgger's 3e-4 fine-tuning rate.
- `train-interrupted-existing-dagger-manifest.log`: the pipeline could validate
  but not resume an existing checksummed DAgger dataset.

The implementation now saves failed overfit diagnostics, uses a fixed 1e-3
rate for dedicated probes, constructs DAgger paths correctly, and resumes an
existing DAgger dataset only when its checksum, round, base dataset, and student
artifact identity match.
