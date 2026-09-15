"""Transparent synthetic time-success profile; not an intercept predictor."""
import math

from backend.domain.evaluated_candidates import SyntheticSuccessProfile


def evaluate_synthetic_success(profile, time_from_start_s):
    """Return clip(p0 - alpha*t, minimum, maximum) for a synthetic scenario."""
    if not isinstance(profile, SyntheticSuccessProfile):
        raise ValueError('profile must be a SyntheticSuccessProfile')
    try:
        valid_time = (type(time_from_start_s) in (int, float)
                      and math.isfinite(time_from_start_s))
    except OverflowError:
        valid_time = False
    if not valid_time:
        raise ValueError('time_from_start_s must be a finite number; booleans are forbidden')
    if time_from_start_s < 0:
        raise ValueError('time_from_start_s must be nonnegative')
    raw_probability = (profile.initial_success_probability
                       - profile.decrease_per_second * time_from_start_s)
    # Finite inputs can overflow only for extreme magnitudes. Clipping still
    # yields a finite configured bound, which is the declared model behavior.
    return min(profile.maximum_success_probability,
               max(profile.minimum_success_probability, raw_probability))
