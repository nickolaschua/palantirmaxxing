"""Obstacle-free, forward-only bounded-curvature reachability to a point.

The terminal heading is unrestricted. The exact free-heading path synthesis uses
straight, curve-straight, or opposite-curve paths rather than fixing or sampling
an arrival heading. Inputs describe a synthetic kinematic simulation, not an
operational interceptor.
"""
import math

from backend.domain import CandidateOpportunity, InterceptorState, TrajectorySample

REACHABILITY_TIME_TOLERANCE_S = 1e-9
GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE = 1e-12
_MAX_GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE = 1e-9
_COORDINATE_ROUNDOFF_ULPS = 16


def _finite_number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(field + ' must be a finite number; booleans are forbidden')


def _directed_arc(start_angle, end_angle, direction):
    """Positive arc angle for direction +1 (left) or -1 (right)."""
    return (direction * (end_angle - start_angle)) % math.tau


def _curve_straight_length(x, y, direction):
    """Unit-radius C-S candidate, or None when no tangent exists."""
    center_y = float(direction)
    offset_x, offset_y = x, y - center_y
    distance = math.hypot(offset_x, offset_y)
    if distance < 1.0:
        return None
    inverse_distance = 1.0 / distance
    straight = distance * math.sqrt(max(0.0, 1.0 - inverse_distance * inverse_distance))
    bearing = math.atan2(offset_y, offset_x)
    tangent_offset = math.atan2(1.0, straight)
    if direction == 1:
        turn = (bearing + tangent_offset) % math.tau
    else:
        turn = (tangent_offset - bearing) % math.tau
    return turn + straight


def _boundary_curve_length(x, y, direction):
    """Degenerate C candidate to the radial projection onto a turn circle."""
    bearing = math.atan2(y - float(direction), x)
    if direction == 1:
        return (bearing + math.pi / 2.0) % math.tau
    return (math.pi / 2.0 - bearing) % math.tau


def _circle_intersections(first_center, first_radius, second_center, second_radius,
                          geometry_tolerance):
    dx = second_center[0] - first_center[0]
    dy = second_center[1] - first_center[1]
    distance = math.hypot(dx, dy)
    if distance == 0:
        return ()
    along = (first_radius * first_radius - second_radius * second_radius
             + distance * distance) / (2.0 * distance)
    height_squared = first_radius * first_radius - along * along
    tolerance = geometry_tolerance * max(1.0, first_radius * first_radius,
                                         second_radius * second_radius, distance * distance)
    if height_squared < -tolerance:
        return ()
    height = math.sqrt(max(0.0, height_squared))
    unit_x, unit_y = dx / distance, dy / distance
    base_x = first_center[0] + along * unit_x
    base_y = first_center[1] + along * unit_y
    perpendicular_x, perpendicular_y = -unit_y, unit_x
    return tuple((base_x + sign * height * perpendicular_x,
                  base_y + sign * height * perpendicular_y) for sign in (-1.0, 1.0))


def _opposite_curve_lengths(x, y, first_direction, geometry_tolerance):
    """Unit-radius R-L or L-R candidates ending at the target point."""
    first_center = (0.0, float(first_direction))
    second_direction = -first_direction
    lengths = []
    for second_center in _circle_intersections(
            first_center, 2.0, (x, y), 1.0, geometry_tolerance):
        switch = ((first_center[0] + second_center[0]) / 2.0,
                  (first_center[1] + second_center[1]) / 2.0)
        first_start = math.atan2(-first_center[1], -first_center[0])
        first_end = math.atan2(switch[1] - first_center[1],
                               switch[0] - first_center[0])
        second_start = math.atan2(switch[1] - second_center[1],
                                  switch[0] - second_center[0])
        second_end = math.atan2(y - second_center[1], x - second_center[0])
        lengths.append(_directed_arc(first_start, first_end, first_direction)
                       + _directed_arc(second_start, second_end, second_direction))
    return lengths


def _normalized_boundary_tolerance(interceptor, position_x_m, position_y_m):
    """Bound coordinate roundoff without creating a material reachability band."""
    coordinate_scale = max(1.0, interceptor.minimum_turning_radius_m,
                           abs(interceptor.position_x_m), abs(interceptor.position_y_m),
                           abs(position_x_m), abs(position_y_m))
    coordinate_roundoff = (_COORDINATE_ROUNDOFF_ULPS * math.ulp(coordinate_scale)
                            / interceptor.minimum_turning_radius_m)
    if coordinate_roundoff > _MAX_GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE:
        raise ValueError('coordinate precision is insufficient relative to the turning radius')
    return max(GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE, coordinate_roundoff)


