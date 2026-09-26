# Fixed-eight overfit, 50k steps, gamma 1.0, seed 7

**Status:** failed the consequence-learning gate.

All eight training episodes completed without violations, but mean policy cost
was 2.7455 versus 1.7555 for the online naive policy. The policy learned safe
completion without learning the cost preference needed to beat the baseline.

See `training-metadata.json` and `training-set-naive-online.json`.
