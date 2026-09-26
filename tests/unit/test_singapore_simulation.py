from dataclasses import replace
import json
import math
from pathlib import Path
import unittest

from shapely.geometry import Point

from backend.data_sources.consequence import (POLICY_DEMO_V2, Score, flag_table,
                                                score_profile, veto)
from backend.domain import CandidateOpportunity
from backend.planning import sample_threat_trajectory
from backend.presentation import simulation_result_to_dict
from backend.simulation import (AbsoluteCandidate, ImmediateInterceptionPolicy,
                                SingaporeConsequenceProvider,
                                SingaporeGenerationError,
                                SingaporeScenarioGenerator, SimulationEngine,
                                canonical_episode_hash, episode_to_dict)


class SingaporeSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = SingaporeConsequenceProvider()
        cls.generator = SingaporeScenarioGenerator(
            consequence_provider=cls.provider)
        cls.spec = cls.generator.generate(7)

    @staticmethod
    def candidate(x, y, opportunity_id='test', reachable=True):
        opportunity = CandidateOpportunity(
            opportunity_id, 'test-threat', 'test-interceptor', 1, 1.0,
            x, y, reachable, 1.0, 0.5, 0.5, 100.0, -1.0)
        return AbsoluteCandidate.from_opportunity(opportunity, 0.0)

    def test_contract_counts_detection_window_and_checksums(self):
        spec = self.spec
        self.assertEqual(spec.schema_version, 'simulation-episode/2')
        self.assertEqual((len(spec.threats), len(spec.interceptors), spec.candidate_count),
                         (8, 8, 20))
        times = [row.detection_time_s for row in spec.threats]
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(0 <= value <= 10 for value in times))
        self.assertTrue(spec.metadata['boundary_source_checksum'].startswith('sha256:'))
        self.assertTrue(spec.metadata['main_island_geometry_checksum'].startswith('sha256:'))
        self.assertEqual(spec.metadata['canonical_episode_hash'],
                         canonical_episode_hash(spec))

    def test_boundary_terminal_altitude_and_parabolic_endpoint(self):
        island = self.generator.main_island.geometry
        for row in self.spec.threats:
            state = row.state
            self.assertAlmostEqual(Point(state.position_x_m, state.position_y_m).distance(island),
                                   10_000, delta=1.0)
            terminal = Point(row.metadata['terminal_position_x_m'],
                             row.metadata['terminal_position_y_m'])
            self.assertTrue(island.covers(terminal))
            self.assertGreaterEqual(state.position_z_m, 5_000)
            self.assertLessEqual(state.position_z_m, 15_000)
            samples = sample_threat_trajectory(state, 20)
            self.assertTrue(all(math.isfinite(sample.position_z_m)
                                and sample.position_z_m >= 0 for sample in samples))
            self.assertAlmostEqual(samples[-1].position_x_m, terminal.x, places=6)
            self.assertAlmostEqual(samples[-1].position_y_m, terminal.y, places=6)
            self.assertEqual(samples[-1].position_z_m, 0.0)

    def test_determinism_canonical_serialization_and_distinct_matching(self):
        again = SingaporeScenarioGenerator(
            consequence_provider=SingaporeConsequenceProvider(
                catalog=self.provider.catalog)).generate(7)
        self.assertEqual(episode_to_dict(self.spec), episode_to_dict(again))
        matching = self.spec.metadata['matching']
        self.assertEqual(len(matching), 8)
        self.assertEqual(len(set(matching.values())), 8)

    def test_retry_limit_is_explicit(self):
        generator = SingaporeScenarioGenerator(
            eligibility_checker=lambda *_: False)
        with self.assertRaisesRegex(SingaporeGenerationError, '100 attempts'):
            generator.generate(99)

    def test_off_island_is_zero_not_partial_population(self):
        _, _, max_x, max_y = self.provider.catalog.main_island.geometry.bounds
        candidate = self.candidate(max_x + 20_000, max_y + 20_000)
        assessment = self.provider.assess_candidates(
            self.spec.threats[0], (candidate,), {})['test']
        self.assertEqual(assessment.population_exposure['status'], 'outside_singapore')
        self.assertEqual(assessment.population_exposure['people_potentially_exposed'], 0)
        self.assertEqual(assessment.C[0], 0)

    def test_point_and_polygon_overlap_rules_are_evidenced(self):
        park = next(row for row in self.provider.catalog.sites
                    if row.source_kind == 'parks_civic')
        park_assessment = self.provider.assess_candidates(
            self.spec.threats[0],
            (self.candidate(park.geometry.x, park.geometry.y, 'park'),), {})['park']
        park_row = next(row for row in park_assessment.intersected_sites
                        if row['site_id'] == park.site_id)
        self.assertEqual(park_row['geometry_rule'], 'point_full_direct_effect')
        self.assertEqual(park_row['overlap_fraction'], 1.0)

        polygon = next(row for row in self.provider.catalog.sites
                       if row.source_kind == 'critical_facility')
        center = polygon.geometry.representative_point()
        polygon_assessment = self.provider.assess_candidates(
            self.spec.threats[0],
            (self.candidate(center.x, center.y, 'polygon'),), {})['polygon']
        polygon_row = next(row for row in polygon_assessment.intersected_sites
                           if row['site_id'] == polygon.site_id)
        self.assertEqual(polygon_row['geometry_rule'], 'polygon_area_fraction')
        self.assertGreater(polygon_row['overlap_fraction'], 0)
        self.assertLessEqual(polygon_row['overlap_fraction'], 1)
        self.assertEqual(polygon_row['inputs']['occupancy']['state'], 'assumption')
        self.assertIn('D', polygon_row['dimensions_missing'])

    def test_adapter_matches_direct_emmanuel_scores_veto_and_tie_band(self):
        park = next(row for row in self.provider.catalog.sites
                    if row.source_kind == 'parks_civic')
        assessment = self.provider.assess_candidates(
            self.spec.threats[0],
            (self.candidate(park.geometry.x, park.geometry.y, 'direct'),),
            {})['direct']
        evidence = next(row for row in assessment.intersected_sites
                        if row['site_id'] == park.site_id)
        direct = score_profile(park.profile)
        for dimension in ('C', 'E', 'D', 'X', 'R', 'A', 'secondary'):
            expected = getattr(direct, dimension)
            actual = evidence['scores'][dimension]
            if expected is None:
                self.assertIsNone(actual)
            else:
                self.assertEqual(
                    actual,
                    {'low': expected.low, 'central': expected.central,
                     'high': expected.high})
        direct_veto = veto(
            flag_table(park.profile, direct), park.profile.priority_asset,
            park.profile.capability.available)
        self.assertEqual(evidence['veto_status'], direct_veto[0])

        provider = SingaporeConsequenceProvider(catalog=self.provider.catalog)
        fixture = {
            'a': (Score(90, 100, 110), Score(8, 10, 12), 'pass'),
            'b': (Score(95, 105, 115), Score(0, 1, 2), 'unknown'),
            'c': (Score(120, 130, 140), Score(0, 0, 1), 'pass'),
            'd': (Score(1, 2, 3), Score(0, 0, 0), 'vetoed'),
        }

        def frozen_spatial(candidate):
            C, secondary, status = fixture[candidate.opportunity.opportunity_id]
            return {
                'population': {
                    'status': 'complete', 'people_potentially_exposed': 1.0},
                'C': C, 'secondary': secondary, 'veto_status': status,
                'veto_reasons': (() if status != 'vetoed' else ('fixture',)),
                'sites': (),
            }

        provider._spatial_assessment = frozen_spatial
        candidates = tuple(self.candidate(0, 0, key) for key in fixture)
        rows = provider.assess_candidates(self.spec.threats[0], candidates, {})
        self.assertEqual(rows['a'].rank_context['tie_band'],
                         POLICY_DEMO_V2['tie_band'])
        self.assertEqual(rows['a'].rank_context['tie_floor'],
                         POLICY_DEMO_V2['tie_floor'])
        self.assertEqual(rows['a'].rank_context['ordered_opportunity_ids'],
                         ['b', 'a', 'c'])
        self.assertEqual((rows['b'].training_cost, rows['a'].training_cost,
                          rows['c'].training_cost), (0.0, 0.5, 1.0))
        self.assertFalse(rows['d'].eligible)

        snapshot = rows['b'].as_dict()
        provider._assessments['b'] = replace(rows['b'], training_cost=1.0)
        evaluated = provider.evaluate_assigned_assessment(
            self.spec.threats[0], candidates[1], snapshot, {})
        self.assertEqual(evaluated.raw_score, 0.0)
        self.assertEqual(evaluated.provenance['assessment_source'],
                         'assignment_snapshot')

    def test_cache_identity_and_identity_changes(self):
        same = SingaporeConsequenceProvider(catalog=self.provider.catalog)
        changed = SingaporeConsequenceProvider(
            catalog=self.provider.catalog, footprint_radius_m=101)
        self.assertEqual(same.config_identity, self.provider.config_identity)
        self.assertNotEqual(changed.config_identity, self.provider.config_identity)
        self.assertEqual(same.cache_identity, self.provider.cache_identity)

    def test_engine_masks_vetoes_and_baseline_handles_every_threat(self):
        provider = SingaporeConsequenceProvider(catalog=self.provider.catalog)
        engine = SimulationEngine(self.spec, provider)
        run = ImmediateInterceptionPolicy().run(engine)
        self.assertTrue(run.terminated)
        self.assertFalse(run.truncated)
        self.assertEqual(len(engine.outcomes), 8)
        self.assertTrue(all(row.resolution.value == 'intercepted'
                            for row in engine.threats.values()))
        self.assertEqual(len(engine.consumed_interceptors), 8)
        self.assertTrue(all(assignment.consequence_snapshot is not None
                            for assignment in engine.assignments.values()))

    def test_unhandled_is_constraint_failure(self):
        result = self.provider.evaluate_unhandled(self.spec.threats[0], {})
        self.assertIsNone(result.raw_score)
        self.assertEqual(result.failure_status,
                         'constraint_failure:unhandled_threat')

    def test_simulation_result_has_3d_trajectories_and_required_wording(self):
        provider = SingaporeConsequenceProvider(catalog=self.provider.catalog)
        engine = SimulationEngine(self.spec, provider)
        baseline = ImmediateInterceptionPolicy().run(engine)
        payload = simulation_result_to_dict(
            engine, baseline_raw_score=baseline.raw_score)
        self.assertEqual(payload['schemaVersion'], 'simulation-result/1')
        self.assertEqual(len(payload['trajectories']), 8)
        self.assertTrue(all(len(row['samples']) == 20
                            for row in payload['trajectories']))
        self.assertEqual(payload['consequenceSummary']['wording'], {
            'area': 'supplied 100 m area',
            'population': 'people potentially exposed',
            'casualties': 'assumption-grade expected casualties',
        })
        self.assertNotIn('optimal', payload['policyVersusBaseline']['claim'])


if __name__ == '__main__':
    unittest.main()
