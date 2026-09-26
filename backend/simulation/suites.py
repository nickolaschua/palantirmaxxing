"""Fixed, non-overlapping seeded scenario suites."""
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Tuple

from .singapore_scenario import canonical_episode_hash


SMOKE_TRAINING_STEPS = 10_000
SUITE_MANIFEST_VERSION = 'rl-scenario-suites/5'
# Generated training episodes occupy a separate, unbounded upper partition.
TRAINING_SEED_OFFSET = 1_000_000_000
VALIDATION_SEEDS = tuple(range(10_000, 10_064))
HELD_OUT_TEST_SEEDS = tuple(range(20_000, 20_256))
STRESS_SEEDS = tuple(range(30_000, 30_032))
ORACLE_SEEDS = tuple(range(40_000, 40_032))
ORACLE_MAX_THREATS = 3
ORACLE_MAX_INTERCEPTORS = 3
ORACLE_CANDIDATES_PER_PAIR = 5
ORACLE_MAX_ACTION_SEQUENCES = 100_000
SINGAPORE_REFERENCE_SEEDS = tuple(range(50_000, 50_064))
OOD_GEOGRAPHY_SEEDS = tuple(range(60_000, 60_064))
OOD_CADENCE_SEEDS = tuple(range(70_000, 70_064))

FROZEN_SPLIT_PROFILES = {
    'validation': (
        ('balanced', 16), ('full-standard', 16),
        ('burst-contention', 12), ('low-slack', 10),
        ('consequence-contrast', 10)),
    'held-out': (
        ('balanced', 64), ('full-standard', 64),
        ('burst-contention', 48), ('low-slack', 40),
        ('consequence-contrast', 40)),
    'stress': (('burst-contention', 16), ('low-slack', 16)),
    'ood-geography': (('geographic-shift', 64),),
    'ood-cadence': (('cadence-shift', 64),),
    'assignment-reference': (('full-standard', 64),),
}
FROZEN_SPLIT_SEEDS = {
    'validation': VALIDATION_SEEDS,
    'held-out': HELD_OUT_TEST_SEEDS,
    'stress': STRESS_SEEDS,
    'ood-geography': OOD_GEOGRAPHY_SEEDS,
    'ood-cadence': OOD_CADENCE_SEEDS,
    'assignment-reference': SINGAPORE_REFERENCE_SEEDS,
}


@dataclass(frozen=True)
class SuiteDefinition:
    name: str
    seeds: Tuple[int, ...]
    threat_capacity: int
    interceptor_capacity: int
    candidate_count: int
    full_capacity: bool = False

    def as_dict(self) -> Mapping[str, object]:
        return {
            'name': self.name,
            'seeds': list(self.seeds),
            'threat_capacity': self.threat_capacity,
            'interceptor_capacity': self.interceptor_capacity,
            'candidate_count': self.candidate_count,
            'full_capacity': self.full_capacity,
        }


VALIDATION_SUITE = SuiteDefinition('validation', VALIDATION_SEEDS, 8, 8, 20)
HELD_OUT_TEST_SUITE = SuiteDefinition('held-out-test', HELD_OUT_TEST_SEEDS, 8, 8, 20)
STRESS_SUITE = SuiteDefinition('stress', STRESS_SEEDS, 8, 8, 20, full_capacity=True)
ORACLE_SUITE = SuiteDefinition(
    'bounded-oracle', ORACLE_SEEDS, ORACLE_MAX_THREATS,
    ORACLE_MAX_INTERCEPTORS, ORACLE_CANDIDATES_PER_PAIR)
SINGAPORE_ASSIGNMENT_REFERENCE_SUITE = SuiteDefinition(
    'singapore-assignment-reference', SINGAPORE_REFERENCE_SEEDS, 8, 8, 20,
    full_capacity=True)

SUITES = {
    item.name: item for item in (
        VALIDATION_SUITE, HELD_OUT_TEST_SUITE, STRESS_SUITE, ORACLE_SUITE,
        SINGAPORE_ASSIGNMENT_REFERENCE_SUITE)
}


def build_suite_manifest(generator: Any, suite: SuiteDefinition,
                         existing_hashes: MutableMapping[str, str] = None
                         ) -> Mapping[str, object]:
    """Materialize canonical episode hashes and reject cross-partition reuse."""
    if suite.name not in SUITES or SUITES[suite.name] != suite:
        raise ValueError('suite must be one of the fixed suite definitions')
    registry = {} if existing_hashes is None else existing_hashes
    episodes = []
    for seed in suite.seeds:
        spec = generator.generate(seed, full_capacity=suite.full_capacity)
        digest = canonical_episode_hash(spec)
        previous = registry.get(digest)
        if previous is not None:
            raise ValueError('canonical episode duplicate across partitions: %s and %s'
                             % (previous, suite.name))
        registry[digest] = suite.name
        episodes.append({'seed': seed, 'episode_id': spec.episode_id,
                         'canonical_episode_hash': digest})
    return {
        'schema_version': SUITE_MANIFEST_VERSION,
        'suite': suite.as_dict(),
        'generator_version': generator.version,
        'canonical_hash_algorithm': 'sha256 of canonical simulation episode JSON',
        'episodes': episodes,
    }


def frozen_scenario_plan() -> Tuple[Mapping[str, object], ...]:
    """Return the immutable 544-reference split/profile/seed plan."""
    rows = []
    for split, quotas in FROZEN_SPLIT_PROFILES.items():
        profiles = tuple(
            profile for profile, count in quotas for _ in range(count))
        seeds = FROZEN_SPLIT_SEEDS[split]
        if len(profiles) != len(seeds):
            raise RuntimeError('frozen split quota and seed range disagree')
        for index, (seed, profile) in enumerate(zip(seeds, profiles)):
            rows.append({
                'scenario_ref': 'sg2:%s:%06d' % (split, index),
                'split': split, 'index': index,
                'seed': seed, 'profile': profile,
            })
    return tuple(rows)
