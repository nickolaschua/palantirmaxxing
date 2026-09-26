"""MaskablePPO training and wall-clock budgeting utilities."""
from collections import Counter
from dataclasses import asdict, dataclass, replace
import json
import hashlib
import importlib.metadata
import math
import multiprocessing
from numbers import Real
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Optional

import numpy as np

from backend.simulation import DeterministicToyProvider, SeededScenarioGenerator

from backend.simulation.suites import TRAINING_SEED_OFFSET

from .environment import (ADVANCE_ACTION, ASSIGNMENT_ACTIONS,
                          OBSERVATION_LAYOUT_VERSION,
                          CentralizedInterceptionEnv, ObservationLayout)


MODEL_VERSION = 'maskable-ppo-centralized/2'


@dataclass(frozen=True)
class TrainingBudget:
    wall_clock_seconds: float
    training_seconds: float
    held_out_evaluation_seconds: float
    rerun_and_demo_seconds: float
    measured_p95_step_ms: float
    planned_training_steps: int
    calibration_steps: int
    ppo_ms_per_timestep: float
    estimated_training_seconds: float
    actual_training_seconds: Optional[float] = None
    training_overrun_seconds: Optional[float] = None
    training_underrun_seconds: Optional[float] = None


@dataclass(frozen=True)
class TrainingArtifacts:
    model_path: str
    normalization_path: str
    metadata_path: str
    total_timesteps: int
    elapsed_seconds: float
    model_version: str = MODEL_VERSION


@dataclass(frozen=True)
class _EnvironmentFactory:
    provider_factory: Callable[[], Any]
    scenario_factory: Callable[[], Any]
    base_seed: int
    seed_stride: int
    scenario_seed_offset: int

    def __call__(self):
        return CentralizedInterceptionEnv(
            self.provider_factory(), scenario_generator=self.scenario_factory(),
            base_seed=self.base_seed, episode_seed_stride=self.seed_stride,
            scenario_seed_offset=self.scenario_seed_offset,
            policy_version=MODEL_VERSION)


def _scenario_seed_offset(generator: Any) -> int:
    return 0 if getattr(generator, 'selects_pool_records', False) else TRAINING_SEED_OFFSET


class NormalizedPolicy:
    """Inference wrapper that reuses the observation statistics saved at training."""

    model_version = MODEL_VERSION
    algorithm = 'maskable-ppo'

    def __init__(self, model: Any, normalization_env: Any,
                 artifact_identity: Optional[str] = None):
        self.model = model
        self.normalization_env = normalization_env
        self.artifact_identity = artifact_identity or 'legacy-ppo-artifact'

    def predict(self, observation, deterministic: bool = True, action_masks=None):
        array = np.asarray(observation, dtype=np.float32)
        batched = array.ndim == 1
        if batched:
            array = array.reshape(1, -1)
        normalized = self.normalization_env.normalize_obs(array)
        masks = action_masks
        if masks is not None and batched and np.asarray(masks).ndim == 1:
            masks = np.asarray(masks).reshape(1, -1)
        action, state = self.model.predict(
            normalized, deterministic=deterministic, action_masks=masks)
        if batched:
            action = np.asarray(action).reshape(-1)[0]
        return action, state

    def close(self) -> None:
        self.normalization_env.close()


def measure_environment_p95_step_ms(sample_steps: int = 256,
                                    seed: int = 90210,
                                    provider_factory: Callable[[], Any] = DeterministicToyProvider,
                                    scenario_factory: Callable[[], Any] = SeededScenarioGenerator) -> float:
    if type(sample_steps) is not int or sample_steps <= 0:
        raise ValueError('sample_steps must be a positive integer')
    env = CentralizedInterceptionEnv(
        provider_factory(),
        scenario_generator=(generator := scenario_factory()),
        base_seed=seed,
        scenario_seed_offset=_scenario_seed_offset(generator),
    )
    env.reset(seed=seed)
    timings = []
    rng = np.random.default_rng(seed)
    for _ in range(sample_steps):
        mask = env.action_masks().astype(bool)
        valid = np.flatnonzero(mask)
        if len(valid) == 0:
            env.reset()
            continue
        # Bias the benchmark toward advance so it measures event processing and
        # candidate generation, not only cheap assignment bookkeeping.
        action = int(valid[-1] if rng.random() < 0.5 else rng.choice(valid))
        started = time.perf_counter()
        _, _, terminated, truncated, _ = env.step(action)
        timings.append((time.perf_counter() - started) * 1000.0)
        if terminated or truncated:
            env.reset()
    env.close()
    if not timings:
        raise RuntimeError('environment benchmark produced no steps')
    return float(np.percentile(np.asarray(timings), 95))


