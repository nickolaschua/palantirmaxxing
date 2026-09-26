# RL optimisation implementation handoff

Date: 26 September 2026  
Machine: Apple M5 Pro, 24 GB unified memory  
Scope: semantics-preserving performance work for centralized MaskablePPO training, including Singapore-v2 benchmarking support.

## Outcome

The immediate RL optimization batch was implemented. Normal training no longer performs recorder-only diagnostic work, action masks are cached safely, PPO can train through multiple simulator workers, rollout accounting is vector-aware, worker seed streams are deterministic and disjoint, and training metadata records the effective execution configuration.

The focused learning test suite passes, a real two-worker Singapore subprocess train/save run passes, and the project knowledge graph was refreshed. The complete 1/2/4/6/8-worker benchmark matrix was not finished because each long command exceeded the execution-session lifetime. One valid 50k one-worker result was captured and documented; no unmeasured multi-worker speedups were claimed.

## Environment optimizations

Changed `backend/learning/environment.py`:

- Added `episode_seed_stride: int = 1` to `CentralizedInterceptionEnv`.
- Preserved default seed behavior: automatic episode seeds remain `base_seed`, `base_seed + 1`, and so on when the stride is omitted.
- Parallel workers use `base_seed=seed+rank` and `episode_seed_stride=n_envs`, producing interleaved, disjoint deterministic streams.
- Added validation requiring a positive integer seed stride.
- Added a state revision and action-mask cache.
- Repeated mask requests in the same state reuse one validity scan.
- Reset and every successful state-changing action invalidate the cache.
- Cached arrays are read-only internally and callers receive copies, so external mutation cannot corrupt later masks.
- Provider failures and partial masks are not cached.
- Simulator snapshots, duplicate pre-action observations, and observation references are now constructed only when a recorder is attached.
- Recorded rollout contents and replay semantics remain unchanged.
- `_info()` now reports the immutable `SIMULATOR_VERSION` constant directly instead of constructing a full simulator snapshot.

Observation layout, action layout, reward behavior, simulator semantics, and policy architecture were not changed.

## Parallel PPO training

Changed `backend/learning/training.py`:

- Added `n_envs: int = 1` to `train_maskable_ppo()`.
- Retained the one-worker Python API default for compatibility.
- Uses `DummyVecEnv` for one worker and `SubprocVecEnv` for multiple workers.
- Uses `forkserver` when supported, otherwise `spawn`.
- Added a top-level callable environment factory used by vector workers.
- Creates one provider and scenario generator per worker and reuses them for that worker's lifetime.
- Closes calibration and training vector environments in `finally` paths.
- Single-environment loading and inference remain unchanged.

Changed `scripts/train_rl.py`:

- Added `--n-envs`.
- CLI default is four workers.
- Passes the selected worker count into `train_maskable_ppo()`.

## Rollout and budget accounting

The PPO configuration now treats a complete rollout as:

```text
n_steps × n_envs
```

The implementation:

- Selects the largest `n_steps` at most 256 whose complete vector rollout divides the requested total when possible.
- Otherwise rounds execution up to a complete rollout.
- Selects a minibatch size no larger than 64 that divides the complete rollout buffer.
- Rounds calibration to complete vectorized rollouts.
- Uses the complete rollout size for wall-clock planning.
- Separately records requested, effective, and actual timesteps.
- Calculates measured end-to-end timesteps per second from actual model timesteps.

New metadata includes:

- `n_envs`
- vector environment type
- multiprocessing start method
- worker rank, base seed, first scenario seed, and episode stride
- PPO steps per environment
- complete rollout-buffer size
- minibatch size
- optimizer epochs
- requested, effective, and actual timesteps
- elapsed time and measured throughput

## Singapore-v2 multiprocessing fixes

Longer benchmark attempts exposed two existing integration problems, which were fixed.

### Infeasible constrained seeds

The training distribution selected a `low-slack` seed that exhausted all 200 deterministic generation attempts and aborted training. The training-only Singapore-v2 adapter was moved to a top-level `TrainingSingaporeV2Generator` and now uses deterministic retry lanes separated by one billion seeds. It retains the originally selected profile bucket and only retries when the constrained generator reports that a seed is infeasible.

### Immutable evidence serialization

Singapore candidate evidence uses `FrozenDict`. Default multiprocessing unpickling reconstructs dictionary subclasses through mutation, which triggered its immutability guard. An explicit pickle reconstruction path was added so nested immutable evidence can cross subprocess boundaries without becoming mutable.

The top-level generator class also fixed `VecNormalize.save()` failing on a function-local class.

## Benchmark command

Added `scripts/benchmark_rl_training.py`.

Default protocol:

