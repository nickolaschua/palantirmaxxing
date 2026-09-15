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
        if not all(math.isfinite(value) for value in (time_s, position_x_m, position_y_m)):
            raise ValueError('trajectory sample exceeds finite numeric range')
        samples.append(TrajectorySample(sample_index, time_s, position_x_m, position_y_m))
    return tuple(samples)
