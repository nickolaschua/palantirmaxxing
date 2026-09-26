# Pilot-pool generalization, 50k steps, seed 7

**Status:** failed on training and validation.

MaskablePPO visited all 512 pilot records one or two times. On a stratified
64-record training sample it produced 21 violations, mean cost 5.5148 versus
2.3935 for the online baseline, and a 21.9% win rate. On frozen validation it
produced 28 violations, mean cost 6.6521 versus 2.6728, and a 17.2% win rate;
the favorable mean difference was -3.9794 with 95% CI
[-4.9946, -3.0056]. This is under-learning, with an additional validation
degradation, rather than evidence that a larger pool would fix memorization.

See `training-metadata.json` and the training/validation evaluation reports.
