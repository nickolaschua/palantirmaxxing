"""Profile contract for the conditional consequence model (singapore-consequence-model.md §4, §13).

Every value is a low/central/high Estimate with provenance. A value that has no
defensible source is Estimate.unavailable(...), never zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Optional

INFORMATION_STATES = ('measured', 'official_aggregate', 'derived', 'operator_input',
                      'restricted_input', 'assumption', 'unavailable')
CONFIDENCE_GRADES = ('A', 'B', 'C', 'D', 'E')
VULNERABILITY_COMPONENTS = ('unable_to_self_evacuate', 'medically_dependent', 'difficult_to_evacuate',
                            'insufficiently_sheltered_or_outdoors', 'age_vulnerable')
HAZARD_COMPONENTS = ('flammable', 'toxic', 'explosive_or_high_energy',
                     'water_or_environmental_contamination', 'proximity_to_other_hazards')


class ProfileError(ValueError):
    """Raised when a profile violates the contract."""


@dataclass(frozen=True)
class Estimate:
    low: Optional[float]
    central: Optional[float]
    high: Optional[float]
    unit: str
    state: str
    grade: Optional[str] = None
    source: str = ''
    source_date: Optional[str] = None
    method: str = ''
    resolution: str = ''

    @classmethod
    def unavailable(cls, reason: str, unit: str = '') -> 'Estimate':
        return cls(None, None, None, unit, 'unavailable', None, reason)

    @classmethod
    def exact(cls, value: float, unit: str, state: str, grade: str, **kw) -> 'Estimate':
        return cls(value, value, value, unit, state, grade, **kw)

    @property
    def available(self) -> bool:
        return self.state != 'unavailable'

    @property
    def bounds(self) -> tuple[float, float, float]:
        return (self.low, self.central, self.high)


@dataclass(frozen=True)
class Condition:
    condition_id: str
    day_type: str
    hour_start: int
    hour_end: int
    operating_state: str = 'normal'


@dataclass(frozen=True)
class Profile:
    site_id: str
    condition_id: str
    role: str
    geometry_wkt: str
    occupancy: Estimate
    beneficiaries_per_hour: Estimate
    loss_fraction: Estimate
    outage_hours: Estimate
    alternative_capacity_fraction: Estimate
    recovery_t90_hours: Estimate
    vulnerability: dict = field(default_factory=dict)
    hazard: dict = field(default_factory=dict)
    capability: Estimate = field(default_factory=lambda: Estimate.unavailable(
        'no authorised capability input', 'score_0_100'))
    dependencies: tuple = ()
    single_point_of_failure: bool = False
    priority_asset: bool = False  # e.g. military airbase; declared, never derived from the score
    categories: tuple = ('transport',)
    raw: dict = field(default_factory=dict)
    population_method: str = 'direct'  # direct | areal_density | building_level (population_disaggregation.py)
    overlap_area_km2: Optional[float] = None  # footprint overlap used by areal_density


def _check_estimate(name: str, e: Estimate, errors: list) -> None:
    if not isinstance(e, Estimate):
        errors.append(f'{name}: not an Estimate')
        return
    if e.state not in INFORMATION_STATES:
        errors.append(f'{name}: unknown state {e.state!r}')
    values = e.bounds
    if e.state == 'unavailable':
        if any(v is not None for v in values):
            errors.append(f'{name}: unavailable estimate must not carry values')
        return
    if any(v is None or not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
           for v in values):
        errors.append(f'{name}: {e.state} estimate needs finite low/central/high')
        return
    if not e.low <= e.central <= e.high:
        errors.append(f'{name}: requires low <= central <= high')
    if e.grade not in CONFIDENCE_GRADES:
        errors.append(f'{name}: grade must be one of A-E')


def validate(profile: Profile) -> bool:
    """Enforce the section 13 minimum fields; return whether the profile may enter automated ranking.

    Raises ProfileError on a contract violation. A profile is rankable only when
    both human exposure (occupancy) and service loss (beneficiaries) are available.
    """
    errors: list = []
    for name in ('site_id', 'condition_id', 'role', 'geometry_wkt'):
        if not isinstance(getattr(profile, name), str) or not getattr(profile, name).strip():
            errors.append(f'{name}: required nonempty string')
    if profile.population_method not in ('direct', 'areal_density', 'building_level'):
        errors.append(f'population_method: unknown {profile.population_method!r}')
    if not profile.categories:
        errors.append('categories: at least one category required')
    for name in ('occupancy', 'beneficiaries_per_hour', 'loss_fraction', 'outage_hours',
                 'alternative_capacity_fraction', 'recovery_t90_hours', 'capability'):
        _check_estimate(name, getattr(profile, name), errors)
    for name, keys, bag in (('vulnerability', VULNERABILITY_COMPONENTS, profile.vulnerability),
                            ('hazard', HAZARD_COMPONENTS, profile.hazard)):
        for key, e in bag.items():
            if key not in keys:
                errors.append(f'{name}.{key}: unknown component')
            else:
                _check_estimate(f'{name}.{key}', e, errors)
    if errors:
        raise ProfileError('; '.join(errors))
    return profile.occupancy.available and profile.beneficiaries_per_hour.available
