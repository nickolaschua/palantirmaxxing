# RL experiments — recorded sequence

Status: both the 512-scenario pilot release and 10,000-scenario training release
are verified. The tiny-overfit, 50k generalization, and three 100k large-pool
pilots are complete. The learned policies failed their performance and
constraint gates; they are retained as diagnostic evidence rather than
presented as successful policies. The observed failure is under-learning, so
the conditional 25,000 expansion and live-generation lane are not activated.

## Recommended immediate order

1. Generate 512–1,000 scenarios for the first pilots; this repository starts with a verified 512-scenario release.
2. Run the tiny-overfit and 50k generalization experiments.
3. Generate a 10,000-scenario final pool in parallel while those experiments run.
4. Train the 100k multi-seed pilots on the larger pool.
5. Expand to 25,000 scenarios only if the training–validation gap shows memorization.
6. Keep a 5–10% optional live-generation lane only if validation suggests the fixed pool lacks diversity.

The dataset release identity and verification result must be recorded before step 2 begins. Pool size and run length are proposed experiment settings, not evidence that generalization has been established.

## Completed pilot evidence

All runs below used `sg2-pilot-512-v1`, the Singapore demo-v2 consequence
provider, MaskablePPO, seed 7, and frozen pool records. Lower cost is better.

| Run | Training scope | Steps | Result |
| --- | --- | ---: | --- |
| `single-overfit-10k-seed7` | One consequence-contrast record | 10,000 | Safe completion, but cost 1.9267 vs offline feasible reference 1.6317; failed the overfit gate |
| `single-overfit-50k-seed7` | Same single record | 50,000 | Safe completion and cost 1.4652 vs 1.6317; passed with a 10.2% improvement |
| `tiny-overfit-seed7` | 16 consequence-contrast records | 10,000 | Mean cost 4.3357 vs 1.7043, four violations; failed |
| `tiny-overfit-50k-seed7` | Same 16 records | 50,000 | Mean cost 4.3146 vs 1.7043, three violations; failed |
| `tiny-overfit-50k-gamma1-seed7` | Same 16 records, undiscounted episode objective | 50,000 | Mean cost 4.3474 vs online baseline 1.7958, four violations; failed |
| `tiny-overfit-8x50k-gamma1-seed7` | First eight consequence-contrast records | 50,000 | 100% completion, but mean cost 2.7455 vs online baseline 1.7555; failed consequence learning |
| `tiny-overfit-8x100k-gamma1-seed7` | Same eight records | 100,000 | Regressed to one violation, zero wins, and mean cost 3.6969 vs 1.7555; failed |
| `generalization-50k-seed7` | All 512 pilot records | 50,000 | Visited all 512 records one or two times; failed on both a 64-record training sample and 64 frozen validation records |

The generalization run completed 922 episodes in 271.5 seconds. On a
profile-stratified 64-record training sample, it had 21 constraint violations,
mean cost 5.5148, online-baseline cost 2.3935, and a 21.9% win rate. On the
independent validation split, it had 28 constraint violations, mean cost 6.6521,
online-baseline cost 2.6728, and a 17.2% win rate. The validation mean difference
was -3.9794 with a 95% bootstrap interval of [-4.9946, -3.0056]. The same
policy also lost to the offline feasible reference.

This is primarily an under-learning result: training performance is already
poor, although validation is worse. It does not support a memorization finding
or a request to expand the pool to 25,000. The single-record result establishes
that the train/save/load/evaluate path can learn one repeated case; the 16- and
512-record results show that the current representation and/or optimization
setup does not yet transfer that behavior across the distribution at 50k steps.
Reducing the fixed set to eight records achieved safe completion at 50k but did
not learn the cost preference, and doubling that run to 100k regressed. This
meets the plan's stopping condition for flat learning: larger scenario pools or
additional PPO steps alone are not a supported remedy.

PPO and reward normalization now use `gamma=1.0`, matching the simulator's
undiscounted additive episode-cost objective. The previous implicit 0.99 value
made later costs depend on the number of zero-reward assignment/advance steps.
The corrected 16-record run still failed, so discount mismatch was real but not
the sole learning problem. Its final diagnostics included entropy 1.60,
explained variance 0.24, approximate KL 0.021, and assignment, cancel, and
advance actions; the policy was learning actively rather than being stuck on a
single action type.