def budget_from_wall_clock(wall_clock_seconds: float,
                           ppo_ms_per_timestep: float,
                           calibration_steps: int,
                           measured_p95_step_ms: float,
                           rollout_steps: int = 1) -> TrainingBudget:
    """Estimate a whole-rollout training count; this is not a deadline.

    Calibration and setup are additional costs. The 60/20/20 split is a planning
    allocation; evaluation and reruns are separate commands.
    """
    for value, name in ((wall_clock_seconds, 'wall_clock_seconds'),
                        (ppo_ms_per_timestep, 'ppo_ms_per_timestep'),
                        (measured_p95_step_ms, 'measured_p95_step_ms')):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(name + ' must be finite and positive')
    for value, name in ((calibration_steps, 'calibration_steps'),
                        (rollout_steps, 'rollout_steps')):
        if type(value) is not int or value <= 0:
            raise ValueError(name + ' must be a positive integer')
    training_seconds = float(wall_clock_seconds) * 0.60
    # PPO completes whole rollouts. A budget smaller than one still needs one.
    rollouts = max(1, int(training_seconds * 1000 / ppo_ms_per_timestep / rollout_steps))
    steps = rollouts * rollout_steps
    return TrainingBudget(
        wall_clock_seconds=float(wall_clock_seconds),
        training_seconds=training_seconds,
        held_out_evaluation_seconds=float(wall_clock_seconds) * 0.20,
        rerun_and_demo_seconds=float(wall_clock_seconds) * 0.20,
        measured_p95_step_ms=float(measured_p95_step_ms),
        planned_training_steps=steps,
        calibration_steps=calibration_steps,
        ppo_ms_per_timestep=float(ppo_ms_per_timestep),
        estimated_training_seconds=steps * ppo_ms_per_timestep / 1000.0,
    )


def _ppo_rollout_configuration(total_timesteps: int, n_envs: int = 1):
    """Choose a rollout/batch pair for a complete vectorized rollout."""
    if type(total_timesteps) is not int or total_timesteps <= 0:
        raise ValueError('total_timesteps must be a positive integer')
    if type(n_envs) is not int or n_envs <= 0:
        raise ValueError('n_envs must be a positive integer')
    upper = min(256, max(2, math.ceil(total_timesteps / n_envs)))
    divisors = [value for value in range(2, upper + 1)
                if total_timesteps % (value * n_envs) == 0]
    n_steps = max(divisors) if divisors else upper
    buffer_size = n_steps * n_envs
    batch_divisors = [value for value in range(2, min(64, buffer_size) + 1)
                      if buffer_size % value == 0]
    batch_size = max(batch_divisors) if batch_divisors else buffer_size
    return n_steps, batch_size


