"""Independent numerical verification of the free-terminal-heading synthesis.

The reference computes all six fixed-terminal-heading Dubins families, samples
the terminal heading over a dense full-circle grid, then refines the best grid
interval. It intentionally shares no geometric construction with production.
"""
import math
import unittest

from backend.domain import InterceptorState
from backend.planning import (GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE,
                              minimum_bounded_curvature_path_length)

_TAU = 2.0 * math.pi
_REFERENCE_GRID_SIZE = 4096


def _mod(angle):
    return angle % _TAU


def _nonnegative_sqrt(value):
    if value < -GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE:
        return None
    return math.sqrt(max(0.0, value))


def _lsl(alpha, beta, distance):
    straight = _nonnegative_sqrt(
        2 + distance ** 2 - 2 * math.cos(alpha - beta)
        + 2 * distance * (math.sin(alpha) - math.sin(beta)))
    if straight is None:
        return None
    tangent = math.atan2(math.cos(beta) - math.cos(alpha),
                         distance + math.sin(alpha) - math.sin(beta))
    return _mod(-alpha + tangent) + straight + _mod(beta - tangent)


def _rsr(alpha, beta, distance):
    straight = _nonnegative_sqrt(
        2 + distance ** 2 - 2 * math.cos(alpha - beta)
        + 2 * distance * (math.sin(beta) - math.sin(alpha)))
    if straight is None:
        return None
    tangent = math.atan2(math.cos(alpha) - math.cos(beta),
                         distance - math.sin(alpha) + math.sin(beta))
    return _mod(alpha - tangent) + straight + _mod(-beta + tangent)


def _lsr(alpha, beta, distance):
    straight = _nonnegative_sqrt(
        -2 + distance ** 2 + 2 * math.cos(alpha - beta)
        + 2 * distance * (math.sin(alpha) + math.sin(beta)))
    if straight is None:
        return None
    tangent = (math.atan2(-math.cos(alpha) - math.cos(beta),
                          distance + math.sin(alpha) + math.sin(beta))
               - math.atan2(-2.0, straight))
    return _mod(-alpha + tangent) + straight + _mod(-beta + tangent)


def _rsl(alpha, beta, distance):
    straight = _nonnegative_sqrt(
        -2 + distance ** 2 + 2 * math.cos(alpha - beta)
        - 2 * distance * (math.sin(alpha) + math.sin(beta)))
    if straight is None:
        return None
    tangent = (math.atan2(math.cos(alpha) + math.cos(beta),
                          distance - math.sin(alpha) - math.sin(beta))
               - math.atan2(2.0, straight))
    return _mod(alpha - tangent) + straight + _mod(beta - tangent)


def _rlr(alpha, beta, distance):
    cosine = (6 - distance ** 2 + 2 * math.cos(alpha - beta)
              + 2 * distance * (math.sin(alpha) - math.sin(beta))) / 8.0
    if not (-1.0 - GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE <= cosine
            <= 1.0 + GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE):
        return None
    middle = _mod(_TAU - math.acos(max(-1.0, min(1.0, cosine))))
    first = _mod(alpha - math.atan2(math.cos(alpha) - math.cos(beta),
                                    distance - math.sin(alpha) + math.sin(beta))
                 + middle / 2.0)
    return first + middle + _mod(alpha - beta - first + middle)


def _lrl(alpha, beta, distance):
    cosine = (6 - distance ** 2 + 2 * math.cos(alpha - beta)
              + 2 * distance * (-math.sin(alpha) + math.sin(beta))) / 8.0
    if not (-1.0 - GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE <= cosine
            <= 1.0 + GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE):
        return None
    middle = _mod(_TAU - math.acos(max(-1.0, min(1.0, cosine))))
    first = _mod(-alpha - math.atan2(math.cos(alpha) - math.cos(beta),
                                     distance + math.sin(alpha) - math.sin(beta))
                 + middle / 2.0)
    return first + middle + _mod(beta - alpha - first + middle)


_POSE_FAMILIES = (_lsl, _rsr, _lsr, _rsl, _rlr, _lrl)


def fixed_heading_reference_length(local_x, local_y, terminal_heading):
    """Independent unit-radius shortest Dubins pose-to-pose length."""
    distance = math.hypot(local_x, local_y)
    bearing = math.atan2(local_y, local_x)
    alpha = _mod(-bearing)
    beta = _mod(terminal_heading - bearing)
    candidates = [family(alpha, beta, distance) for family in _POSE_FAMILIES]
    return min(value for value in candidates if value is not None)


def free_heading_reference_length(local_x, local_y, radius=1.0):
    """Numerically minimize the independent pose solver over terminal heading."""
    values = [fixed_heading_reference_length(local_x, local_y, _TAU * i / _REFERENCE_GRID_SIZE)
              for i in range(_REFERENCE_GRID_SIZE)]
    best_index = min(range(_REFERENCE_GRID_SIZE), key=values.__getitem__)
    step = _TAU / _REFERENCE_GRID_SIZE
    lower = (best_index - 1) * step
    upper = (best_index + 1) * step
    golden = (math.sqrt(5.0) - 1.0) / 2.0
    left = upper - golden * (upper - lower)
    right = lower + golden * (upper - lower)
    left_value = fixed_heading_reference_length(local_x, local_y, left % _TAU)
    right_value = fixed_heading_reference_length(local_x, local_y, right % _TAU)
    for _ in range(80):
        if left_value <= right_value:
            upper, right, right_value = right, left, left_value
            left = upper - golden * (upper - lower)
            left_value = fixed_heading_reference_length(local_x, local_y, left % _TAU)
        else:
            lower, left, left_value = left, right, right_value
            right = lower + golden * (upper - lower)
            right_value = fixed_heading_reference_length(local_x, local_y, right % _TAU)
    return min(values[best_index], left_value, right_value) * radius


