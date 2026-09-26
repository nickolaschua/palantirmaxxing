"""Structured behavior cloning from the privileged fixed-rank optimizer.

The teacher is deliberately clairvoyant and offline.  Demonstration generation
is the only place that may inspect a complete episode; the saved student takes
only the environment observation and current action mask at inference time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import importlib.metadata
import json
import math
from pathlib import Path
import random
import time
import zipfile
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.simulation import (MAX_CANDIDATES_PER_PAIR, MAX_INTERCEPTORS,
                                AssignmentStatus, EpisodeSpec,
                                OptimalFixedRankAssignmentPolicy,
                                SimulationEngine, ThreatStatus,
                                candidate_universes,
                                canonical_episode_hash, load_scenario_pool,
                                optimal_fixed_rank_plan)

from .environment import (ADVANCE_ACTION, ASSIGNMENT_ACTIONS,
                          CANCEL_ACTION_START, CANDIDATE_FEATURE_COUNT,
                          GLOBAL_FEATURE_COUNT, INTERCEPTOR_FEATURE_COUNT,
                          OBSERVATION_LAYOUT_VERSION, PROVIDER_FEATURE_COUNT,
                          THREAT_FEATURE_COUNT, ASSIGNMENT_FEATURE_COUNT,
                          CentralizedInterceptionEnv, ObservationLayout)


DEMONSTRATION_SCHEMA_VERSION = 'imitation-demonstrations/1'
POLICY_ARTIFACT_SCHEMA_VERSION = 'policy-artifact/1'
IMITATION_ALGORITHM = 'structured-behavior-cloning/1'
IMITATION_MODEL_VERSION = 'structured-imitation-centralized/1'
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_LEARNING_RATE = 1e-3
STATE_FEATURE_COUNT = GLOBAL_FEATURE_COUNT + PROVIDER_FEATURE_COUNT
ACTION_FEATURE_COUNT = (THREAT_FEATURE_COUNT + ASSIGNMENT_FEATURE_COUNT
                        + INTERCEPTOR_FEATURE_COUNT + CANDIDATE_FEATURE_COUNT + 3)
FEATURE_SCHEMA = {
    'version': 'structured-action-features/1',
    'state': {'global': GLOBAL_FEATURE_COUNT, 'provider': PROVIDER_FEATURE_COUNT,
              'total': STATE_FEATURE_COUNT},
    'action_local': {
        'threat': THREAT_FEATURE_COUNT,
        'assignment': ASSIGNMENT_FEATURE_COUNT,
        'interceptor': INTERCEPTOR_FEATURE_COUNT,
        'candidate': CANDIDATE_FEATURE_COUNT,
        'action_type_one_hot': 3,
        'total': ACTION_FEATURE_COUNT,
    },
    'action_type_order': ['assignment', 'cancel', 'advance'],
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha256_bytes(value: bytes) -> str:
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return 'sha256:' + digest.hexdigest()


def _write_npz_deterministic(path: Path, **arrays: np.ndarray) -> None:
    """Write an NPZ whose bytes do not depend on wall-clock ZIP metadata."""
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for name in sorted(arrays):
            buffer = io.BytesIO()
            np.save(buffer, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(name + '.npy', date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, buffer.getvalue(), compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=6)


def feature_schema_checksum() -> str:
    return _sha256_bytes(_canonical_json(FEATURE_SCHEMA))


def extract_state_features(observation: np.ndarray) -> np.ndarray:
    """Extract the compact observation-wide features available to the student."""
    layout = ObservationLayout.build()
    values = np.asarray(observation, dtype=np.float32)
    if values.ndim != 1 or values.shape[0] != layout.size:
        raise ValueError('observation shape does not match centralized layout')
    return np.concatenate((values[layout.global_state],
                           values[layout.provider_features])).astype(np.float32)


def extract_action_features(observation: np.ndarray, action: int) -> np.ndarray:
    """Encode one environment action without looking outside the observation."""
    layout = ObservationLayout.build()
    values = np.asarray(observation, dtype=np.float32)
    if values.ndim != 1 or values.shape[0] != layout.size:
        raise ValueError('observation shape does not match centralized layout')
    if type(action) not in (int, np.int64, np.int32):
        raise ValueError('action must be an integer')
    action = int(action)
    if not 0 <= action <= ADVANCE_ACTION:
        raise ValueError('action is outside the environment action space')

    threat = np.zeros(THREAT_FEATURE_COUNT, dtype=np.float32)
    assignment = np.zeros(ASSIGNMENT_FEATURE_COUNT, dtype=np.float32)
    interceptor = np.zeros(INTERCEPTOR_FEATURE_COUNT, dtype=np.float32)
    candidate = np.zeros(CANDIDATE_FEATURE_COUNT, dtype=np.float32)
    action_type = np.zeros(3, dtype=np.float32)
    if action < ASSIGNMENT_ACTIONS:
        threat_slot, interceptor_slot, candidate_slot = \
            CentralizedInterceptionEnv.decode_assignment_action(action)
        flat_candidate = ((threat_slot * MAX_INTERCEPTORS + interceptor_slot)
                          * MAX_CANDIDATES_PER_PAIR
                          + candidate_slot)
        threat[:] = values[layout.threats].reshape(-1, THREAT_FEATURE_COUNT)[threat_slot]
        assignment[:] = values[layout.assignments].reshape(
            -1, ASSIGNMENT_FEATURE_COUNT)[threat_slot]
        interceptor[:] = values[layout.interceptors].reshape(
            -1, INTERCEPTOR_FEATURE_COUNT)[interceptor_slot]
        candidate[:] = values[layout.candidates].reshape(
            -1, CANDIDATE_FEATURE_COUNT)[flat_candidate]
        action_type[0] = 1.0
    elif action < ADVANCE_ACTION:
        threat_slot = action - CANCEL_ACTION_START
        threat[:] = values[layout.threats].reshape(-1, THREAT_FEATURE_COUNT)[threat_slot]
        assignment[:] = values[layout.assignments].reshape(
            -1, ASSIGNMENT_FEATURE_COUNT)[threat_slot]
        action_type[1] = 1.0
    else:
        action_type[2] = 1.0
    result = np.concatenate(
        (threat, assignment, interceptor, candidate, action_type))
    if result.shape != (ACTION_FEATURE_COUNT,):
        raise AssertionError('structured action feature width changed')
    return result.astype(np.float32)


def extract_valid_action_features(
        observation: np.ndarray, action_mask: np.ndarray
        ) -> Tuple[np.ndarray, np.ndarray]:
    mask = np.asarray(action_mask, dtype=bool)
    if mask.ndim != 1 or mask.shape[0] != ADVANCE_ACTION + 1:
        raise ValueError('action mask shape does not match environment action space')
    indices = np.flatnonzero(mask).astype(np.int64)
    if not len(indices):
        raise ValueError('at least one valid action is required')
    features = np.stack(
        [extract_action_features(observation, int(action)) for action in indices])
    return indices, features


def deterministic_family_split(family_ids: Sequence[str], seed: int = 7,
                               validation_fraction: float = 0.10
                               ) -> Mapping[str, str]:
    """Assign whole families to train/internal-validation deterministically."""
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if not 0 < validation_fraction < 1:
        raise ValueError('validation_fraction must be between zero and one')
    families = sorted(set(family_ids), key=lambda item: hashlib.sha256(
        ('%d|%s' % (seed, item)).encode('utf-8')).hexdigest())
    if len(families) < 2:
        raise ValueError('family split requires at least two distinct families')
    validation_count = max(1, min(len(families) - 1,
                                  int(round(len(families) * validation_fraction))))
    validation = set(families[:validation_count])
    return {family: ('internal-validation' if family in validation else 'training')
            for family in families}


@dataclass(frozen=True)
class DemonstrationDataset:
    root: Path
    manifest: Mapping[str, Any]
    state_features: np.ndarray
    action_offsets: np.ndarray
    action_features: np.ndarray
    action_indices: np.ndarray
    acceptable_targets: np.ndarray
    decision_episode_indices: np.ndarray
    split_labels: np.ndarray

    def decision_count(self) -> int:
        return int(self.state_features.shape[0])


def _provider_metadata(provider: Any) -> Mapping[str, Any]:
    return {
        'identity': provider.identity,
        'version': provider.version,
        'configuration_identity': getattr(provider, 'config_identity', None),
        'fixed_candidate_costs': bool(getattr(provider, 'fixed_candidate_costs', False)),
        'additive_training_costs': bool(getattr(provider, 'additive_training_costs', False)),
        'operational_updates_affect_costs': bool(
            getattr(provider, 'operational_updates_affect_costs', True)),
    }


def _assert_exact_provider(provider: Any) -> None:
    if not (getattr(provider, 'fixed_candidate_costs', False)
            and getattr(provider, 'additive_training_costs', False)
            and not getattr(provider, 'operational_updates_affect_costs', True)):
        raise ValueError(
            'expert demonstrations require fixed additive costs without '
            'cost-changing operational updates')


def _planned_actions(env: CentralizedInterceptionEnv, plan: Any,
                     mask: np.ndarray) -> Tuple[int, ...]:
    decisions = {row.threat_id: row for row in plan.decisions}
    result = []
    for threat_slot, threat_id in enumerate(env.threat_slots):
        if threat_id is None or threat_id in env.engine.assignments:
            continue
        decision = decisions.get(threat_id)
        if decision is None or threat_id not in env.engine.visible_threat_ids():
            continue
        interceptor_slot = env.interceptor_slots.index(decision.interceptor_id)
        rows = env.engine.threats[threat_id].candidates.get(decision.interceptor_id, ())
        candidate_slot = next((index for index, candidate in enumerate(rows)
                               if candidate.opportunity.opportunity_id
                               == decision.opportunity_id), None)
        if candidate_slot is None:
            raise ValueError('planned opportunity is absent from expert replay')
        action = env.encode_assignment_action(
            threat_slot, interceptor_slot, candidate_slot)
        if mask[action]:
            result.append(action)
    if result:
        return tuple(sorted(set(result)))
    if not mask[ADVANCE_ACTION]:
        raise ValueError('expert plan has no visible valid action and cannot advance')
    return (ADVANCE_ACTION,)


def _episode_demonstrations(spec: EpisodeSpec, provider: Any
                            ) -> Tuple[List[np.ndarray], List[np.ndarray],
                                       List[np.ndarray], List[np.ndarray], float]:
    plan = optimal_fixed_rank_plan(spec, provider)
    if not plan.exact:
        raise ValueError('expert plan is not exact in the declared fixed-rank scope')
    env = CentralizedInterceptionEnv(provider, episode_spec=spec,
                                     policy_version=IMITATION_MODEL_VERSION)
    observations: List[np.ndarray] = []
    actions: List[np.ndarray] = []
    features: List[np.ndarray] = []
    targets: List[np.ndarray] = []
    try:
        observation, _ = env.reset()
        while True:
            mask = env.action_masks().astype(bool)
            acceptable = _planned_actions(env, plan, mask)
            valid_indices, local = extract_valid_action_features(observation, mask)
            target = np.isin(valid_indices, np.asarray(acceptable, dtype=np.int64))
            if not np.any(target):
                raise ValueError('expert target is absent from valid-action set')
            observations.append(extract_state_features(observation))
            actions.append(valid_indices)
            features.append(local)
            targets.append(target.astype(np.bool_))
            observation, _, terminated, truncated, info = env.step(min(acceptable))
            if terminated or truncated:
                if truncated or info['termination_reason'] != 'all_threats_resolved':
                    raise ValueError('exact expert plan did not replay normally')
                score = float(info['raw_score'])
                if not math.isclose(score, plan.predicted_cost,
                                    rel_tol=0.0, abs_tol=1e-12):
                    raise ValueError('expert plan and replay score disagree')
                return observations, actions, features, targets, score
    finally:
        env.close()


def generate_demonstrations(pool_path: Path, output_dir: Path,
                            provider_factory: Any, seed: int = 7,
                            shard_episode_limit: int = 64,
                            episode_limit: Optional[int] = None) -> Mapping[str, Any]:
    """Generate checksummed compact shards from a verified training pool."""
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if type(shard_episode_limit) is not int or shard_episode_limit <= 0:
        raise ValueError('shard_episode_limit must be a positive integer')
    pool = load_scenario_pool(pool_path)
    if pool.manifest.get('dataset_role') != 'development-training':
        raise ValueError('demonstrations may only use a development-training pool')
    records = pool.records
    if episode_limit is not None:
        if type(episode_limit) is not int or episode_limit <= 0:
            raise ValueError('episode_limit must be a positive integer')
        records = records[:episode_limit]
    if not records:
        raise ValueError('demonstration source pool is empty')
    forbidden = {'validation', 'held-out', 'held-out-test', 'stress',
                 'ood-geography', 'ood-cadence', 'assignment-reference'}
    if any(row.get('split') != 'development-training'
           or row.get('split') in forbidden for row in records):
        raise ValueError('non-training scenario found in demonstration source')
    identity_keys = ('record_id', 'canonical_episode_hash', 'content_hash')
    for key in identity_keys:
        values = [row[key] for row in records]
        if len(values) != len(set(values)):
            raise ValueError('duplicate source episode identity: ' + key)

    provider = provider_factory()
    _assert_exact_provider(provider)
    if provider.identity != pool.manifest.get('provider_identity'):
        raise ValueError('scenario pool and expert provider identities disagree')
    family_split = deterministic_family_split(
        [str(row['family_id']) for row in records], seed)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'manifest.json').exists():
        raise ValueError('demonstration output already contains a manifest')

    shards = []
    episode_manifest = []
    dataset_hash = hashlib.sha256()
    decision_total = valid_action_total = 0
    for shard_number, start in enumerate(range(0, len(records), shard_episode_limit)):
        selected = records[start:start + shard_episode_limit]
        states: List[np.ndarray] = []
        offsets = [0]
        all_action_features: List[np.ndarray] = []
        all_action_indices: List[np.ndarray] = []
        all_targets: List[np.ndarray] = []
        episode_indices: List[int] = []
        split_labels: List[int] = []
        for local_episode_index, record in enumerate(selected):
            spec = pool.load(record['record_id'])
            if canonical_episode_hash(spec) != record['canonical_episode_hash']:
                raise ValueError('source episode identity changed during generation')
            obs, indices, local, targets, score = _episode_demonstrations(
                spec, provider_factory())
            absolute_episode_index = start + local_episode_index
            split = family_split[str(record['family_id'])]
            decision_start = decision_total + len(states)
            for state_row, action_row, feature_row, target_row in zip(
                    obs, indices, local, targets):
                states.append(state_row)
                all_action_indices.append(action_row)
                all_action_features.append(feature_row)
                all_targets.append(target_row)
                offsets.append(offsets[-1] + len(action_row))
                episode_indices.append(absolute_episode_index)
                split_labels.append(1 if split == 'internal-validation' else 0)
            episode_manifest.append({
                'episode_index': absolute_episode_index,
                'record_id': record['record_id'],
                'canonical_episode_hash': record['canonical_episode_hash'],
                'family_id': record['family_id'],
                'profile': record['profile'],
                'source_split': record['split'],
                'training_split': split,
                'decision_start': decision_start,
                'decision_count': len(obs),
                'teacher_raw_score': score,
            })
        state_array = np.stack(states).astype(np.float32)
        feature_array = np.concatenate(all_action_features).astype(np.float32)
        index_array = np.concatenate(all_action_indices).astype(np.int64)
        target_array = np.concatenate(all_targets).astype(np.bool_)
        name = 'shard-%05d.npz' % shard_number
        path = output / name
        _write_npz_deterministic(
            path, state_features=state_array,
            action_offsets=np.asarray(offsets, dtype=np.int64),
            action_features=feature_array, action_indices=index_array,
            acceptable_targets=target_array,
            decision_episode_indices=np.asarray(episode_indices, dtype=np.int64),
            split_labels=np.asarray(split_labels, dtype=np.int8))
        digest = _sha256_file(path)
        dataset_hash.update(path.read_bytes())
        shards.append({
            'path': name, 'sha256': digest,
            'episode_start': start, 'episode_count': len(selected),
            'decision_count': len(states), 'valid_action_count': len(index_array),
        })
        decision_total += len(states)
        valid_action_total += len(index_array)

    manifest = {
        'schema_version': DEMONSTRATION_SCHEMA_VERSION,
        'dataset_checksum': 'sha256:' + dataset_hash.hexdigest(),
        'feature_schema': FEATURE_SCHEMA,
        'feature_schema_checksum': feature_schema_checksum(),
        'observation_layout_version': OBSERVATION_LAYOUT_VERSION,
        'observation_layout_checksum': ObservationLayout.build().checksum,
        'seed': seed,
        'source_pool': {
            'root': str(Path(pool_path).resolve()),
            'release_id': pool.manifest['release_id'],
            'manifest_checksum': pool.manifest['manifest_checksum'],
            'dataset_role': pool.manifest['dataset_role'],
            'record_count': len(records),
        },
        'teacher': {
            'identity': OptimalFixedRankAssignmentPolicy.identity,
            'information_scope': OptimalFixedRankAssignmentPolicy.information_scope,
            'privileged': True,
            'scope': 'clairvoyant/offline exact fixed-rank assignment',
        },
        'provider': _provider_metadata(provider),
        'generator': {
            'version': pool.manifest['generator_version'],
            'configuration_checksum': pool.manifest['generator_configuration_checksum'],
            'distribution_checksum': pool.manifest['distribution_checksum'],
        },
        'family_split': dict(sorted(family_split.items())),
        'episode_count': len(records),
        'decision_count': decision_total,
        'valid_action_count': valid_action_total,
        'episodes': episode_manifest,
        'shards': shards,
    }
    (output / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + '\n',
        encoding='utf-8')
    return manifest


def load_demonstrations(path: Path, expected_pool_checksum: Optional[str] = None,
                        expected_provider: Optional[Any] = None,
                        expected_generator: Optional[Any] = None
                        ) -> DemonstrationDataset:
    root = Path(path)
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('cannot load imitation demonstration manifest') from exc
    if manifest.get('schema_version') != DEMONSTRATION_SCHEMA_VERSION:
        raise ValueError('imitation demonstration schema version mismatch')
    if manifest.get('feature_schema_checksum') != feature_schema_checksum():
        raise ValueError('imitation feature schema checksum mismatch')
    if manifest.get('feature_schema') != FEATURE_SCHEMA:
        raise ValueError('imitation feature schema definition mismatch')
    if (manifest.get('observation_layout_version') != OBSERVATION_LAYOUT_VERSION
            or manifest.get('observation_layout_checksum')
            != ObservationLayout.build().checksum):
        raise ValueError('imitation observation layout identity mismatch')
    if manifest.get('source_pool', {}).get('dataset_role') != 'development-training':
        raise ValueError('imitation dataset is not sourced from development training')
    try:
        source_pool = load_scenario_pool(Path(manifest['source_pool']['root']))
    except (KeyError, ValueError, OSError) as exc:
        raise ValueError('cannot verify imitation training-pool identity') from exc
    if (source_pool.manifest['manifest_checksum']
            != manifest['source_pool'].get('manifest_checksum')
            or source_pool.manifest['release_id']
            != manifest['source_pool'].get('release_id')
            or source_pool.manifest['provider_identity']
            != manifest.get('provider', {}).get('identity')
            or source_pool.manifest['generator_version']
            != manifest.get('generator', {}).get('version')
            or source_pool.manifest['generator_configuration_checksum']
            != manifest.get('generator', {}).get('configuration_checksum')):
        raise ValueError('imitation training-pool provenance mismatch')
    if (expected_pool_checksum is not None
            and manifest.get('source_pool', {}).get('manifest_checksum')
            != expected_pool_checksum):
        raise ValueError('imitation training-pool identity mismatch')
    if expected_provider is not None:
        provider = expected_provider() if callable(expected_provider) else expected_provider
        recorded = manifest.get('provider', {})
        if (recorded.get('identity') != provider.identity
                or recorded.get('version') != provider.version
                or recorded.get('configuration_identity')
                != getattr(provider, 'config_identity', None)):
            raise ValueError('imitation provider identity mismatch')
    if expected_generator is not None:
        generator = expected_generator() if callable(expected_generator) else expected_generator
        recorded = manifest.get('generator', {})
        if (recorded.get('version') != getattr(generator, 'version', None)
                or recorded.get('configuration_checksum')
                != getattr(generator, 'configuration_checksum', None)):
            raise ValueError('imitation generator identity mismatch')

    arrays: Dict[str, List[np.ndarray]] = {key: [] for key in (
        'state_features', 'action_features', 'action_indices',
        'acceptable_targets', 'decision_episode_indices', 'split_labels')}
    offsets = [0]
    dataset_hash = hashlib.sha256()
    for shard in manifest.get('shards', ()):
        shard_path = root / shard['path']
        if _sha256_file(shard_path) != shard['sha256']:
            raise ValueError('imitation shard checksum mismatch')
        raw = shard_path.read_bytes()
        dataset_hash.update(raw)
        try:
            data = np.load(shard_path, allow_pickle=False)
            local_offsets = np.asarray(data['action_offsets'], dtype=np.int64)
            if local_offsets.ndim != 1 or local_offsets[0] != 0:
                raise ValueError('invalid ragged action offsets')
            base = offsets[-1]
            offsets.extend((base + local_offsets[1:]).tolist())
            for key in arrays:
                arrays[key].append(np.asarray(data[key]))
        except (OSError, KeyError, ValueError) as exc:
            raise ValueError('cannot load imitation shard arrays') from exc
    if 'sha256:' + dataset_hash.hexdigest() != manifest.get('dataset_checksum'):
        raise ValueError('imitation dataset checksum mismatch')
    merged = {key: np.concatenate(value) for key, value in arrays.items()}
    state = merged['state_features'].astype(np.float32, copy=False)
    local = merged['action_features'].astype(np.float32, copy=False)
    indices = merged['action_indices'].astype(np.int64, copy=False)
    targets = merged['acceptable_targets'].astype(np.bool_, copy=False)
    if (state.ndim != 2 or state.shape[1] != STATE_FEATURE_COUNT
            or local.ndim != 2 or local.shape[1] != ACTION_FEATURE_COUNT
            or len(offsets) != len(state) + 1
            or offsets[-1] != len(local)
            or len(indices) != len(local) or len(targets) != len(local)):
        raise ValueError('imitation dataset array dimensions are inconsistent')
    if (manifest.get('decision_count') != len(state)
            or manifest.get('valid_action_count') != len(local)):
        raise ValueError('imitation dataset manifest counts are inconsistent')
    for start, end in zip(offsets[:-1], offsets[1:]):
        if end <= start or not np.any(targets[start:end]):
            raise ValueError('each decision needs valid and acceptable actions')
    return DemonstrationDataset(
        root=root.resolve(), manifest=manifest, state_features=state,
        action_offsets=np.asarray(offsets, dtype=np.int64), action_features=local,
        action_indices=indices, acceptable_targets=targets,
        decision_episode_indices=merged['decision_episode_indices'].astype(np.int64),
        split_labels=merged['split_labels'].astype(np.int8))


def normalization_statistics(dataset: DemonstrationDataset
                             ) -> Mapping[str, np.ndarray]:
    training = np.flatnonzero(dataset.split_labels == 0)
    return _normalization_statistics_for_decisions(dataset, training)


def _normalization_statistics_for_decisions(
        dataset: DemonstrationDataset, decisions: Sequence[int]
        ) -> Mapping[str, np.ndarray]:
    training = np.asarray(decisions, dtype=np.int64)
    if not len(training):
        raise ValueError('imitation dataset has no training decisions')
    states = dataset.state_features[training]
    action_rows = np.concatenate([
        np.arange(dataset.action_offsets[index], dataset.action_offsets[index + 1])
        for index in training])
    actions = dataset.action_features[action_rows, :ACTION_FEATURE_COUNT - 3]
    state_mean = states.mean(axis=0, dtype=np.float64).astype(np.float32)
    state_std = states.std(axis=0, dtype=np.float64).astype(np.float32)
    action_mean = actions.mean(axis=0, dtype=np.float64).astype(np.float32)
    action_std = actions.std(axis=0, dtype=np.float64).astype(np.float32)
    state_std[state_std < 1e-6] = 1.0
    action_std[action_std < 1e-6] = 1.0
    return {'state_mean': state_mean, 'state_std': state_std,
            'action_mean': action_mean, 'action_std': action_std}


def _train_diagnostic_scorer(
        dataset: DemonstrationDataset, decisions: Sequence[int], seed: int,
        learning_rate: float, batch_size: int, max_epochs: int
        ) -> Tuple[Any, Mapping[str, np.ndarray], Mapping[str, Any]]:
    """Train an intentionally overfit probe without internal early stopping."""
    import torch
    torch.manual_seed(seed)
    statistics = _normalization_statistics_for_decisions(dataset, decisions)
    model = StructuredActionScorer()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    rng = np.random.default_rng(seed)
    losses = []
    for epoch in range(1, max_epochs + 1):
        model.train()
        epoch_losses = []
        shuffled = rng.permutation(decisions)
        for start in range(0, len(decisions), batch_size):
            batch = shuffled[start:start + batch_size].tolist()
            state, local, offsets, target = _batch_arrays(
                dataset, batch, statistics)
            optimizer.zero_grad()
            logits = model(torch.from_numpy(state), torch.from_numpy(local),
                           torch.from_numpy(offsets))
            loss = set_valued_masked_cross_entropy(
                logits, offsets, torch.from_numpy(target))
            loss.backward()
            optimizer.step()
            epoch_losses.append(float(loss.detach()))
        losses.append(float(np.mean(epoch_losses)))
        if _agreement(model, dataset, decisions, statistics) == 1.0:
            break
    return model, statistics, {
        'epochs': epoch, 'final_loss': losses[-1],
        'learning_rate': learning_rate,
        'teacher_path_acceptable_action_agreement': _agreement(
            model, dataset, decisions, statistics),
    }


def _trained_overfit_diagnostics(
        dataset: DemonstrationDataset, pool: Any, provider_factory: Any,
        seed: int, learning_rate: float, batch_size: int,
        max_epochs: int, diagnostic_limit: int) -> Mapping[str, Any]:
    training_episodes = [
        row for row in dataset.manifest['episodes']
        if row['training_split'] == 'training']
    if not training_episodes:
        raise RuntimeError('overfit diagnostics have no training episodes')
    selected = training_episodes[:min(16, diagnostic_limit)]

    def decision_indices(rows):
        episode_ids = {int(row['episode_index']) for row in rows}
        return np.flatnonzero(np.isin(
            dataset.decision_episode_indices,
            np.asarray(sorted(episode_ids), dtype=np.int64))).tolist()

    single_model, single_stats, single_training = _train_diagnostic_scorer(
        dataset, decision_indices(selected[:1]), seed, learning_rate,
        batch_size, max_epochs)
    single_policy = StructuredImitationPolicy(
        single_model, single_stats, 'overfit-diagnostic-single')
    single_spec = pool.load(selected[0]['record_id'])
    single = diagnostic_rollout(single_policy, single_spec, provider_factory)
    single_pass = bool(
        single['acceptable_action_agreement'] == 1.0
        and single['identical_teacher_score'] and single['normal_termination']
        and not single['constraint_violation'] and not single['invalid_action_count'])

    fixed_model, fixed_stats, fixed_training = _train_diagnostic_scorer(
        dataset, decision_indices(selected), seed, learning_rate,
        batch_size, max_epochs)
    fixed_policy = StructuredImitationPolicy(
        fixed_model, fixed_stats, 'overfit-diagnostic-fixed')
    fixed = tuple(diagnostic_rollout(
        fixed_policy, pool.load(row['record_id']), provider_factory)
                  for row in selected)
    total_decisions = sum(row['decision_count'] for row in fixed)
    agreement = sum(
        row['acceptable_action_agreement'] * row['decision_count']
        for row in fixed) / total_decisions
    fixed_pass = bool(
        agreement >= 0.95
        and all(row['normal_termination'] for row in fixed)
        and not any(row['constraint_violation'] for row in fixed)
        and not any(row['invalid_action_count'] for row in fixed))
    result = {
        'single_scenario': single,
        'single_training': single_training,
        'single_scenario_passed': single_pass,
        'fixed_scenario_count': len(fixed),
        'fixed_training': fixed_training,
        'fixed_acceptable_action_agreement': agreement,
        'fixed_scenarios': fixed,
        'fixed_scenario_gate_passed': fixed_pass,
        'passed': single_pass and fixed_pass,
    }
    return result


def normalize_features(state: np.ndarray, actions: np.ndarray,
                       statistics: Mapping[str, np.ndarray]
                       ) -> Tuple[np.ndarray, np.ndarray]:
    state_result = ((np.asarray(state, dtype=np.float32)
                     - statistics['state_mean']) / statistics['state_std'])
    action_result = np.asarray(actions, dtype=np.float32).copy()
    action_result[..., :ACTION_FEATURE_COUNT - 3] = (
        (action_result[..., :ACTION_FEATURE_COUNT - 3] - statistics['action_mean'])
        / statistics['action_std'])
    return state_result.astype(np.float32), action_result.astype(np.float32)


def set_valued_masked_cross_entropy(logits: Any, offsets: Any,
                                    acceptable_targets: Any) -> Any:
    """Mean -log probability mass assigned to each decision's target set."""
    import torch
    offsets_list = [int(value) for value in offsets]
    losses = []
    for start, end in zip(offsets_list[:-1], offsets_list[1:]):
        row_logits = logits[start:end]
        row_targets = acceptable_targets[start:end].bool()
        if end <= start or not bool(torch.any(row_targets)):
            raise ValueError('each decision must have an acceptable valid action')
        losses.append(torch.logsumexp(row_logits, dim=0)
                      - torch.logsumexp(row_logits[row_targets], dim=0))
    if not losses:
        raise ValueError('ragged batch cannot be empty')
    return torch.stack(losses).mean()


