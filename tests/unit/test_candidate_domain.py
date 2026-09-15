import math
import unittest

from backend.domain import CandidateOpportunity, InterceptorState, ThreatState, TrajectorySample


class CandidateDomainTests(unittest.TestCase):
    def test_valid_threat(self):
        threat = ThreatState('threat-1', 10, -20, 30, 40, 50)
        self.assertEqual(threat.threat_id, 'threat-1')
        self.assertEqual(threat.maximum_time_to_go_s, 50)

    def test_invalid_threat_time_and_coordinates(self):
        with self.assertRaisesRegex(ValueError, 'nonnegative'):
            ThreatState('threat-1', 0, 0, 0, 0, -1)
        for field, value in [('position_x_m', float('nan')),
                             ('position_y_m', float('inf')),
                             ('velocity_x_mps', float('-inf')),
                             ('velocity_y_mps', True),
                             ('maximum_time_to_go_s', float('nan'))]:
            values = dict(threat_id='threat-1', position_x_m=0, position_y_m=0,
                          velocity_x_mps=0, velocity_y_mps=0, maximum_time_to_go_s=10)
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                ThreatState(**values)

    def test_invalid_interceptor_speed_and_turn_rate(self):
        for field, values in [('speed_mps', (0, -1, float('inf'), True)),
                              ('max_turn_rate_rad_s', (0, -1, float('nan'), False))]:
            for value in values:
                state = dict(interceptor_id='interceptor-1', position_x_m=0, position_y_m=0,
                             heading_rad=0, speed_mps=100, max_turn_rate_rad_s=1)
                state[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    InterceptorState(**state)
        with self.assertRaisesRegex(ValueError, 'turning radius'):
            InterceptorState('interceptor-1', 0, 0, 0, 1e308, 1e-308)

    def test_heading_normalization(self):
        def heading(value):
            return InterceptorState('interceptor-1', 0, 0, value, 100, 1).heading_rad

        self.assertEqual(heading(0), 0.0)
        self.assertEqual(heading(math.tau), 0.0)
        self.assertAlmostEqual(heading(-math.pi / 2), 3 * math.pi / 2)
        self.assertAlmostEqual(heading(5 * math.pi), math.pi)
        for value in (float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                heading(value)

    def test_identifiers_and_generated_record_shapes_are_strict(self):
        with self.assertRaises(ValueError):
            ThreatState(' ', 0, 0, 0, 0, 1)
        with self.assertRaises(ValueError):
            InterceptorState('', 0, 0, 0, 1, 1)
        with self.assertRaises(ValueError):
            TrajectorySample(0, 1, 0, 0)
        with self.assertRaises(ValueError):
            TrajectorySample(1, 0, 0, 0)
        with self.assertRaises(ValueError):
            CandidateOpportunity('o', 't', 'i', 1, 1, 0, 0, True, None, None, None)
        with self.assertRaises(ValueError):
            CandidateOpportunity('o', 't', 'i', 1, 1, 0, 0, False, 1, None, -1)


if __name__ == '__main__':
    unittest.main()
