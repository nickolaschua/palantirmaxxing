# Masked centralized policy adapter

Use a separate `.venv-rl` with the RL, geospatial, consequence, and test
requirements described in the root README. The fixed discrete
action space contains 1,280 assignment triples, eight cancellation actions and
one advance action. Invalid external actions raise `ValueError`; `action_masks()`
is compatible with `sb3_contrib.MaskablePPO`.

The observation is one flat `float32` vector with global state, eight threat
slots, eight interceptor slots, tentative assignment state, all 8 x 8 x 20
candidate evidence rows, sixteen provider features and explicit presence masks.
Scheduled future threats contribute only zero-filled rows and false masks.

`centralized-observation/2` expands each candidate row with altitude, ordinal
consequence cost, casualty bounds, secondary score, veto/unknown flags, and
population-coverage state. Model version `maskable-ppo-centralized/2` records
and validates observation, provider, generator, data/config/cache, dependency,
and geometry identities. Older normalization/model artifacts are rejected.

Provider aggregate scores are preserved raw in `info` and rollout records. The
environment applies only the declared objective direction when producing the
terminal RL reward: maximize uses the raw score and minimize uses its negation.
Any reward/observation normalization is an external training concern.
