# RL Training Tips and Runtime Guide

This guide is specific to the current centralized interception environment and the 15-core Apple M5 Pro with 24 GB of unified memory used for development.

## September 2026 implementation status

The immediate, semantics-preserving optimization batch is implemented:

- Unrecorded steps no longer build simulator snapshots, duplicate pre-action observations, or observation references; recorded rollout/replay behavior remains covered by the existing semantic tests.
- `_info()` reads the immutable simulator version directly, and action masks use a revision-keyed protected cache invalidated by reset and every successful action.
- `train_maskable_ppo(..., n_envs=1)` supports `DummyVecEnv` for one worker and `SubprocVecEnv` for multiple workers. The CLI defaults to `--n-envs 4`, while the Python API keeps its compatible one-worker default.
- Workers use disjoint deterministic streams (`base_seed=seed+rank`, `episode_seed_stride=n_envs`), with deterministic retry lanes for infeasible constrained Singapore-v2 seeds.
- Rollout sizing, calibration, minibatches, effective timestep accounting, cleanup, and metadata are vector-environment aware. Metadata now records worker streams, vector type, start method, rollout buffer, batch size, epochs, actual timesteps, and measured throughput.
- `scripts/benchmark_rl_training.py` implements the prescribed 10k warm-up plus 50k measured Singapore-v2 matrix for 1/2/4/6/8 workers and supports resumable checkpointing below ignored `data/results/rl/`.

The full matrix is not yet complete, so projected multi-worker speedups have not been replaced with invented values. The completed one-worker measured leg produced **50,000 actual timesteps in 1,377.75 seconds (36.29 timesteps/s)**. The 2/4/6/8-worker measurements remain to be completed with:

```bash
.venv-rl/bin/python scripts/benchmark_rl_training.py --resume
```

At the measured one-worker rate, raw training takes approximately 7.66 hours for 1M steps, 22.96 hours for 3M, and 38.27 hours for 5M. Three serial seeds require approximately 22.96, 68.89, and 114.80 hours respectively, before evaluation overhead. Keep the CLI default at four workers until the completed stable matrix supports a different documented recommendation.

Remaining optimization work is unchanged: observation caching, scenario pooling, provider/geometry caching, CPU-versus-MPS measurement, and policy architecture experiments are separate follow-ups.

## Current workload

- Algorithm: `sb3-contrib` MaskablePPO with the default MLP policy.
- Observation: 23,272 `float32` features.
- Action space: 1,289 discrete actions with invalid-action masking.
- Maximum scenario shape: 8 threats, 8 interceptors, and 20 candidates per pair.
- Rollout length: at most 256 steps in the current training helper.
- Vectorization: `DummyVecEnv` for one worker or `SubprocVecEnv` for multiple workers; CLI default 4.
- The Singapore simulator is primarily CPU- and Python-bound. Memory is not the present bottleneck.

Short local benchmarks on this M5 Pro measured approximately:

| Environment | Throughput | 100k steps | 1M steps | 10M steps |
| --- | ---: | ---: | ---: | ---: |
| Toy provider | 337 steps/s | 5 min | 49 min | 8.2 hr |
| Singapore provider and generator | 68 steps/s | 25 min | 4.1 hr | 41 hr |

These are planning estimates, not deadlines. Longer runs can change with scenario complexity, evaluation overhead, background load, and thermal throttling. Use `--wall-clock-minutes` or a fresh calibration run when scheduling an experiment.

## Recommended training progression

Do not begin with a multi-day run. Increase the budget only after the preceding stage passes its checks.

1. **Smoke test — 10k steps:** about 2.5 minutes on the Singapore environment. Confirm that training completes, artifacts reload, observations remain finite, masks always admit a valid action, and evaluation is deterministic.
2. **Pipeline validation — 100k steps:** about 25 minutes. Confirm that the agent beats random and does not collapse to always selecting `advance` or another single action.
3. **First meaningful experiment — 1M steps:** about 4–5 hours. Evaluate on held-out seeds every 100k–250k steps and retain the best checkpoint.
4. **Serious run — 3M to 5M steps:** approximately 12–21 hours. This is a reasonable overnight training range once reward curves and held-out performance are improving.
5. **Long run — 10M steps:** approximately 41 hours. Attempt this only when shorter runs show continued gains and the evaluation suite demonstrates that the learned policy is better than the baselines.

A practical initial target is **1 million Singapore timesteps**, followed by held-out evaluation. If performance is still improving, extend the same configuration to **3–5 million timesteps**. The number of timesteps is not a success criterion by itself; stop when held-out performance plateaus or regresses.

## Tips that matter most

### Measure learning, not just training loss

