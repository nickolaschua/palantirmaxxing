import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.domain import InterceptorState, ThreatState
from backend.simulation import (EpisodeSpec, InterceptorResource,
                                ScheduledThreat)
from backend.simulation.scenario_pool import (
    EpisodePoolFactory, EpisodePoolScenarioGenerator, generate_scenario_pool,
    load_scenario_pool, scenario_content_hash, training_pool_plan,
    verify_scenario_pool)
from backend.simulation.singapore_scenario import canonical_episode_hash
from backend.simulation.suites import TRAINING_SEED_OFFSET


class _Distribution:
    version = 'test-distribution/1'
    checksum = 'sha256:' + '1' * 64
    source_path = 'unused.json'


class _Provider:
    identity = 'test-provider'


class _Generator:
    version = 'test-generator/1'
    distribution = _Distribution()
    configuration_checksum = 'sha256:' + '2' * 64
    config = object()
    eligibility_checker = None

    def __init__(self, fail_seed=None):
        self.fail_seed = fail_seed

    def _provider(self):
        return _Provider()

    def generate(self, seed, profile):
        if seed == self.fail_seed:
            raise RuntimeError('injected generation interruption')
        threat = ScheduledThreat(
            0.0, ThreatState(
                'threat', float(seed), 0.0, 1.0, 0.0, 10.0),
            {'ingress_sector': seed % 8, 'terminal_grid_cell': seed % 16})
        interceptor = InterceptorResource(
            InterceptorState('interceptor', 0.0, float(seed), 0.0, 2.0, 1.0))
        return EpisodeSpec(
            'episode-%d' % seed, seed, (threat,), (interceptor,), 1,
            metadata={
                'profile': profile,
                'ingress_sectors': [seed % 8],
                'terminal_grid_cells': [seed % 16],
                'generation_attempt_count': 2,
                'rejected_attempt_count': 1,
                'rejected_attempts': [
                    {'attempt': 1, 'failed_predicates': ['fixture']}],
            })


class _InterruptedGenerator(_Generator):
    def generate(self, seed, profile):
        raise KeyboardInterrupt()


