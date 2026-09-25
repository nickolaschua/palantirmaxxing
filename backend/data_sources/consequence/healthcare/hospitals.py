"""Acute hospital consequence profiles: one Profile per hospital and transport condition.

Measured inputs (grade B): MOH daily bed occupancy and emergency attendances per hospital, summarised as
p10/p50/p90 over days of the condition's day type. Bed counts are a cited table (each hospital's published
figure). Every number marked (assumption) is uncalibrated and grade D.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import shapely

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS
from backend.data_sources.consequence.conditions import CONDITIONS

MOH_SOURCE = 'MOH Healthcare Institution Statistics: daily BOR and EMD attendances by hospital'
QUANTILES = (0.10, 0.50, 0.90)
SINCE = date(2023, 1, 1)  # first day of the EMD series; keeps BOR and ED on the same recent window
Triple = tuple  # (low, central, high)


@dataclass(frozen=True)
class Hospital:
    code: str  # column code in the MOH workbooks
    name: str
    postal: str
    beds: Triple  # published bed count with a band for vintage and definition differences
    bed_source: str


# Published bed counts, retrieved 2026-09-25. Bands reflect disagreement between sources, ramp-up (WH) or
# the adult/children split (NUH(A) excludes the children's hospital, which MOH also excludes from BOR).
HOSPITALS = (
    Hospital('AH', 'Alexandra Hospital', '159964', (300, 326, 360), 'https://en.wikipedia.org/wiki/Alexandra_Hospital'),
    Hospital('CGH', 'Changi General Hospital', '529889', (1000, 1132, 1200),
             'https://en.wikipedia.org/wiki/Changi_General_Hospital'),
    Hospital('KTPH', 'Khoo Teck Puat Hospital', '768828', (750, 795, 850),
             'https://www.ktph.com.sg/about-us/corporate-profile'),
    Hospital('NTFGH', 'Ng Teng Fong General Hospital', '609606', (650, 700, 760),
             'https://en.wikipedia.org/wiki/Ng_Teng_Fong_General_Hospital'),
    Hospital('NUH(A)', 'National University Hospital (Adults)', '119074', (900, 1050, 1239),
             'https://www.nuh.com.sg/about-nuh/who-we-are'),
    Hospital('SGH', 'Singapore General Hospital', '169608', (1850, 1931, 2440),
             'https://www.sgh.com.sg/about-sgh/who-we-are'),
    Hospital('SKH', 'Sengkang General Hospital', '544886', (900, 1000, 1100),
             'https://en.wikipedia.org/wiki/Sengkang_General_Hospital'),
    Hospital('TTSH', 'Tan Tock Seng Hospital', '308433', (1600, 1700, 1800), 'https://www.nhghealth.com.sg/ttsh'),
    Hospital('WH', 'Woodlands Hospital', '737628', (460, 680, 1000), 'https://en.wikipedia.org/wiki/Woodlands_Hospital'),
)

# Occupancy (assumption): ED patients present = arrivals per hour x hour factor x hours spent in the ED.
ED_STAY_HOURS = (2.0, 4.0, 6.0)
ED_HOUR_FACTOR = {  # arrivals in the window relative to the daily mean hourly rate
    'weekday_am_peak': (0.8, 1.0, 1.2), 'weekday_midday': (1.1, 1.3, 1.5), 'weekday_pm_peak': (1.0, 1.2, 1.4),
    'weekday_night': (0.4, 0.6, 0.8), 'weekend_day': (1.0, 1.2, 1.4), 'weekend_night': (0.4, 0.6, 0.8),
}
STAFF_PER_BED = (2.0, 3.0, 4.0)  # all hospital staff per bed
SHIFT_FRACTION = {  # share of all staff on site in the window
    'weekday_am_peak': (0.30, 0.40, 0.50), 'weekday_midday': (0.35, 0.45, 0.55),
    'weekday_pm_peak': (0.25, 0.35, 0.45), 'weekday_night': (0.12, 0.18, 0.25),
    'weekend_day': (0.20, 0.28, 0.36), 'weekend_night': (0.12, 0.18, 0.25),
}
VISITORS_PER_INPATIENT = {
    'weekday_am_peak': (0.0, 0.1, 0.3), 'weekday_midday': (0.3, 0.6, 1.0), 'weekday_pm_peak': (0.3, 0.6, 1.0),
    'weekday_night': (0.0, 0.02, 0.1), 'weekend_day': (0.4, 0.8, 1.2), 'weekend_night': (0.0, 0.02, 0.1),
}
# Vulnerability (assumption unless noted).
NON_AMBULANT_INPATIENTS = (0.3, 0.5, 0.7)  # inpatients who cannot walk out unaided
AMBULANCE_CONVEYANCE = (0.7, 0.9, 1.0)  # share of SCDF emergency calls conveyed to a public ED
AGE65_BEDDAY_UPLIFT = 1.5  # older patients stay longer, so their share of beds exceeds their share of admissions
DIFFICULT_TO_EVACUATE = (0.1, 0.2, 0.4)  # multi-storey wards, ICU, theatres
OUTDOORS = (0.0, 0.0, 0.02)
# Service loss (E) and recovery (R).
LOSS_FRACTION = (0.2, 0.5, 1.0)
OUTAGE_HOURS = (72, 336, 2160)  # 3 days, 2 weeks, 90 days
RECOVERY_T90_HOURS = (336, 2160, 8760)  # 2 weeks, 90 days, 1 year
HAZARD = {  # (assumption) site potential, 0-100
    'flammable': (10.0, 20.0, 40.0),  # piped oxygen and medical gases
    'toxic': (5.0, 15.0, 30.0),  # pharmacy, laboratory, radiology
    'explosive_or_high_energy': (0.0, 5.0, 15.0),  # pressurised gas cylinders
    'water_or_environmental_contamination': (5.0, 10.0, 25.0),  # clinical and radiological waste
    'proximity_to_other_hazards': (0.0, 0.0, 10.0),
}


@dataclass(frozen=True)
class Site:
    hospital: Hospital
    geometry_wkt: str  # EPSG:3414
    stats: dict  # {day_type: {bor, ed, spare, days, last}} from build_stats
    age65_share: Triple  # share of acute admissions aged 65+
    ambulance_share: Triple  # share of ED attendances arriving by SCDF emergency ambulance
    raw: dict = field(default_factory=dict)


def day_type(day: date) -> str:
    return 'weekend' if day.weekday() >= 5 else 'weekday'


def quantiles(values: list) -> Triple:
    return tuple(float(q) for q in np.quantile(np.asarray(values, dtype=float), QUANTILES))


def build_stats(bor: dict, ed: dict, hospitals=HOSPITALS, since: date = SINCE) -> dict:
    """{code: {day_type: {bor, ed, spare, days, last}}} for hospitals with both series.

    spare is the number of empty beds at every *other* hospital on the same day, sum(beds x (1 - BOR)), using
    central bed counts; a hospital not reporting that day (for example before it opened) contributes nothing.
    """
    beds = {h.code: h.beds[1] for h in hospitals}
    out = {}
    for h in hospitals:
        if h.code not in bor or h.code not in ed:
            continue
        per_type = {}
        for kind in ('weekday', 'weekend'):
            days = sorted(d for d in bor[h.code] if d >= since and day_type(d) == kind)
            ed_days = [v for d, v in ed[h.code].items() if d >= since and day_type(d) == kind]
            if not days or not ed_days:
                continue
            spare = [sum(beds[c] * max(0.0, 1.0 - bor[c][d]) for c in beds if c != h.code and d in bor.get(c, {}))
                     for d in days]
            per_type[kind] = dict(bor=quantiles([bor[h.code][d] for d in days]), ed=quantiles(ed_days),
                                  spare=quantiles(spare), days=len(days), last=days[-1].isoformat())
        if per_type:
            out[h.code] = per_type
    return out


def age65_share(rate_rows: list, census_total: dict) -> tuple:
    """(share of acute admissions aged 65+, year): sum of rate x residents over sexes, 65+ over all ages.

    Rates are admissions per 1,000 residents (latest year); residents are Census 2020 by sex and age.
    """
    acute = [r for r in rate_rows if r.get('facility_type_a') == 'Acute' and r.get('rate') not in (None, '', 'na')]
    year = max(r['year'] for r in acute)
    bands = {'0-14 years': range(0, 15), '15-64 years': range(15, 65), '65 years & over': range(65, 91)}
    admissions = {}
    for r in acute:
        if r['year'] != year:
            continue
        prefix = {'male': 'Males', 'female': 'Females'}[r['sex'].strip().lower()]
        ages = bands[r['age'].strip().lower()]
        residents = sum(float(v) for k, v in census_total.items() if k.startswith(prefix + '_')
                        and _age_start(k) in ages)
        admissions[r['age'].strip().lower()] = admissions.get(r['age'].strip().lower(), 0.0) + float(r['rate']) * residents
    return admissions['65 years & over'] / sum(admissions.values()), year


def ambulance_share(ems_rows: list, attendance_rows: list) -> tuple:
    """(share of A&E attendances arriving by emergency ambulance, year) from SCDF and SingStat annual tables.

    Emergency calls / A&E attendances for the latest year both tables cover, times a conveyance band because not
    every emergency call ends in a conveyance to a public ED.
    """
    def series(rows, label):
        row = next(r for r in rows if r['DataSeries'].strip().lower() == label)
        return {k: float(v) for k, v in row.items() if k.isdigit() and v not in (None, '', 'na')}

    calls = series(ems_rows, 'emergency medical services - emergency calls')
    attendances = series(attendance_rows, 'accident & emergency departments')
    year = max(set(calls) & set(attendances))
    share = calls[year] / attendances[year]
    return tuple(min(1.0, share * c) for c in AMBULANCE_CONVEYANCE), year


def _age_start(column: str):
    part = column.split('_', 1)[1]
    if part == 'Total':
        return None
    return 90 if part.startswith('90') else int(part.split('_')[0])


def _estimate(triple: Triple, unit: str, state: str, grade: str, method: str, source: str = 'assumption',
              source_date: str | None = None) -> Estimate:
    return Estimate(triple[0], triple[1], triple[2], unit, state, grade, source=source, source_date=source_date,
                    method=method)


def _times(*triples: Triple) -> Triple:
    out = [1.0, 1.0, 1.0]
    for t in triples:
        out = [o * v for o, v in zip(out, t)]
    return tuple(out)


def _plus(*triples: Triple) -> Triple:
    return tuple(sum(t[i] for t in triples) for i in range(3))


def _share(part: Triple, whole: Triple) -> Triple:
    """Bounds of part/whole when part is contained in whole: low uses the largest whole, high the smallest."""
    return (part[0] / whole[2], part[1] / whole[1], min(1.0, part[2] / whole[0]))


def hospital_profiles(site: Site) -> list:
    h = site.hospital
    hazard = {name: _estimate(HAZARD[name], 'score_0_100', 'assumption', 'D', 'hospital site potential')
              for name in HAZARD_COMPONENTS}
    loss = _estimate(LOSS_FRACTION, 'fraction', 'assumption', 'D', 'share of hospital function lost')
    outage = _estimate(OUTAGE_HOURS, 'hours', 'assumption', 'D', 'duration of lost function')
    recovery = _estimate(RECOVERY_T90_HOURS, 'hours', 'assumption', 'D', 'time to 90% of hospital function')
    profiles = []
    for condition in CONDITIONS:
        cid = condition.condition_id
        stats = site.stats.get(condition.day_type)
        common = dict(site_id=f'hospital:{h.code}', condition_id=cid, role='acute_hospital',
                      geometry_wkt=site.geometry_wkt, loss_fraction=loss, outage_hours=outage,
                      recovery_t90_hours=recovery, hazard=hazard, categories=('health_emergency',), raw=site.raw)
        if stats is None:
            missing = Estimate.unavailable(f'no MOH {condition.day_type} observations since {SINCE}', 'people')
            profiles.append(Profile(occupancy=missing, beneficiaries_per_hour=missing,
                                    alternative_capacity_fraction=Estimate.unavailable('no MOH observations', 'fraction'),
                                    **common))
            continue
        stamp = stats['last']
        inpatients = _times(h.beds, stats['bor'])
        ed_per_hour = tuple(v / 24 for v in stats['ed'])
        ed_present = _times(ed_per_hour, ED_HOUR_FACTOR[cid], ED_STAY_HOURS)
        staff = _times(h.beds, STAFF_PER_BED, SHIFT_FRACTION[cid])
        visitors = _times(inpatients, VISITORS_PER_INPATIENT[cid])
        people = _plus(inpatients, ed_present, staff, visitors)
        patients = _plus(inpatients, ed_present)
        occupancy = _estimate(people, 'people', 'derived', 'C',
                              'beds x BOR + ED arrivals x stay + staff on shift + visitors', MOH_SOURCE, stamp)
        beneficiaries = _estimate(_plus(inpatients, ed_per_hour), 'people', 'derived', 'B',
                                  f'inpatients (beds x BOR p10/p50/p90, {condition.day_type}) + ED arrivals per hour',
                                  MOH_SOURCE, stamp)
        spare, needed = stats['spare'], inpatients
        alternative = _estimate(
            (min(1.0, spare[0] / needed[2]), min(1.0, spare[1] / needed[1]), min(1.0, spare[2] / needed[0])),
            'fraction', 'derived', 'B', 'empty beds at the other MOH-reported hospitals / this hospital\'s inpatients',
            MOH_SOURCE, stamp)
        unable = _plus(_times(inpatients, NON_AMBULANT_INPATIENTS), _times(ed_present, site.ambulance_share))
        age65 = (site.age65_share[0], site.age65_share[1] * (1 + AGE65_BEDDAY_UPLIFT) / 2,
                 min(1.0, site.age65_share[2] * AGE65_BEDDAY_UPLIFT))
        vulnerability = {
            'medically_dependent': _estimate(_share(patients, people), 'fraction', 'derived', 'C',
                                             'inpatients and ED patients / people present', MOH_SOURCE),
            'unable_to_self_evacuate': _estimate(_share(unable, people), 'fraction', 'derived', 'D',
                                                 'non-ambulant inpatients + ambulance-borne ED patients / people present'),
            'age_vulnerable': _estimate(_times(age65, _share(inpatients, people)), 'fraction', 'derived', 'C',
                                        'share of admissions aged 65+ x inpatient share of people present',
                                        'MOH admission rate by age x Census 2020 residents'),
            'difficult_to_evacuate': _estimate(DIFFICULT_TO_EVACUATE, 'fraction', 'assumption', 'D',
                                               'wards, ICU and theatres on upper floors'),
            'insufficiently_sheltered_or_outdoors': _estimate(OUTDOORS, 'fraction', 'assumption', 'D',
                                                              'people outdoors on the campus'),
        }
        raw = dict(site.raw, bor_p10=round(stats['bor'][0], 4), bor_p50=round(stats['bor'][1], 4),
                   bor_p90=round(stats['bor'][2], 4), ed_daily_p50=round(stats['ed'][1], 1),
                   spare_beds_elsewhere_p50=round(spare[1], 1), days_observed=stats['days'], last_observation=stamp)
        profiles.append(Profile(occupancy=occupancy, beneficiaries_per_hour=beneficiaries,
                                alternative_capacity_fraction=alternative, vulnerability=vulnerability,
                                single_point_of_failure=spare[1] < inpatients[1],
                                **dict(common, raw=raw)))
    return profiles


def _year_value(rows: list, label: str, after: str | None = None) -> tuple:
    """(latest year, value) of a SingStat DataSeries row; `after` picks the first `label` row below that heading."""
    seen = after is None
    for r in sorted(rows, key=lambda r: r['_id']):
        name = r['DataSeries'].strip()
        if not seen:
            seen = name == after
            continue
        if name == label:
            years = {k: v for k, v in r.items() if k.isdigit() and v not in (None, '', 'na')}
            year = max(years)
            return year, float(years[year])
    raise ValueError(f'SingStat row {label!r} not found')


def hospital_sites(bor: dict, ed: dict, census_total: dict, rate_rows: list, ems_rows: list,
                   attendance_rows: list, geocode: dict) -> tuple:
    stats = build_stats(bor, ed)
    age65, rate_year = age65_share(rate_rows, census_total)
    ambulance, ems_year = ambulance_share(ems_rows, attendance_rows)
    sites, skipped = [], []
    for h in HOSPITALS:
        hit = geocode.get(h.postal)
        if hit is None or h.code not in stats:
            skipped.append(h.code)
            continue
        raw = dict(code=h.code, name=h.name, postal=h.postal, onemap_building=hit['building'],
                   beds_low=h.beds[0], beds_central=h.beds[1], beds_high=h.beds[2], bed_source=h.bed_source)
        sites.append(Site(h, shapely.Point(hit['x'], hit['y']).wkt, stats[h.code], (age65,) * 3,
                                    ambulance, raw))
    shares = dict(age65_share_of_acute_admissions=age65, admission_rate_year=rate_year,
                  ambulance_share=ambulance, ems_year=ems_year)
    return sites, skipped, shares


def reconcile(bor: dict, ed: dict, bed_rows: list, attendance_rows: list) -> dict:
    """Cross-checks against SingStat national totals; reported, never used to adjust values."""
    bed_year, public_acute = _year_value(bed_rows, 'Public', after='Acute Hospitals')
    table = sum(h.beds[1] for h in HOSPITALS)
    ae_year, ae_total = _year_value(attendance_rows, 'Accident & Emergency Departments')
    moh_sum = sum(v for s in ed.values() for d, v in s.items() if d.year == int(ae_year))
    return dict(
        beds=dict(table_central_total=table, singstat_public_acute=public_acute, singstat_year=bed_year,
                  table_share=round(table / public_acute, 3),
                  note='SingStat also counts KKH and NUH children\'s beds, which MOH BOR excludes'),
        ed_attendances=dict(moh_daily_sum=moh_sum, singstat_ae=ae_total, year=ae_year,
                            moh_share=round(moh_sum / ae_total, 3) if moh_sum else None,
                            note='SingStat A&E includes KKH and NUH children\'s EDs; MOH daily series start 2023'),
        latest_observation=max(d for s in bor.values() for d in s).isoformat())
