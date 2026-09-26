from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.simulation import (
    PROFILE_NAMES, EpisodeSpec, SingaporeConsequenceProvider,
    SingaporeGenerationError, SingaporeScenarioGenerator,
    SingaporeScenarioV2Generator, canonical_distribution_checksum,
    canonical_episode_hash, episode_to_dict, load_scenario_distribution,
    profile_predicate_failures, scenario_graph_metrics)


ROOT = Path(__file__).resolve().parents[2]
DISTRIBUTION = ROOT / 'data/scenarios/rl/singapore-distribution-v1.json'


class ScenarioDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = SingaporeConsequenceProvider()
        cls.generator = SingaporeScenarioV2Generator(
            config=cls.provider.scenario_config,
            consequence_provider=cls.provider)

    def test_v1_seed_seven_contract_and_frozen_hash(self):
        spec = SingaporeScenarioGenerator(
            consequence_provider=SingaporeConsequenceProvider()).generate(7)
        self.assertEqual((len(spec.threats), len(spec.interceptors),
                          spec.candidate_count), (8, 8, 20))
        self.assertEqual(
            canonical_episode_hash(spec),
            'sha256:33f3a96a82e59db03d7ea60f354d0415d5d712d84ffea564eb808713fc95eed9')

    def test_v2_regeneration_is_byte_identical_with_complete_metadata(self):
        first = self.generator.generate(91234, 'balanced')
        provider = SingaporeConsequenceProvider(catalog=self.provider.catalog)
        with TemporaryDirectory() as directory:
            copied = Path(directory) / 'renamed-distribution.json'
            copied.write_bytes(DISTRIBUTION.read_bytes())
            second = SingaporeScenarioV2Generator(
                distribution=load_scenario_distribution(copied),
                config=provider.scenario_config,
                consequence_provider=provider).generate(91234, 'balanced')
        self.assertEqual(episode_to_dict(first), episode_to_dict(second))
        self.assertEqual(canonical_episode_hash(first), canonical_episode_hash(second))
        for key in (
                'profile', 'distribution_identity', 'distribution_checksum',
                'generator', 'canonical_episode_hash', 'active_threat_count',
                'active_interceptor_count', 'ingress_sectors',
                'terminal_grid_cells', 'generation_attempt_count',
                'matching_summary', 'scenario_config_checksum',
                'generator_configuration_checksum', 'boundary_source_checksum',
                'main_island_geometry_checksum', 'provider_config_checksum',
                'provider_data_checksum', 'provider_source_checksums'):
            self.assertIn(key, first.metadata)

    def test_checked_audit_has_at_least_128_distinct_fixed_pairs(self):
        audit = json.loads((ROOT / 'data/results/rl/scenario-audit-v2.json').read_text())
        rows = audit['episodes'][:128]
        self.assertEqual(len(rows), 128)
        self.assertTrue(all(row['status'] == 'audited' for row in rows))
        self.assertEqual(len({row['canonical_episode_hash'] for row in rows}), 128)
        self.assertEqual(len({(row['seed'], row['profile']) for row in rows}), 128)

    def test_distribution_rejects_unknown_range_checksum_and_nonfinite(self):
        original = json.loads(DISTRIBUTION.read_text())
        cases = []
        unknown = json.loads(json.dumps(original)); unknown['unexpected'] = 1
        unknown['checksum'] = canonical_distribution_checksum(unknown); cases.append(unknown)
        invalid = json.loads(json.dumps(original)); invalid['profiles']['warmup']['threat_count_min'] = 0
        invalid['checksum'] = canonical_distribution_checksum(invalid); cases.append(invalid)
        reversed_gap = json.loads(json.dumps(original))
        reversed_gap['profiles']['balanced']['detection']['gap_min_s'] = 9.0
        reversed_gap['checksum'] = canonical_distribution_checksum(reversed_gap)
        cases.append(reversed_gap)
        fractional_burst = json.loads(json.dumps(original))
        fractional_burst['profiles']['burst-contention']['detection']['burst_count'] = 4.5
        fractional_burst['checksum'] = canonical_distribution_checksum(fractional_burst)
        cases.append(fractional_burst)
        overflow = json.loads(json.dumps(original))
        overflow['profiles']['warmup']['threat_count_max'] = 8
        overflow['checksum'] = canonical_distribution_checksum(overflow)
        cases.append(overflow)
        checksum = json.loads(json.dumps(original)); checksum['checksum'] = 'sha256:' + '0' * 64
        cases.append(checksum)
        with TemporaryDirectory() as directory:
            for index, value in enumerate(cases):
                path = Path(directory) / ('case-%d.json' % index)
                path.write_text(json.dumps(value))
                with self.subTest(index=index), self.assertRaises(ValueError):
                    load_scenario_distribution(path)
            path = Path(directory) / 'nonfinite.json'
            path.write_text(DISTRIBUTION.read_text().replace(
                '"trajectory_duration_max_s": 84.0',
                '"trajectory_duration_max_s": NaN', 1))
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                load_scenario_distribution(path)
        with self.assertRaises(ValueError):
            self.generator.generate(1, 'not-a-profile')

    def test_every_profile_fixture_satisfies_declared_predicates(self):
        for index, profile in enumerate(PROFILE_NAMES):
            with self.subTest(profile=profile):
                spec = self.generator.generate(93000 + index, profile)
                metrics = scenario_graph_metrics(spec, self.generator._provider())
                comparison = spec.metadata.get('profile_comparison')
                failures = profile_predicate_failures(
                    profile, self.generator.distribution.profile(profile), metrics,
                    [row.detection_time_s for row in spec.threats],
                    [row.state.threat_id for row in spec.threats[:4]], comparison)
                self.assertEqual(failures, ())
                self.assertTrue(metrics['complete_matchable'])

    def test_retries_are_recorded_and_exhaustion_is_a_hard_failure(self):
        spec = self.generator.generate(80000, 'low-slack')
        self.assertEqual(spec.metadata['generation_attempt_count'],
                         spec.metadata['rejected_attempt_count'] + 1)
        self.assertEqual(len(spec.metadata['rejected_attempts']),
                         spec.metadata['rejected_attempt_count'])
        with patch.object(self.generator, '_draft',
                          side_effect=SingaporeGenerationError('injected')) as draft:
            with self.assertRaisesRegex(SingaporeGenerationError,
                                        'failed all 200'):
                self.generator.generate(999, 'warmup')
        self.assertEqual(draft.call_count, 200)

    def test_component_retry_stream_is_local_to_one_threat(self):
        profile_name = 'balanced'
        profile = self.generator.distribution.profile(profile_name)
        times = self.generator._detection_times(
            77, profile_name, profile, 4, 0)
        before_other = self.generator._threat(
            77, profile_name, profile, 1, 0, times[1], episode_attempt=0)
        before_resources = self.generator._interceptors(
            77, profile_name, profile, 4, 0)
        retried = self.generator._threat(
            77, profile_name, profile, 0, 1, times[0], episode_attempt=0)
        after_other = self.generator._threat(
            77, profile_name, profile, 1, 0, times[1], episode_attempt=0)
        after_resources = self.generator._interceptors(
            77, profile_name, profile, 4, 0)
        self.assertNotEqual(retried.metadata['threat_retry_attempt'], 0)
        self.assertEqual(before_other, after_other)
        self.assertEqual(before_resources, after_resources)

    def test_canonical_hash_binds_profile_sources_provider_geometry_and_content(self):
        spec = self.generator.generate(94567, 'balanced')
        original = canonical_episode_hash(spec)
        metadata_fields = (
            ('profile', 'different-profile'),
            ('main_island_geometry_checksum', 'sha256:' + '1' * 64),
            ('provider_identity', 'different-provider'),
            ('boundary_source_checksum', 'sha256:' + '2' * 64),
        )
        for key, value in metadata_fields:
            metadata = dict(spec.metadata); metadata[key] = value
            changed = EpisodeSpec(
                spec.episode_id, spec.seed, spec.threats, spec.interceptors,
                spec.candidate_count, metadata, spec.schema_version)
            self.assertNotEqual(canonical_episode_hash(changed), original)
        first = spec.threats[0]
        state = replace(first.state, position_z_m=first.state.position_z_m + 1.0)
        threats = (replace(first, state=state),) + spec.threats[1:]
        changed = EpisodeSpec(
            spec.episode_id, spec.seed, threats, spec.interceptors,
            spec.candidate_count, spec.metadata, spec.schema_version)
        self.assertNotEqual(canonical_episode_hash(changed), original)


if __name__ == '__main__':
    unittest.main()