class ScenarioPoolTests(unittest.TestCase):
    def test_512_plan_has_declared_stratification_and_training_seeds(self):
        plan = training_pool_plan()
        self.assertEqual(len(plan), 512)
        counts = {
            profile: sum(row['profile'] == profile for row in plan)
            for profile in {row['profile'] for row in plan}}
        self.assertEqual(counts, {
            'warmup': 52,
            'balanced': 92,
            'full-standard': 92,
            'burst-contention': 92,
            'low-slack': 92,
            'consequence-contrast': 92,
        })
        self.assertEqual(plan[0]['seed'], TRAINING_SEED_OFFSET)
        self.assertEqual(plan[-1]['seed'], TRAINING_SEED_OFFSET + 511)
        self.assertTrue(all(row['split'] == 'development-training'
                            for row in plan))

    def test_release_round_trip_exact_loading_and_verification(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'pool'
            manifest = generate_scenario_pool(
                _Generator(), root, 'test-pool-v1', count=6,
                source_revision='abc123', source_tree_dirty=False,
                source_files={'generator.py': 'sha256:' + '3' * 64},
                dependencies={'python': 'test'}, workers=1)
            self.assertEqual(manifest['record_count'], 6)
            self.assertEqual(
                manifest['coverage']['distinct_canonical_episode_hashes'], 6)
            pool = load_scenario_pool(root)
            first = pool.load('sg2pool:test-pool-v1:000000')
            self.assertEqual(first.seed, TRAINING_SEED_OFFSET)
            self.assertEqual(first.metadata['profile'],
                             manifest['records'][0]['profile'])
            verification = verify_scenario_pool(root, _Generator())
            self.assertEqual(verification['status'], 'verified')
            self.assertEqual(verification['reproduced_records'], 6)
            self.assertEqual(verification['distinct_content_hashes'], 6)
            self.assertFalse((root / 'progress.json').exists())

    def test_interrupted_generation_resumes_from_completed_prefix(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'pool'
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                generate_scenario_pool(
                    _Generator(TRAINING_SEED_OFFSET + 2), root,
                    'test-resume-v1', count=6, source_revision='abc123',
                    workers=1)
            progress = json.loads((root / 'progress.json').read_text())
            self.assertEqual(len(progress['records']), 2)
            self.assertEqual(progress['failures'], [{
                'index': 2, 'seed': TRAINING_SEED_OFFSET + 2,
                'profile': training_pool_plan(6)[2]['profile'],
                'error_type': 'RuntimeError',
                'error': 'injected generation interruption',
            }])
            completed = (root / 'episodes/000000.json').read_bytes()
            manifest = generate_scenario_pool(
                _Generator(), root, 'test-resume-v1', count=6,
                source_revision='abc123', workers=1, resume=True)
            self.assertEqual(manifest['record_count'], 6)
            self.assertEqual(len(manifest['generation_failures']), 1)
            self.assertEqual((root / 'episodes/000000.json').read_bytes(), completed)
            self.assertEqual(verify_scenario_pool(root)['record_count'], 6)

    def test_operator_interrupt_is_not_recorded_as_generation_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'pool'
            with self.assertRaises(KeyboardInterrupt):
                generate_scenario_pool(
                    _InterruptedGenerator(), root, 'test-interrupt-v1',
                    count=6, source_revision='abc123', workers=1)
            progress = json.loads((root / 'progress.json').read_text())
            self.assertEqual(progress['records'], [])
            self.assertEqual(progress['failures'], [])

    def test_artifact_and_manifest_corruption_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'pool'
            generate_scenario_pool(
                _Generator(), root, 'test-corrupt-v1', count=6,
                source_revision='abc123', workers=1)
            artifact = root / 'episodes/000000.json'
            artifact.write_bytes(artifact.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'artifact checksum'):
                verify_scenario_pool(root)
            document = json.loads((root / 'manifest.json').read_text())
            document['record_count'] = 7
            (root / 'manifest.json').write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, 'record count|checksum'):
                load_scenario_pool(root)

    def test_pool_selector_is_a_complete_deterministic_permutation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'pool'
            generate_scenario_pool(
                _Generator(), root, 'test-selector-v1', count=6,
                source_revision='abc123', workers=1)
            selector = EpisodePoolScenarioGenerator(root)
            first_cycle = [selector.generate(seed).seed for seed in range(6)]
            second_cycle = [selector.generate(seed).seed for seed in range(6, 12)]
            self.assertEqual(len(set(first_cycle)), 6)
            self.assertEqual(second_cycle, first_cycle)
            streams = [
                selector.generate(rank + step * 2).seed
                for step in range(3) for rank in range(2)]
            self.assertEqual(streams, first_cycle)
            filtered = EpisodePoolFactory(
                str(root), profile='consequence-contrast', limit=1)()
            self.assertEqual(len(filtered.records), 1)
            self.assertEqual(filtered.generate(0).metadata['profile'],
                             'consequence-contrast')

    def test_substantive_hash_ignores_record_identity_and_seed(self):
        first = _Generator().generate(TRAINING_SEED_OFFSET, 'warmup')
        threat = first.threats[0]
        threats = (replace(
            threat, metadata={**threat.metadata,
                              'generation_attempt': 99,
                              'threat_retry_attempt': 98}),)
        second = EpisodeSpec(
            'renamed-record', TRAINING_SEED_OFFSET + 99,
            threats, first.interceptors, first.candidate_count,
            {**first.metadata, 'release_note': 'incidental'},
            first.schema_version)
        self.assertNotEqual(canonical_episode_hash(first),
                            canonical_episode_hash(second))
        self.assertEqual(scenario_content_hash(first),
                         scenario_content_hash(second))


if __name__ == '__main__':
    unittest.main()