def minimum_bounded_curvature_path_length(interceptor, position_x_m, position_y_m):
    """Return the shortest path to a point with unrestricted terminal heading.

    Outside the documented turn-circle boundary band, the solution is exact for
    the obstacle-free forward Dubins model up to floating-point arithmetic.
    Inside that band, a radial boundary projection is an equivalent endpoint.
    Euclidean distance is never substituted for a failed calculation.
    """
    if not isinstance(interceptor, InterceptorState):
        raise ValueError('interceptor must be an InterceptorState')
    _finite_number(position_x_m, 'position_x_m')
    _finite_number(position_y_m, 'position_y_m')
    delta_x = position_x_m - interceptor.position_x_m
    delta_y = position_y_m - interceptor.position_y_m
    if not math.isfinite(delta_x) or not math.isfinite(delta_y):
        raise ValueError('target displacement exceeds finite numeric range')
    if delta_x == 0 and delta_y == 0:
        return 0.0

    radius = interceptor.minimum_turning_radius_m
    boundary_tolerance = _normalized_boundary_tolerance(
        interceptor, position_x_m, position_y_m)
    cosine = math.cos(interceptor.heading_rad)
    sine = math.sin(interceptor.heading_rad)
    try:
        local_x = math.fsum((cosine * delta_x, sine * delta_y)) / radius
        local_y = math.fsum((-sine * delta_x, cosine * delta_y)) / radius
    except OverflowError as exc:
        raise ValueError('normalized target geometry exceeds finite numeric range') from exc
    if not math.isfinite(local_x) or not math.isfinite(local_y):
        raise ValueError('normalized target geometry exceeds finite numeric range')
    if local_x == 0 and local_y == 0:
        raise ValueError('target displacement is not representable at the turning-radius scale')

    candidates = []
    for direction in (1, -1):
        length = _curve_straight_length(local_x, local_y, direction)
        if length is not None:
            candidates.append(length)

    left_circle_distance = math.hypot(local_x, local_y - 1.0)
    right_circle_distance = math.hypot(local_x, local_y + 1.0)
    if left_circle_distance < 1.0:
        candidates.extend(_opposite_curve_lengths(
            local_x, local_y, -1, boundary_tolerance))
    if right_circle_distance < 1.0:
        candidates.extend(_opposite_curve_lengths(
            local_x, local_y, 1, boundary_tolerance))

    # The exact free-heading solution changes path family at the initial turn
    # circles. Coordinate transforms can move an analytic boundary point a few
    # ulps across that boundary and otherwise cause a macroscopic branch flip.
    # Inside this roundoff-only band, also evaluate the valid degenerate arc to
    # the radial boundary projection. Ordinary inside/outside points never use it.
    if abs(left_circle_distance - 1.0) <= boundary_tolerance:
        candidates.append(_boundary_curve_length(local_x, local_y, 1))
    if abs(right_circle_distance - 1.0) <= boundary_tolerance:
        candidates.append(_boundary_curve_length(local_x, local_y, -1))
    if not candidates:
        raise ValueError('no finite bounded-curvature path construction was found')

    normalized_length = min(candidates)
    path_length = normalized_length * radius
    if not math.isfinite(path_length) or path_length < 0:
        raise ValueError('bounded-curvature path length exceeds finite numeric range')
    euclidean = math.hypot(delta_x, delta_y)
    numerical_slack = max(
        GEOMETRY_BOUNDARY_RELATIVE_TOLERANCE * max(1.0, euclidean, path_length),
        boundary_tolerance * radius)
    if path_length + numerical_slack < euclidean:
        raise ValueError('bounded-curvature path is numerically shorter than Euclidean distance')
    return path_length


def evaluate_candidate_reachability(threat_id, interceptor, sample):
    """Create deterministic reachability evidence for one future sample."""
    if not isinstance(sample, TrajectorySample):
        raise ValueError('sample must be a TrajectorySample')
    path_length = minimum_bounded_curvature_path_length(
        interceptor, sample.position_x_m, sample.position_y_m)
    required_time = path_length / interceptor.speed_mps
    time_margin = sample.time_from_start_s - required_time
    if not all(math.isfinite(value) for value in (required_time, time_margin)):
        raise ValueError('reachability timing exceeds finite numeric range')
    opportunity_id = '%s__%s__k%d' % (threat_id, interceptor.interceptor_id, sample.sample_index)
    return CandidateOpportunity(
        opportunity_id=opportunity_id,
        threat_id=threat_id,
        interceptor_id=interceptor.interceptor_id,
        sample_index=sample.sample_index,
        time_from_start_s=sample.time_from_start_s,
        position_x_m=sample.position_x_m,
        position_y_m=sample.position_y_m,
        reachable=time_margin >= -REACHABILITY_TIME_TOLERANCE_S,
        minimum_path_length_m=path_length,
        required_travel_time_s=required_time,
        time_margin_s=time_margin,
    )