def train_maskable_ppo(output_dir: Path,
                       total_timesteps: int = 10_000,
                       seed: int = 7,
                       wall_clock_seconds: Optional[float] = None,
                       benchmark_steps: int = 256,
                       calibration_steps: int = 256,
                       provider_factory: Callable[[], Any] = DeterministicToyProvider,
                       scenario_factory: Callable[[], Any] = SeededScenarioGenerator,
                       n_envs: int = 1,
                       gamma: float = 1.0,
                       gae_lambda: float = 0.95,
                       entropy_coefficient: float = 0.0) -> TrainingArtifacts:
    """Train with replaceable provider/scenario factories and save identities."""
    if type(total_timesteps) is not int or total_timesteps <= 0:
        raise ValueError('total_timesteps must be a positive integer')
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if type(n_envs) is not int or n_envs <= 0:
        raise ValueError('n_envs must be a positive integer')
    for value, name, lower_inclusive, upper_inclusive in (
            (gamma, 'gamma', 0.0, 1.0),
            (gae_lambda, 'gae_lambda', 0.0, 1.0)):
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not lower_inclusive <= value <= upper_inclusive):
            raise ValueError(name + ' must be finite and between zero and one')
    if (type(entropy_coefficient) not in (int, float)
            or not math.isfinite(entropy_coefficient)
            or entropy_coefficient < 0):
        raise ValueError('entropy_coefficient must be finite and nonnegative')
    try:
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.vec_env import (DummyVecEnv, SubprocVecEnv,
                                                      VecNormalize)
        from stable_baselines3.common.callbacks import BaseCallback
        from torch.distributions import Distribution
    except ImportError as exc:
        raise RuntimeError(
            'install backend/learning/requirements-rl.txt in .venv-rl first') from exc
    # PyTorch's optional Simplex assertion can reject a valid 1,289-way
    # float32 softmax solely from accumulated roundoff.  Provider outputs and
    # complete observations are independently checked for non-finite values.
    Distribution.set_default_validate_args(False)

    if type(calibration_steps) is not int or calibration_steps <= 0:
        raise ValueError('calibration_steps must be a positive integer')
    if wall_clock_seconds is not None and (
            type(wall_clock_seconds) not in (int, float)
            or not math.isfinite(wall_clock_seconds) or wall_clock_seconds <= 0):
        raise ValueError('wall_clock_seconds must be finite and positive')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    requested_timesteps = total_timesteps
    identity_provider = provider_factory()
    identity_generator = scenario_factory()
    scenario_seed_offset = _scenario_seed_offset(identity_generator)
    p95_ms = None
    budget = None
    calibration_elapsed = None
    # Freeze this configuration before calibration so training uses the same PPO
    # rollout and minibatch sizes even when its effective step count changes.
    n_steps, batch_size = _ppo_rollout_configuration(requested_timesteps, n_envs)
    rollout_buffer_size = n_steps * n_envs
    start_method = None
    if n_envs > 1:
        start_method = ('forkserver' if 'forkserver' in multiprocessing.get_all_start_methods()
                        else 'spawn')
    env_factories = tuple(
        _EnvironmentFactory(
            provider_factory, scenario_factory, seed + rank, n_envs,
            scenario_seed_offset)
        for rank in range(n_envs))

    class EpisodeCoverageCallback(BaseCallback):
        def __init__(self):
            super().__init__(verbose=0)
            self.completed = 0
            self.episodes = Counter()
            self.profiles = Counter()
            self.actions = Counter()

        def _on_step(self) -> bool:
            for action in np.asarray(self.locals.get('actions', ())).reshape(-1):
                value = int(action)
                kind = ('assign' if value < ASSIGNMENT_ACTIONS else
                        'cancel' if value < ADVANCE_ACTION else 'advance')
                self.actions[kind] += 1
            for done, info in zip(
                    self.locals.get('dones', ()), self.locals.get('infos', ())):
                if done:
                    self.completed += 1
                    self.episodes[str(info.get('episode_id', 'unknown'))] += 1
                    profile = info.get('scenario_profile')
                    if profile is not None:
                        self.profiles[str(profile)] += 1
            return True

    def make_training_run():
        vector_env = (DummyVecEnv(env_factories) if n_envs == 1 else
                      SubprocVecEnv(env_factories, start_method=start_method))
        normalized = VecNormalize(
            vector_env, norm_obs=True, norm_reward=True, clip_obs=10.0,
            gamma=float(gamma))
        model = MaskablePPO(
            'MlpPolicy', normalized, seed=seed, verbose=0,
            n_steps=n_steps, batch_size=batch_size,
            gamma=float(gamma), gae_lambda=float(gae_lambda),
            ent_coef=float(entropy_coefficient),
        )
        return model, normalized

    if wall_clock_seconds is not None:
        p95_ms = measure_environment_p95_step_ms(
            benchmark_steps, seed, provider_factory, scenario_factory)
        calibration_model, calibration_env = make_training_run()
        try:
            started = time.perf_counter()
            calibration_target = (math.ceil(calibration_steps / rollout_buffer_size)
                                  * rollout_buffer_size)
            calibration_model.learn(total_timesteps=calibration_target)
            calibration_elapsed = time.perf_counter() - started
            completed = int(calibration_model.num_timesteps)
            ppo_ms = calibration_elapsed * 1000.0 / completed
        finally:
            calibration_env.close()
        del calibration_model, calibration_env
        budget = budget_from_wall_clock(
            wall_clock_seconds, ppo_ms, completed, p95_ms,
            rollout_steps=rollout_buffer_size)
        total_timesteps = budget.planned_training_steps

    total_timesteps = (math.ceil(total_timesteps / rollout_buffer_size)
                       * rollout_buffer_size)

    # A fresh model and fresh statistics prevent calibration from becoming
    # unreported training. MaskablePPO reseeds this run with the same seed.
    model, normalized_env = make_training_run()
    coverage_callback = EpisodeCoverageCallback()
    started = time.perf_counter()
    try:
        model.learn(total_timesteps=total_timesteps, callback=coverage_callback)
        elapsed = time.perf_counter() - started
        if budget is not None:
            budget = replace(
                budget, actual_training_seconds=elapsed,
                training_overrun_seconds=max(0.0, elapsed - budget.training_seconds),
                training_underrun_seconds=max(0.0, budget.training_seconds - elapsed))
        artifact_stem = ('maskable_ppo_toy'
                         if identity_provider.identity == DeterministicToyProvider.identity
                         else 'maskable_ppo_' + identity_provider.identity.replace('-', '_'))
        model_path = output / artifact_stem
        normalization_path = output / 'vecnormalize.pkl'
        metadata_path = output / 'training-metadata.json'
        model.save(str(model_path))
        normalized_env.save(str(normalization_path))
        provider_metadata = {
            'identity': identity_provider.identity, 'version': identity_provider.version,
            'objective_direction': identity_provider.objective_direction.value,
            'data_identity': getattr(getattr(identity_provider, 'catalog', None), 'identity', None),
            'configuration_identity': getattr(identity_provider, 'config_identity', None),
            'cache_identity': getattr(identity_provider, 'cache_identity', None),
            'source_checksums': dict(getattr(
                getattr(identity_provider, 'catalog', None), 'source_checksums', {})),
        }
        generator_metadata = {
            'version': identity_generator.version,
            'configuration_checksum': getattr(identity_generator, 'configuration_checksum',
                                                _stable_identity(vars(identity_generator))),
            'geometry_checksum': getattr(getattr(identity_generator, 'main_island', None),
                                         'geometry_checksum', None),
            'source_checksum': getattr(getattr(identity_generator, 'main_island', None),
                                       'source_checksum', None),
        }
        pool_provenance = getattr(identity_generator, 'provenance', None)
        if pool_provenance is not None:
            generator_metadata['scenario_pool'] = dict(pool_provenance)
        layout = ObservationLayout.build()
        configuration_checksum = _stable_identity({
            'model_version': MODEL_VERSION,
            'observation_layout_version': OBSERVATION_LAYOUT_VERSION,
            'observation_layout_checksum': layout.checksum,
            'provider': provider_metadata, 'generator': generator_metadata,
        })
        dependencies = _dependency_versions()
        metadata = {
        'schema_version': 'policy-artifact/1',
        'algorithm': 'maskable-ppo',
        'artifact_label': ('plumbing validation only'
                           if identity_provider.identity == DeterministicToyProvider.identity
                           else 'Singapore demo-v2 assumption-grade training'),
        'model_version': MODEL_VERSION,
        'model_file': artifact_stem + '.zip',
        'observation_layout_version': OBSERVATION_LAYOUT_VERSION,
        'observation_layout_checksum': layout.checksum,
        'configuration_checksum': configuration_checksum,
        'provider': provider_metadata,
        'scenario_generator': generator_metadata,
        'scenario_generator_version': identity_generator.version,
        'seed': seed,
        'algorithm_seed': seed,
        'scenario_seed_offset': scenario_seed_offset,
        'first_scenario_seed': scenario_seed_offset + seed,
        'n_envs': n_envs,
        'vector_environment_type': ('DummyVecEnv' if n_envs == 1 else 'SubprocVecEnv'),
        'multiprocessing_start_method': start_method,
        'worker_seed_streams': [
            {'rank': rank, 'base_seed': seed + rank,
             'episode_seed_stride': n_envs,
             'first_scenario_seed': scenario_seed_offset + seed + rank}
            for rank in range(n_envs)],
        'completed_episodes': coverage_callback.completed,
        'unique_episodes_visited': len(coverage_callback.episodes),
        'episode_visit_counts': dict(sorted(coverage_callback.episodes.items())),
        'profile_episode_counts': dict(sorted(coverage_callback.profiles.items())),
        'action_counts': dict(sorted(coverage_callback.actions.items())),
        'requested_timesteps': requested_timesteps,
        'effective_timesteps': total_timesteps,
        'total_timesteps': model.num_timesteps,
        'ppo_n_steps': n_steps,
        'ppo_batch_size': batch_size,
        'ppo_rollout_buffer_size': rollout_buffer_size,
        'ppo_n_epochs': model.n_epochs,
        'ppo_gamma': model.gamma,
        'ppo_gae_lambda': model.gae_lambda,
        'ppo_entropy_coefficient': model.ent_coef,
        'ppo_final_diagnostics': {
            key.removeprefix('train/'): float(value)
            for key, value in sorted(model.logger.name_to_value.items())
            if key.startswith('train/') and isinstance(value, Real)
        },
        'elapsed_seconds': elapsed,
        'measured_timesteps_per_second': model.num_timesteps / elapsed,
        'measured_p95_step_ms': p95_ms,
        'calibration_steps': 0 if budget is None else budget.calibration_steps,
        'calibration_seconds': calibration_elapsed,
        'ppo_ms_per_timestep': None if budget is None else budget.ppo_ms_per_timestep,
        'estimated_training_seconds': None if budget is None else budget.estimated_training_seconds,
        'actual_training_seconds': elapsed,
        'training_overrun_seconds': None if budget is None else budget.training_overrun_seconds,
        'training_underrun_seconds': None if budget is None else budget.training_underrun_seconds,
        'budget': None if budget is None else asdict(budget),
        'dependencies': dependencies,
        'dependency_identity': _stable_identity(dependencies),
        }
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + '\n',
            encoding='utf-8')
    finally:
        normalized_env.close()
    return TrainingArtifacts(
        model_path=str(model_path) + '.zip',
        normalization_path=str(normalization_path),
        metadata_path=str(metadata_path),
        total_timesteps=model.num_timesteps,
        elapsed_seconds=elapsed,
    )


