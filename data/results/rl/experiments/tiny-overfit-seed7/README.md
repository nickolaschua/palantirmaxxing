# Fixed-16 overfit, 10k steps, seed 7

**Status:** failed.

MaskablePPO trained on 16 fixed consequence-contrast scenarios. Mean cost was
4.3357 versus 1.7043 for the reference and four episodes violated constraints.
The policy had not fit the tiny training set, so generalization experiments
could not be justified from this result.

See `training-metadata.json` and `training-set-evaluation.json`.
