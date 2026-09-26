# Fixed-eight overfit, 100k steps, gamma 1.0, seed 7

**Status:** failed and regressed.

Doubling the fixed-eight run to 100,000 steps produced one constraint violation,
zero wins, and mean cost 3.6969 versus 1.7555 for the online naive policy. More
flat-PPO training was therefore rejected as the next remedy.

See `training-metadata.json` and `training-set-naive-online.json`.
