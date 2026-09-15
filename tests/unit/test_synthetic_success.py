import math
import unittest

from backend.domain import SyntheticSuccessProfile
from backend.scenario import evaluate_synthetic_success


class SyntheticSuccessTests(unittest.TestCase):
    def test_time_zero_returns_configured_initial_value(self):
        profile = SyntheticSuccessProfile(.83, .01, .7, .9)
        self.assertEqual(evaluate_synthetic_success(profile, 0), .83)

    def test_linear_decrease_and_monotonic_nonincrease(self):
        profile = SyntheticSuccessProfile(.97, .004, .7, 1)
        values = [evaluate_synthetic_success(profile, time_s)
                  for time_s in (0, 1, 2.5, 20, 100)]
        self.assertEqual(values[1], .966)
        self.assertEqual(values[2], .96)
        self.assertTrue(all(first >= second
                            for first, second in zip(values, values[1:])))

    def test_lower_and_upper_bounds_are_respected(self):
        profile = SyntheticSuccessProfile(.8, .2, .7, .8)
        self.assertEqual(evaluate_synthetic_success(profile, 0), .8)
        self.assertEqual(evaluate_synthetic_success(profile, 100), .7)
        extreme = SyntheticSuccessProfile(1, 1e308, 0, 1)
        self.assertEqual(evaluate_synthetic_success(extreme, 1e308), 0)

    def test_invalid_profile_probabilities_are_rejected(self):
        fields = ('initial_success_probability', 'minimum_success_probability',
                  'maximum_success_probability')
        baseline = dict(initial_success_probability=.8, decrease_per_second=.01,
                        minimum_success_probability=.7,
                        maximum_success_probability=.9)
        for field in fields:
            for value in (-.1, 1.1, True, float('nan'), float('inf'),
                          float('-inf'), 10**400):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    SyntheticSuccessProfile(**dict(baseline, **{field: value}))

    def test_inconsistent_initial_and_bounds_are_rejected(self):
        for values in ((.69, .7, .9), (.91, .7, .9), (.8, .9, .7)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SyntheticSuccessProfile(values[0], .01, values[1], values[2])

    def test_invalid_decrease_is_rejected(self):
        for value in (-.001, True, float('nan'), float('inf'), float('-inf'),
                      10**400):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SyntheticSuccessProfile(.8, value, .7, .9)

    def test_invalid_time_is_rejected(self):
        profile = SyntheticSuccessProfile()
        for value in (-1, True, float('nan'), float('inf'), float('-inf'),
                      10**400):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_synthetic_success(profile, value)

    def test_repeated_output_is_exactly_deterministic(self):
        profile = SyntheticSuccessProfile()
        first = [evaluate_synthetic_success(profile, value / 7) for value in range(50)]
        second = [evaluate_synthetic_success(profile, value / 7) for value in range(50)]
        self.assertEqual(first, second)
        self.assertTrue(all(math.isfinite(value) and .7 <= value <= 1 for value in first))


if __name__ == '__main__':
    unittest.main()
