"""Immutable domain records for synthetic candidate-opportunity planning."""
from dataclasses import dataclass
import math
from typing import Optional


def _identifier(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be a nonempty string')


def _finite_number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(field + ' must be a finite number; booleans are forbidden')


def _positive_index(value, field='sample_index'):
    if type(value) is not int or value <= 0:
        raise ValueError(field + ' must be a positive integer')


@dataclass(frozen=True)
class ThreatState:
    """Current state for a deterministic horizontal and optional vertical path.

    The three vertical fields are deliberately appended.  Existing positional
    construction therefore keeps its exact two-dimensional behaviour.
    """
    threat_id: str
    position_x_m: float
    position_y_m: float
    velocity_x_mps: float
    velocity_y_mps: float
    maximum_time_to_go_s: float
    position_z_m: float = 0.0
    velocity_z_mps: float = 0.0
    acceleration_z_mps2: float = 0.0

    def __post_init__(self):
        _identifier(self.threat_id, 'threat_id')
        for field in ('position_x_m', 'position_y_m', 'velocity_x_mps',
                      'velocity_y_mps', 'maximum_time_to_go_s', 'position_z_m',
                      'velocity_z_mps', 'acceleration_z_mps2'):
            _finite_number(getattr(self, field), field)
        if self.maximum_time_to_go_s < 0:
            raise ValueError('maximum_time_to_go_s must be nonnegative')
        if self.position_z_m < 0:
            raise ValueError('position_z_m must be nonnegative')


@dataclass(frozen=True)
class InterceptorState:
    """Synthetic constant-speed, bounded-turn-rate interceptor state."""
    interceptor_id: str
    position_x_m: float
    position_y_m: float
    heading_rad: float
    speed_mps: float
    max_turn_rate_rad_s: float

    def __post_init__(self):
        _identifier(self.interceptor_id, 'interceptor_id')
        for field in ('position_x_m', 'position_y_m', 'heading_rad',
                      'speed_mps', 'max_turn_rate_rad_s'):
            _finite_number(getattr(self, field), field)
        if self.speed_mps <= 0:
            raise ValueError('speed_mps must be positive')
        if self.max_turn_rate_rad_s <= 0:
            raise ValueError('max_turn_rate_rad_s must be positive')
        radius = self.speed_mps / self.max_turn_rate_rad_s
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError('speed and turn rate must produce a finite positive turning radius')
        heading = self.heading_rad % math.tau
        object.__setattr__(self, 'heading_rad', 0.0 if heading == 0 else heading)

    @property
    def minimum_turning_radius_m(self):
        return self.speed_mps / self.max_turn_rate_rad_s


@dataclass(frozen=True)
class TrajectorySample:
    """One strictly future point on a supplied predicted trajectory."""
    sample_index: int
    time_from_start_s: float
    position_x_m: float
    position_y_m: float
    position_z_m: float = 0.0
    velocity_z_mps: float = 0.0

    def __post_init__(self):
        _positive_index(self.sample_index)
        for field in ('time_from_start_s', 'position_x_m', 'position_y_m',
                      'position_z_m', 'velocity_z_mps'):
            _finite_number(getattr(self, field), field)
        if self.time_from_start_s <= 0:
            raise ValueError('time_from_start_s must be positive for a future sample')
        if self.position_z_m < 0:
            raise ValueError('position_z_m must be nonnegative')


@dataclass(frozen=True)
class CandidateOpportunity:
    """Reachability evidence for one future trajectory sample."""
    opportunity_id: str
    threat_id: str
    interceptor_id: str
    sample_index: int
    time_from_start_s: float
    position_x_m: float
    position_y_m: float
    reachable: bool
    minimum_path_length_m: Optional[float]
    required_travel_time_s: Optional[float]
    time_margin_s: Optional[float]
    position_z_m: float = 0.0
    velocity_z_mps: float = 0.0

    def __post_init__(self):
        for field in ('opportunity_id', 'threat_id', 'interceptor_id'):
            _identifier(getattr(self, field), field)
        _positive_index(self.sample_index)
        for field in ('time_from_start_s', 'position_x_m', 'position_y_m',
                      'position_z_m', 'velocity_z_mps'):
            _finite_number(getattr(self, field), field)
        if self.time_from_start_s <= 0:
            raise ValueError('time_from_start_s must be positive for a candidate opportunity')
        if self.position_z_m < 0:
            raise ValueError('position_z_m must be nonnegative')
        if type(self.reachable) is not bool:
            raise ValueError('reachable must be a boolean')
        metrics = (self.minimum_path_length_m, self.required_travel_time_s, self.time_margin_s)
        if any(value is None for value in metrics) and not all(value is None for value in metrics):
            raise ValueError('reachability metrics must either all be present or all be None')
        if all(value is None for value in metrics):
            if self.reachable:
                raise ValueError('reachable cannot be true without reachability metrics')
            return
        for field in ('minimum_path_length_m', 'required_travel_time_s', 'time_margin_s'):
            _finite_number(getattr(self, field), field)
        if self.minimum_path_length_m < 0:
            raise ValueError('minimum_path_length_m must be nonnegative')
        if self.required_travel_time_s < 0:
            raise ValueError('required_travel_time_s must be nonnegative')