def _model_class():
    import torch
    from torch import nn

    class StructuredActionScorer(nn.Module):
        def __init__(self, hidden_size: int = 96):
            super().__init__()
            self.state_encoder = nn.Sequential(
                nn.Linear(STATE_FEATURE_COUNT, hidden_size), nn.ReLU(),
                nn.Linear(hidden_size, hidden_size), nn.ReLU())
            self.local_encoder = nn.Sequential(
                nn.Linear(ACTION_FEATURE_COUNT, hidden_size), nn.ReLU(),
                nn.Linear(hidden_size, hidden_size), nn.ReLU())
            self.scorer = nn.Sequential(
                nn.Linear(hidden_size * 4, hidden_size), nn.ReLU(),
                nn.Linear(hidden_size, 1))

        def forward(self, states, local_actions, offsets):
            state_encoded = self.state_encoder(states)
            local_encoded = self.local_encoder(local_actions)
            rows = []
            for decision, (start, end) in enumerate(zip(
                    offsets[:-1].tolist(), offsets[1:].tolist())):
                group = local_encoded[start:end]
                mean = group.mean(dim=0)
                maximum = group.max(dim=0).values
                context = torch.cat((state_encoded[decision], mean, maximum))
                repeated = context.unsqueeze(0).expand(end - start, -1)
                rows.append(self.scorer(torch.cat((group, repeated), dim=1)).squeeze(-1))
            return torch.cat(rows)

    return StructuredActionScorer


