"""Immutable Singapore v2 scenario references and strict resolver."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .audit import AUDIT_SEED_START
from .scenario_distribution import (
    DEFAULT_DISTRIBUTION_PATH, SINGAPORE_DISTRIBUTION_VERSION,
    SINGAPORE_SCENARIO_V2_VERSION, SingaporeScenarioV2Generator,
    load_scenario_distribution)
from .singapore_provider import SingaporeConsequenceProvider
from .singapore_scenario import canonical_episode_hash
from .suites import (FROZEN_SPLIT_PROFILES, FROZEN_SPLIT_SEEDS,
                     ORACLE_CANDIDATES_PER_PAIR,
                     ORACLE_MAX_ACTION_SEQUENCES, ORACLE_MAX_INTERCEPTORS,
                     ORACLE_MAX_THREATS, ORACLE_SEEDS,
                     SUITE_MANIFEST_VERSION, TRAINING_SEED_OFFSET,
                     frozen_scenario_plan)


DEFAULT_SCENARIO_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / 'data' / 'scenarios' / 'rl' / 'suites.json')
MANIFEST_PROVIDER_IDENTITY = 'singapore-demo-v2'
SCENARIO_REF_PATTERN = re.compile(
    r'^sg2:(validation|held-out|stress|ood-geography|ood-cadence|assignment-reference):[0-9]{6}$',
    re.ASCII)
ENTRY_KEYS = (
    'canonical_episode_hash', 'distribution_checksum',
    'distribution_version', 'expected_feasible', 'generator_version',
    'index', 'profile', 'provider_identity', 'scenario_ref', 'seed', 'split')
TOP_LEVEL_KEYS = (
    'bounded_oracle', 'distribution_checksum', 'distribution_version',
    'entries', 'generator_version', 'provider_identity', 'schema_version',
    'training_seed_partition')


class ScenarioIdentityMismatch(ValueError):
    """A checked reference no longer regenerates its recorded scenario."""


@dataclass(frozen=True)
class ScenarioManifest:
    document: Mapping[str, Any]
    entries_by_ref: Mapping[str, Mapping[str, Any]]
    source_path: str

    @property
    def entries(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self.document['entries'])


def _strict_keys(value: Any, keys, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    unknown, missing = set(value) - set(keys), set(keys) - set(value)
    if unknown:
        raise ValueError(label + ' has unknown fields: ' + ', '.join(sorted(unknown)))
    if missing:
        raise ValueError(label + ' is missing fields: ' + ', '.join(sorted(missing)))
    return value


def validate_scenario_ref(value: Any) -> str:
    if type(value) is not str or len(value) > 64 or SCENARIO_REF_PATTERN.fullmatch(value) is None:
        raise ValueError('scenario reference is not canonical')
    return value


def _validate_manifest_document(document: Any) -> Mapping[str, Any]:
    root = _strict_keys(document, TOP_LEVEL_KEYS, 'scenario manifest')
    if root['schema_version'] != SUITE_MANIFEST_VERSION:
        raise ValueError('scenario manifest schema version mismatch')
    if root['generator_version'] != SINGAPORE_SCENARIO_V2_VERSION:
        raise ValueError('scenario manifest generator version mismatch')
    if root['distribution_version'] != SINGAPORE_DISTRIBUTION_VERSION:
        raise ValueError('scenario manifest distribution version mismatch')
    if root['provider_identity'] != MANIFEST_PROVIDER_IDENTITY:
        raise ValueError('scenario manifest provider identity mismatch')
    if not isinstance(root['distribution_checksum'], str) \
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', root['distribution_checksum']):
        raise ValueError('scenario manifest distribution checksum is invalid')
    if not isinstance(root['entries'], list) or len(root['entries']) != 544:
        raise ValueError('scenario manifest must contain exactly 544 flat entries')
    training = _strict_keys(root['training_seed_partition'], (
        'explicit_episode_specs_bypass_offset', 'minimum_scenario_seed',
        'scenario_seed_offset'), 'training seed partition')
    if (type(training['scenario_seed_offset']) is not int
            or type(training['minimum_scenario_seed']) is not int
            or training['scenario_seed_offset'] != TRAINING_SEED_OFFSET
            or training['minimum_scenario_seed'] != TRAINING_SEED_OFFSET
            or training['explicit_episode_specs_bypass_offset'] is not True):
        raise ValueError('scenario manifest training seed partition mismatch')
    oracle = _strict_keys(root['bounded_oracle'], (
        'candidates_per_pair', 'episode_count',
        'maximum_enumerated_action_sequences', 'maximum_interceptors',
        'maximum_threats', 'seed_end_exclusive',
        'seed_start_inclusive'), 'bounded oracle')
    expected_oracle = {
        'seed_start_inclusive': ORACLE_SEEDS[0],
        'seed_end_exclusive': ORACLE_SEEDS[-1] + 1,
        'episode_count': len(ORACLE_SEEDS),
        'maximum_threats': ORACLE_MAX_THREATS,
        'maximum_interceptors': ORACLE_MAX_INTERCEPTORS,
        'candidates_per_pair': ORACLE_CANDIDATES_PER_PAIR,
        'maximum_enumerated_action_sequences': ORACLE_MAX_ACTION_SEQUENCES,
    }
    if (any(type(value) is not int for value in oracle.values())
            or oracle != expected_oracle):
        raise ValueError('scenario manifest bounded oracle mismatch')
    plan = frozen_scenario_plan()
    entries_by_ref: Dict[str, Mapping[str, Any]] = {}
    hashes = set()
    seen_seeds = set()
    for position, (entry_value, expected) in enumerate(zip(root['entries'], plan)):
        entry = _strict_keys(entry_value, ENTRY_KEYS, 'manifest entry %d' % position)
        scenario_ref = validate_scenario_ref(entry['scenario_ref'])
        if type(entry['index']) is not int or type(entry['seed']) is not int:
            raise ValueError(
                'manifest entry index and seed must be integers: '
                + scenario_ref)
        for key in ('scenario_ref', 'split', 'index', 'seed', 'profile'):
            if entry[key] != expected[key]:
                raise ValueError('manifest entry differs from frozen split plan: ' + scenario_ref)
        if (entry['generator_version'] != root['generator_version']
                or entry['distribution_version'] != root['distribution_version']
                or entry['distribution_checksum'] != root['distribution_checksum']
                or entry['provider_identity'] != root['provider_identity']
                or entry['expected_feasible'] is not True):
            raise ValueError('manifest entry provenance mismatch: ' + scenario_ref)
        digest = entry['canonical_episode_hash']
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ValueError('manifest episode hash is invalid: ' + scenario_ref)
        if scenario_ref in entries_by_ref or digest in hashes:
            raise ValueError('duplicate scenario reference or canonical episode hash')
        if entry['seed'] in seen_seeds:
            raise ValueError('scenario split seeds overlap')
        entries_by_ref[scenario_ref] = entry
        hashes.add(digest)
        seen_seeds.add(entry['seed'])
    audit_seeds = set(range(AUDIT_SEED_START, AUDIT_SEED_START + 1000))
    if (seen_seeds & audit_seeds or seen_seeds & set(ORACLE_SEEDS)
            or any(seed >= TRAINING_SEED_OFFSET for seed in seen_seeds)):
        raise ValueError(
            'scenario seeds overlap oracle, audit, or training partitions')
    return root


def load_scenario_manifest(
        path: Path = DEFAULT_SCENARIO_MANIFEST_PATH) -> ScenarioManifest:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding='utf-8'),
                              parse_constant=lambda value: (_ for _ in ()).throw(
                                  ValueError('nonfinite manifest value: ' + value)))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('cannot load checked scenario manifest') from exc
    root = _validate_manifest_document(document)
    return ScenarioManifest(
        root, {row['scenario_ref']: row for row in root['entries']},
        str(path.resolve()))


def _audit_passed(audit: Mapping[str, Any]) -> bool:
    return bool(
        audit.get('requested_episode_count') == 1000
        and audit.get('goldilocks', {}).get('all_passed') is True
        and not audit.get('failed_generations')
        and len(audit.get('episodes', ())) == 1000)


def _require_passing_audit(
        generator: SingaporeScenarioV2Generator,
        audit: Mapping[str, Any]) -> None:
    if not _audit_passed(audit):
        raise ValueError(
            'frozen manifest creation requires the passing canonical audit')
    if (audit.get('distribution_checksum') != generator.distribution.checksum
            or audit.get('generator_version') != generator.version):
        raise ValueError('audit and manifest generator identities disagree')


def _manifest_document(
        generator: SingaporeScenarioV2Generator,
        generated: Tuple[Tuple[Mapping[str, Any], str, bool], ...]
        ) -> Mapping[str, Any]:
    entries = []
    hashes: Dict[str, str] = {}
    for row, digest, feasible in generated:
        if digest in hashes:
            raise ValueError(
                'duplicate canonical episode hash for %s and %s'
                % (hashes[digest], row['scenario_ref']))
        if not feasible:
            raise ValueError(
                'frozen scenario is not completely matchable: '
                + row['scenario_ref'])
        hashes[digest] = row['scenario_ref']
        entries.append({
            **row,
            'generator_version': generator.version,
            'distribution_version': generator.distribution.version,
            'distribution_checksum': generator.distribution.checksum,
            'provider_identity': MANIFEST_PROVIDER_IDENTITY,
            'canonical_episode_hash': digest,
            'expected_feasible': True,
        })
    document = {
        'schema_version': SUITE_MANIFEST_VERSION,
        'generator_version': generator.version,
        'distribution_version': generator.distribution.version,
        'distribution_checksum': generator.distribution.checksum,
        'provider_identity': MANIFEST_PROVIDER_IDENTITY,
        'training_seed_partition': {
            'scenario_seed_offset': TRAINING_SEED_OFFSET,
            'minimum_scenario_seed': TRAINING_SEED_OFFSET,
            'explicit_episode_specs_bypass_offset': True,
        },
        'bounded_oracle': {
            'seed_start_inclusive': ORACLE_SEEDS[0],
            'seed_end_exclusive': ORACLE_SEEDS[-1] + 1,
            'episode_count': len(ORACLE_SEEDS),
            'maximum_threats': ORACLE_MAX_THREATS,
            'maximum_interceptors': ORACLE_MAX_INTERCEPTORS,
            'candidates_per_pair': ORACLE_CANDIDATES_PER_PAIR,
            'maximum_enumerated_action_sequences':
                ORACLE_MAX_ACTION_SEQUENCES,
        },
        'entries': entries,
    }
    _validate_manifest_document(document)
    return document


def build_frozen_scenario_manifest(
        generator: SingaporeScenarioV2Generator,
        audit: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_passing_audit(generator, audit)
    generated = []
    base_provider = generator._provider()
    catalog = getattr(base_provider, 'catalog', None)
    for row in frozen_scenario_plan():
        if isinstance(base_provider, SingaporeConsequenceProvider):
            generator.consequence_provider = SingaporeConsequenceProvider(
                catalog=catalog, scenario_config=generator.config)
        spec = generator.generate(row['seed'], row['profile'])
        digest = canonical_episode_hash(spec)
        generated.append((row, digest, bool(
            spec.metadata['matching_summary']['complete_matchable'])))
    return _manifest_document(generator, tuple(generated))


_MANIFEST_GENERATOR: Optional[SingaporeScenarioV2Generator] = None
_MANIFEST_CATALOG: Any = None


def _initialize_manifest_worker(distribution_path: str, checksum: str,
                                config: Any) -> None:
    global _MANIFEST_GENERATOR, _MANIFEST_CATALOG
    distribution = load_scenario_distribution(
        Path(distribution_path), expected_checksum=checksum)
    provider = SingaporeConsequenceProvider(scenario_config=config)
    _MANIFEST_CATALOG = provider.catalog
    _MANIFEST_GENERATOR = SingaporeScenarioV2Generator(
        distribution=distribution, config=config,
        consequence_provider=provider)


def _parallel_manifest_entry(
        row: Mapping[str, Any]) -> Tuple[Mapping[str, Any], str, bool]:
    if _MANIFEST_GENERATOR is None:
        raise RuntimeError('manifest worker was not initialized')
    _MANIFEST_GENERATOR.consequence_provider = SingaporeConsequenceProvider(
        catalog=_MANIFEST_CATALOG,
        scenario_config=_MANIFEST_GENERATOR.config)
    spec = _MANIFEST_GENERATOR.generate(row['seed'], row['profile'])
    return (row, canonical_episode_hash(spec), bool(
        spec.metadata['matching_summary']['complete_matchable']))


def _worker_count(workers: Optional[int]) -> int:
    count = min(6, os.cpu_count() or 1) if workers is None else workers
    if type(count) is not int or count <= 0:
        raise ValueError('manifest worker count must be a positive integer')
    return count


def build_frozen_scenario_manifest_parallel(
        generator: SingaporeScenarioV2Generator,
        audit: Mapping[str, Any],
        workers: Optional[int] = None) -> Mapping[str, Any]:
    """Build the frozen manifest in deterministic plan order."""
    _require_passing_audit(generator, audit)
    count = _worker_count(workers)
    if count == 1:
        return build_frozen_scenario_manifest(generator, audit)
    plan = frozen_scenario_plan()
    with ProcessPoolExecutor(
            max_workers=count, initializer=_initialize_manifest_worker,
            initargs=(generator.distribution.source_path,
                      generator.distribution.checksum,
                      generator.config)) as executor:
        generated = tuple(executor.map(
            _parallel_manifest_entry, plan, chunksize=1))
    return _manifest_document(generator, generated)


def manifest_public_metadata(
        manifest: Optional[ScenarioManifest] = None) -> Mapping[str, Any]:
    manifest = manifest or load_scenario_manifest()
    return {
        'schemaVersion': manifest.document['schema_version'],
        'generatorVersion': manifest.document['generator_version'],
        'distributionVersion': manifest.document['distribution_version'],
        'distributionChecksum': manifest.document['distribution_checksum'],
        'providerIdentity': manifest.document['provider_identity'],
        'entries': [{
            'scenarioRef': row['scenario_ref'], 'split': row['split'],
            'index': row['index'], 'seed': row['seed'],
            'profile': row['profile'],
            'canonicalEpisodeHash': row['canonical_episode_hash'],
        } for row in manifest.entries],
    }


def _resolve_manifest_entry(
        entry: Mapping[str, Any], provider_identity: str,
        generator: SingaporeScenarioV2Generator):
    if (generator.version != entry['generator_version']
            or generator.distribution.version != entry['distribution_version']
            or generator.distribution.checksum != entry['distribution_checksum']
            or provider_identity != entry['provider_identity']):
        raise ScenarioIdentityMismatch('scenario reference provenance mismatch')
    spec = generator.generate(entry['seed'], entry['profile'])
    if canonical_episode_hash(spec) != entry['canonical_episode_hash']:
        raise ScenarioIdentityMismatch(
            'scenario reference canonical episode hash mismatch')
    if not spec.metadata['matching_summary']['complete_matchable']:
        raise ScenarioIdentityMismatch(
            'scenario reference is unexpectedly infeasible')
    return spec


def resolve_scenario_ref(
        scenario_ref: str,
        manifest: Optional[ScenarioManifest] = None,
        generator: Optional[SingaporeScenarioV2Generator] = None):
    """Resolve only a checked canonical reference; no paths/config are accepted."""
    scenario_ref = validate_scenario_ref(scenario_ref)
    manifest = manifest or load_scenario_manifest()
    entry = manifest.entries_by_ref.get(scenario_ref)
    if entry is None:
        raise KeyError('unknown scenario reference')
    if generator is None:
        distribution = load_scenario_distribution(
            DEFAULT_DISTRIBUTION_PATH,
            expected_checksum=entry['distribution_checksum'])
        provider = SingaporeConsequenceProvider()
        generator = SingaporeScenarioV2Generator(
            distribution=distribution, config=provider.scenario_config,
            consequence_provider=provider)
    return _resolve_manifest_entry(
        entry, manifest.document['provider_identity'], generator)


def _parallel_verify_entry(
        entry: Mapping[str, Any]) -> Tuple[str, str]:
    if _MANIFEST_GENERATOR is None:
        raise RuntimeError('manifest worker was not initialized')
    _MANIFEST_GENERATOR.consequence_provider = SingaporeConsequenceProvider(
        catalog=_MANIFEST_CATALOG,
        scenario_config=_MANIFEST_GENERATOR.config)
    spec = _resolve_manifest_entry(
        entry, MANIFEST_PROVIDER_IDENTITY, _MANIFEST_GENERATOR)
    return entry['scenario_ref'], canonical_episode_hash(spec)


def verify_all_scenario_references(
        manifest: Optional[ScenarioManifest] = None,
        generator: Optional[SingaporeScenarioV2Generator] = None,
        workers: Optional[int] = None) -> Tuple[Tuple[str, str], ...]:
    """Regenerate and hash-check every entry in deterministic manifest order."""
    manifest = manifest or load_scenario_manifest()
    if generator is None:
        distribution = load_scenario_distribution(
            DEFAULT_DISTRIBUTION_PATH,
            expected_checksum=manifest.document['distribution_checksum'])
        provider = SingaporeConsequenceProvider()
        generator = SingaporeScenarioV2Generator(
            distribution=distribution, config=provider.scenario_config,
            consequence_provider=provider)
    count = _worker_count(workers)
    if count == 1:
        base_provider = generator._provider()
        catalog = getattr(base_provider, 'catalog', None)
        checked = []
        for entry in manifest.entries:
            generator.consequence_provider = SingaporeConsequenceProvider(
                catalog=catalog, scenario_config=generator.config)
            spec = _resolve_manifest_entry(
                entry, manifest.document['provider_identity'], generator)
            checked.append((entry['scenario_ref'], canonical_episode_hash(spec)))
        return tuple(checked)
    if manifest.document['provider_identity'] != MANIFEST_PROVIDER_IDENTITY:
        raise ScenarioIdentityMismatch('scenario manifest provider mismatch')
    with ProcessPoolExecutor(
            max_workers=count, initializer=_initialize_manifest_worker,
            initargs=(generator.distribution.source_path,
                      generator.distribution.checksum,
                      generator.config)) as executor:
        return tuple(executor.map(
            _parallel_verify_entry, manifest.entries, chunksize=1))
