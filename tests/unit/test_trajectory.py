from dataclasses import asdict
import json
import unittest

from backend.domain import ThreatState
from backend.planning import sample_threat_trajectory


class TrajectoryTests(unittest.TestCase):
    def test_constant_velocity_coordinates_and_sample_times(self):
        threat = ThreatState('threat-1', 100, -50, 3, -4, 10)
        samples = sample_threat_trajectory(threat, 5)
        self.assertEqual([sample.time_from_start_s for sample in samples], [2, 4, 6, 8, 10])
        self.assertEqual([(sample.position_x_m, sample.position_y_m) for sample in samples],
                         [(106, -58), (112, -66), (118, -74), (124, -82), (130, -90)])
        self.assertEqual([sample.sample_index for sample in samples], [1, 2, 3, 4, 5])

    def test_default_and_configurable_sample_counts(self):
        threat = ThreatState('threat-1', 0, 0, 1, 1, 10)
        self.assertEqual(len(sample_threat_trajectory(threat)), 50)
        for count in (1, 5, 100):
            with self.subTest(count=count):
                self.assertEqual(len(sample_threat_trajectory(threat, count)), count)

    def test_zero_time_to_go_returns_no_future_samples(self):
        threat = ThreatState('threat-1', 0, 0, 1, 1, 0)
        self.assertEqual(sample_threat_trajectory(threat), ())

    def test_determinism(self):
        threat = ThreatState('threat-1', 2.5, -7.25, 11.5, 3.75, 13)
        first = sample_threat_trajectory(threat)
        second = sample_threat_trajectory(threat)
        self.assertEqual(first, second)
        encode = lambda rows: json.dumps([asdict(row) for row in rows], separators=(',', ':'), allow_nan=False)
        self.assertEqual(encode(first), encode(second))

    def test_invalid_count_and_numeric_overflow(self):
        threat = ThreatState('threat-1', 0, 0, 1, 1, 10)
        for count in (0, -1, True, 1.0, None):
            with self.subTest(count=count), self.assertRaises(ValueError):
                sample_threat_trajectory(threat, count)
        overflowing = ThreatState('threat-1', 1e308, 0, 1e308, 0, 10)
        with self.assertRaisesRegex(ValueError, 'finite numeric range'):
            sample_threat_trajectory(overflowing)


if __name__ == '__main__':
    unittest.main()