StructuredActionScorer = _model_class()


def _batch_arrays(dataset: DemonstrationDataset, decisions: Sequence[int],
                  statistics: Mapping[str, np.ndarray]):
    states, locals_, targets, offsets = [], [], [], [0]
    for decision in decisions:
        start, end = dataset.action_offsets[decision:decision + 2]
        states.append(dataset.state_features[decision])
        locals_.append(dataset.action_features[start:end])
        targets.append(dataset.acceptable_targets[start:end])
        offsets.append(offsets[-1] + int(end - start))
    state, local = normalize_features(np.stack(states), np.concatenate(locals_), statistics)
    return state, local, np.asarray(offsets, dtype=np.int64), np.concatenate(targets)


def _agreement(model: Any, dataset: DemonstrationDataset,
               decisions: Sequence[int], statistics: Mapping[str, np.ndarray]) -> float:
    import torch
    correct = 0
    model.eval()
    with torch.no_grad():
        for decision in decisions:
            state, local, offsets, target = _batch_arrays(
                dataset, [decision], statistics)
            logits = model(torch.from_numpy(state), torch.from_numpy(local),
                           torch.from_numpy(offsets))
            correct += bool(target[int(torch.argmax(logits).item())])
    return correct / len(decisions) if decisions else 0.0


@dataclass(frozen=True)
class ImitationTrainingArtifacts:
    model_path: str
    normalization_path: str
    metadata_path: str
    model_version: str
    best_epoch: int
    validation_loss: float
    validation_agreement: float


