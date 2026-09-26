# Single-scenario overfit, 50k steps, seed 7

**Status:** passed the narrow single-scenario overfit check.

MaskablePPO trained on the same repeated consequence-contrast scenario for
50,000 steps. It completed safely with cost 1.4652 versus 1.6317 for the
privileged feasible offline reference, a 10.2% improvement. This establishes
that the implementation can memorize one case; it supplies no evidence of
transfer across scenarios.

See `training-metadata.json` and `training-set-evaluation.json`.