- Provider: `singapore-demo-v2`
- Generator: `singapore-v2`
- Worker counts: 1, 2, 4, 6, and 8
- Warm-up: 10,000 timesteps per worker-count experiment
- Measurement: 50,000 requested timesteps
- Temporary model directories
- Summary JSON: `data/results/rl/singapore-v2-worker-benchmark.json`
- Reports requested and actual timesteps, elapsed seconds, throughput, speedup versus one worker, fastest stable worker count, and the fixed CLI default of four workers.
- Checkpoints each completed row and supports `--resume`.

Run or resume it with:

```bash
.venv-rl/bin/python scripts/benchmark_rl_training.py --resume
```

The output is below the repository's ignored `data/results/rl/` area.

## Benchmark attempts and measured result

Several full-matrix attempts were made. They uncovered and led to fixes for:

1. An infeasible `low-slack` seed.
2. A non-picklable local Singapore-v2 training generator.
3. Non-picklable immutable provider evidence in subprocess results.
4. Long command sessions being interrupted after roughly 1,000 seconds.

The completed valid baseline is:

| Workers | Requested | Actual | Elapsed | Throughput |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 50,000 | 50,000 | 1,377.75 s | 36.29 timesteps/s |

At this measured one-worker throughput, raw training estimates are:

| Scope | One run | Three serial seeds |
| --- | ---: | ---: |
| 1M | 7.66 hr | 22.96 hr |
| 3M | 22.96 hr | 68.89 hr |
| 5M | 38.27 hr | 114.80 hr |

The 2/4/6/8-worker measurements remain incomplete. The four-worker CLI default was deliberately retained, and documentation does not invent a fastest worker recommendation from incomplete evidence.

## Tests added or updated

Environment coverage now proves that:

- Unrecorded steps call neither `snapshot()` nor the duplicate pre-action observation path.
- Recorded rollouts and replay remain semantically valid.
- Two mask requests in one state perform one validity scan.
- A successful action invalidates the mask cache.
- Callers cannot mutate the cached mask.
- Default episode seeding is unchanged.
- Parallel episode seed streams are disjoint.

Training coverage now includes:

- Vectorized rollout and minibatch divisibility for representative totals and worker counts.
- Invalid worker-count validation.
- Whole-rollout calibration and effective timestep accounting through existing smoke coverage.
- A real two-worker MaskablePPO train/save subprocess smoke run.
- Metadata inspection confirming worker streams, vector type, start method, buffer size, batch size, actual timesteps, and measured throughput.

One latency test threshold was updated because mask caching intentionally removes repeated provider/mask work from decisions that do not require reassessment.

## Verification performed

- Python compilation passed for all changed RL modules and scripts.
- `git diff --check` passed.
- Focused learning suite: **30/30 passed**.
- Two-worker toy MaskablePPO train/save smoke: passed.
- Two-worker Singapore-v2 subprocess/train/save smoke: passed.
- Broader unit suite: **183 passed, 3 errored**.

The three broader-suite errors were unrelated repository evidence problems:

- `data/results/rl/scenario-audit-v2.json` was absent in two tests.
- The checked scenario manifest contained legacy/unknown fields in one test.

No existing user changes were discarded or reset.

Finally, `graphify update .` completed successfully and refreshed `graphify-out/graph.json`, the HTML graph, and the graph report.

## Documentation updated

- `RL_tricks.md` now records the completed implementation work, the measured one-worker result, honest one-worker runtime projections, the incomplete matrix status, and remaining optimization opportunities.
- `scripts/scripts.md` documents Singapore-v2 training, parallel workers, and the benchmark command.

## Remaining work

1. Complete the 2/4/6/8-worker benchmark matrix with the resume command.
2. Replace projected multi-worker runtimes in `RL_tricks.md` only after the matrix completes.
3. Identify the fastest stable worker count while retaining four as the CLI default unless evidence strongly supports changing it.
4. Repair or regenerate the missing/stale scenario audit and manifest evidence responsible for the three unrelated unit-suite errors.
5. Keep the following optimizations separate until profiling justifies them:
   - Observation caching.
   - Scenario pooling or pregeneration.
   - Provider and geometry caching.
   - CPU-versus-MPS benchmarking.
   - Policy architecture or observation/action-space changes.

## Files changed for this work

- `backend/learning/environment.py`
- `backend/learning/training.py`
- `backend/simulation/factories.py`
- `backend/simulation/singapore_provider.py`
- `scripts/train_rl.py`
- `scripts/benchmark_rl_training.py`
- `scripts/scripts.md`
- `tests/unit/test_learning_environment.py`
- `tests/unit/test_learning_remediation.py`
- `RL_tricks.md`
- `graphify-out/` generated graph artifacts
