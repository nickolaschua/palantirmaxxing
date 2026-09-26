# Single-scenario overfit, 10k steps, seed 7

**Status:** failed the overfit performance gate.

MaskablePPO trained on one consequence-contrast scenario for 10,000 steps. It
completed safely, with cost 1.9267 versus 1.6317 for the privileged feasible
offline reference. This confirms that the run/evaluation path works, but does
not show that the policy learned the preferred action strongly enough.

See `training-metadata.json` and `training-set-evaluation.json` for the exact
configuration and raw evaluation.
