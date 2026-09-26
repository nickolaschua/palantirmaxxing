"""Versioned, resumable training pools for Singapore v2 scenarios."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from backend.domain import InterceptorState, ThreatState

from .models import EpisodeSpec, InterceptorResource, ScheduledThreat
from .scenario_distribution import (
    SingaporeScenarioV2Generator, load_scenario_distribution)
from .singapore_provider import SingaporeConsequenceProvider
from .singapore_scenario import canonical_episode_hash, episode_to_dict
from .suites import TRAINING_SEED_OFFSET


SCENARIO_POOL_SCHEMA_VERSION = 'singapore-scenario-pool/1'
SCENARIO_POOL_RECORD_FORMAT = 'one canonical simulation episode JSON per file'
SCENARIO_POOL_SELECTOR_VERSION = 'scenario-pool-selector/1'
TRAINING_POOL_PROFILE_WEIGHTS = (
    ('warmup', 10),
    ('balanced', 18),
    ('full-standard', 18),
    ('burst-contention', 18),
    ('low-slack', 18),
    ('consequence-contrast', 18),
)
_RELEASE_ID = re.compile(r'^[a-z0-9][a-z0-9._-]{2,63}$', re.ASCII)
_SHA256 = re.compile(r'^sha256:[0-9a-f]{64}$', re.ASCII)
_MANIFEST_KEYS = (
    'artifact_count', 'artifact_format', 'coverage', 'dataset_role',
    'dependencies', 'distribution_checksum', 'distribution_version',
    'generation_failures', 'generator_configuration_checksum', 'generator_version',
    'manifest_checksum', 'provider_identity', 'record_count', 'records',
    'release_id', 'schema_version', 'seed_partition', 'source_files',
    'source_revision', 'source_tree_dirty')
_RECORD_KEYS = (
    'artifact_sha256', 'canonical_episode_hash', 'content_hash', 'family_id',
    'generation_attempt_count', 'index', 'profile', 'record_id',
    'rejected_attempt_count', 'rejected_attempts', 'relative_path',
    'requested_seed', 'realized_seed', 'split')
_EPISODE_KEYS = (
    'candidate_count', 'episode_id', 'interceptors', 'metadata', 'schema_version',
    'seed', 'threats')


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False).encode('utf-8')


def _pretty_json(value: Any) -> bytes:
    return (json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + '\n').encode('utf-8')


def _sha256(value: bytes) -> str:
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _strict_keys(value: Any, expected: Sequence[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    unknown = set(value) - set(expected)
    missing = set(expected) - set(value)
    if unknown:
        raise ValueError(label + ' has unknown fields: ' + ', '.join(sorted(unknown)))
    if missing:
        raise ValueError(label + ' is missing fields: ' + ', '.join(sorted(missing)))
    return value


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)


def validate_pool_release_id(value: Any) -> str:
    if type(value) is not str or _RELEASE_ID.fullmatch(value) is None:
        raise ValueError('pool release ID must be 3-64 lowercase ASCII characters')
    return value


def _profile_counts(count: int) -> Mapping[str, int]:
    if type(count) is not int or count <= 0:
        raise ValueError('scenario count must be a positive integer')
    total_weight = sum(weight for _, weight in TRAINING_POOL_PROFILE_WEIGHTS)
    floors = {
        profile: count * weight // total_weight
        for profile, weight in TRAINING_POOL_PROFILE_WEIGHTS}
    remaining = count - sum(floors.values())
    remainders = sorted(
        TRAINING_POOL_PROFILE_WEIGHTS,
        key=lambda item: (-(count * item[1] % total_weight), item[0]))
    for profile, _ in remainders[:remaining]:
        floors[profile] += 1
    return floors


def training_pool_plan(
        count: int = 512,
        seed_start: int = TRAINING_SEED_OFFSET) -> Tuple[Mapping[str, Any], ...]:
    """Return a deterministic, profile-stratified development-training plan."""
    if type(seed_start) is not int or seed_start < TRAINING_SEED_OFFSET:
        raise ValueError('training pool seed start is outside the training partition')
    counts = _profile_counts(count)
    # Midpoint ranks interleave profiles while preserving the exact quotas.
    ranked = sorted(
        ((index + 0.5) / profile_count, profile, index)
        for profile, profile_count in counts.items()
        for index in range(profile_count))
    return tuple({
        'index': index,
        'seed': seed_start + index,
        'profile': profile,
        'split': 'development-training',
        'family_id': 'sg2-profile:' + profile,
    } for index, (_, profile, _) in enumerate(ranked))


def episode_from_dict(value: Any) -> EpisodeSpec:
    """Load the canonical episode representation with strict structural checks."""
    root = _strict_keys(value, _EPISODE_KEYS, 'scenario episode')
    if not isinstance(root['threats'], list) or not isinstance(root['interceptors'], list):
        raise ValueError('scenario episode threats and interceptors must be arrays')
    threats = []
    for index, value in enumerate(root['threats']):
        row = _strict_keys(
            value, ('detection_time_s', 'metadata', 'state'),
            'scenario threat %d' % index)
        state = _strict_keys(row['state'], tuple(ThreatState.__dataclass_fields__),
                             'scenario threat state %d' % index)
        if not isinstance(row['metadata'], dict):
            raise ValueError('scenario threat metadata must be an object')
        threats.append(ScheduledThreat(
            row['detection_time_s'], ThreatState(**state), row['metadata']))
    interceptors = []
    for index, value in enumerate(root['interceptors']):
        row = _strict_keys(
            value, ('metadata', 'state'), 'scenario interceptor %d' % index)
        state = _strict_keys(
            row['state'], tuple(InterceptorState.__dataclass_fields__),
            'scenario interceptor state %d' % index)
        if not isinstance(row['metadata'], dict):
            raise ValueError('scenario interceptor metadata must be an object')
        interceptors.append(InterceptorResource(
            InterceptorState(**state), row['metadata']))
    if not isinstance(root['metadata'], dict):
        raise ValueError('scenario episode metadata must be an object')
    return EpisodeSpec(
        episode_id=root['episode_id'], seed=root['seed'],
        threats=tuple(threats), interceptors=tuple(interceptors),
        candidate_count=root['candidate_count'], metadata=root['metadata'],
        schema_version=root['schema_version'])


def scenario_content_hash(spec: EpisodeSpec) -> str:
    """Hash simulator inputs without record IDs, seeds, or release provenance."""
    episode = episode_to_dict(spec)
    threat_incidental = {
        'generation_attempt', 'threat_retry_attempt', 'generator', 'synthetic'}
    interceptor_incidental = {
        'generation_attempt', 'generator', 'layout', 'synthetic'}
    threats = [{
        **row,
        'metadata': {
            key: value for key, value in row['metadata'].items()
            if key not in threat_incidental},
    } for row in episode['threats']]
    interceptors = [{
        **row,
        'metadata': {
            key: value for key, value in row['metadata'].items()
            if key not in interceptor_incidental},
    } for row in episode['interceptors']]
    substantive = {
        'schema_version': episode['schema_version'],
        'candidate_count': episode['candidate_count'],
        'threats': threats,
        'interceptors': interceptors,
    }
    return _sha256(_canonical_json(substantive))


def _safe_artifact_path(root: Path, relative_path: Any) -> Path:
    if type(relative_path) is not str or not re.fullmatch(
            r'episodes/[0-9]{6}\.json', relative_path, re.ASCII):
        raise ValueError('scenario pool artifact path is not canonical')
    resolved = (root / relative_path).resolve()
    if os.path.commonpath((str(root.resolve()), str(resolved))) != str(root.resolve()):
        raise ValueError('scenario pool artifact path escapes the release')
    return resolved


def _manifest_checksum(document: Mapping[str, Any]) -> str:
    content = dict(document)
    content.pop('manifest_checksum', None)
    return _sha256(_canonical_json(content))


def _validate_manifest(document: Any) -> Mapping[str, Any]:
    root = _strict_keys(document, _MANIFEST_KEYS, 'scenario pool manifest')
    if root['schema_version'] != SCENARIO_POOL_SCHEMA_VERSION:
        raise ValueError('scenario pool schema version mismatch')
    validate_pool_release_id(root['release_id'])
    if root['dataset_role'] != 'development-training':
        raise ValueError('scenario pool dataset role mismatch')
    if root['artifact_format'] != SCENARIO_POOL_RECORD_FORMAT:
        raise ValueError('scenario pool artifact format mismatch')
    if (type(root['record_count']) is not int or root['record_count'] <= 0
            or root['artifact_count'] != root['record_count']
            or not isinstance(root['records'], list)
            or len(root['records']) != root['record_count']):
        raise ValueError('scenario pool record count mismatch')
    if root['manifest_checksum'] != _manifest_checksum(root):
        raise ValueError('scenario pool manifest checksum mismatch')
    for key in ('distribution_checksum', 'generator_configuration_checksum'):
        if not _is_sha256(root[key]):
            raise ValueError('scenario pool %s is invalid' % key)
    for key in ('distribution_version', 'generator_version', 'provider_identity',
                'source_revision'):
        if type(root[key]) is not str or not root[key]:
            raise ValueError('scenario pool %s must be a nonempty string' % key)
    partition = _strict_keys(
        root['seed_partition'], ('end_exclusive', 'start_inclusive'),
        'scenario pool seed partition')
    if (type(partition['start_inclusive']) is not int
            or type(partition['end_exclusive']) is not int
            or partition['start_inclusive'] < TRAINING_SEED_OFFSET
            or partition['end_exclusive'] - partition['start_inclusive']
            != root['record_count']):
        raise ValueError('scenario pool seed partition is invalid')
    if not isinstance(root['coverage'], dict) or not isinstance(root['dependencies'], dict) \
            or not isinstance(root['source_files'], dict):
        raise ValueError('scenario pool provenance and coverage must be objects')
    if not isinstance(root['generation_failures'], list):
        raise ValueError('scenario pool generation failures must be an array')
    for path, digest in root['source_files'].items():
        if type(path) is not str or not path or not _is_sha256(digest):
            raise ValueError('scenario pool source file provenance is invalid')
    if any(type(key) is not str or type(value) is not str
           for key, value in root['dependencies'].items()):
        raise ValueError('scenario pool dependency provenance is invalid')
    for position, value in enumerate(root['generation_failures']):
        row = _strict_keys(
            value, ('error', 'error_type', 'index', 'profile', 'seed'),
            'scenario pool generation failure %d' % position)
        if (type(row['index']) is not int or type(row['seed']) is not int
                or type(row['profile']) is not str
                or type(row['error_type']) is not str
                or type(row['error']) is not str):
            raise ValueError('scenario pool generation failure is invalid')
    if type(root['source_tree_dirty']) is not bool:
        raise ValueError('scenario pool source_tree_dirty must be a boolean')
    seen_ids, seen_hashes, seen_content, seen_seeds, seen_paths = (
        set(), set(), set(), set(), set())
    profiles = {profile for profile, _ in TRAINING_POOL_PROFILE_WEIGHTS}
    for position, value in enumerate(root['records']):
        row = _strict_keys(value, _RECORD_KEYS, 'scenario pool record %d' % position)
        expected_id = 'sg2pool:%s:%06d' % (root['release_id'], position)
        expected_path = 'episodes/%06d.json' % position
        if (row['index'] != position or row['record_id'] != expected_id
                or row['relative_path'] != expected_path
                or row['requested_seed'] != partition['start_inclusive'] + position
                or row['realized_seed'] != row['requested_seed']
                or row['split'] != 'development-training'
                or row['profile'] not in profiles
                or row['family_id'] != 'sg2-profile:' + row['profile']):
            raise ValueError('scenario pool record differs from its frozen plan')
        if (not _is_sha256(row['canonical_episode_hash'])
                or not _is_sha256(row['content_hash'])
                or not _is_sha256(row['artifact_sha256'])):
            raise ValueError('scenario pool record checksum is invalid')
        if (type(row['generation_attempt_count']) is not int
                or row['generation_attempt_count'] <= 0
                or type(row['rejected_attempt_count']) is not int
                or row['rejected_attempt_count'] < 0
                or row['generation_attempt_count'] != row['rejected_attempt_count'] + 1
                or not isinstance(row['rejected_attempts'], list)
                or len(row['rejected_attempts']) != row['rejected_attempt_count']):
            raise ValueError('scenario pool retry provenance is invalid')
        for value, collection in (
                (row['record_id'], seen_ids),
                (row['canonical_episode_hash'], seen_hashes),
                (row['content_hash'], seen_content),
                (row['requested_seed'], seen_seeds),
                (row['relative_path'], seen_paths)):
            if value in collection:
                raise ValueError('scenario pool contains a duplicate identity')
            collection.add(value)
    coverage = root['coverage']
    if coverage.get('profile_counts') != dict(sorted(Counter(
            row['profile'] for row in root['records']).items())):
        raise ValueError('scenario pool profile coverage does not match records')
    if (coverage.get('distinct_canonical_episode_hashes') != len(seen_hashes)
            or coverage.get('distinct_content_hashes') != len(seen_content)):
        raise ValueError('scenario pool distinct-hash coverage does not match records')
    return root


@dataclass(frozen=True)
class ScenarioPool:
    root: Path
    manifest: Mapping[str, Any]
    entries_by_id: Mapping[str, Mapping[str, Any]]

    @property
    def records(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self.manifest['records'])

    def load(self, record_id: str) -> EpisodeSpec:
        entry = self.entries_by_id.get(record_id)
        if entry is None:
            raise KeyError('unknown scenario pool record')
        path = _safe_artifact_path(self.root, entry['relative_path'])
        try:
            raw = path.read_bytes()
            document = json.loads(
                raw, parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError('nonfinite episode value: ' + value)))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('cannot load scenario pool artifact') from exc
        if _sha256(raw) != entry['artifact_sha256']:
            raise ValueError('scenario pool artifact checksum mismatch')
        spec = episode_from_dict(document)
        if (spec.seed != entry['realized_seed']
                or spec.metadata.get('profile') != entry['profile']
                or canonical_episode_hash(spec) != entry['canonical_episode_hash']
                or scenario_content_hash(spec) != entry['content_hash']):
            raise ValueError('scenario pool artifact identity mismatch')
        return spec


class EpisodePoolScenarioGenerator:
    """In-memory deterministic selector over an immutable scenario release."""

    version = SCENARIO_POOL_SELECTOR_VERSION
    selects_pool_records = True

    def __init__(self, pool_path: Path, profile: Optional[str] = None,
                 limit: Optional[int] = None):
        if profile is not None and profile not in {
                value for value, _ in TRAINING_POOL_PROFILE_WEIGHTS}:
            raise ValueError('unknown training-pool profile')
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError('training-pool limit must be a positive integer')
        self.pool = load_scenario_pool(pool_path)
        records = tuple(
            row for row in self.pool.records
            if profile is None or row['profile'] == profile)
        if limit is not None:
            records = records[:limit]
        if not records:
            raise ValueError('training-pool selection is empty')
        self.records = records
        self.episodes = tuple(
            self.pool.load(row['record_id']) for row in self.records)
        self.profile = profile
        self.limit = limit
        selection = {
            'selector_version': self.version,
            'manifest_checksum': self.pool.manifest['manifest_checksum'],
            'record_ids': [row['record_id'] for row in self.records],
        }
        self.configuration_checksum = _sha256(_canonical_json(selection))
        digest = hashlib.sha256(
            (self.configuration_checksum + '|permutation').encode('utf-8')).digest()
        size = len(self.records)
        multiplier = max(1, int.from_bytes(digest[:8], 'big') % size)
        while math.gcd(multiplier, size) != 1:
            multiplier = (multiplier + 1) % size or 1
        self._multiplier = multiplier
        self._offset = int.from_bytes(digest[8:16], 'big') % size

    def record_index(self, selector_seed: int) -> int:
        if type(selector_seed) is not int or selector_seed < 0:
            raise ValueError('pool selector seed must be a nonnegative integer')
        return (self._multiplier * selector_seed + self._offset) % len(self.records)

    def generate(self, seed: int, **_ignored: Any) -> EpisodeSpec:
        return self.episodes[self.record_index(seed)]

    @property
    def provenance(self) -> Mapping[str, Any]:
        return {
            'selector_version': self.version,
            'selector_configuration_checksum': self.configuration_checksum,
            'release_id': self.pool.manifest['release_id'],
            'manifest_checksum': self.pool.manifest['manifest_checksum'],
            'record_count': len(self.records),
            'source_record_count': self.pool.manifest['record_count'],
            'profile_filter': self.profile,
            'limit': self.limit,
            'root': str(self.pool.root),
        }


@dataclass(frozen=True)
class EpisodePoolFactory:
    pool_path: str
    profile: Optional[str] = None
    limit: Optional[int] = None

    def __call__(self) -> EpisodePoolScenarioGenerator:
        return EpisodePoolScenarioGenerator(
            Path(self.pool_path), profile=self.profile, limit=self.limit)


def load_scenario_pool(path: Path) -> ScenarioPool:
    root = Path(path)
    manifest_path = root / 'manifest.json'
    try:
        document = json.loads(
            manifest_path.read_text(encoding='utf-8'),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError('nonfinite manifest value: ' + value)))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('cannot load scenario pool manifest') from exc
    manifest = _validate_manifest(document)
    return ScenarioPool(
        root.resolve(), manifest,
        {row['record_id']: row for row in manifest['records']})


def verify_scenario_pool(
        path: Path,
        generator: Optional[SingaporeScenarioV2Generator] = None,
        reproduce_all: bool = False) -> Mapping[str, Any]:
    pool = load_scenario_pool(path)
    for row in pool.records:
        pool.load(row['record_id'])
    reproduced = 0
    if generator is not None:
        if (generator.version != pool.manifest['generator_version']
                or generator.distribution.version
                != pool.manifest['distribution_version']
                or generator.distribution.checksum
                != pool.manifest['distribution_checksum']
                or generator.configuration_checksum
                != pool.manifest['generator_configuration_checksum']
                or generator._provider().identity
                != pool.manifest['provider_identity']):
            raise ValueError('scenario pool generator identity mismatch')
        selected = pool.records if reproduce_all else tuple(
            next(row for row in pool.records if row['profile'] == profile)
            for profile, _ in TRAINING_POOL_PROFILE_WEIGHTS
            if any(row['profile'] == profile for row in pool.records))
        initial_provider = generator._provider()
        catalog = getattr(initial_provider, 'catalog', None)
        for row in selected:
            if isinstance(initial_provider, SingaporeConsequenceProvider):
                generator.consequence_provider = SingaporeConsequenceProvider(
                    catalog=catalog, scenario_config=generator.config)
            regenerated = generator.generate(
                row['requested_seed'], row['profile'])
            if (canonical_episode_hash(regenerated)
                    != row['canonical_episode_hash']
                    or scenario_content_hash(regenerated) != row['content_hash']):
                raise ValueError('scenario pool deterministic reproduction mismatch')
            reproduced += 1
    return {
        'release_id': pool.manifest['release_id'],
        'record_count': len(pool.records),
        'manifest_checksum': pool.manifest['manifest_checksum'],
        'distinct_canonical_episode_hashes': len({
            row['canonical_episode_hash'] for row in pool.records}),
        'distinct_content_hashes': len({
            row['content_hash'] for row in pool.records}),
        'reproduced_records': reproduced,
        'status': 'verified',
    }


def _coverage(records: Sequence[Mapping[str, Any]],
              documents: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    profiles = Counter(row['profile'] for row in records)
    threats = Counter(len(document['threats']) for document in documents)
    interceptors = Counter(len(document['interceptors']) for document in documents)
    sectors = Counter(
        sector for document in documents
        for sector in document['metadata']['ingress_sectors'])
    cells = Counter(
        cell for document in documents
        for cell in document['metadata']['terminal_grid_cells'])
    joint = Counter(
        '%s|threats=%d|interceptors=%d' % (
            row['profile'], len(document['threats']), len(document['interceptors']))
        for row, document in zip(records, documents))
    attempts = [row['generation_attempt_count'] for row in records]
    return {
        'profile_counts': dict(sorted(profiles.items())),
        'threat_count_distribution': {
            str(key): value for key, value in sorted(threats.items())},
        'interceptor_count_distribution': {
            str(key): value for key, value in sorted(interceptors.items())},
        'profile_scale_joint_counts': dict(sorted(joint.items())),
        'ingress_detection_counts': {
            str(index): sectors[index] for index in range(8)},
        'terminal_grid_detection_counts': {
            str(index): cells[index] for index in range(16)},
        'generation_attempts': {
            'minimum': min(attempts), 'maximum': max(attempts),
            'total': sum(attempts),
            'rejected_total': sum(
                row['rejected_attempt_count'] for row in records)},
        'distinct_canonical_episode_hashes': len({
            row['canonical_episode_hash'] for row in records}),
        'distinct_content_hashes': len({
            row['content_hash'] for row in records}),
        'limitations': [
            'All records are synthetic development-training scenarios.',
            'Frozen validation, held-out, stress, oracle, and OOD suites are separate.',
            'Profile balance does not establish coverage outside the declared distribution.',
        ],
    }


_POOL_WORKER_GENERATOR: Optional[SingaporeScenarioV2Generator] = None
_POOL_WORKER_CATALOG: Any = None


def _initialize_pool_worker(distribution_path: str, checksum: str,
                            config: Any) -> None:
    global _POOL_WORKER_GENERATOR, _POOL_WORKER_CATALOG
    distribution = load_scenario_distribution(
        Path(distribution_path), expected_checksum=checksum)
    provider = SingaporeConsequenceProvider(scenario_config=config)
    _POOL_WORKER_CATALOG = provider.catalog
    _POOL_WORKER_GENERATOR = SingaporeScenarioV2Generator(
        distribution=distribution, config=config, consequence_provider=provider)


def _parallel_generate(row: Mapping[str, Any]) -> Mapping[str, Any]:
    if _POOL_WORKER_GENERATOR is None:
        raise RuntimeError('scenario pool worker was not initialized')
    _POOL_WORKER_GENERATOR.consequence_provider = SingaporeConsequenceProvider(
        catalog=_POOL_WORKER_CATALOG,
        scenario_config=_POOL_WORKER_GENERATOR.config)
    spec = _POOL_WORKER_GENERATOR.generate(row['seed'], row['profile'])
    return {'index': row['index'], 'episode': episode_to_dict(spec)}


def _record_from_document(
        release_id: str, row: Mapping[str, Any], document: Mapping[str, Any],
        output: Path) -> Mapping[str, Any]:
    spec = episode_from_dict(document)
    if spec.seed != row['seed'] or spec.metadata.get('profile') != row['profile']:
        raise ValueError('generated scenario does not match the pool plan')
    digest = canonical_episode_hash(spec)
    raw = _pretty_json(document)
    relative_path = 'episodes/%06d.json' % row['index']
    _atomic_write(output / relative_path, raw)
    return {
        'index': row['index'],
        'record_id': 'sg2pool:%s:%06d' % (release_id, row['index']),
        'split': row['split'],
        'family_id': row['family_id'],
        'profile': row['profile'],
        'requested_seed': row['seed'],
        'realized_seed': spec.seed,
        'relative_path': relative_path,
        'canonical_episode_hash': digest,
        'content_hash': scenario_content_hash(spec),
        'artifact_sha256': _sha256(raw),
        'generation_attempt_count': spec.metadata['generation_attempt_count'],
        'rejected_attempt_count': spec.metadata['rejected_attempt_count'],
        'rejected_attempts': list(spec.metadata['rejected_attempts']),
    }


def generate_scenario_pool(
        generator: SingaporeScenarioV2Generator,
        output_dir: Path,
        release_id: str,
        count: int = 512,
        seed_start: int = TRAINING_SEED_OFFSET,
        source_revision: str = 'unknown',
        source_tree_dirty: bool = True,
        source_files: Optional[Mapping[str, str]] = None,
        dependencies: Optional[Mapping[str, str]] = None,
        workers: Optional[int] = None,
        resume: bool = False) -> Mapping[str, Any]:
    """Generate and checkpoint an immutable development-training release."""
    release_id = validate_pool_release_id(release_id)
    if type(source_revision) is not str or not source_revision:
        raise ValueError('source revision must be a nonempty string')
    if type(source_tree_dirty) is not bool:
        raise ValueError('source_tree_dirty must be a boolean')
    if generator.eligibility_checker is not None:
        raise ValueError('pool generation requires the checked consequence provider')
    generator._provider()
    plan = training_pool_plan(count, seed_start)
    output = Path(output_dir)
    manifest_path = output / 'manifest.json'
    progress_path = output / 'progress.json'
    if manifest_path.is_file():
        if not resume:
            raise ValueError('scenario pool release already exists')
        return load_scenario_pool(output).manifest
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError('scenario pool output is not empty; use resume explicitly')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'episodes').mkdir(parents=True, exist_ok=True)
    identity = {
        'schema_version': SCENARIO_POOL_SCHEMA_VERSION,
        'release_id': release_id,
        'record_count': count,
        'seed_start': seed_start,
        'generator_version': generator.version,
        'distribution_version': generator.distribution.version,
        'distribution_checksum': generator.distribution.checksum,
        'generator_configuration_checksum': generator.configuration_checksum,
        'provider_identity': generator._provider().identity,
        'source_revision': source_revision,
        'source_tree_dirty': source_tree_dirty,
        'source_files': dict(sorted((source_files or {}).items())),
        'dependencies': dict(sorted((dependencies or {}).items())),
    }
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding='utf-8'))
        if progress.get('identity') != identity:
            raise ValueError('resume progress does not match the requested release')
    else:
        progress = {'identity': identity, 'status': 'in_progress',
                    'records': [], 'failures': []}
        _atomic_write(progress_path, _pretty_json(progress))
    records = list(progress['records'])
    if [row['index'] for row in records] != list(range(len(records))):
        raise ValueError('resume progress records are not a contiguous prefix')
    documents = []
    for entry in records:
        path = _safe_artifact_path(output, entry['relative_path'])
        raw = path.read_bytes()
        if _sha256(raw) != entry['artifact_sha256']:
            raise ValueError('resume artifact checksum mismatch')
        document = json.loads(raw)
        spec = episode_from_dict(document)
        if canonical_episode_hash(spec) != entry['canonical_episode_hash']:
            raise ValueError('resume artifact canonical hash mismatch')
        documents.append(document)
    missing = plan[len(records):]
    count_workers = min(6, os.cpu_count() or 1) if workers is None else workers
    if type(count_workers) is not int or count_workers <= 0:
        raise ValueError('pool worker count must be a positive integer')

    def save(result: Mapping[str, Any]) -> None:
        expected = plan[len(records)]
        if result['index'] != expected['index']:
            raise RuntimeError('parallel pool generation returned out of order')
        document = result['episode']
        record = _record_from_document(release_id, expected, document, output)
        if (record['canonical_episode_hash'] in {
                row['canonical_episode_hash'] for row in records}
                or record['content_hash'] in {
                    row['content_hash'] for row in records}):
            raise ValueError('duplicate canonical or substantive episode in training pool')
        records.append(record)
        documents.append(document)
        progress['records'] = records
        _atomic_write(progress_path, _pretty_json(progress))

    def record_failure(row: Mapping[str, Any], exc: BaseException) -> None:
        progress['failures'].append({
            'index': row['index'], 'seed': row['seed'],
            'profile': row['profile'], 'error_type': type(exc).__name__,
            'error': str(exc),
        })
        _atomic_write(progress_path, _pretty_json(progress))

    if count_workers == 1:
        initial_provider = generator._provider()
        catalog = getattr(initial_provider, 'catalog', None)
        for row in missing:
            try:
                if isinstance(initial_provider, SingaporeConsequenceProvider):
                    generator.consequence_provider = SingaporeConsequenceProvider(
                        catalog=catalog, scenario_config=generator.config)
                spec = generator.generate(row['seed'], row['profile'])
                save({'index': row['index'], 'episode': episode_to_dict(spec)})
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                record_failure(row, exc)
                raise
    elif missing:
        with ProcessPoolExecutor(
                max_workers=count_workers, initializer=_initialize_pool_worker,
                initargs=(generator.distribution.source_path,
                          generator.distribution.checksum,
                          generator.config)) as executor:
            futures = tuple(executor.submit(_parallel_generate, row)
                            for row in missing)
            for row, future in zip(missing, futures):
                try:
                    save(future.result())
                except KeyboardInterrupt:
                    for pending in futures:
                        pending.cancel()
                    raise
                except Exception as exc:
                    record_failure(row, exc)
                    for pending in futures:
                        pending.cancel()
                    raise
    document = {
        'schema_version': SCENARIO_POOL_SCHEMA_VERSION,
        'release_id': release_id,
        'dataset_role': 'development-training',
        'artifact_format': SCENARIO_POOL_RECORD_FORMAT,
        'record_count': len(records),
        'artifact_count': len(records),
        'seed_partition': {
            'start_inclusive': seed_start,
            'end_exclusive': seed_start + count,
        },
        'generator_version': identity['generator_version'],
        'distribution_version': identity['distribution_version'],
        'distribution_checksum': identity['distribution_checksum'],
        'generator_configuration_checksum': identity[
            'generator_configuration_checksum'],
        'provider_identity': identity['provider_identity'],
        'source_revision': source_revision,
        'source_tree_dirty': source_tree_dirty,
        'source_files': identity['source_files'],
        'dependencies': identity['dependencies'],
        'generation_failures': list(progress['failures']),
        'records': records,
        'coverage': _coverage(records, documents),
    }
    document['manifest_checksum'] = _manifest_checksum(document)
    _validate_manifest(document)
    _atomic_write(manifest_path, _pretty_json(document))
    progress_path.unlink(missing_ok=True)
    return document
