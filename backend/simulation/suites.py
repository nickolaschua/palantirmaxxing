"""Fixed, non-overlapping seeded scenario suites."""
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Tuple

from .singapore_scenario import canonical_episode_hash


SMOKE_TRAINING_STEPS = 10_000
SUITE_MANIFEST_VERSION = 'rl-scenario-suites/3'
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

SUITES = {
    item.name: item for item in (
        VALIDATION_SUITE, HELD_OUT_TEST_SUITE, STRESS_SUITE, ORACLE_SUITE)
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