def boundary_aware_reference_length(local_x, local_y, radius, boundary_tolerance):
    """Apply the documented endpoint-equivalence band to the independent solver."""
    candidates = [free_heading_reference_length(local_x, local_y, radius)]
    for center_y in (1.0, -1.0):
        offset_x, offset_y = local_x, local_y - center_y
        distance = math.hypot(offset_x, offset_y)
        if distance and abs(distance - 1.0) <= boundary_tolerance:
            # The boundary-band contract permits the radial projection as an
            # equivalent endpoint. Calculate its known single-arc length
            # directly: reconstructing the projected Cartesian point and then
            # giving it to an exact-point solver merely reintroduces the same
            # floating-point side-of-boundary ambiguity under test.
            bearing = math.atan2(offset_y, offset_x)
            arc = ((bearing + math.pi / 2.0) % _TAU if center_y == 1.0
                   else (math.pi / 2.0 - bearing) % _TAU)
            candidates.append(arc * radius)
    return min(candidates)


REFERENCE_CASES = (
    (10.0, 0.0, 1.0),       # straight ahead
    (-1.0, 0.0, 1.0),       # directly behind
    (0.0, 1.0, 1.0),        # inside left initial turning disc
    (0.0, -1.0, 1.0),       # inside right initial turning disc
    (0.2, 0.5, 1.0),
    (-0.2, 0.5, 1.0),
    (0.5, -0.2, 1.0),
    (-0.5, -0.2, 1.0),
    (1.0, 1.0, 1.0),        # on a turning-circle boundary
    (1.0, -1.0, 1.0),       # mirrored boundary
    (1.0 - 5e-13, 1.0, 1.0),
    (1.0 + 5e-13, 1.0, 1.0),
    (1.0 - 5e-13, -1.0, 1.0),
    (1.0 + 5e-13, -1.0, 1.0),
    (1.0 - 1e-8, 1.0, 1.0),
    (1.0 + 1e-8, 1.0, 1.0),
    (1.0 - 1e-8, -1.0, 1.0),
    (1.0 + 1e-8, -1.0, 1.0),
    (0.0, 2.0, 1.0),        # opposite boundary point
    (0.0, 2.000001, 1.0),
    (0.0, 1.999999, 1.0),
    (5.0, 3.0, 0.25),       # small radius scale
    (-5.0, 3.0, 0.25),
    (2.0, -7.0, 10.0),      # larger radius scales
    (-2.0, -7.0, 10.0),
    (25.0, 4.0, 1000.0),
    (-25.0, -4.0, 1000.0),
)


class ReachabilityReferenceTests(unittest.TestCase):
    def test_closed_form_matches_independent_terminal_heading_minimization(self):
        transforms = (((0.0, 0.0), 0.0),
                      ((123.5, -87.25), 1.1),
                      ((-5000.0, 3000.0), -2.4))
        for local_x, local_y, radius in REFERENCE_CASES:
            for origin, heading in transforms:
                speed = 50.0
                state = InterceptorState('reference-interceptor', origin[0], origin[1], heading,
                                         speed, speed / radius)
                cosine, sine = math.cos(heading), math.sin(heading)
                target_x = origin[0] + radius * (cosine * local_x - sine * local_y)
                target_y = origin[1] + radius * (sine * local_x + cosine * local_y)
                production = minimum_bounded_curvature_path_length(state, target_x, target_y)
                # Reference the exact local geometry reconstructed from the same
                # represented global inputs used by production, not the ideal point
                # from which those inputs were generated.
                delta_x, delta_y = target_x - origin[0], target_y - origin[1]
                normalized_heading = state.heading_rad
                normalized_cosine, normalized_sine = (math.cos(normalized_heading),
                                                        math.sin(normalized_heading))
                recovered_x = math.fsum((normalized_cosine * delta_x,
                                         normalized_sine * delta_y)) / radius
                recovered_y = math.fsum((-normalized_sine * delta_x,
                                         normalized_cosine * delta_y)) / radius
                coordinate_scale = max(1.0, radius, abs(origin[0]), abs(origin[1]),
                                       abs(target_x), abs(target_y))
                boundary_tolerance = max(
                    GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE,
                    16 * math.ulp(coordinate_scale) / radius)
                reference = boundary_aware_reference_length(
                    recovered_x, recovered_y, radius, boundary_tolerance)
                material_tolerance = 2e-7 * max(1.0, reference)
                with self.subTest(local=(local_x, local_y), radius=radius,
                                  heading=heading, origin=origin):
                    self.assertLessEqual(abs(production - reference), material_tolerance)


if __name__ == '__main__':
    unittest.main()
