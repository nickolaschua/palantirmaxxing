from dataclasses import asdict
import json
import math
import unittest

from backend.domain import InterceptorState, ThreatState
from backend.planning import generate_candidate_opportunities


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.threat = ThreatState('threat-1', 500, 200, 10, 0, 20)
        self.interceptor = InterceptorState(
            'interceptor-1', 0, 0, 0, 100, math.radians(15))

    def test_default_generation_retains_all_samples_and_stable_ids(self):
        opportunities = generate_candidate_opportunities(self.threat, self.interceptor)
        self.assertEqual(len(opportunities), 50)
        self.assertEqual(opportunities[0].opportunity_id, 'threat-1__interceptor-1__k1')
        self.assertEqual(opportunities[-1].opportunity_id, 'threat-1__interceptor-1__k50')
        self.assertTrue(any(not row.reachable for row in opportunities))
        self.assertTrue(any(row.reachable for row in opportunities))

    def test_metrics_and_identity_are_propagated(self):
        row = generate_candidate_opportunities(self.threat, self.interceptor, 1)[0]
        self.assertEqual(row.threat_id, self.threat.threat_id)
        self.assertEqual(row.interceptor_id, self.interceptor.interceptor_id)
        self.assertAlmostEqual(row.required_travel_time_s,
                               row.minimum_path_length_m / self.interceptor.speed_mps)
        self.assertAlmostEqual(row.time_margin_s,
                               row.time_from_start_s - row.required_travel_time_s)

    def test_zero_time_to_go_and_determinism(self):
        stopped = ThreatState('threat-1', 0, 0, 0, 0, 0)
        self.assertEqual(generate_candidate_opportunities(stopped, self.interceptor), ())
        first = generate_candidate_opportunities(self.threat, self.interceptor)
        second = generate_candidate_opportunities(self.threat, self.interceptor)
        self.assertEqual(first, second)
        encode = lambda rows: json.dumps([asdict(row) for row in rows], separators=(',', ':'), allow_nan=False)
        self.assertEqual(encode(first), encode(second))

    def test_inputs_are_not_mutated_and_invalid_count_is_rejected(self):
        before = (self.threat, self.interceptor)
        generate_candidate_opportunities(self.threat, self.interceptor, 5)
        self.assertEqual(before, (self.threat, self.interceptor))
        for count in (0, -1, True, 5.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                generate_candidate_opportunities(self.threat, self.interceptor, count)


if __name__ == '__main__':
    unittest.main()
