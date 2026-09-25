"""Consequence-vector formulas (singapore-consequence-model.md §6-7).

Each dimension is computed three times, from the low, central and high inputs,
so results carry bounds. Every formula here is monotone in its inputs, so
"low inputs give a low score" holds; alternative capacity is the one input that
lowers a score, and is flipped accordingly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import NamedTuple, Optional

from .profile import HAZARD_COMPONENTS, VULNERABILITY_COMPONENTS, Estimate, Profile

# Versioned policy profile (spec §7): a demonstration blend, not objective truth.
POLICY_DEMO_V1 = {
    'version': 'demo-v1',
    'weights': {'H': 0.35, 'E': 0.20, 'D': 0.20, 'X': 0.15, 'R': 0.05, 'A': 0.05},
    'max_blend': 0.30,
}
VULNERABILITY_WEIGHTS = dict(zip(VULNERABILITY_COMPONENTS, (0.30, 0.25, 0.20, 0.15, 0.10)))
HAZARD_WEIGHTS = dict(zip(HAZARD_COMPONENTS, (0.30, 0.25, 0.20, 0.15, 0.10)))
HIGH_EXPOSURE_H = 80
SERVICE_FLOOR_E = 80
HAZARD_HIGH_A = 60
UNCERTAINTY_SPREAD = 40
STALE_DAYS = 400


class Score(NamedTuple):
    low: float
    central: float
    high: float

    def __str__(self) -> str:
        return f'{self.central:.0f} [{self.low:.0f}, {self.high:.0f}]'


@dataclass(frozen=True)
class Scored:
    H: Optional[Score]
    E: Optional[Score]
    D: Optional[Score]
    X: Optional[Score]
    R: Optional[Score]
    A: Optional[Score]
    total: Optional[Score]
    rankable: bool
    dimensions_missing: tuple
    policy_version: str


def occupancy_score(n: float) -> float:
    return min(100.0, 20.0 * math.log10(n + 1))


def service_score(effective_person_hours: float) -> int:
    for limit, score in ((1_000, 10), (10_000, 25), (100_000, 40), (1_000_000, 60), (10_000_000, 80)):
        if effective_person_hours < limit:
            return score
    return 100


def recovery_score(hours_to_90: float) -> int:
    """§6.5 bands: <6 h, 6-24 h, 1-3 d, 4-14 d, 15-90 d, longer. Upper edges are inclusive."""
    if hours_to_90 < 6:
        return 5
    for limit, score in ((24, 15), (72, 30), (336, 50), (2160, 75)):
        if hours_to_90 <= limit:
            return score
    return 100


def _triple(estimate: Estimate, flip: bool = False) -> tuple:
    low, central, high = estimate.bounds
    return (high, central, low) if flip else (low, central, high)


def _map3(fn, *triples) -> Score:
    return Score(*(fn(*(t[i] for t in triples)) for i in range(3)))


def _vulnerability(profile: Profile) -> tuple:
    """Weighted V (0-100). A missing component contributes (0, 0, 1): widen, never assume zero."""
    total = [0.0, 0.0, 0.0]
    for key, weight in VULNERABILITY_WEIGHTS.items():
        e = profile.vulnerability.get(key)
        parts = (0.0, 0.0, 1.0) if e is None or not e.available else e.bounds
        for i in range(3):
            total[i] += weight * parts[i]
    return tuple(100 * t for t in total)


def _hazard(profile: Profile) -> Score:
    total = [0.0, 0.0, 0.0]
    for key, weight in HAZARD_WEIGHTS.items():
        e = profile.hazard.get(key)
        parts = (0.0, 0.0, 100.0) if e is None or not e.available else e.bounds
        for i in range(3):
            total[i] += weight * parts[i]
    return Score(*total)


def _direct(e: Estimate) -> Optional[Score]:
    return Score(*e.bounds) if e.available else None


def score_profile(profile: Profile, policy: dict = POLICY_DEMO_V1) -> Scored:
    v = _vulnerability(profile)
    H = E = R = None
    if profile.occupancy.available:
        H = _map3(lambda n, vv: occupancy_score(n) * (0.6 + 0.4 * vv / 100), _triple(profile.occupancy), v)
    if all(getattr(profile, k).available for k in
           ('beneficiaries_per_hour', 'loss_fraction', 'outage_hours', 'alternative_capacity_fraction')):
        E = _map3(lambda b, lf, h, alt: service_score(b * lf * h * (1 - alt)),
                  _triple(profile.beneficiaries_per_hour), _triple(profile.loss_fraction),
                  _triple(profile.outage_hours), _triple(profile.alternative_capacity_fraction, flip=True))
    if profile.recovery_t90_hours.available:
        R = _map3(recovery_score, _triple(profile.recovery_t90_hours))
    D = _direct(profile.capability)
    A = _hazard(profile)
    X = None  # dependency cascade deferred: no dependency records supplied yet

    dims = {'H': H, 'E': E, 'D': D, 'X': X, 'R': R, 'A': A}
    missing = tuple(k for k, s in dims.items() if s is None)
    rankable = H is not None and E is not None
    total = None
    if rankable:
        present = {k: s for k, s in dims.items() if s is not None}
        weights = policy['weights']
        norm = sum(weights[k] for k in present)
        blend = policy['max_blend']
        parts = []
        for i in range(3):
            weighted = sum(weights[k] * present[k][i] for k in present) / norm
            peak = max(present[k][i] for k in ('H', 'E', 'D') if k in present)
            parts.append((1 - blend) * weighted + blend * peak)
        total = Score(*parts)
    return Scored(H, E, D, X, R, A, total, rankable, missing, policy['version'])


def flags(profile: Profile, scored: Scored, as_of: Optional[str] = None) -> tuple:
    """Non-compensatory flags (spec §7); never cleared by a low total."""
    out = []
    if scored.H is not None and scored.H.central >= HIGH_EXPOSURE_H:
        out.append('high_human_exposure')
    if scored.E is not None and scored.E.central >= SERVICE_FLOOR_E:
        out.append('essential_service_floor_breach')
    if profile.single_point_of_failure:
        out.append('single_point_of_failure')
    if scored.A is not None and scored.A.central >= HAZARD_HIGH_A:
        out.append('hazard_inventory_high')
    if as_of is not None and _stale(profile, as_of):
        out.append('data_stale')
    dims = [s for s in (scored.H, scored.E, scored.D, scored.X, scored.total) if s is not None]
    if any(s.high - s.low >= UNCERTAINTY_SPREAD for s in dims):
        out.append('uncertainty_high')
    return tuple(out)


def _stale(profile: Profile, as_of: str) -> bool:
    now = date.fromisoformat(as_of)
    for name in ('occupancy', 'beneficiaries_per_hour', 'loss_fraction', 'outage_hours',
                 'alternative_capacity_fraction', 'recovery_t90_hours'):
        stamp = getattr(profile, name).source_date
        if stamp:
            try:
                if (now - date.fromisoformat(stamp[:10])).days > STALE_DAYS:
                    return True
            except ValueError:
                continue
    return False


FLAG_NAMES = ('high_human_exposure', 'mass_vulnerability_condition', 'essential_service_floor_breach',
              'minimum_capability_breach', 'single_point_of_failure', 'hazard_inventory_high',
              'data_stale', 'uncertainty_high')


def flag_table(profile: Profile, scored: Scored, as_of: Optional[str] = None) -> dict:
    """All eight spec §7 flags, each True, False or 'unavailable' when the input needed to judge it is absent.

    mass_vulnerability_condition needs vulnerability components; minimum_capability_breach needs the
    authorised capability input. data_stale needs an as_of date.
    """
    raised = set(flags(profile, scored, as_of))
    table = {name: name in raised for name in FLAG_NAMES}
    if not any(e.available for e in profile.vulnerability.values()):
        table['mass_vulnerability_condition'] = 'unavailable'
    elif scored.H is not None and scored.H.central >= HIGH_EXPOSURE_H:
        table['mass_vulnerability_condition'] = True
    if not profile.capability.available:
        table['minimum_capability_breach'] = 'unavailable'
    if as_of is None:
        table['data_stale'] = 'unavailable'
    return table