- Keep training, validation, and final test seed suites disjoint.
- Compare against random-valid-action, deterministic heuristic, and oracle/bounded-oracle baselines where applicable.
- Track score, success/interception rate, invalid or degenerate behavior, episode length, action distribution, and inference latency.
- Report the median and spread across several training seeds. One lucky PPO seed is not reliable evidence.
- Select checkpoints using held-out validation seeds, then use the final test suite only once.

### Diagnose the policy early

- Plot reward and baseline-relative performance against environment timesteps.
- Record how often each action family is used: assignment, cancellation, and advance.
- Watch for mask-induced collapse, especially a policy that almost always advances.
- Inspect explained variance, approximate KL, entropy, clipping fraction, and value loss, but judge success primarily by held-out simulator outcomes.
- Run a small overfit test on a fixed scenario. Failure to learn a tiny fixed case usually indicates a reward, observation, masking, or optimization problem.

### Improve throughput before buying more memory

- Replace the single `DummyVecEnv` with a benchmarked `SubprocVecEnv` configuration. Test 2, 4, 6, and 8 workers; do not assume the largest count is fastest.
- Keep each worker's provider and consequence catalog alive instead of rebuilding static data every episode.
- Cache or precompute candidate and consequence features that are invariant during an episode.
- Profile scenario generation, candidate assessment, action-mask construction, and observation construction separately.
- Increase rollout and batch sizes only after adding parallel environments, while ensuring the rollout buffer divides cleanly into minibatches.
- Avoid writing full rollout traces during normal training; enable detailed recording for evaluation or selected diagnostic episodes.

### CPU versus Apple GPU

- Start with CPU. The simulator is CPU-bound and the current MLP is small, so MPS dispatch overhead may outweigh GPU gains.
- Benchmark CPU and MPS end to end before choosing a device. Measure complete timesteps per second, not only neural-network forward time.
- The Neural Engine is not automatically used by PyTorch/Stable-Baselines3 training.
- Keep the Mac plugged in, use the high-performance power mode if available, and avoid other memory- or CPU-heavy work during long runs.

### Memory management

- The current project comfortably fits in 24 GB. Additional RAM is unlikely to improve single-environment throughput.
- Unified memory is shared by macOS, CPU, and GPU. Leave several gigabytes free and monitor memory pressure rather than relying only on the used-memory number.
- Parallel workers duplicate Python and some provider state. Increase worker count gradually while watching Activity Monitor or `memory_pressure`.
- Do not retain observations, snapshots, or detailed event histories for every training step unless they are needed for analysis.

### Reproducibility and checkpoints

- Save the model, `VecNormalize` state, full hyperparameters, dependency versions, provider/generator identities, git revision, seed, and observation-layout checksum together.
- Save periodic and best-validation checkpoints so a long run is recoverable.
- Evaluate with frozen normalization statistics and deterministic actions, while optionally also reporting stochastic-policy results.
- Repeat promising configurations with at least 3 seeds before drawing conclusions; use 5 or more for a result intended to be reported formally.

## Suggested first campaign

1. Run three 100k-step configurations to verify that learning is real and choose sensible PPO settings.
2. Train the best configuration for 1M steps with periodic held-out evaluation.
3. Repeat the 1M-step run with three algorithm seeds.
4. If all three runs improve and have not plateaued, extend to 3–5M steps.

At the currently measured Singapore throughput, that campaign is roughly **14–16 hours of raw training** for three 1M-step seeds plus the exploratory runs, before evaluation overhead. A three-seed 5M-step campaign would be roughly **62 hours** serially. Separate concurrent runs are possible, but they will compete for CPU and may take longer individually; environment-level parallelism within one experiment is usually the better first optimization.

## Optimized runtime estimate

The current Singapore measurement is about 68 timesteps per second. A sensible optimization target on this machine is a 2.5–4x end-to-end improvement. This is a target to verify by measurement, not a promised multiplier.

| Training scope | Current implementation | Target after optimization |
| --- | ---: | ---: |
| 100k steps | 25 min | 6–10 min |
| 1M steps | 4.1 hr | 1–1.7 hr |
| 3M steps | 12.3 hr | 3–5 hr |
| 5M steps | 20.5 hr | 5–8 hr |
| 10M steps | 41 hr | 10–16 hr |

Allow another 10–20% for periodic evaluation and checkpointing. A single serious 3–5M-step policy therefore needs roughly **13–22 hours now**, or a target of **4–9 hours after optimization**. Three independent 3–5M-step seeds need roughly **37–65 hours now**, or approximately **12–27 hours after optimization**.

## Implementation optimization plan

Apply these changes one at a time and rerun the same benchmark after each change. Preserve a one-environment mode as the deterministic reference implementation.

### Phase 0: establish a repeatable benchmark

Before changing behavior, add a benchmark that records:

