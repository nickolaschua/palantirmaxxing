# RL experiment archive

This directory is the canonical archive for learned-policy experiments. Raw
JSON, model files, normalization state, and dataset manifests are the source of
truth. Each experiment directory also contains a short `README.md` explaining
the question, result, significance, and next decision.

Lower episode cost is better. Learned policies are compared primarily with
`naive-launch-on-detection/1`, which uses only threats detected at decision
time. Exact fixed-rank optimization and feasible immediate matching are
privileged offline references and are identified as such in reports.

## Completed MaskablePPO experiments

| Experiment | Status | Significance |
| --- | --- | --- |
| [single-overfit-10k-seed7](single-overfit-10k-seed7/) | Failed gate | The policy completed one repeated scenario safely but did not beat the offline reference. |
| [single-overfit-50k-seed7](single-overfit-50k-seed7/) | Passed narrow overfit | The training path can memorize one scenario; this does not establish generalization. |
| [tiny-overfit-seed7](tiny-overfit-seed7/) | Failed | Ten thousand steps did not fit the fixed 16-scenario set. |
| [tiny-overfit-50k-seed7](tiny-overfit-50k-seed7/) | Failed | More steps did not repair the 16-scenario result. |
| [tiny-overfit-50k-gamma1-seed7](tiny-overfit-50k-gamma1-seed7/) | Failed | Correcting discounting to the undiscounted objective was necessary but insufficient. |
| [tiny-overfit-8x50k-gamma1-seed7](tiny-overfit-8x50k-gamma1-seed7/) | Failed cost gate | Eight scenarios completed safely, but consequence preference was not learned. |
| [tiny-overfit-8x100k-gamma1-seed7](tiny-overfit-8x100k-gamma1-seed7/) | Failed/regressed | Doubling training introduced a violation and still produced no wins. |
| [generalization-50k-seed7](generalization-50k-seed7/) | Failed | The 512-pool policy under-learned both its training sample and frozen validation. |
| [training10000-100k-seed7](training10000-100k-seed7/) | Failed | Large-pool seed 7 underperformed the online baseline on validation. |
| [training10000-100k-seed17](training10000-100k-seed17/) | Failed | Large-pool seed 17 underperformed the online baseline on validation. |
| [training10000-100k-seed27](training10000-100k-seed27/) | Failed | Large-pool seed 27 underperformed the online baseline on validation. |

The aggregate large-pool evidence is stored in
[`training10000-100k-multiseed-summary.json`](training10000-100k-multiseed-summary.json).
Across the three seeds, validation completion was 83.9%, win rate was 25.5%,
mean learned cost was 4.5258 versus 2.6728 for the online baseline, and the
constraint-violation rate was 16.1%. The result blocks expansion to 25,000
scenarios and the optional live-generation lane because the observed problem
is learning rather than memorization.

## Structured imitation campaign

The next experiment replaces the flat 1,289-logit PPO output with a shared
scorer over currently valid actions. It trains from an exact offline teacher,
but the student receives observation-time information only.

The campaign runs in this order:

1. `structured-imitation-diagnostic-32-seed7`: generate 32 demonstrations and
   run the single-scenario and fixed-16 overfit gates.
2. `structured-imitation-512-seed7`: only after the diagnostic passes, generate
   the full pilot dataset, train behavior cloning, evaluate the frozen 64-case
   validation suite, and run up to three DAgger rounds only when needed.
3. Keep the 256-case held-out suite sealed even if validation promotes an
   artifact. Opening it requires a separate final-test decision.

Promotion requires zero constraint violations, at least 60% wins against the
online naive policy, at least 5% mean improvement, a favorable 95% bootstrap
interval excluding zero, and decision-path p95 below 100 ms.

| Structured experiment | Status | Significance |
| --- | --- | --- |
| [structured-imitation-diagnostic-32-seed7](structured-imitation-diagnostic-32-seed7/) | Passed | The shared scorer fit both mandatory probes after raising the diagnostic ceiling from 100 to 500 epochs. |
| [structured-imitation-512-seed7](structured-imitation-512-seed7/) | Experimental, not promoted | BC and DAgger learned strong cost preferences and high win rates, but every candidate violated constraints and every confidence interval crossed zero. |

The full campaign's [violation analysis and next-step specification](structured-imitation-512-seed7/VIOLATIONS_AND_NEXT_STEPS.md)
explains the `unhandled_threat` failures and defines the safety-shield follow-up.

The full campaign completed behavior cloning and all three permitted DAgger
rounds. Round 3 was strongest by mean cost: 82.8% wins and 15.0% mean
improvement, but six of 64 validation episodes violated constraints. The
pipeline therefore selected `naive-launch-on-detection/1` as the deterministic
fallback and left the held-out suite sealed.

## Record requirements

Every new experiment record must contain the exact commands, seed, source pool
and manifest checksum, provider and generator identities, raw reports, artifact
paths, pass/fail gates, interpretation, and next decision. Failed and
interrupted runs remain in the archive.