def train_structured_behavior_cloning(
        dataset_dir: Path, output_dir: Path, seed: int = 7,
        learning_rate: float = 1e-3, batch_size: int = 128,
        max_epochs: int = 100, patience: int = 10,
        initial_artifact_dir: Optional[Path] = None,
        provider_factory: Optional[Any] = None,
        diagnostic_limit: int = 16,
        require_diagnostics: bool = True) -> ImitationTrainingArtifacts:
    import torch
    if any(type(value) is not int or value <= 0
           for value in (batch_size, max_epochs, patience, diagnostic_limit)):
        raise ValueError('batch size, epochs, and patience must be positive integers')
    if type(seed) is not int or seed < 0 or learning_rate <= 0:
        raise ValueError('invalid behavior-cloning training configuration')
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.use_deterministic_algorithms(True)
    dataset = load_demonstrations(dataset_dir)
    statistics = normalization_statistics(dataset)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    overfit_diagnostics = None
    if require_diagnostics:
        if provider_factory is None:
            provider_identity = dataset.manifest.get('provider', {}).get('identity')
            if provider_identity == 'singapore-consequence-provider':
                from backend.simulation import runtime_factories
                provider_factory, _ = runtime_factories(
                    'singapore-demo-v2', 'singapore-v2')
            else:
                raise ValueError(
                    'provider_factory is required for mandatory overfit diagnostics')
        source_pool = Path(dataset.manifest['source_pool']['root'])
        diagnostic_pool = load_scenario_pool(source_pool)
        overfit_diagnostics = _trained_overfit_diagnostics(
            dataset, diagnostic_pool, provider_factory, seed,
            DIAGNOSTIC_LEARNING_RATE,
            batch_size, max_epochs, diagnostic_limit)
        (output / 'overfit-diagnostics.json').write_text(
            json.dumps(overfit_diagnostics, indent=2, sort_keys=True,
                       allow_nan=False) + '\n', encoding='utf-8')
        if not overfit_diagnostics['passed']:
            raise RuntimeError(
                'behavior-cloning overfit diagnostics failed; inspect '
                'overfit-diagnostics.json for feature extraction, masking, '
                'target construction, and model-capacity evidence')
    model = StructuredActionScorer()
    if initial_artifact_dir is not None:
        previous = load_imitation_policy(initial_artifact_dir)
        model.load_state_dict(previous.model.state_dict())
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    training = np.flatnonzero(dataset.split_labels == 0).tolist()
    validation = np.flatnonzero(dataset.split_labels == 1).tolist()
    if not validation:
        raise ValueError('imitation dataset has no internal-validation decisions')
    rng = np.random.default_rng(seed)
    best_state = None
    best_loss = math.inf
    best_epoch = 0
    epochs_without_improvement = 0
    history = []
    started = time.perf_counter()
    for epoch in range(1, max_epochs + 1):
        model.train()
        shuffled = rng.permutation(training)
        train_losses = []
        for start in range(0, len(shuffled), batch_size):
            decisions = shuffled[start:start + batch_size].tolist()
            state, local, offsets, target = _batch_arrays(
                dataset, decisions, statistics)
            optimizer.zero_grad()
            logits = model(torch.from_numpy(state), torch.from_numpy(local),
                           torch.from_numpy(offsets))
            loss = set_valued_masked_cross_entropy(
                logits, offsets, torch.from_numpy(target))
            loss.backward()
            optimizer.step()
            train_losses.append(float(loss.detach()))
        model.eval()
        validation_losses = []
        with torch.no_grad():
            for start in range(0, len(validation), batch_size):
                decisions = validation[start:start + batch_size]
                state, local, offsets, target = _batch_arrays(
                    dataset, decisions, statistics)
                logits = model(torch.from_numpy(state), torch.from_numpy(local),
                               torch.from_numpy(offsets))
                validation_losses.append(float(set_valued_masked_cross_entropy(
                    logits, offsets, torch.from_numpy(target))))
        validation_loss = float(np.mean(validation_losses))
        agreement = _agreement(model, dataset, validation, statistics)
        history.append({'epoch': epoch, 'training_loss': float(np.mean(train_losses)),
                        'validation_loss': validation_loss,
                        'validation_acceptable_action_agreement': agreement})
        if validation_loss < best_loss - 1e-9:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = {key: value.detach().clone()
                          for key, value in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                break
    model.load_state_dict(best_state)
    validation_agreement = _agreement(
        model, dataset, validation, statistics)
    model_path = output / 'model.pt'
    normalization_path = output / 'normalization.npz'
    metadata_path = output / 'policy-metadata.json'
    torch.save(model.state_dict(), model_path)
    _write_npz_deterministic(normalization_path, **statistics)
    dependencies = {name: importlib.metadata.version(name) for name in (
        'numpy', 'torch', 'gymnasium')}
    metadata = {
        'schema_version': POLICY_ARTIFACT_SCHEMA_VERSION,
        'algorithm': IMITATION_ALGORITHM,
        'model_version': IMITATION_MODEL_VERSION,
        'model_file': model_path.name,
        'normalization_file': normalization_path.name,
        'model_sha256': _sha256_file(model_path),
        'normalization_sha256': _sha256_file(normalization_path),
        'dataset_checksum': dataset.manifest['dataset_checksum'],
        'dataset_manifest_checksum': _sha256_file(Path(dataset_dir) / 'manifest.json'),
        'feature_schema_checksum': feature_schema_checksum(),
        'observation_layout_version': OBSERVATION_LAYOUT_VERSION,
        'observation_layout_checksum': ObservationLayout.build().checksum,
        'teacher': dataset.manifest['teacher'],
        'training_pool': dataset.manifest['source_pool'],
        'provider': dataset.manifest['provider'],
        'generator': dataset.manifest['generator'],
        'seed': seed,
        'optimizer': 'AdamW',
        'learning_rate': learning_rate,
        'decision_batch_size': batch_size,
        'maximum_epochs': max_epochs,
        'patience': patience,
        'best_epoch': best_epoch,
        'training_seconds': time.perf_counter() - started,
        'validation_loss': best_loss,
        'validation_acceptable_action_agreement': validation_agreement,
        'training_metrics': history,
        'dependencies': dependencies,
    }
    metadata['artifact_identity'] = _sha256_bytes(_canonical_json({
        key: metadata[key] for key in (
            'algorithm', 'model_version', 'model_sha256', 'normalization_sha256',
            'dataset_checksum', 'feature_schema_checksum',
            'observation_layout_checksum', 'seed')}))
    if overfit_diagnostics is not None:
        metadata['overfit_diagnostics'] = overfit_diagnostics
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + '\n',
        encoding='utf-8')
    return ImitationTrainingArtifacts(
        str(model_path), str(normalization_path), str(metadata_path),
        IMITATION_MODEL_VERSION, best_epoch, best_loss, validation_agreement)