def load_normalized_policy(
        output_dir: Path, seed: int = 0,
        provider_factory: Callable[[], Any] = DeterministicToyProvider,
        scenario_factory: Callable[[], Any] = SeededScenarioGenerator) -> NormalizedPolicy:
    """Load a policy and its frozen observation-normalization statistics."""
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    try:
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        from torch.distributions import Distribution
    except ImportError as exc:
        raise RuntimeError(
            'install backend/learning/requirements-rl.txt in .venv-rl first') from exc
    Distribution.set_default_validate_args(False)
    output = Path(output_dir)
    metadata_path = output / 'training-metadata.json'
    normalization_path = output / 'vecnormalize.pkl'
    if not metadata_path.is_file() or not normalization_path.is_file():
        raise ValueError('model metadata and normalization artifacts are required')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    model_path = output / metadata.get('model_file', 'maskable_ppo_toy.zip')
    if not model_path.is_file():
        raise ValueError('recorded model artifact is required')
    provider = provider_factory()
    generator = scenario_factory()
    scenario_seed_offset = _scenario_seed_offset(generator)
    expected = {
        'model_version': MODEL_VERSION,
        'observation_layout_version': OBSERVATION_LAYOUT_VERSION,
        'observation_layout_checksum': ObservationLayout.build().checksum,
        'provider_identity': provider.identity,
        'provider_version': provider.version,
        'scenario_generator_version': generator.version,
    }
    actual = {
        'model_version': metadata.get('model_version'),
        'observation_layout_version': metadata.get('observation_layout_version'),
        'observation_layout_checksum': metadata.get('observation_layout_checksum'),
        'provider_identity': metadata.get('provider', {}).get('identity'),
        'provider_version': metadata.get('provider', {}).get('version'),
        'scenario_generator_version': metadata.get('scenario_generator_version'),
    }
    if actual != expected:
        raise ValueError('model/provider/generator/observation identity mismatch')
    if metadata.get('dependency_identity') != _stable_identity(_dependency_versions()):
        raise ValueError('model dependency identity mismatch')
    recorded_provider_config = metadata.get('provider', {}).get('configuration_identity')
    if recorded_provider_config != getattr(provider, 'config_identity', None):
        raise ValueError('provider configuration identity mismatch')
    recorded_generator_config = metadata.get('scenario_generator', {}).get(
        'configuration_checksum')
    current_generator_config = getattr(
        generator, 'configuration_checksum', _stable_identity(vars(generator)))
    if recorded_generator_config != current_generator_config:
        raise ValueError('scenario generator configuration identity mismatch')

    def make_env():
        return CentralizedInterceptionEnv(
            provider_factory(),
            scenario_generator=scenario_factory(),
            base_seed=seed,
            scenario_seed_offset=scenario_seed_offset,
            policy_version=MODEL_VERSION,
        )

    vector_env = DummyVecEnv([make_env])
    normalized_env = VecNormalize.load(str(normalization_path), vector_env)
    normalized_env.training = False
    normalized_env.norm_reward = False
    model = MaskablePPO.load(str(model_path), env=normalized_env)
    artifact_identity = _stable_identity({
        'algorithm': metadata.get('algorithm', 'maskable-ppo'),
        'model_version': metadata.get('model_version'),
        'configuration_checksum': metadata.get('configuration_checksum'),
        'dependency_identity': metadata.get('dependency_identity'),
        'total_timesteps': metadata.get('total_timesteps'),
    })
    return NormalizedPolicy(model, normalized_env, artifact_identity)


