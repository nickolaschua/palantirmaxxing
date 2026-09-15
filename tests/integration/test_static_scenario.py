import json
from pathlib import Path
import unittest

from backend.domain import InterceptorState, SyntheticSuccessProfile, ThreatState
from backend.exposure import prepare_population
from backend.orchestration import (evaluate_static_scenario,
                                   trade_space_result_to_dict)
from backend.scenario import evaluate_synthetic_success

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / 'data' / 'scenarios' / 'static-mvp-scenario.json'


def load_fixture():
    scenario = json.loads(SCENARIO.read_text())
    population = prepare_population(json.loads(
        (ROOT / scenario['population_fixture']).read_text()))
    return scenario, population


def evaluate_fixture():
    scenario, population = load_fixture()
    return evaluate_static_scenario(
        ThreatState(**scenario['threat']),
        InterceptorState(**scenario['interceptor']),
        SyntheticSuccessProfile(**scenario['synthetic_success_profile']),
        scenario['footprint_radius_m'], population,
        scenario['number_of_samples'])


class StaticScenarioIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario, _ = load_fixture()
        cls.result = evaluate_fixture()

    def test_full_pipeline_counts_and_reachability_pattern(self):
        self.assertEqual(self.result.total_candidates, 50)
        self.assertEqual(self.result.reachable_candidates, 36)
        self.assertEqual(self.result.complete_coverage_candidates, 36)
        self.assertEqual(self.result.eligible_candidates, 36)
        self.assertEqual([row.sample_index for row in self.result.candidate_opportunities],
                         list(range(1, 51)))
        self.assertTrue(all(not row.reachable
                            for row in self.result.candidate_opportunities[:14]))
        self.assertTrue(all(row.reachable
                            for row in self.result.candidate_opportunities[14:]))

    def test_every_reachable_candidate_has_complete_supplied_evidence(self):
        profile = SyntheticSuccessProfile(
            **self.scenario['synthetic_success_profile'])
        self.assertEqual(len(self.result.candidates), 36)
        for candidate in self.result.candidates:
            opportunity = candidate.opportunity
            self.assertEqual(candidate.supplied_success_probability,
                             evaluate_synthetic_success(
                                 profile, opportunity.time_from_start_s))
            self.assertEqual(candidate.footprint.center_x_m,
                             opportunity.position_x_m)
            self.assertEqual(candidate.footprint.center_y_m,
                             opportunity.position_y_m)
            self.assertEqual(candidate.footprint.radius_m, 500)
            self.assertEqual(candidate.exposure.exposure_status, 'complete')
            self.assertIsNotNone(candidate.exposure.people_potentially_exposed)
            self.assertTrue(candidate.eligible)

    def test_pareto_and_representative_categories_are_deterministic(self):
        assignments = self.result.category_assignments
        self.assertTrue(self.result.pareto_candidate_ids)
        self.assertEqual(assignments.earliest_viable, assignments.highest_success)
        self.assertNotEqual(assignments.earliest_viable, assignments.lowest_exposure)
        self.assertEqual(self.result.representative_candidate_ids,
                         (assignments.earliest_viable, assignments.lowest_exposure))
        by_id = {row.opportunity.opportunity_id: row for row in self.result.candidates}
        early = by_id[assignments.earliest_viable]
        low = by_id[assignments.lowest_exposure]
        self.assertGreater(low.opportunity.time_from_start_s, early.opportunity.time_from_start_s)
        self.assertLess(low.supplied_success_probability, early.supplied_success_probability)
        self.assertLess(low.exposure.people_potentially_exposed,
                        early.exposure.people_potentially_exposed * 0.5)
        self.assertGreater(len(set((assignments.earliest_viable,
                                    assignments.highest_success,
                                    assignments.lowest_exposure))), 1)

    def test_representative_records_contain_complete_evidence(self):
        by_id = {row.opportunity.opportunity_id: row
                 for row in self.result.candidates}
        for candidate_id in self.result.representative_candidate_ids:
            candidate = by_id[candidate_id]
            self.assertTrue(candidate.eligible)
            self.assertIsNotNone(candidate.supplied_success_probability)
            self.assertIsNotNone(candidate.exposure.people_potentially_exposed)
            self.assertEqual(candidate.exposure.exposure_status, 'complete')
            self.assertTrue(candidate.exposure.zone_breakdown)

    def test_serialized_result_is_complete_and_repeated_evidence_is_deterministic(self):
        evidence = trade_space_result_to_dict(
            self.result, include_diagnostics=False)
        self.assertEqual(len(evidence['candidate_opportunities']), 50)
        self.assertEqual(len(evidence['candidates']), 36)
        self.assertTrue(all('pareto_efficient' in row
                            and 'categories' in row
                            and 'dominated_by_candidate_ids' in row
                            and 'equivalent_candidate_ids' in row
                            for row in evidence['candidates']))
        repeated = trade_space_result_to_dict(
            evaluate_fixture(), include_diagnostics=False)
        self.assertEqual(evidence, repeated)


if __name__ == '__main__':
    unittest.main()
