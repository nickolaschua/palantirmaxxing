"""Parks and civic venue consequence profiles: one Profile per site and parks scenario.

Reads the committed evidence tables built by build_parks_civic.mjs. Occupancy bands come from those tables
(area-density or venue priors, grade C/D). Service loss, recovery and hazard have no public per-site source, so
they are per-subtype assumptions (grade D), set so that open space scores no higher than roads and civic buildings
no higher than other buildings (see doc/plans/2026-09-25-parks-civic-profiles.md).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from pyproj import Transformer
import shapely

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS

HERE = Path(__file__).parent
SCENARIOS = ('WD_AM', 'WD_DAY', 'WD_PM', 'WD_NIGHT', 'WE_DAY', 'WE_PM', 'EVENT', 'CLOSED')
USERS_SCENARIO = 'WE_DAY'  # weekend-day occupancy stands in for a site's regular users
Triple = tuple  # (low, central, high)

OPEN = 'park', 'nature_reserve', 'community_use_site'
LOSS_FRACTION = {  # share of the site's use lost (assumption)
    'park': (0.3, 0.7, 1.0), 'nature_reserve': (0.2, 0.5, 1.0), 'community_use_site': (0.3, 0.7, 1.0),
    'sport_venue': (0.5, 0.8, 1.0), 'community_club': (0.3, 0.7, 1.0), 'library': (0.3, 0.7, 1.0),
    'theatre': (0.5, 1.0, 1.0), 'monument': (0.3, 0.7, 1.0),
}
USE_HOURS_LOST = {  # hours of use lost per regular user over the outage (assumption)
    'park': (2, 6, 24), 'nature_reserve': (2, 8, 48), 'community_use_site': (2, 6, 24),
    'sport_venue': (4, 12, 48), 'community_club': (6, 24, 96), 'library': (4, 12, 48),
    'theatre': (2, 6, 24), 'monument': (1, 2, 8),
}
ALTERNATIVE = {  # share of users served elsewhere: other parks, venues, branches, e-services (assumption)
    'park': (0.7, 0.85, 0.95), 'nature_reserve': (0.5, 0.7, 0.9), 'community_use_site': (0.7, 0.85, 0.95),
    'sport_venue': (0.5, 0.7, 0.9), 'community_club': (0.3, 0.5, 0.7), 'library': (0.5, 0.7, 0.9),
    'theatre': (0.3, 0.5, 0.7), 'monument': (0.5, 0.7, 0.9),
}
RECOVERY_T90_HOURS = {  # open space at or below roads (R 30); buildings at or below schools/housing (R 75)
    'park': (24, 72, 336), 'nature_reserve': (24, 72, 2160), 'community_use_site': (24, 72, 336),
    'sport_venue': (24, 72, 720), 'community_club': (168, 720, 2160), 'library': (168, 720, 2160),
    'theatre': (168, 720, 2160), 'monument': (720, 2160, 8760),
}
OUTDOORS = {  # share of people insufficiently sheltered or outdoors (assumption)
    'park': (0.7, 0.9, 1.0), 'nature_reserve': (0.7, 0.9, 1.0), 'community_use_site': (0.7, 0.9, 1.0),
    'sport_venue': (0.3, 0.6, 0.9), 'monument': (0.2, 0.5, 0.9),
    'community_club': (0.0, 0.02, 0.05), 'library': (0.0, 0.02, 0.05), 'theatre': (0.0, 0.02, 0.05),
}
HAZARD_BASE = (0.0, 0.0, 5.0)
HAZARD = {  # (assumption) site potential, 0-100; unlisted components use HAZARD_BASE
    'sport_venue': {'toxic': (0.0, 5.0, 15.0)},  # pool chlorine
    'theatre': {'flammable': (0.0, 5.0, 15.0)},  # stage materials
}

_TO_SVY21 = Transformer.from_crs('EPSG:4326', 'EPSG:3414', always_xy=True)


@dataclass(frozen=True)
class Site:
    site_id: str
    name: str
    subtype: str
    category: str
    geometry_wkt: str  # EPSG:3414
    source_date: str | None  # ISO date of the site's source record
    occupancy: dict  # scenario_id -> (triple, grade, method)
    raw: dict = field(default_factory=dict)


def iso_date(stamp: str) -> str | None:
    """'20260115000106' -> '2026-01-15'; a year alone -> Dec 31 of that year (latest possible, so least stale)."""
    stamp = (stamp or '').strip()
    if len(stamp) >= 8 and stamp[:8].isdigit():
        return f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}'
    if len(stamp) == 4 and stamp.isdigit():
        return f'{stamp}-12-31'
    return None


def load_sites(folder: Path = HERE) -> list:
    with (folder / 'input_conditions.csv').open(encoding='utf-8') as f:
        occupancy: dict = {}
        for r in csv.DictReader(f):
            triple = tuple(float(r[f'occupancy_{p}']) for p in ('low', 'central', 'high'))
            occupancy.setdefault(r['site_id'], {})[r['scenario_id']] = (triple, r['estimate_confidence'],
                                                                         r['occupancy_method'])
    sites = []
    with (folder / 'input_sites.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            x, y = _TO_SVY21.transform(float(r['longitude']), float(r['latitude']))
            raw = {k: r[k] for k in ('name', 'subtype', 'postal_code', 'area_sqm', 'facility_count', 'source_id',
                                     'source_native_id', 'source_updated', 'data_confidence')}
            sites.append(Site(r['site_id'], r['name'], r['subtype'], r['category'], shapely.Point(x, y).wkt,
                              iso_date(r['source_updated']), occupancy[r['site_id']], raw))
    return sites


def _estimate(triple: Triple, unit: str, method: str, state: str = 'assumption', grade: str = 'D', **kw) -> Estimate:
    return Estimate(triple[0], triple[1], triple[2], unit, state, grade, method=method, **kw)


def parks_profiles(site: Site) -> list:
    sub = site.subtype
    source = f"parks-civic evidence tables ({site.raw['source_id']})"
    users, users_grade, _ = site.occupancy[USERS_SCENARIO]
    beneficiaries = _estimate(users, 'people', 'weekend-day occupancy as a proxy for regular users', 'derived',
                              users_grade, source=source, source_date=site.source_date)
    loss = _estimate(LOSS_FRACTION[sub], 'fraction', 'share of site use lost')
    outage = _estimate(USE_HOURS_LOST[sub], 'hours', 'hours of use lost per regular user')
    alternative = _estimate(ALTERNATIVE[sub], 'fraction', 'users served by other sites or services')
    recovery = _estimate(RECOVERY_T90_HOURS[sub], 'hours', 'time to 90% of site function')
    hazard = {name: _estimate(HAZARD.get(sub, {}).get(name, HAZARD_BASE), 'score_0_100', f'{sub} site potential')
              for name in HAZARD_COMPONENTS}
    reason = 'no per-site public source'
    vulnerability = {
        'insufficiently_sheltered_or_outdoors': _estimate(OUTDOORS[sub], 'fraction', f'{sub} outdoor share'),
        'unable_to_self_evacuate': Estimate.unavailable(reason, 'fraction'),
        'medically_dependent': Estimate.unavailable(reason, 'fraction'),
        'difficult_to_evacuate': Estimate.unavailable(reason, 'fraction'),
        'age_vulnerable': Estimate.unavailable(reason, 'fraction'),
    }
    profiles = []
    for scenario in SCENARIOS:
        triple, grade, method = site.occupancy[scenario]
        occupancy = _estimate(triple, 'people', method, 'derived', grade, source=source,
                              source_date=site.source_date)
        profiles.append(Profile(
            site_id=site.site_id, condition_id=scenario, role=sub, geometry_wkt=site.geometry_wkt,
            occupancy=occupancy, beneficiaries_per_hour=beneficiaries, loss_fraction=loss, outage_hours=outage,
            alternative_capacity_fraction=alternative, recovery_t90_hours=recovery, vulnerability=vulnerability,
            hazard=hazard, categories=(site.category,), raw=site.raw))
    return profiles