def load_policy(
        output_dir: Path, seed: int = 0,
        provider_factory: Optional[Callable[[], Any]] = None,
        scenario_factory: Optional[Callable[[], Any]] = None):
    """Load PPO or structured imitation based on artifact metadata.

    PPO metadata produced before the generic artifact schema did not contain an
    ``algorithm`` field; those directories intentionally retain legacy PPO
    loading behavior.
    """
    output = Path(output_dir)
    imitation_metadata = output / 'policy-metadata.json'
    ppo_metadata = output / 'training-metadata.json'
    metadata_path = imitation_metadata if imitation_metadata.is_file() else ppo_metadata
    if not metadata_path.is_file():
        raise ValueError('policy metadata artifact is required')
    try:
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('cannot load policy metadata') from exc
    algorithm = metadata.get('algorithm', 'maskable-ppo')
    if algorithm == 'maskable-ppo':
        return load_normalized_policy(
            output, seed=seed,
            provider_factory=(provider_factory or DeterministicToyProvider),
            scenario_factory=(scenario_factory or SeededScenarioGenerator))
    if algorithm == 'structured-behavior-cloning/1':
        from .imitation import load_imitation_policy
        return load_imitation_policy(
            output, provider_factory=provider_factory,
            scenario_factory=scenario_factory)
    raise ValueError('unsupported policy algorithm: ' + str(algorithm))


def _stable_identity(value: Any) -> str:
    def default(item: Any):
        if isinstance(item, Path):
            return str(item)
        return repr(item)
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         default=default, allow_nan=False).encode('utf-8')
    return 'sha256:' + hashlib.sha256(encoded).hexdigest()


def _dependency_versions() -> Mapping[str, Optional[str]]:
    names = ('numpy', 'gymnasium', 'torch', 'stable-baselines3', 'sb3-contrib',
             'shapely', 'pyproj')
    result = {}
    for name in names:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result