class StructuredImitationPolicy:
    """Loaded observation-only structured scorer with the PPO predict contract."""

    model_version = IMITATION_MODEL_VERSION
    algorithm = IMITATION_ALGORITHM

    def __init__(self, model: Any, statistics: Mapping[str, np.ndarray],
                 artifact_identity: str):
        self.model = model
        self.statistics = statistics
        self.artifact_identity = artifact_identity
        self.model.eval()

    def predict(self, observation, deterministic: bool = True,
                action_masks=None):
        import torch
        values = np.asarray(observation, dtype=np.float32)
        masks = np.asarray(action_masks, dtype=bool) if action_masks is not None else None
        if values.ndim == 1:
            values = values[None, :]
            if masks is not None and masks.ndim == 1:
                masks = masks[None, :]
            single = True
        elif values.ndim == 2:
            single = False
        else:
            raise ValueError('observation must be one observation or a batch')
        if masks is None or masks.shape != (len(values), ADVANCE_ACTION + 1):
            raise ValueError('structured imitation requires matching action masks')
        selected = []
        with torch.no_grad():
            for observation_row, mask_row in zip(values, masks):
                indices, local = extract_valid_action_features(observation_row, mask_row)
                state = extract_state_features(observation_row)[None, :]
                state, local = normalize_features(state, local, self.statistics)
                offsets = torch.tensor([0, len(indices)], dtype=torch.int64)
                logits = self.model(torch.from_numpy(state), torch.from_numpy(local), offsets)
                if deterministic:
                    position = int(torch.argmax(logits).item())
                else:
                    position = int(torch.distributions.Categorical(logits=logits).sample().item())
                selected.append(int(indices[position]))
        actions = np.asarray(selected, dtype=np.int64)
        return (int(actions[0]) if single else actions), None

    def close(self) -> None:
        return None


