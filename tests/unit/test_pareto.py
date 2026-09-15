import unittest

from backend.domain import (CandidateOpportunity, EvaluatedCandidate,
                            PopulationExposureEvidence, SuppliedCircularFootprint)
from backend.trade_space import (EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE,
                                 EXPOSURE_RELATIVE_TOLERANCE,
                                 SUCCESS_ABSOLUTE_TOLERANCE, analyze_pareto,
                                 compare_exposure, compare_success)


def candidate(candidate_id, sample, success, exposure, status='complete'):
    opportunity = CandidateOpportunity(
        opportunity_id=candidate_id, threat_id='threat', interceptor_id='interceptor',
        sample_index=sample, time_from_start_s=float(sample),
        position_x_m=float(sample), position_y_m=0, reachable=True,
        minimum_path_length_m=0, required_travel_time_s=0,
        time_margin_s=float(sample))
    footprint = SuppliedCircularFootprint(candidate_id + '__footprint',
                                          float(sample), 0, 0)
    evidence = PopulationExposureEvidence(
        event_id=candidate_id, footprint_id=footprint.footprint_id,
        center_x_m=float(sample), center_y_m=0, radius_m=0,
        exposure_status=status, footprint_area_m2=0, uncovered_area_m2=0,
        covered_area_fraction=None,
        people_potentially_exposed=exposure if status == 'complete' else None,
        known_area_exposure=exposure, zone_breakdown=())
    reasons = () if status == 'complete' else ('partial_population_coverage',)
    return EvaluatedCandidate(opportunity, success, footprint, evidence, reasons)


class ParetoTests(unittest.TestCase):
    def test_clear_dominance_and_all_dominator_evidence(self):
        rows = (candidate('A', 1, .95, 100), candidate('B', 2, .90, 200),
                candidate('C', 3, .92, 150))
        result = analyze_pareto(rows)
        self.assertEqual(result.pareto_candidate_ids, ('A',))
        evidence = {row.candidate_id: row for row in result.candidate_evidence}
        self.assertEqual(evidence['B'].dominated_by_candidate_ids, ('A', 'C'))
        self.assertEqual(evidence['C'].dominated_by_candidate_ids, ('A',))

    def test_success_exposure_tradeoff_is_not_dominance(self):
        result = analyze_pareto((candidate('A', 1, .95, 500),
                                 candidate('B', 2, .90, 100)))
        self.assertEqual(result.pareto_candidate_ids, ('A', 'B'))

    def test_equal_success_prefers_lower_exposure(self):
        result = analyze_pareto((candidate('A', 1, .9, 100),
                                 candidate('B', 2, .9, 200)))
        self.assertEqual(result.pareto_candidate_ids, ('A',))

    def test_equal_exposure_prefers_higher_success(self):
        result = analyze_pareto((candidate('A', 1, .95, 100),
                                 candidate('B', 2, .9, 100)))
        self.assertEqual(result.pareto_candidate_ids, ('A',))

    def test_exact_duplicates_remain_efficient_with_equivalence_evidence(self):
        result = analyze_pareto((candidate('A', 1, .9, 100),
                                 candidate('B', 2, .9, 100)))
        self.assertEqual(result.pareto_candidate_ids, ('A', 'B'))
        evidence = {row.candidate_id: row for row in result.candidate_evidence}
        self.assertEqual(evidence['A'].equivalent_candidate_ids, ('B',))
        self.assertEqual(evidence['B'].equivalent_candidate_ids, ('A',))

    def test_success_tolerance_immediately_inside_and_outside(self):
        inside = SUCCESS_ABSOLUTE_TOLERANCE * .5
        outside = SUCCESS_ABSOLUTE_TOLERANCE * 2
        self.assertEqual(compare_success(.9, .9 - inside), 0)
        self.assertEqual(compare_success(.9, .9 - outside), 1)
        self.assertEqual(analyze_pareto((candidate('A', 1, .9, 100),
                                        candidate('B', 2, .9-inside, 100))).pareto_candidate_ids,
                         ('A', 'B'))
        self.assertEqual(analyze_pareto((candidate('A', 1, .9, 100),
                                        candidate('B', 2, .9-outside, 100))).pareto_candidate_ids,
                         ('A',))

    def test_exposure_absolute_tolerance_immediately_inside_and_outside(self):
        inside = EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE * .5
        outside = EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE * 2
        self.assertEqual(compare_exposure(100, 100 + inside), 0)
        self.assertEqual(compare_exposure(100, 100 + outside), -1)
        self.assertEqual(analyze_pareto((candidate('A', 1, .9, 100),
                                        candidate('B', 2, .9, 100+inside))).pareto_candidate_ids,
                         ('A', 'B'))
        self.assertEqual(analyze_pareto((candidate('A', 1, .9, 100),
                                        candidate('B', 2, .9, 100+outside))).pareto_candidate_ids,
                         ('A',))

    def test_exposure_relative_tolerance_immediately_inside_and_outside(self):
        scale = 1e9
        tolerance = EXPOSURE_RELATIVE_TOLERANCE * scale
        self.assertEqual(compare_exposure(scale, scale + tolerance*.5), 0)
        self.assertEqual(compare_exposure(scale, scale + tolerance*2), -1)

    def test_partial_coverage_is_not_eligible_for_pareto(self):
        result = analyze_pareto((candidate('A', 1, .9, 100),
                                 candidate('B', 2, .99, 1, 'partial_coverage')))
        self.assertEqual(result.pareto_candidate_ids, ('A',))
        self.assertEqual([row.candidate_id for row in result.candidate_evidence], ['A'])

    def test_input_order_does_not_change_canonical_output(self):
        a, b = candidate('A', 1, .95, 500), candidate('B', 2, .9, 100)
        self.assertEqual(analyze_pareto((b, a)), analyze_pareto((a, b)))


if __name__ == '__main__':
    unittest.main()
