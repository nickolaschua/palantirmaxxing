from dataclasses import asdict
import json
import math
import unittest

from backend.domain import InterceptorState, ThreatState
from backend.planning import REACHABILITY_TIME_TOLERANCE_S, generate_candidate_opportunities


class CandidateOpportunityIntegrationTests(unittest.TestCase):
    def test_deterministic_unreachable_to_reachable_scenario(self):
        # All values are synthetic simulation inputs, not operational performance data.
        threat = ThreatState('synthetic-threat', 500, 200, 10, 0, 20)
        interceptor = InterceptorState(
            'synthetic-interceptor', 0, 0, 0, 100, math.radians(15))
        rows = generate_candidate_opportunities(threat, interceptor)

        self.assertEqual(len(rows), 50)
        self.assertEqual([row.sample_index for row in rows], list(range(1, 51)))
        self.assertEqual(rows[0].opportunity_id,
                         'synthetic-threat__synthetic-interceptor__k1')
        self.assertEqual(rows[-1].opportunity_id,
                         'synthetic-threat__synthetic-interceptor__k50')
        self.assertTrue(all(a.time_from_start_s < b.time_from_start_s
                            for a, b in zip(rows, rows[1:])))
        for row in rows:
            self.assertAlmostEqual(row.position_x_m, 500 + 10 * row.time_from_start_s)
            self.assertEqual(row.position_y_m, 200)
            self.assertAlmostEqual(row.time_margin_s,
                                   row.time_from_start_s - row.required_travel_time_s)
            if row.reachable:
                self.assertGreaterEqual(row.time_margin_s, -REACHABILITY_TIME_TOLERANCE_S)
            else:
                self.assertLess(row.time_margin_s, -REACHABILITY_TIME_TOLERANCE_S)

        flags = [row.reachable for row in rows]
        first_reachable = flags.index(True)
        self.assertEqual(first_reachable + 1, 15)
        self.assertEqual(flags[:first_reachable], [False] * first_reachable)
        self.assertEqual(flags[first_reachable:], [True] * (len(flags) - first_reachable))
        encoded = lambda values: json.dumps([asdict(row) for row in values], separators=(',', ':'), allow_nan=False)
        self.assertEqual(encoded(rows), encoded(generate_candidate_opportunities(threat, interceptor)))


if __name__ == '__main__':
    unittest.main()