- Environment count and multiprocessing start method.
- Total environment timesteps per second, including PPO updates.
- Reset, mask, observation, simulator-step, and policy-update timings.
- Peak resident memory and macOS memory pressure.
- Fixed seed, requested timesteps, PPO settings, provider identity, and generator identity.

Use at least 10k warm timesteps and 50k measured timesteps for throughput comparisons. Very short 256-step measurements include startup and compilation noise. Verify that each candidate implementation produces the same observations, masks, rewards, termination state, and episode result as the reference for a fixed action sequence.

### Phase 1: remove unconditional diagnostic work

This is the safest first code change. In `CentralizedInterceptionEnv.step()` the implementation currently creates `before` and `after` engine snapshots and a `before_observation` on every training step, even when `self.recorder` is `None`. Those values are used only to construct a `RolloutRecord`.

Change the structure so that:

```python
if self.recorder is not None:
    before = self.engine.snapshot()
    before_observation = self._observation()

# Execute the action and build the returned observation.

if self.recorder is not None:
    after = self.engine.snapshot()
    self.recorder.record(...)
```

Also avoid calling `self.engine.snapshot()` inside `_info()` merely to retrieve the simulator version. Import or expose the immutable simulator version directly. Detailed snapshots and JSONL recording should remain enabled for selected evaluation/audit episodes, not ordinary PPO collection.

Files to change:

- `backend/learning/environment.py`
- Tests that assert recorder/replay equivalence and unrecorded environment behavior

Acceptance test: recorded rollouts remain byte-for-byte or semantically identical, while an environment with no recorder performs no snapshot or observation-reference work.

### Phase 2: cache masks and repeated observations

`action_masks()` scans up to 8 × 8 × 20 assignment actions. MaskablePPO can ask for a mask immediately before `step()`, after which `step()` asks for it again to validate the selected action.

Add an environment state revision and caches:

```python
self._state_revision = 0
self._mask_cache_revision = -1
self._mask_cache = None
self._observation_cache_revision = -1
self._observation_cache = None
```

Increment the revision after `reset()` and after every successful state-changing action. `action_masks()` and `_observation()` should return cached results when their revision matches. Return a copy, or mark the cached arrays read-only, so an external caller cannot corrupt future results. Do not cache provider failures or partially constructed results.

The invalidation order matters:

1. Validate the selected action using the current mask.
2. Apply the action.
3. Increment the state revision and clear caches.
4. Construct the next observation.

Acceptance tests should count calls to `engine.is_assignment_valid()` and prove that two mask requests in the same state perform one scan, while a state transition forces recomputation. Run the existing action-mask and observation correctness tests unchanged.

### Phase 3: introduce parallel environments

Change `train_maskable_ppo()` to accept `n_envs`, initially defaulting to `1`. Add `--n-envs` to `scripts/train_rl.py`. Use `DummyVecEnv` for one environment and `SubprocVecEnv` for more than one.

Conceptually:

```python
env_fns = [make_env_factory(rank) for rank in range(n_envs)]
vector_env = (
    DummyVecEnv(env_fns)
    if n_envs == 1
    else SubprocVecEnv(env_fns, start_method="forkserver")
)
normalized = VecNormalize(vector_env, ...)
```

Important implementation details:

- Use a top-level callable class or a picklable `functools.partial` for each worker factory. Avoid relying on nested closures and captured live geometry objects across macOS worker processes.
- Construct the provider, consequence catalog, and scenario generator once inside each worker, then reuse them for that worker's lifetime.
- Give workers disjoint scenario streams. For example, reserve a large deterministic seed stride per rank rather than giving every worker the same `base_seed`.
- Keep process creation under the CLI's `if __name__ == '__main__'` guard.
- Keep the native `action_masks()` method on the environment; the subprocess must be able to call it locally.
- Close the vector environment in `finally` blocks so failed experiments do not leave worker processes alive.
- Record `n_envs`, start method, worker seed ranges, and effective rollout-buffer size in training metadata.

Benchmark 1, 2, 4, 6, and 8 workers. Select the fastest stable configuration rather than assuming all cores should be occupied. Leave CPU capacity for PPO updates, macOS, and the parent process. Four or six workers are reasonable starting candidates for this 10-performance-core machine.

### Phase 4: correct rollout sizing for multiple workers

Stable-Baselines3 collects `n_steps` **per environment**, so the total rollout buffer is:

```text
rollout_buffer_size = n_steps × n_envs
```

Update `_ppo_rollout_configuration()` to consider `n_envs`. Ensure:

- `batch_size` divides `n_steps × n_envs` exactly.
- Calibration and wall-clock calculations round to whole multi-environment rollouts.
- The requested total timestep count is interpreted consistently when `n_envs > 1`.
- Metadata stores `n_steps`, `n_envs`, buffer size, batch size, and number of optimizer epochs.

