"""Military area consequence profiles: one Profile per OSM military polygon and time condition.

Reads output/defence/defence_output.csv (81 public OpenStreetMap landuse=military outlines, written by
geography/build_military_areas.py). Nothing about a site's function, headcount or capability is inferred:
- occupancy is one generic assumed density for military land, the same for every site, times the spec section 9
  "Office" time coefficients, and only the share inside the placeholder footprint is scored (areal density);
- no civilian service is publicly attributable, so service loss is set to the lowest band by assumption;
- capability (D) stays unavailable until an authorised input supplies it.
The six outlines named as air bases are declared priority assets, so the veto rejects them while their capability
is unassessed (scoring.veto). The other areas are ranked like any site.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from pyproj import Transformer
import shapely
from shapely.ops import transform

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.conditions import CONDITIONS
from backend.data_sources.consequence.paths import OUTPUT
from backend.data_sources.consequence.population_disaggregation import (PLACEHOLDER_FOOTPRINT_RADIUS_M,
                                                                        effective_occupancy_areal_density,
                                                                        placeholder_overlap_km2)

SOURCE = OUTPUT / 'defence' / 'defence_output.csv'
DENSITY_PER_KM2 = (100.0, 500.0, 2000.0)  # people per km2 at full occupancy, every military site (assumption)
TIME_COEFFICIENT = {  # spec section 9 "Office" row mapped onto the six conditions (assumption)
    'weekday_am_peak': 0.60, 'weekday_midday': 0.85, 'weekday_pm_peak': 0.40,
    'weekday_night': 0.05, 'weekend_day': 0.10, 'weekend_night': 0.05,
}
RECOVERY_T90_HOURS = (168, 720, 2160)  # as other buildings (assumption)
Triple = tuple

_TO_SVY21 = Transformer.from_crs('EPSG:4326', 'EPSG:3414', always_xy=True)


@dataclass(frozen=True)
class Site:
    site_id: str
    name: str
    air_base: bool
    geometry_wkt: str  # EPSG:3414
    raw: dict = field(default_factory=dict)


def load_sites(path: Path = SOURCE) -> list:
    sites = []
    with path.open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            geometry = transform(_TO_SVY21.transform, shapely.from_wkt(r['geometry_wkt']))
            sites.append(Site(r['id'], r['name'], r['name_contains_air_base'] == 'True', geometry.wkt,
                              dict(name=r['name'], area_m2=r['area_m2'], source=r['source'])))
    return sites


def _estimate(triple: Triple, unit: str, method: str, state: str = 'assumption', grade: str = 'D') -> Estimate:
    return Estimate(triple[0], triple[1], triple[2], unit, state, grade, method=method)


def military_profiles(site: Site) -> list:
    geometry = shapely.from_wkt(site.geometry_wkt)
    area_km2 = geometry.area / 1e6
    overlap = placeholder_overlap_km2(geometry)
    role = 'military_air_base' if site.air_base else 'military_area'
    categories = ('defence_security', 'aviation') if site.air_base else ('defence_security',)
    # No civilian service is publicly attributable: zero beneficiaries puts E in its lowest band (10).
    beneficiaries = Estimate.exact(0.0, 'people', 'assumption', 'D',
                                   method='no publicly attributable civilian service; lowest E band by assumption')
    loss = _estimate((1.0, 1.0, 1.0), 'fraction', 'placeholder; beneficiaries are zero')
    outage = _estimate((24.0, 24.0, 24.0), 'hours', 'placeholder; beneficiaries are zero')
    alternative = _estimate((0.0, 0.0, 0.0), 'fraction', 'placeholder; beneficiaries are zero')
    recovery = _estimate(RECOVERY_T90_HOURS, 'hours', 'time to 90% of site function (as other buildings)')
    method = (f'generic military-land density x office time coefficient, share of site inside a '
              f'{PLACEHOLDER_FOOTPRINT_RADIUS_M:.0f} m placeholder footprint (uniform density, assumption)')
    profiles = []
    for condition in CONDITIONS:
        k = TIME_COEFFICIENT[condition.condition_id]
        people = tuple(effective_occupancy_areal_density(d * area_km2 * k, area_km2, overlap) for d in DENSITY_PER_KM2)
        profiles.append(Profile(
            site_id=site.site_id, condition_id=condition.condition_id, role=role, geometry_wkt=site.geometry_wkt,
            occupancy=_estimate(people, 'people', method), beneficiaries_per_hour=beneficiaries, loss_fraction=loss,
            outage_hours=outage, alternative_capacity_fraction=alternative, recovery_t90_hours=recovery,
            priority_asset=site.air_base, categories=categories, raw=site.raw,
            population_method='areal_density', overlap_area_km2=overlap))
    return profiles