def load_imitation_policy(output_dir: Path, provider_factory: Optional[Any] = None,
                          scenario_factory: Optional[Any] = None
                          ) -> StructuredImitationPolicy:
    import torch
    output = Path(output_dir)
    try:
        metadata = json.loads((output / 'policy-metadata.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('cannot load imitation policy metadata') from exc
    if (metadata.get('schema_version') != POLICY_ARTIFACT_SCHEMA_VERSION
            or metadata.get('algorithm') != IMITATION_ALGORITHM
            or metadata.get('model_version') != IMITATION_MODEL_VERSION):
        raise ValueError('imitation policy artifact schema or algorithm mismatch')
    if (metadata.get('feature_schema_checksum') != feature_schema_checksum()
            or metadata.get('observation_layout_version') != OBSERVATION_LAYOUT_VERSION
            or metadata.get('observation_layout_checksum')
            != ObservationLayout.build().checksum):
        raise ValueError('imitation policy feature/observation identity mismatch')
    training_pool = metadata.get('training_pool', {})
    try:
        pool_path = Path(training_pool['root'])
        if not pool_path.is_absolute():
            pool_path = REPOSITORY_ROOT / pool_path
        pool = load_scenario_pool(pool_path)
    except (KeyError, ValueError, OSError) as exc:
        raise ValueError('cannot verify imitation policy training pool') from exc
    if (pool.manifest['manifest_checksum'] != training_pool.get('manifest_checksum')
            or pool.manifest['release_id'] != training_pool.get('release_id')):
        raise ValueError('imitation policy training-pool identity mismatch')
    if provider_factory is not None:
        provider = provider_factory()
        recorded_provider = metadata.get('provider', {})
        if (recorded_provider.get('identity') != provider.identity
                or recorded_provider.get('version') != provider.version
                or recorded_provider.get('configuration_identity')
                != getattr(provider, 'config_identity', None)):
            raise ValueError('imitation policy provider identity mismatch')
    if scenario_factory is not None:
        generator = scenario_factory()
        provenance = getattr(generator, 'provenance', None)
        if provenance is not None:
            if (provenance.get('manifest_checksum')
                    != metadata.get('training_pool', {}).get('manifest_checksum')):
                raise ValueError('imitation policy training-pool identity mismatch')
        elif metadata.get('generator', {}).get('version') != getattr(
                generator, 'version', None):
            raise ValueError('imitation policy generator identity mismatch')
    recorded_dependencies = metadata.get('dependencies', {})
    current_dependencies = {name: importlib.metadata.version(name)
                            for name in ('numpy', 'torch', 'gymnasium')}
    if recorded_dependencies != current_dependencies:
        raise ValueError('imitation policy dependency identity mismatch')
    model_path = output / metadata.get('model_file', '')
    normalization_path = output / metadata.get('normalization_file', '')
    if (_sha256_file(model_path) != metadata.get('model_sha256')
            or _sha256_file(normalization_path)
            != metadata.get('normalization_sha256')):
        raise ValueError('imitation policy artifact checksum mismatch')
    normalization = np.load(normalization_path, allow_pickle=False)
    statistics = {key: np.asarray(normalization[key], dtype=np.float32)
                  for key in ('state_mean', 'state_std', 'action_mean', 'action_std')}
    if (statistics['state_mean'].shape != (STATE_FEATURE_COUNT,)
            or statistics['action_mean'].shape != (ACTION_FEATURE_COUNT - 3,)):
        raise ValueError('imitation normalization shape mismatch')
    model = StructuredActionScorer()
    model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    return StructuredImitationPolicy(
        model, statistics, str(metadata.get('artifact_identity', 'unknown')))


def diagnostic_rollout(policy: Any, spec: EpisodeSpec, provider_factory: Any,
                       teacher_actions: Optional[Mapping[str, Sequence[int]]] = None
                       ) -> Mapping[str, Any]:
    """Roll out a student and return gate-ready safety/score evidence."""
    provider = provider_factory()
    teacher = OptimalFixedRankAssignmentPolicy().run(
        SimulationEngine(spec, provider_factory()))
    env = CentralizedInterceptionEnv(provider, episode_spec=spec)
    correct = decisions = invalid = 0
    try:
        observation, _ = env.reset()
        plan = teacher.plan
        while True:
            mask = env.action_masks().astype(bool)
            acceptable = _planned_actions(env, plan, mask)
            action, _ = policy.predict(observation, deterministic=True, action_masks=mask)
            action = int(np.asarray(action).reshape(-1)[0])
            decisions += 1
            correct += action in acceptable
            if not 0 <= action < len(mask) or not mask[action]:
                invalid += 1
                break
            observation, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                return {
                    'episode_id': spec.episode_id,
                    'decision_count': decisions,
                    'acceptable_action_agreement': correct / decisions,
                    'invalid_action_count': invalid,
                    'normal_termination': bool(terminated and not truncated
                                               and info['termination_reason']
                                               == 'all_threats_resolved'),
                    'constraint_violation': str(info['termination_reason']).startswith(
                        'constraint_violation:'),
                    'student_raw_score': info['raw_score'],
                    'teacher_raw_score': teacher.raw_score,
                    'identical_teacher_score': (info['raw_score'] is not None
                                                and math.isclose(
                                                    float(info['raw_score']),
                                                    float(teacher.raw_score),
                                                    rel_tol=0.0, abs_tol=1e-12)),
                }
        return {'episode_id': spec.episode_id, 'decision_count': decisions,
                'acceptable_action_agreement': correct / max(1, decisions),
                'invalid_action_count': invalid, 'normal_termination': False,
                'constraint_violation': True, 'student_raw_score': None,
                'teacher_raw_score': teacher.raw_score,
                'identical_teacher_score': False}
    finally:
        env.close()


def run_overfit_diagnostics(policy: Any, episodes: Sequence[EpisodeSpec],
                            provider_factory: Any, fixed_limit: int = 16
                            ) -> Mapping[str, Any]:
    if not episodes:
        raise ValueError('diagnostics require at least one training episode')
    selected = tuple(episodes[:fixed_limit])
    single = diagnostic_rollout(policy, selected[0], provider_factory)
    fixed = tuple(diagnostic_rollout(policy, spec, provider_factory)
                  for spec in selected)
    single_pass = bool(
        single['acceptable_action_agreement'] == 1.0
        and single['identical_teacher_score'] and single['normal_termination']
        and not single['constraint_violation'] and not single['invalid_action_count'])
    total_decisions = sum(row['decision_count'] for row in fixed)
    agreement = (sum(row['acceptable_action_agreement'] * row['decision_count']
                     for row in fixed) / total_decisions)
    fixed_pass = bool(
        agreement >= 0.95
        and all(row['normal_termination'] for row in fixed)
        and not any(row['constraint_violation'] for row in fixed)
        and not any(row['invalid_action_count'] for row in fixed))
    result = {'single_scenario': single, 'single_scenario_passed': single_pass,
              'fixed_scenario_count': len(fixed),
              'fixed_acceptable_action_agreement': agreement,
              'fixed_scenarios': fixed, 'fixed_scenario_gate_passed': fixed_pass,
              'passed': single_pass and fixed_pass}
    if not result['passed']:
        raise RuntimeError(
            'behavior-cloning overfit diagnostics failed; inspect feature extraction, '
            'masking, target construction, and model capacity')
    return result


class PrivilegedResidualExpert:
    """Exact residual labeler for student-visited simulator states.

    This teacher is privileged/offline: future scheduled threats are included.
    It is intended only for DAgger dataset labeling, never deployment.
    """

    identity = 'privileged-residual-fixed-rank/1'
    information_scope = 'clairvoyant/offline-current-state'

    def __init__(self):
        self._universe_cache: Dict[str, Any] = {}

    @staticmethod
    def _assessment_value(value: Any, key: str, default: Any = None) -> Any:
        return value.get(key, default) if isinstance(value, Mapping) \
            else getattr(value, key, default)

    def _options(self, env: CentralizedInterceptionEnv
                 ) -> Mapping[Tuple[str, str], Tuple[Tuple[float, str, int], ...]]:
        """Return surviving immutable-cost candidates for each residual pair."""
        engine = env.engine
        cache_key = canonical_episode_hash(engine.spec)
        universes = self._universe_cache.get(cache_key)
        if universes is None:
            universes = candidate_universes(engine.spec, engine.provider)
            self._universe_cache[cache_key] = universes
        options: Dict[Tuple[str, str], Tuple[Tuple[float, str, int], ...]] = {}
        for threat_id, runtime in engine.threats.items():
            if runtime.status == ThreatStatus.RESOLVED:
                continue
            assignment = engine.assignments.get(threat_id)
            if assignment is not None and assignment.status == AssignmentStatus.LOCKED:
                continue
            for interceptor_id in sorted(engine.interceptor_resources):
                if interceptor_id in engine.consumed_interceptors:
                    continue
                rows = []
                if runtime.status == ThreatStatus.SCHEDULED:
                    source = universes[threat_id][interceptor_id]
                    for index, (candidate, eligible, cost) in enumerate(source):
                        if eligible and candidate.lock_time_s + 1e-9 >= engine.current_time_s:
                            rows.append((float(cost),
                                         candidate.opportunity.opportunity_id, index))
                else:
                    universe_by_id = {
                        candidate.opportunity.opportunity_id: (eligible, cost)
                        for candidate, eligible, cost
                        in universes[threat_id][interceptor_id]}
                    for index, candidate in enumerate(runtime.candidates.get(
                            interceptor_id, ())):
                        eligible, cost = universe_by_id.get(
                            candidate.opportunity.opportunity_id, (False, None))
                        eligible = candidate.opportunity.reachable and eligible
                        if (eligible and type(cost) in (int, float)
                                and math.isfinite(cost)
                                and candidate.lock_time_s + 1e-9 >= engine.current_time_s):
                            rows.append((float(cost),
                                         candidate.opportunity.opportunity_id, index))
                if rows:
                    best_cost = min(row[0] for row in rows)
                    options[(threat_id, interceptor_id)] = tuple(
                        row for row in rows if math.isclose(
                            row[0], best_cost, rel_tol=0.0, abs_tol=1e-12))
        return options

    @staticmethod
    def _solve(threat_ids: Sequence[str], interceptor_ids: Sequence[str],
               options: Mapping[Tuple[str, str], Sequence[Tuple[float, str, int]]]
               ) -> Tuple[float, frozenset]:
        """Return optimal residual cost and all pair edges occurring in a tie."""
        from functools import lru_cache
        threats = tuple(sorted(threat_ids))
        interceptors = tuple(sorted(interceptor_ids))

        @lru_cache(maxsize=None)
        def visit(position: int, remaining: Tuple[str, ...]):
            if position == len(threats):
                return 0.0, frozenset()
            threat_id = threats[position]
            best = math.inf
            edges = frozenset()
            for interceptor_id in remaining:
                pair = options.get((threat_id, interceptor_id))
                if not pair:
                    continue
                tail_cost, tail_edges = visit(
                    position + 1,
                    tuple(item for item in remaining if item != interceptor_id))
                cost = pair[0][0] + tail_cost
                candidate_edges = tail_edges | {(threat_id, interceptor_id)}
                if cost < best - 1e-12:
                    best, edges = cost, candidate_edges
                elif math.isclose(cost, best, rel_tol=0.0, abs_tol=1e-12):
                    edges = edges | candidate_edges
            return best, edges

        result = visit(0, interceptors)
        if not math.isfinite(result[0]):
            raise ValueError('no exact residual completion exists')
        return result

    def acceptable_actions(self, env: CentralizedInterceptionEnv) -> Tuple[int, ...]:
        if env.engine is None or env.engine.terminated or env.engine.truncated:
            raise ValueError('residual expert requires a live simulator state')
        _assert_exact_provider(env.provider)
        engine = env.engine
        mask = env.action_masks().astype(bool)
        options = self._options(env)
        threats = [threat_id for threat_id, runtime in engine.threats.items()
                   if runtime.status != ThreatStatus.RESOLVED
                   and not (threat_id in engine.assignments
                            and engine.assignments[threat_id].status
                            == AssignmentStatus.LOCKED)]
        interceptors = [value for value in engine.interceptor_resources
                        if value not in engine.consumed_interceptors]
        optimum, _ = self._solve(threats, interceptors, options)

        tentative = [(threat_id, assignment)
                     for threat_id, assignment in sorted(engine.assignments.items())
                     if assignment.status == AssignmentStatus.TENTATIVE]
        inconsistent = []
        for threat_id, assignment in tentative:
            pair_options = options.get((threat_id, assignment.interceptor_id), ())
            selected = next((row for row in pair_options
                             if row[1] == assignment.candidate.opportunity.opportunity_id),
                            None)
            if selected is None:
                inconsistent.append(threat_id)
                continue
            remaining_threats = [item for item in threats if item != threat_id]
            remaining_interceptors = [item for item in interceptors
                                      if item != assignment.interceptor_id]
            try:
                forced_tail, _ = self._solve(
                    remaining_threats, remaining_interceptors, options)
                forced_cost = selected[0] + forced_tail
            except ValueError:
                forced_cost = math.inf
            if not math.isclose(forced_cost, optimum,
                                rel_tol=0.0, abs_tol=1e-12):
                inconsistent.append(threat_id)
        if tentative and not inconsistent:
            forced_cost = 0.0
            forced_threats = set()
            forced_interceptors = set()
            for threat_id, assignment in tentative:
                selected = next(row for row in options[
                    (threat_id, assignment.interceptor_id)]
                                if row[1]
                                == assignment.candidate.opportunity.opportunity_id)
                forced_cost += selected[0]
                forced_threats.add(threat_id)
                forced_interceptors.add(assignment.interceptor_id)
            try:
                tail, _ = self._solve(
                    [item for item in threats if item not in forced_threats],
                    [item for item in interceptors
                     if item not in forced_interceptors], options)
                forced_cost += tail
            except ValueError:
                forced_cost = math.inf
            if not math.isclose(forced_cost, optimum,
                                rel_tol=0.0, abs_tol=1e-12):
                # Each edge is individually compatible with an optimum but the
                # tentative set is not. Any cancellation restores feasibility;
                # expose all currently cancellable choices as tied targets.
                inconsistent.extend(threat_id for threat_id, _ in tentative)
        cancellations = []
        for threat_id in inconsistent:
            action = env.cancel_action(env.threat_slots.index(threat_id))
            if mask[action]:
                cancellations.append(action)
        if cancellations:
            return tuple(sorted(cancellations))

        fixed_tentative_threats = {item[0] for item in tentative}
        fixed_tentative_interceptors = {item[1].interceptor_id for item in tentative}
        residual_threats = [item for item in threats
                            if item not in fixed_tentative_threats]
        residual_interceptors = [item for item in interceptors
                                 if item not in fixed_tentative_interceptors]
        _, optimal_edges = self._solve(
            residual_threats, residual_interceptors, options)
        actions = []
        visible = set(engine.visible_threat_ids())
        for threat_id, interceptor_id in sorted(optimal_edges):
            if threat_id not in visible or threat_id in engine.assignments:
                continue
            threat_slot = env.threat_slots.index(threat_id)
            interceptor_slot = env.interceptor_slots.index(interceptor_id)
            for _, opportunity_id, candidate_slot in options[
                    (threat_id, interceptor_id)]:
                action = env.encode_assignment_action(
                    threat_slot, interceptor_slot, candidate_slot)
                if mask[action]:
                    actions.append(action)
        if actions:
            return tuple(sorted(set(actions)))
        if mask[ADVANCE_ACTION]:
            return (ADVANCE_ACTION,)
        raise ValueError('no valid residual expert action exists')


def observation_mask_hash(observation: np.ndarray, action_mask: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(np.asarray(observation, dtype='<f4').tobytes())
    digest.update(np.asarray(action_mask, dtype=np.uint8).tobytes())
    return 'sha256:' + digest.hexdigest()


def collect_dagger_round(policy: Any, base_dataset_dir: Path, pool_path: Path,
                         output_dir: Path, provider_factory: Any,
                         round_number: int, episode_limit: Optional[int] = None
                         ) -> Mapping[str, Any]:
    """Aggregate residual-expert labels from student-visited training states."""
    if type(round_number) is not int or not 1 <= round_number <= 3:
        raise ValueError('DAgger round number must be between one and three')
    base = load_demonstrations(base_dataset_dir)
    pool = load_scenario_pool(pool_path)
    if (pool.manifest['dataset_role'] != 'development-training'
            or pool.manifest['manifest_checksum']
            != base.manifest['source_pool']['manifest_checksum']):
        raise ValueError('DAgger pool does not match the original training pool')
    records = pool.records if episode_limit is None else pool.records[:episode_limit]
    family_split = base.manifest['family_split']
    expert = PrivilegedResidualExpert()
    visited: Dict[str, Dict[str, Any]] = {}
    rollout_rows = []
    impossible_residual_states = 0
    for episode_index, record in enumerate(records):
        spec = pool.load(record['record_id'])
        env = CentralizedInterceptionEnv(
            provider_factory(), episode_spec=spec,
            policy_version=getattr(policy, 'model_version', 'unknown'))
        episode_decisions = 0
        try:
            observation, _ = env.reset()
            while True:
                mask = env.action_masks().astype(bool)
                try:
                    acceptable = expert.acceptable_actions(env)
                except ValueError as exc:
                    if 'residual' not in str(exc):
                        raise
                    impossible_residual_states += 1
                else:
                    digest = observation_mask_hash(observation, mask)
                    indices, local = extract_valid_action_features(observation, mask)
                    targets = np.isin(indices, np.asarray(acceptable, dtype=np.int64))
                    if not np.any(targets):
                        raise ValueError('residual expert target is not currently valid')
                    existing = visited.get(digest)
                    if existing is None:
                        visited[digest] = {
                            'state': extract_state_features(observation),
                            'indices': indices, 'local': local, 'targets': targets,
                            'episode_index': episode_index,
                            'split_label': (1 if family_split[record['family_id']]
                                            == 'internal-validation' else 0),
                        }
                    else:
                        if not np.array_equal(existing['indices'], indices):
                            raise ValueError('observation-mask hash collision')
                        existing['targets'] = np.logical_or(existing['targets'], targets)
                prediction = policy.predict(
                    observation, deterministic=True, action_masks=mask)
                action = prediction[0] if isinstance(prediction, tuple) else prediction
                action = int(np.asarray(action).reshape(-1)[0])
                if not 0 <= action < len(mask) or not mask[action]:
                    raise ValueError('student selected an invalid action during DAgger')
                observation, _, terminated, truncated, info = env.step(action)
                episode_decisions += 1
                if terminated or truncated:
                    rollout_rows.append({
                        'record_id': record['record_id'],
                        'decision_count': episode_decisions,
                        'termination_reason': info['termination_reason'],
                        'constraint_violation': str(info['termination_reason']).startswith(
                            'constraint_violation:'),
                    })
                    break
        finally:
            env.close()

    states = [base.state_features]
    locals_ = [base.action_features]
    indices_ = [base.action_indices]
    targets_ = [base.acceptable_targets]
    episode_indices_ = [base.decision_episode_indices]
    split_labels_ = [base.split_labels]
    offsets = base.action_offsets.tolist()
    for row in visited.values():
        states.append(row['state'][None, :])
        locals_.append(row['local'])
        indices_.append(row['indices'])
        targets_.append(row['targets'])
        episode_indices_.append(np.asarray([row['episode_index']], dtype=np.int64))
        split_labels_.append(np.asarray([row['split_label']], dtype=np.int8))
        offsets.append(offsets[-1] + len(row['indices']))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'manifest.json').exists():
        raise ValueError('DAgger output already contains a manifest')
    shard_path = output / 'shard-00000.npz'
    _write_npz_deterministic(
        shard_path,
        state_features=np.concatenate(states).astype(np.float32),
        action_offsets=np.asarray(offsets, dtype=np.int64),
        action_features=np.concatenate(locals_).astype(np.float32),
        action_indices=np.concatenate(indices_).astype(np.int64),
        acceptable_targets=np.concatenate(targets_).astype(np.bool_),
        decision_episode_indices=np.concatenate(episode_indices_).astype(np.int64),
        split_labels=np.concatenate(split_labels_).astype(np.int8))
    raw = shard_path.read_bytes()
    manifest = dict(base.manifest)
    manifest.update({
        'dataset_checksum': _sha256_bytes(raw),
        'decision_count': base.decision_count() + len(visited),
        'valid_action_count': len(np.concatenate(indices_)),
        'shards': [{
            'path': shard_path.name, 'sha256': _sha256_bytes(raw),
            'episode_start': 0, 'episode_count': len(records),
            'decision_count': base.decision_count() + len(visited),
            'valid_action_count': len(np.concatenate(indices_)),
        }],
        'dagger': {
            'round': round_number,
            'base_dataset_checksum': base.manifest['dataset_checksum'],
            'student_model_version': getattr(policy, 'model_version', 'unknown'),
            'student_artifact_identity': getattr(policy, 'artifact_identity', 'unknown'),
            'residual_teacher_identity': expert.identity,
            'residual_teacher_scope': expert.information_scope,
            'rollout_episode_count': len(records),
            'visited_state_count': sum(row['decision_count'] for row in rollout_rows),
            'deduplicated_state_count': len(visited),
            'impossible_residual_state_count': impossible_residual_states,
            'rollouts': rollout_rows,
        },
    })
    (output / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + '\n',
        encoding='utf-8')
    # Re-load before returning so checksum, ragged offsets, and target unions are
    # checked exactly as they will be during fine-tuning.
    load_demonstrations(output)
    return manifest


def train_with_conditional_dagger(
        dataset_dir: Path, pool_path: Path, output_dir: Path,
        validation_episodes: Sequence[EpisodeSpec], provider_factory: Any,
        seed: int = 7, max_dagger_rounds: int = 3,
        batch_size: int = 128, max_epochs: int = 100,
        patience: int = 10, diagnostic_limit: int = 16) -> Mapping[str, Any]:
    """Train BC, validate once, then run up to three DAgger rounds if needed.

    This API deliberately accepts exactly the 64-case frozen validation suite,
    not held-out data.  Its promotion record freezes the selected artifact
    identity before a separate held-out evaluation can be started.
    """
    from .evaluation import (behavior_cloning_acceptance_evidence,
                             evaluate_model, summarize_comparison)
    if len(validation_episodes) != 64:
        raise ValueError('conditional DAgger requires all 64 frozen validation episodes')
    from backend.simulation import load_scenario_manifest
    frozen_manifest = load_scenario_manifest()
    expected_hashes = {
        row['canonical_episode_hash'] for row in frozen_manifest.entries
        if row['split'] == 'validation'}
    actual_hashes = {canonical_episode_hash(spec) for spec in validation_episodes}
    if actual_hashes != expected_hashes:
        raise ValueError('conditional DAgger received a non-validation or incomplete suite')
    if type(max_dagger_rounds) is not int or not 0 <= max_dagger_rounds <= 3:
        raise ValueError('max_dagger_rounds must be between zero and three')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    current_dataset = Path(dataset_dir)
    previous_artifact: Optional[Path] = None
    rounds = []
    final_identity = None
    selected_artifact = None
    for round_number in range(max_dagger_rounds + 1):
        artifact_dir = output / ('bc-artifact' if round_number == 0
                                 else 'dagger-%d-artifact' % round_number)
        train_structured_behavior_cloning(
            current_dataset, artifact_dir, seed=seed,
            learning_rate=(1e-3 if round_number == 0 else 3e-4),
            batch_size=batch_size, max_epochs=max_epochs, patience=patience,
            initial_artifact_dir=previous_artifact,
            provider_factory=provider_factory,
            diagnostic_limit=diagnostic_limit,
            require_diagnostics=True)
        policy = load_imitation_policy(
            artifact_dir, provider_factory=provider_factory)
        report_path = output / ('bc-validation.json' if round_number == 0
                                else 'dagger-%d-validation.json' % round_number)
        try:
            evaluated = evaluate_model(
                policy, episode_specs=tuple(validation_episodes),
                provider_factory=provider_factory, report_path=report_path)
            summary = summarize_comparison(evaluated)
            gates = behavior_cloning_acceptance_evidence(summary)
            row = {
                'round': round_number,
                'algorithm': ('behavior-cloning' if round_number == 0 else 'DAgger'),
                'artifact_dir': str(artifact_dir.resolve()),
                'artifact_identity': policy.artifact_identity,
                'dataset_checksum': load_demonstrations(
                    current_dataset).manifest['dataset_checksum'],
                'validation_report': str(report_path.resolve()),
                'summary': asdict(summary), 'acceptance_gates': gates,
                'passed': all(gates.values()),
            }
            rounds.append(row)
            if row['passed']:
                final_identity = policy.artifact_identity
                selected_artifact = str(artifact_dir.resolve())
                break
            if round_number == max_dagger_rounds:
                break
            next_dataset = output / ('dagger-%d-dataset' % (round_number + 1))
            if (next_dataset / 'manifest.json').exists():
                resumed = load_demonstrations(next_dataset)
                dagger_metadata = resumed.manifest.get('dagger', {})
                base_checksum = load_demonstrations(
                    current_dataset).manifest['dataset_checksum']
                expected = {
                    'round': round_number + 1,
                    'base_dataset_checksum': base_checksum,
                    'student_artifact_identity': policy.artifact_identity,
                }
                actual = {key: dagger_metadata.get(key) for key in expected}
                if actual != expected:
                    raise ValueError(
                        'existing DAgger dataset does not match the current '
                        'round, base dataset, and student artifact')
            else:
                collect_dagger_round(
                    policy, current_dataset, pool_path, next_dataset,
                    provider_factory, round_number + 1)
            current_dataset = next_dataset
            previous_artifact = artifact_dir
        finally:
            policy.close()
    promoted = final_identity is not None
    promotion = {
        'schema_version': 'imitation-promotion/1',
        'status': ('promoted' if promoted else 'experimental-not-promoted'),
        'promoted': promoted,
        'final_artifact_identity': (final_identity if promoted
                                    else 'naive-launch-on-detection/1'),
        'selected_artifact_dir': selected_artifact,
        'deterministic_fallback': (None if promoted
                                   else 'naive-launch-on-detection/1'),
        'teacher_disclosure': 'clairvoyant/offline fixed-rank optimizer',
        'held_out_suite_opened': False,
        'rounds': rounds,
    }
    (output / 'promotion.json').write_text(
        json.dumps(promotion, indent=2, sort_keys=True, allow_nan=False) + '\n',
        encoding='utf-8')
    return promotion
