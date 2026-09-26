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

Provider aggregate scores are preserved raw in `info` and rollout records.
Assign and cancel actions return zero. An advance step returns the signed sum of
the immutable `training_cost` values for interception/constraint outcomes at
that timestamp (negative for minimize, positive for maximize). A 9.0 Singapore
constraint penalty is emitted once, without replaying earlier costs. At normal
or constraint termination the accumulated reward must equal the signed
aggregate cost. Rollout schema `rl-rollout/2` records reward and per-step costs,
and replay verifies them with masks, observations, assignments, and reasons.
Any reward/observation normalization is an external training concern.

## Structured imitation fallback

`imitation-demonstrations/1` datasets are generated only from a verified
`development-training` pool. The teacher is the privileged, clairvoyant/offline
exact fixed-rank optimizer; it is never a deployable policy. Each checksummed
NPZ shard stores 24 observation-wide features and ragged valid-action sets with
44 action-local features and set-valued acceptable targets. Family IDs are kept
whole in the deterministic 90/10 training/internal-validation split.

The `structured-behavior-cloning/1` student is observation-only. A shared local
action encoder, state encoder, and mean/max valid-action pooling produce one
score per currently valid action. Continuous normalization statistics come only
from the internal training split. `policy-artifact/1` records the model,
normalization, dataset and feature checksums, observation layout, pool/provider/
generator identities, dependency versions, teacher disclosure, and metrics.

Training runs the required one-scenario and fixed 16-scenario overfit gates
before frozen validation. `train_with_conditional_dagger()` evaluates behavior
cloning once on all 64 validation cases and collects residual-expert labels from
the 512 training episodes only when a promotion gate fails. It runs at most
three rounds at learning rate `3e-4`; failure retains
`naive-launch-on-detection/1` as the deterministic fallback. Held-out episodes
are not accepted by that API.

`load_policy()` dispatches by metadata to either structured imitation or PPO.
Metadata without an `algorithm` remains legacy PPO. `load_normalized_policy()`
is unchanged for explicit PPO callers.