A sensible first benchmark is a total buffer of 1,024–4,096 samples with minibatches of 128 or 256. This is an experiment range, not a fixed recommendation; compare learning quality as well as throughput.

### Phase 5: pool or pre-generate scenarios

Singapore resets perform threat generation, trajectory sampling, consequence eligibility assessment, and matching. Separate reset time from ordinary step time in the profiler. If reset is material, implement a deterministic `EpisodePoolScenarioGenerator`:

- Build a pool from an explicit training-only seed range.
- Store complete immutable `EpisodeSpec` objects or a versioned serialized representation.
- Select episodes deterministically from the worker's assigned stream.
- Never mix validation or final-test seeds into the training pool.
- Include generator configuration, source checksums, schema version, and pool checksum in metadata.
- Retain an on-the-fly generation mode and test pool results against freshly generated episodes.

Start with a pool large enough to prevent obvious memorization. If the pool is small, refresh it or mix pooled and freshly generated episodes. Scenario pooling must not reduce scenario diversity merely to improve benchmark numbers.

### Phase 6: profile provider and geometry work

If scenario generation or provider assessment remains dominant:

- Reuse the consequence catalog and prepared geometry within each worker.
- Cache only calculations whose inputs have a complete deterministic cache key.
- Precompute static candidate/provider features once per episode instead of reconstructing them on every observation.
- Batch spatial queries where the geometry libraries support it.
- Avoid converting repeatedly between dictionaries, dataclasses, NumPy arrays, and geometry objects in the innermost loops.

Do not cache time-dependent assignment validity, reservations, consumed-interceptor state, or other mutable simulator facts as if they were static. Add equivalence tests for every cache.

### Phase 7: benchmark CPU and MPS last

After simulator parallelism is working, add an explicit `device` option and compare `cpu` with `mps`. Measure complete environment timesteps per second and held-out learning results. The MLP may be too small for MPS to win, and moving PPO work to the shared GPU does not accelerate subprocess simulation. Keep CPU as the default unless the end-to-end benchmark demonstrates a repeatable gain.

## Recommended order of work

1. Add the repeatable 50k-step benchmark.
2. Remove unconditional snapshots and the duplicate pre-action observation.
3. Cache action masks by state revision.
4. Add `--n-envs` and benchmark 1/2/4/6/8 workers.
5. Fix rollout budgeting and metadata for multiple workers.
6. Measure reset cost, then add an episode pool only if reset is significant.
7. Profile and cache static provider/geometry features.
8. Test MPS only after the CPU pipeline is efficient.

The first three changes are low-risk and should be completed before altering PPO hyperparameters. Parallel environments are likely to provide the largest overall gain, but avoiding unconditional snapshots and repeated mask scans may improve both single-worker and multi-worker performance without changing the learning problem.

## What can be implemented immediately

The following work is ready now and does not require changing the policy objective, scenario distribution, observation layout, or reward definition.

| Change | Readiness | Risk | Expected value |
| --- | --- | --- | --- |
| Repeatable throughput benchmark | Implement now | Low | Establishes reliable before/after evidence |
| Skip snapshots and duplicate observation when not recording | Implement now | Low | Removes clearly unused work from every step |
| Cache action masks by state revision | Implement now | Low–medium | Avoids repeated 1,289-action validity scans |
| Add `--n-envs` with `SubprocVecEnv` | Implement now, after benchmark | Medium | Likely largest speedup |
| Make rollout sizing aware of `n_envs` | Implement with parallel environments | Medium | Required for correct PPO batching and budgeting |
| Add timing and worker configuration to metadata | Implement now | Low | Makes results reproducible and comparable |
| Observation caching | Implement after measuring call counts | Low–medium | Useful only if observations are requested repeatedly per state |
| Pre-generated scenario pool | Wait for reset profiling | Medium–high | Can help resets but may reduce diversity if designed poorly |
| Provider/geometry caches | Wait for function-level profiling | Medium–high | Cache keys and mutable state require careful correctness tests |
| MPS training | Benchmark last | Medium | May be neutral or slower for this small MLP |
| Change network architecture or reduce features/actions | Separate learning experiment | High | Changes learning behavior and invalidates direct comparisons |

### Recommended first implementation batch

One focused batch can safely deliver:

1. A benchmark command for 50k Singapore timesteps.
2. Conditional snapshots and observation references in `CentralizedInterceptionEnv.step()`.
3. Direct simulator-version reporting in `_info()` without a full snapshot.
4. A revision-keyed action-mask cache with invalidation tests.
5. `n_envs` support, CLI configuration, disjoint worker seeds, metadata, and clean shutdown.
6. Worker-count benchmarks for 1, 2, 4, 6, and 8 environments.

Do not combine scenario pooling, provider caching, MPS, or network changes into this first batch. Keeping them separate makes any speedup measurable and makes semantic regressions much easier to locate.
