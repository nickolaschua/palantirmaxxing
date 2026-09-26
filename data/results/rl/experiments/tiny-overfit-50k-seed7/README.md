# Fixed-16 overfit, 50k steps, seed 7

**Status:** failed.

Extending the fixed-16 MaskablePPO run to 50,000 steps produced mean cost
4.3146 versus 1.7043 for the reference and three constraint violations. Extra
steps did not repair tiny-set learning.

See `training-metadata.json` and `training-set-evaluation.json`.
