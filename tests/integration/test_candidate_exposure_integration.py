from dataclasses import asdict
import unittest
from unittest.mock import patch

from backend.domain import (CandidateOpportunity, InterceptorState,
                            SyntheticSuccessProfile, ThreatState)
from backend.exposure import prepare_population
from backend.orchestration.footprint_assessment import assess_footprints
from backend.orchestration.static_scenario import (evaluate_static_scenario,
                                                   trade_space_result_to_dict)


def square_population():
    return prepare_population({
        'schema_version': 'pec-population/1', 'dataset_id': 'square-population',
        'version': '1', 'coordinate_reference_system': 'EPSG:3414',
        'zones': [{
            'zone_id': 'square', 'population': 100,
            'geometry': {'type': 'Polygon', 'coordinates': [[
                [-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]]},
        }],
    })


def opportunity(candidate_id, sample, x):
    return CandidateOpportunity(
        opportunity_id=candidate_id, threat_id='threat', interceptor_id='interceptor',
        sample_index=sample, time_from_start_s=float(sample), position_x_m=x,
        position_y_m=0, reachable=True, minimum_path_length_m=0,
        required_travel_time_s=0, time_margin_s=float(sample))


def adapter_shape(exposure):
    return {
        'event_id': exposure.event_id,
        'footprint_id': exposure.footprint_id,
        'center_x_m': exposure.center_x_m,
        'center_y_m': exposure.center_y_m,
        'radius_m': exposure.radius_m,
        'status': exposure.exposure_status,
        'footprint_area_m2': exposure.footprint_area_m2,
        'uncovered_area_m2': exposure.uncovered_area_m2,
        'covered_area_fraction': exposure.covered_area_fraction,
        'people_potentially_exposed': exposure.people_potentially_exposed,
        'known_area_exposure': exposure.known_area_exposure,
        'zone_breakdown': [asdict(row) for row in exposure.zone_breakdown],
    }


class CandidateExposureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.population = square_population()
        self.opportunities = (opportunity('complete', 1, 0),
                              opportunity('partial', 2, 4.5))
        self.threat = ThreatState('threat', 0, 0, 0, 0, 2)
        self.interceptor = InterceptorState('interceptor', 0, 0, 0, 1, 1)
        self.profile = SyntheticSuccessProfile(.9, .01, .7, 1)

    def evaluate(self):
        with patch('backend.orchestration.static_scenario.generate_candidate_opportunities',
                   return_value=self.opportunities):
            return evaluate_static_scenario(
                self.threat, self.interceptor, self.profile, 1,
                self.population, number_of_samples=2)

    def direct_assessment(self):
        scenario_id = 'threat__interceptor__static-scenario'
        return assess_footprints(self.population, {
            'schema_version': 'footprint-assessment-request/1',
            'assessment_id': scenario_id + '__footprint-assessment',
            'mode': 'alternatives',
            'population_dataset_id': self.population.dataset_id,
            'population_dataset_version': self.population.version,
            'coordinate_reference_system': 'EPSG:3414',
            'records': [{
                'record_id': row.opportunity_id,
                'footprint': {
                    'footprint_id': row.opportunity_id + '__footprint',
                    'center_x_m': row.position_x_m,
                    'center_y_m': row.position_y_m,
                    'radius_m': 1,
                },
            } for row in self.opportunities],
            'comparisons': [],
        })

    def test_join_exactly_matches_direct_adapter_and_preserves_provenance(self):
        result = self.evaluate()
        direct = self.direct_assessment()
        expected = {row['record_id']: row['exposure'] for row in direct['records']}
        for candidate in result.candidates:
            self.assertEqual(adapter_shape(candidate.exposure),
                             expected[candidate.opportunity.opportunity_id])
        self.assertEqual(result.population_exposure_provenance,
                         direct['provenance'])

    def test_complete_and_partial_coverage_attach_with_correct_eligibility(self):
        result = self.evaluate()
        by_id = {row.opportunity.opportunity_id: row for row in result.candidates}
        self.assertEqual(by_id['complete'].exposure.exposure_status, 'complete')
        self.assertTrue(by_id['complete'].eligible)
        self.assertIsNotNone(by_id['complete'].exposure.people_potentially_exposed)
        self.assertEqual(by_id['partial'].exposure.exposure_status, 'partial_coverage')
        self.assertFalse(by_id['partial'].eligible)
        self.assertEqual(by_id['partial'].ineligibility_reasons,
                         ('partial_population_coverage',))
        self.assertIsNone(by_id['partial'].exposure.people_potentially_exposed)
        self.assertGreater(by_id['partial'].exposure.known_area_exposure, 0)
        self.assertEqual(result.complete_coverage_candidates, 1)
        self.assertEqual(result.eligible_candidates, 1)
        self.assertEqual(result.pareto_candidate_ids, ('complete',))

    def test_repeated_deterministic_evidence_is_identical(self):
        first = trade_space_result_to_dict(self.evaluate(), include_diagnostics=False)
        second = trade_space_result_to_dict(self.evaluate(), include_diagnostics=False)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
