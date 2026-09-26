# Fixed-16 overfit, 50k steps, gamma 1.0, seed 7

**Status:** failed.

This run aligned PPO discounting with the simulator's undiscounted additive
cost. Mean cost was 4.3474 versus 1.7958 for the online naive policy, with four
constraint violations. Discount mismatch was a real configuration defect, but
fixing it did not solve the representation or optimization problem.

See `training-metadata.json`, `training-set-naive-online.json`, and the separate
offline-reference report.
