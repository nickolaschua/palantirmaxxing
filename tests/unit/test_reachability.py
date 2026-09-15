import math
import unittest

from backend.domain import InterceptorState, TrajectorySample
from backend.planning import (REACHABILITY_TIME_TOLERANCE_S,
                              evaluate_candidate_reachability,
                              minimum_bounded_curvature_path_length)


def interceptor(heading=0, speed=20, turn_rate=2):
    return InterceptorState('interceptor-1', 0, 0, heading, speed, turn_rate)


class ReachabilityTests(unittest.TestCase):
    def test_straight_ahead_matches_euclidean_distance(self):
        self.assertAlmostEqual(minimum_bounded_curvature_path_length(interceptor(), 100, 0), 100)

    def test_behind_requires_more_than_euclidean_distance(self):
        length = minimum_bounded_curvature_path_length(interceptor(), -100, 0)
        self.assertGreater(length, 100)

    def test_nearby_but_impossible_and_far_with_enough_time(self):
        state = interceptor()
        near = evaluate_candidate_reachability('threat-1', state, TrajectorySample(1, 0.01, 1, 0))
        far = evaluate_candidate_reachability('threat-1', state, TrajectorySample(2, 10, 100, 0))
        self.assertFalse(near.reachable)
        self.assertLess(near.time_margin_s, 0)
        self.assertTrue(far.reachable)
        self.assertGreater(far.time_margin_s, 0)

    def test_higher_turn_rate_never_increases_path_length(self):
        points = [(0, 50), (-20, 10), (20, -10), (-100, 0), (100, 100)]
        lower = interceptor(speed=20, turn_rate=0.5)
        higher = interceptor(speed=20, turn_rate=2.0)
        for point in points:
            with self.subTest(point=point):
                low_length = minimum_bounded_curvature_path_length(lower, *point)
                high_length = minimum_bounded_curvature_path_length(higher, *point)
                self.assertLessEqual(high_length, low_length + 1e-9)

    def test_heading_alignment_is_easier_at_equal_distance(self):
        state = interceptor()
        ahead = minimum_bounded_curvature_path_length(state, 100, 0)
        side = minimum_bounded_curvature_path_length(state, 0, 100)
        behind = minimum_bounded_curvature_path_length(state, -100, 0)
        self.assertLess(ahead, side)
        self.assertLess(ahead, behind)

    def test_reachability_boundary_uses_documented_time_tolerance(self):
        state = interceptor()
        length = minimum_bounded_curvature_path_length(state, 100, 0)
        required = length / state.speed_mps
        exactly = evaluate_candidate_reachability(
            'threat-1', state, TrajectorySample(1, required, 100, 0))
        within = evaluate_candidate_reachability(
            'threat-1', state,
            TrajectorySample(1, required - REACHABILITY_TIME_TOLERANCE_S / 2, 100, 0))
        outside = evaluate_candidate_reachability(
            'threat-1', state,
            TrajectorySample(1, required - REACHABILITY_TIME_TOLERANCE_S * 2, 100, 0))
        self.assertTrue(exactly.reachable)
        self.assertTrue(within.reachable)
        self.assertFalse(outside.reachable)
        self.assertAlmostEqual(exactly.time_margin_s, 0)

    def test_inside_turning_disc_and_left_right_symmetry(self):
        state = interceptor(speed=10, turn_rate=1)
        left = minimum_bounded_curvature_path_length(state, 0, 10)
        right = minimum_bounded_curvature_path_length(state, 0, -10)
        self.assertAlmostEqual(left, right)
        self.assertGreater(left, 10)

    def test_turning_circle_boundary_is_stable_under_coordinate_transforms(self):
        canonical = InterceptorState('interceptor-1', 0, 0, 0, 1, 1)
        self.assertAlmostEqual(
            minimum_bounded_curvature_path_length(canonical, 1, 1), math.pi / 2)
        self.assertAlmostEqual(
            minimum_bounded_curvature_path_length(canonical, 1, -1), math.pi / 2)

        # Regression: this analytic boundary point recovered just inside the
        # circle before boundary-band handling was introduced.
        origin = (-5000.0, 3000.0)
        heading = -2.4
        transformed = InterceptorState('interceptor-1', *origin, heading, 1, 1)
        cosine, sine = math.cos(heading), math.sin(heading)
        for local_y in (1.0, -1.0):
            target_x = origin[0] + cosine - sine * local_y
            target_y = origin[1] + sine + cosine * local_y
            with self.subTest(local_y=local_y):
                self.assertAlmostEqual(
                    minimum_bounded_curvature_path_length(transformed, target_x, target_y),
                    math.pi / 2, places=10)

    def test_points_immediately_inside_and_outside_turning_circle_boundary(self):
        state = InterceptorState('interceptor-1', 0, 0, 0, 1, 1)
        for local_y in (1.0, -1.0):
            for delta in (-5e-13, 5e-13):
                with self.subTest(local_y=local_y, delta=delta):
                    length = minimum_bounded_curvature_path_length(
                        state, 1.0 + delta, local_y)
                    self.assertAlmostEqual(length, math.pi / 2, places=10)

            inside = minimum_bounded_curvature_path_length(state, 1.0 - 1e-8, local_y)
            outside = minimum_bounded_curvature_path_length(state, 1.0 + 1e-8, local_y)
            self.assertGreater(inside, outside + 1.0)
            self.assertAlmostEqual(outside, math.pi / 2, places=7)

    def test_target_at_start_has_zero_path_and_rotated_pose_is_invariant(self):
        state = InterceptorState('interceptor-1', 30, -20, 1.25, 10, 1)
        self.assertEqual(minimum_bounded_curvature_path_length(state, 30, -20), 0)
        distance = 100
        target = (30 + distance * math.cos(1.25), -20 + distance * math.sin(1.25))
        self.assertAlmostEqual(minimum_bounded_curvature_path_length(state, *target), distance)

    def test_path_is_not_shorter_than_euclidean_distance(self):
        state = interceptor(speed=10, turn_rate=1)
        for point in [(10, 0), (0, 10), (-10, 0), (3, 7), (-30, -20), (100, 20)]:
            with self.subTest(point=point):
                path = minimum_bounded_curvature_path_length(state, *point)
                self.assertGreaterEqual(path + 1e-10, math.hypot(*point))

    def test_invalid_target_and_argument_types(self):
        state = interceptor()
        for x, y in [(float('nan'), 0), (0, float('inf')), (True, 0)]:
            with self.subTest(x=x, y=y), self.assertRaises(ValueError):
                minimum_bounded_curvature_path_length(state, x, y)
        with self.assertRaises(ValueError):
            minimum_bounded_curvature_path_length(None, 0, 0)
        with self.assertRaises(ValueError):
            evaluate_candidate_reachability('threat-1', state, None)
        imprecise = InterceptorState('interceptor-1', 1e16, 1e16, 0, 1, 1)
        with self.assertRaisesRegex(ValueError, 'coordinate precision'):
            minimum_bounded_curvature_path_length(imprecise, 1e16 + 100, 1e16)


if __name__ == '__main__':
    unittest.main()