The evaluator now records the comparator identity and information scope. The
online `naive-launch-on-detection/1` policy is the primary comparator for learned
policies; `feasible-immediate-matching/1` remains an explicitly offline
full-episode reference.

## 100k large-pool multi-seed pilots

Seeds 7, 17, and 27 each trained for 100,000 steps on the verified
`sg2-training-10000-v1` release. Each completed about 1,870 episodes and visited
every selected pool record exactly once: 1,862, 1,879, and 1,881 unique records,
respectively. Thus each run saw roughly 18.7% of the pool and did not repeatedly
memorize a subset.

| Seed | Training sample: completion / wins / mean difference | Validation: completion / wins / mean difference | Validation 95% CI |
| ---: | --- | --- | --- |
| 7 | 89.1% / 26.6% / -1.5493 | 92.2% / 29.7% / -1.0995 | [-1.7199, -0.5725] |
| 17 | 81.2% / 12.5% / -2.2485 | 79.7% / 17.2% / -2.3204 | [-3.1406, -1.5688] |
| 27 | 84.4% / 25.0% / -2.1821 | 79.7% / 29.7% / -2.1392 | [-2.9666, -1.3208] |

The across-seed validation means are 83.9% completion, 25.5% win rate, learned
cost 4.5258 versus online-baseline cost 2.6728, and favorable difference
-1.8530. The mean constraint-violation rate is 16.1%. Every seed fails both on
the fixed training sample and on validation, and every validation confidence
interval excludes zero in the unfavorable direction.

The decision for steps 5 and 6 is therefore **do not expand**. There is no
training-success/validation-failure pattern indicating memorization, and no
evidence that the fixed pool lacks diversity in a way a 5–10% live-generation
lane would repair. The next justified RL change is representation or curriculum
work under a new experiment identity, beginning with the mandatory eight-case
overfit gate. The machine-readable aggregate is
`data/results/rl/experiments/training10000-100k-multiseed-summary.json`.

## General experiment record

For any reported experiment, retain its question, dated configuration, source revision, dataset release identifier, environment specification, random seeds, and artifact paths. Distinguish planned, running, completed, failed, interrupted, and inconclusive results.

Record actual work completed alongside requested work. State whether reported elapsed time includes setup, input loading, evaluation, and artifact persistence. Preserve failed and interrupted results so that a results table does not silently include only successful runs.

Keep observed measurements separate from estimates. A single completed timing measurement supports a measurement for that configuration; it does not establish reliable worker scaling or predict a different workload. An absent process or incomplete checkpoint alone does not establish the cause of interruption.

## Reporting checks

- Every claimed completed result resolves to a readable artifact with its configuration and dataset identity.
- Reported summaries reconcile with the underlying records, including failed or incomplete runs.
- Comparisons identify changed factors and disclose differences in workloads or measurement boundaries.
- Generalization claims identify the evaluation split, its exposure to development, and uncertainty.
- Proposed acceptance criteria are distinguished from measured outcomes.

See [datagen.md](datagen.md) for dataset versioning, split integrity, coverage documentation, and exact-record auditing.

## Structured imitation follow-up

The representation follow-up is complete under
`data/results/rl/experiments/structured-imitation-512-seed7/`. The shared
valid-action scorer passed the single and fixed-16 overfit probes, then trained
on all 512 pilot demonstrations and ran all three conditional DAgger rounds.

No candidate was promoted. Behavior cloning achieved 82.8% validation wins and
11.4% lower mean cost, but had seven constraint violations and an inconclusive
confidence interval. DAgger rounds 1 and 2 regressed. Round 3 recovered to 82.8%
wins and 15.0% lower mean cost, but still had six violations and an interval
crossing zero. The deterministic naive policy remains the fallback and the
256-case held-out suite remains sealed.

This result shows that the structured representation learns cost-sensitive
behavior far better than flat PPO, while also identifying the remaining blocker:
rare unsafe decisions. The next experiment should add safety-aware action
selection and improve residual-expert coverage rather than increasing PPO
steps or pool size.
