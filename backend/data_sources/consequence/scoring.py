"""Consequence-vector formulas (singapore-consequence-model.md §6-7).

Human harm is expected casualties C = N * p_base * (1 + k*V/100), linear in the
people present. Sites are judged in two steps: a hard veto on magnitude flags,
then a lexicographic rank on C with the secondary E/D/X/R/A score breaking ties.

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

# Superseded demo-v1 blend (log occupancy H in a compensatory total), kept for reference only.
POLICY_DEMO_V1 = {
    'version': 'demo-v1',
    'weights': {'H': 0.35, 'E': 0.20, 'D': 0.20, 'X': 0.15, 'R': 0.05, 'A': 0.05},
    'max_blend': 0.30,
}
# Versioned policy profile (spec §7). Every constant is an uncalibrated placeholder, not objective truth:
# p_base is the baseline harm probability for an unshielded person in the debris footprint; k is how much
# likelier a fully vulnerable person is to be harmed; tie_band/tie_floor bound the C values that count as tied.
POLICY_DEMO_V2 = {
    'version': 'demo-v2',
    'p_base': 0.01,
    'k': 3.0,
    'secondary_weights': {'E': 0.30, 'D': 0.30, 'X': 0.25, 'R': 0.10, 'A': 0.05},
    'tie_band': 0.10,
    'tie_floor': 0.5,
}
VULNERABILITY_WEIGHTS = dict(zip(VULNERABILITY_COMPONENTS, (0.30, 0.25, 0.20, 0.15, 0.10)))
HAZARD_WEIGHTS = dict(zip(HAZARD_COMPONENTS, (0.30, 0.25, 0.20, 0.15, 0.10)))
HIGH_EXPOSURE_C = 10  # expected casualties (placeholder)
SERVICE_FLOOR_E = 80
ESSENTIAL_THRESHOLD_FACTOR = 0.5  # essential sites trip high_human_exposure at half the casualties
ESSENTIAL_SERVICE_FLOOR_E = 60
MASS_VULNERABILITY_V = 50
# Categories whose loss is essential: they lower trip thresholds, never trip a flag by themselves.
ESSENTIAL_CATEGORIES = ('health_emergency', 'defence_security', 'aviation', 'energy', 'water', 'port')
CIVILIAN_VETO_FLAGS = ('high_human_exposure', 'essential_service_floor_breach')
CAPABILITY_VETO_FLAGS = ('minimum_capability_breach',)
# Precautionary: a declared priority asset whose capability no authorised input has assessed is vetoed.
UNASSESSED_PRIORITY = 'priority_asset_capability_not_assessed'
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
    C: Optional[Score]  # expected casualties; the primary ranking key
    O_display: Optional[Score]  # min(100, 20*log10(C+1)): dashboard only, never used to rank
    V: Score
    E: Optional[Score]
    D: Optional[Score]
    X: Optional[Score]
    R: Optional[Score]
    A: Optional[Score]
    secondary: Optional[Score]  # tie-breaker over E/D/X/R/A
    rankable: bool
    dimensions_missing: tuple
    policy_version: str


def occupancy_score(n: float) -> float:
    return min(100.0, 20.0 * math.log10(n + 1))


def expected_casualties(n: float, v: float, p_base: float, k: float) -> float:
    return n * p_base * (1 + k * v / 100)


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


def score_profile(profile: Profile, policy: dict = POLICY_DEMO_V2) -> Scored:
    v = _vulnerability(profile)
    C = O_display = E = R = None
    if profile.occupancy.available:
        C = _map3(lambda n, vv: expected_casualties(n, vv, policy['p_base'], policy['k']),
                  _triple(profile.occupancy), v)
        O_display = _map3(occupancy_score, C)
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

    dims = {'C': C, 'E': E, 'D': D, 'X': X, 'R': R, 'A': A}
    missing = tuple(k for k, s in dims.items() if s is None)
    rankable = C is not None and E is not None
    secondary = None
    present = {k: s for k, s in dims.items() if k != 'C' and s is not None}
    if rankable:
        weights = policy['secondary_weights']
        norm = sum(weights[k] for k in present)
        secondary = Score(*(sum(weights[k] * present[k][i] for k in present) / norm for i in range(3)))
    return Scored(C, O_display, Score(*v), E, D, X, R, A, secondary, rankable, missing, policy['version'])


def _essential(profile: Profile) -> bool:
    return profile.priority_asset or any(c in ESSENTIAL_CATEGORIES for c in profile.categories)


def _casualty_threshold(profile: Profile) -> float:
    return HIGH_EXPOSURE_C * (ESSENTIAL_THRESHOLD_FACTOR if _essential(profile) else 1)


def flags(profile: Profile, scored: Scored, as_of: Optional[str] = None) -> tuple:
    """Non-compensatory flags (spec §7); never cleared by a low total."""
    out = []
    if scored.C is not None and scored.C.central >= _casualty_threshold(profile):
        out.append('high_human_exposure')
    floor = ESSENTIAL_SERVICE_FLOOR_E if _essential(profile) else SERVICE_FLOOR_E
    if scored.E is not None and scored.E.central >= floor:
        out.append('essential_service_floor_breach')
    if profile.single_point_of_failure:
        out.append('single_point_of_failure')
    if profile.priority_asset:
        out.append('priority_asset')
    if scored.A is not None and scored.A.central >= HAZARD_HIGH_A:
        out.append('hazard_inventory_high')
    if as_of is not None and _stale(profile, as_of):
        out.append('data_stale')
    # C is unbounded, so its spread is judged on the 0-100 display transform.
    dims = [s for s in (scored.O_display, scored.E, scored.D, scored.X, scored.secondary) if s is not None]
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
    elif (scored.C is not None and scored.C.central >= _casualty_threshold(profile)
          and scored.V.central >= MASS_VULNERABILITY_V):
        table['mass_vulnerability_condition'] = True
    if not profile.capability.available:
        table['minimum_capability_breach'] = 'unavailable'
    if as_of is None:
        table['data_stale'] = 'unavailable'
    return table


def veto(table: dict, priority_asset: bool = False, capability_available: bool = True) -> tuple:
    """Step A: (status, civilian_reasons, capability_reasons) from a flag_table.

    status is 'vetoed' when any veto flag is True, 'unknown' when none is True but one could not be
    judged ('unavailable'), else 'pass'. Capability reasons stay separate from civilian-harm reasons.
    A priority asset without an authorised capability input is vetoed as a precaution; the veto is
    never derived from the site's scores.
    """
    civilian = tuple(f for f in CIVILIAN_VETO_FLAGS if table.get(f) is True)
    capability = tuple(f for f in CAPABILITY_VETO_FLAGS if table.get(f) is True)
    if priority_asset and not capability_available:
        capability += (UNASSESSED_PRIORITY,)
    if civilian or capability:
        status = 'vetoed'
    elif any(table.get(f) == 'unavailable' for f in CIVILIAN_VETO_FLAGS + CAPABILITY_VETO_FLAGS):
        status = 'unknown'
    else:
        status = 'pass'
    return status, civilian, capability


def rank_sites(rows: list, policy: dict = POLICY_DEMO_V2) -> list:
    """Step B: order rows (dicts with C_central, secondary_central, veto_status) and add 'rank'.

    Survivors ('pass' and 'unknown') come first, then vetoed rows, then rows with no C. Within a group,
    the lowest remaining C opens a tie band (C <= max(C_min * (1 + tie_band), C_min + tie_floor));
    rows in the band are ordered by secondary, lowest first, and the next band starts after them.
    Never drops a row.
    """
    def number(v):
        return None if v is None or v == '' else float(v)

    def banded(group):
        rest = sorted(group, key=lambda r: number(r['C_central']))
        out = []
        while rest:
            c_min = number(rest[0]['C_central'])
            limit = max(c_min * (1 + policy['tie_band']), c_min + policy['tie_floor'])
            band = [r for r in rest if number(r['C_central']) <= limit]
            rest = rest[len(band):]
            out += sorted(band, key=lambda r: (number(r['secondary_central']) is None,
                                               number(r['secondary_central']) or 0.0,
                                               number(r['C_central'])))
        return out

    scored = [r for r in rows if number(r['C_central']) is not None]
    ordered = (banded([r for r in scored if r['veto_status'] != 'vetoed'])
               + banded([r for r in scored if r['veto_status'] == 'vetoed'])
               + [r for r in rows if number(r['C_central']) is None])
    return [dict(r, rank=i) for i, r in enumerate(ordered, 1)]
