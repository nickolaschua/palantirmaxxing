from dataclasses import asdict
import unittest
from unittest.mock import patch

from backend.domain import (CandidateOpportunity, InterceptorState,
                            SyntheticSuccessProfile, ThreatState)
from backend.exposure import prepare_population
from backend.orchestration.static_scenario import evaluate_static_scenario
from backend.scenario import build_supplied_circular_footprint


def opportunity(reachable=True):
    return CandidateOpportunity(
        opportunity_id='threat__interceptor__k1', threat_id='threat',
        interceptor_id='interceptor', sample_index=1, time_from_start_s=1,
        position_x_m=12.5, position_y_m=-7.25, reachable=reachable,
        minimum_path_length_m=1, required_travel_time_s=1,
        time_margin_s=0 if reachable else -1)


class CandidateEnrichmentTests(unittest.TestCase):
    def test_supplied_footprint_copies_center_radius_and_deterministic_id(self):
        candidate = opportunity()
        footprint = build_supplied_circular_footprint(candidate, 3.5)
        self.assertEqual(footprint.center_x_m, candidate.position_x_m)
        self.assertEqual(footprint.center_y_m, candidate.position_y_m)
        self.assertEqual(footprint.radius_m, 3.5)
        self.assertEqual(footprint.footprint_id,
                         candidate.opportunity_id + '__footprint')
        self.assertEqual(footprint,
                         build_supplied_circular_footprint(candidate, 3.5))

    def test_invalid_radius_is_rejected(self):
        for value in (-1, True, float('nan'), float('inf'), float('-inf'),
                      10**400):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_supplied_circular_footprint(opportunity(), value)

    def test_pipeline_rejects_invalid_radius_even_without_reachable_candidates(self):
        population = prepare_population({
            'schema_version': 'pec-population/1', 'dataset_id': 'population',
            'version': '1', 'coordinate_reference_system': 'EPSG:3414',
            'zones': []})
        threat = ThreatState('threat', 0, 0, 0, 0, 0)
        interceptor = InterceptorState('interceptor', 0, 0, 0, 1, 1)
        for value in (-1, True, float('nan'), float('inf'), 10**400):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_static_scenario(
                    threat, interceptor, SyntheticSuccessProfile(), value,
                    population, 1)

    def test_zero_radius_is_supported_consistently_with_pec(self):
        self.assertEqual(build_supplied_circular_footprint(opportunity(), 0).radius_m, 0)

    def test_original_candidate_is_not_mutated(self):
        candidate = opportunity()
        before = asdict(candidate)
        build_supplied_circular_footprint(candidate, 5)
        self.assertEqual(asdict(candidate), before)

    def test_unreachable_candidate_is_not_submitted_for_assessment(self):
        population = prepare_population({
            'schema_version': 'pec-population/1', 'dataset_id': 'population',
            'version': '1', 'coordinate_reference_system': 'EPSG:3414',
            'zones': []})
        assessment = {
            'schema_version': 'footprint-assessment-result/1',
            'assessment_id': 'unused', 'mode': 'alternatives', 'status': 'complete',
            'records': [], 'comparisons': [], 'summary': {}, 'provenance': {}}
        threat = ThreatState('threat', 0, 0, 0, 0, 1)
        interceptor = InterceptorState('interceptor', 0, 0, 0, 1, 1)
        with patch('backend.orchestration.static_scenario.generate_candidate_opportunities',
                   return_value=(opportunity(False),)), patch(
                       'backend.orchestration.static_scenario.assess_footprints',
                       return_value=assessment) as assess:
            result = evaluate_static_scenario(
                threat, interceptor, SyntheticSuccessProfile(), 1, population, 1)
        self.assertEqual(result.reachable_candidates, 0)
        self.assertEqual(result.candidates, ())
        self.assertEqual(assess.call_args.args[1]['records'], [])


if __name__ == '__main__':
    unittest.main()
