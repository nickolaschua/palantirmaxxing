"""Deterministic sampling of a constant-velocity predicted threat trajectory."""
import math

from backend.domain import ThreatState, TrajectorySample

DEFAULT_NUMBER_OF_SAMPLES = 50


def sample_threat_trajectory(threat, number_of_samples=DEFAULT_NUMBER_OF_SAMPLES):
    """Return uniformly timed future samples; zero time-to-go returns no samples."""
    if not isinstance(threat, ThreatState):
        raise ValueError('threat must be a ThreatState')
    if type(number_of_samples) is not int or number_of_samples <= 0:
        raise ValueError('number_of_samples must be a positive integer')
    if threat.maximum_time_to_go_s == 0:
        return ()
    samples = []
    for sample_index in range(1, number_of_samples + 1):
        time_s = (sample_index / number_of_samples) * threat.maximum_time_to_go_s
        position_x_m = threat.position_x_m + threat.velocity_x_mps * time_s
        position_y_m = threat.position_y_m + threat.velocity_y_mps * time_s
        position_z_m = (threat.position_z_m + threat.velocity_z_mps * time_s
                        + 0.5 * threat.acceleration_z_mps2 * time_s * time_s)
        velocity_z_mps = threat.velocity_z_mps + threat.acceleration_z_mps2 * time_s
        tolerance = max(1e-7, abs(threat.position_z_m) * 1e-12)
        if abs(position_z_m) <= tolerance:
            position_z_m = 0.0
        if not all(math.isfinite(value) for value in (
                time_s, position_x_m, position_y_m, position_z_m, velocity_z_mps)):
            raise ValueError('trajectory sample exceeds finite numeric range')
        if position_z_m < 0:
            raise ValueError('trajectory altitude must remain nonnegative')
        samples.append(TrajectorySample(
            sample_index, time_s, position_x_m, position_y_m,
            position_z_m, velocity_z_mps))
    return tuple(samples)
