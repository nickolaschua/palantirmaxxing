"""MOE school consequence profiles: one Profile per school and transport condition.

Spec §3 stores schools as `commercial_civic` with an education role. MOE publishes enrolment and staff by
school level, not by school, so each school receives its level's mean (official aggregate, grade C) with a
size band. Presence by time window is the spec §9 'School teaching' row (assumption, grade D), term time only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import shapely

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS
from backend.data_sources.consequence.sources import postal6
from backend.data_sources.consequence.conditions import CONDITIONS

MOE_SOURCE = 'MOE Students, Education Officers and Education Partners in Schools by Level'
Triple = tuple  # (low, central, high)

# MOE directory mainlevel_code -> MOE by-level table row, and role suffix.
LEVELS = {
    'Primary': 'primary', 'Secondary': 'secondary',
    'Junior College/Centralised Institute': 'jc_ci', 'Mixed Level': 'mixed',
}
SIZE_BAND = (0.6, 1.0, 1.5)  # a school relative to its level mean (assumption)
PRESENCE = {  # share of students and staff on site (spec §9 school teaching row, assumption)
    'weekday_am_peak': (0.50, 0.80, 0.95),  # school starts about 07:30
    'weekday_midday': (0.80, 0.90, 0.97),
    'weekday_pm_peak': (0.10, 0.25, 0.40),  # co-curricular activities
    'weekday_night': (0.00, 0.02, 0.05),
    'weekend_day': (0.02, 0.05, 0.15),
    'weekend_night': (0.00, 0.01, 0.03),
}
PRIMARY_SHARE_MIXED_P1_S4 = 6 / 10  # P1-P6 of ten year groups
SUPERVISION_NEED = (0.3, 0.5, 0.7)  # young children who need adult help to evacuate (assumption)
OUTDOORS = (0.0, 0.05, 0.15)  # physical education and recess (assumption)
LOSS_FRACTION = (0.2, 0.6, 1.0)
INSTRUCTION_HOURS_LOST = (30, 180, 600)  # 1, 6 and 20 school weeks at 30 teaching hours
ALTERNATIVE = (0.3, 0.5, 0.8)  # home-based learning or a holding school
RECOVERY_T90_HOURS = (720, 2160, 4320)
HAZARD = {  # laboratory chemicals and gas (assumption)
    'flammable': (0.0, 5.0, 15.0), 'toxic': (0.0, 5.0, 15.0), 'explosive_or_high_energy': (0.0, 0.0, 5.0),
    'water_or_environmental_contamination': (0.0, 0.0, 5.0), 'proximity_to_other_hazards': (0.0, 0.0, 5.0),
}


@dataclass(frozen=True)
class Site:
    site_id: str
    name: str
    level: str  # key of LEVELS
    geometry_wkt: str  # EPSG:3414
    students: float  # level mean per school
    staff: float
    primary_share: float  # share of students aged 12 or under
    year: str  # MOE statistics year
    raw: dict = field(default_factory=dict)


def school_level(mainlevel_code: str) -> str | None:
    code = (mainlevel_code or '').strip().upper()
    if code == 'PRIMARY':
        return 'Primary'
    if code.startswith('SECONDARY'):
        return 'Secondary'
    if code in ('JUNIOR COLLEGE', 'CENTRALISED INSTITUTE'):
        return 'Junior College/Centralised Institute'
    if code.startswith('MIXED LEVEL'):
        return 'Mixed Level'
    return None


def primary_share(mainlevel_code: str) -> float:
    code = (mainlevel_code or '').strip().upper()
    if code == 'PRIMARY':
        return 1.0
    return PRIMARY_SHARE_MIXED_P1_S4 if code.startswith('MIXED LEVEL (P1') else 0.0


def per_school_counts(level_rows: list, schools: list) -> dict:
    """{level: {students, staff, schools, year}}: latest MOE level totals / schools at that level in the directory."""
    rows = [r for r in level_rows if r.get('sex') == 'MF' and r.get('school') in LEVELS and r.get('student_enrolment')]
    year = max(r['year'] for r in rows)
    counts: dict = {}
    for s in schools:
        level = school_level(s.get('mainlevel_code'))
        if level:
            counts[level] = counts.get(level, 0) + 1
    out = {}
    for r in rows:
        if r['year'] != year or r['school'] not in counts:
            continue
        staff = sum(float(r.get(k) or 0) for k in ('no_of_teacher', 'no_of_vice_principal', 'no_of_principal',
                                                   'no_of_education_partners'))
        n = counts[r['school']]
        out[r['school']] = dict(students=float(r['student_enrolment']) / n, staff=staff / n, schools=n, year=year)
    return out


def _estimate(triple: Triple, unit: str, state: str, grade: str, method: str, source: str = 'assumption') -> Estimate:
    return Estimate(triple[0], triple[1], triple[2], unit, state, grade, source=source, method=method)


def school_profiles(site: Site) -> list:
    students = tuple(site.students * b for b in SIZE_BAND)
    people = tuple((site.students + site.staff) * b for b in SIZE_BAND)
    source = f'{MOE_SOURCE}, {site.year}'
    beneficiaries = _estimate(students, 'people', 'official_aggregate', 'C',
                              f'{site.level} enrolment / schools at that level', source)
    loss = _estimate(LOSS_FRACTION, 'fraction', 'assumption', 'D', 'share of teaching capacity lost')
    outage = _estimate(INSTRUCTION_HOURS_LOST, 'hours', 'assumption', 'D', 'teaching hours lost per student')
    alternative = _estimate(ALTERNATIVE, 'fraction', 'assumption', 'D', 'home-based learning or holding school')
    recovery = _estimate(RECOVERY_T90_HOURS, 'hours', 'assumption', 'D', 'time to 90% of school function')
    hazard = {name: _estimate(HAZARD[name], 'score_0_100', 'assumption', 'D', 'school laboratory')
              for name in HAZARD_COMPONENTS}
    young = site.primary_share * site.students / (site.students + site.staff)
    vulnerability = {
        'age_vulnerable': Estimate.exact(young, 'fraction', 'derived', 'C', source=source,
                                         method='students aged 12 or under / students and staff'),
        'difficult_to_evacuate': _estimate(tuple(young * s for s in SUPERVISION_NEED), 'fraction', 'assumption', 'D',
                                           'young children needing adult help'),
        'insufficiently_sheltered_or_outdoors': _estimate(OUTDOORS, 'fraction', 'assumption', 'D',
                                                          'physical education and recess'),
        'unable_to_self_evacuate': Estimate.unavailable('no per-school public source', 'fraction'),
        'medically_dependent': Estimate.unavailable('no per-school public source', 'fraction'),
    }
    profiles = []
    for condition in CONDITIONS:
        cid = condition.condition_id
        present = PRESENCE[cid]
        occupancy = _estimate(tuple(p * f for p, f in zip(people, present)), 'people', 'derived', 'D',
                              'students and staff x share present (term time)', source)
        profiles.append(Profile(
            site_id=site.site_id, condition_id=cid, role=f'education_{LEVELS[site.level]}',
            geometry_wkt=site.geometry_wkt, occupancy=occupancy, beneficiaries_per_hour=beneficiaries,
            loss_fraction=loss, outage_hours=outage, alternative_capacity_fraction=alternative,
            recovery_t90_hours=recovery, vulnerability=vulnerability, hazard=hazard,
            categories=('commercial_civic',), raw=site.raw))
    return profiles


def school_sites(school_rows: list, level_rows: list, geocode: dict) -> tuple:
    counts = per_school_counts(level_rows, school_rows)
    sites, skipped = [], []
    for r in school_rows:
        level = school_level(r['mainlevel_code'])
        hit = geocode.get(postal6(r['postal_code']))
        if level not in counts or hit is None:
            skipped.append(r['school_name'])
            continue
        c = counts[level]
        raw = dict(school_name=r['school_name'], postal=r['postal_code'], mainlevel_code=r['mainlevel_code'],
                   type_code=r['type_code'], session_code=r['session_code'], zone_code=r['zone_code'],
                   dgp_code=r['dgp_code'], level_students_per_school=round(c['students'], 1),
                   level_staff_per_school=round(c['staff'], 1), level_schools=c['schools'])
        sites.append(Site(f"school:{r['school_name']}", r['school_name'], level,
                                  shapely.Point(hit['x'], hit['y']).wkt, c['students'], c['staff'],
                                  primary_share(r['mainlevel_code']), c['year'], raw))
    return sites, skipped, counts
