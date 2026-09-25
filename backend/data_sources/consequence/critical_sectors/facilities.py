"""Critical-sector facility profiles: official URA land-use parcels carrying their national system's evidence.

The national profiles (input_profiles.csv) and scenario vectors (output/critical_sectors/critical_sectors_output.csv)
are system totals with no location. This module places them on URA Master Plan 2019 land-use parcels (already
cached for the residential sector, so no network) so they can be ranked with every other site:
- `build_facilities` writes input_facilities.csv, which later runs read offline:
  PORT / AIRPORT parcels near Changi or Seletar are dissolved into one airport site each (AVI-PAX; parcels mostly
  inside a defence air-base polygon are dropped); the other PORT / AIRPORT parcels are grouped into contiguous port
  sites (PORT-CONT); every UTILITY parcel is one utility site (energy and water together: URA does not say which).
- each site carries a share of its system: Changi 1.0 and Seletar a small band for AVI-PAX; ports an equal split;
  utilities their share of total utility land area. Non-fixed shares carry a 0.5x-1.5x band (assumption).
- service loss takes the system's beneficiaries x share x the builder's MAJOR_12H loss, duration and alternative
  capacity bands (utilities use ENE-ELEC's, which match every energy and water profile); recovery maps the builder's
  R back to hours.
- occupancy is AVI-PAX people for airports, else a generic workforce density; both are area sites, so only the
  share inside the placeholder footprint is scored.
Profiles with no site of their own stay national and are listed by `unsited_profiles`.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import logging
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
import shapely

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.conditions import CONDITIONS
from backend.data_sources.consequence.paths import OUTPUT, SOURCES_CACHE
from backend.data_sources.consequence.population_disaggregation import (PLACEHOLDER_FOOTPRINT_RADIUS_M,
                                                                        effective_occupancy_areal_density,
                                                                        placeholder_overlap_km2)

log = logging.getLogger(__name__)

HERE = Path(__file__).parent
FACILITIES = HERE / 'input_facilities.csv'
LANDUSE = SOURCES_CACHE / 'landuse-mp2019.geojson'  # URA Master Plan 2019, cached by the residential sector
SCENARIO_ROWS = OUTPUT / 'critical_sectors' / 'critical_sectors_output.csv'
DISRUPTION = 'MAJOR_12H'  # builder scenario used for a facility lost to debris
AIR_BASE_OVERLAP = 0.5  # a parcel mostly inside a defence air-base polygon is a military airfield
PORT_JOIN_M = 50.0  # port parcels closer than this form one port site
AIRPORTS = {  # name -> ((lon, lat) public airport reference point, radius m, share band, basis)
    'Changi Airport': ((103.9915, 1.3644), 4000.0, (1.0, 1.0, 1.0),
                       'Changi carries all AVI-PAX passenger movements'),
    'Seletar Airport': ((103.8678, 1.4172), 2000.0, (0.0, 0.005, 0.02),
                        'Seletar business/turboprop airport, small share (assumption)'),
}
_TO_SVY21 = Transformer.from_crs('EPSG:4326', 'EPSG:3414', always_xy=True)
ROLE = {'AVI-PAX': 'airport', 'PORT-CONT': 'port_terminal', 'UTILITY': 'utility'}
EVIDENCE_OF = {'UTILITY': 'ENE-ELEC'}  # utilities borrow the energy scenario bands (identical across energy/water)
CATEGORIES = {'UTILITY': ('energy', 'water')}
THROUGHPUT = ('PORT-CONT',)  # no person-hour basis: ordinal E by assumption
THROUGHPUT_E_PERSON_HOURS = (1e4, 1e5, 1e6)  # service_score 40 / 60 / 80
WORKFORCE_PER_KM2 = (50.0, 200.0, 600.0)  # people per km2 at full occupancy, any facility (assumption)
INDUSTRIAL_COEFFICIENT = {  # spec section 9 "Continuous industrial" row (assumption)
    'weekday_am_peak': 0.70, 'weekday_midday': 0.70, 'weekday_pm_peak': 0.55,
    'weekday_night': 0.45, 'weekend_day': 0.50, 'weekend_night': 0.45,
}
AIRPORT_COEFFICIENT = {  # passengers present relative to the daily average (assumption)
    'weekday_am_peak': 1.0, 'weekday_midday': 1.0, 'weekday_pm_peak': 1.0,
    'weekday_night': 0.5, 'weekend_day': 1.0, 'weekend_night': 0.5,
}
R_HOURS = {5: 3, 15: 12, 30: 48, 50: 200, 75: 1000, 100: 4000}  # R band score -> representative hours to 90%
FIELDS = ('site_id', 'name', 'profile_id', 'parcels', 'area_m2', 'share_low', 'share_central', 'share_high',
          'share_basis', 'geometry_wkt')


@dataclass(frozen=True)
class Facility:
    site_id: str
    name: str
    profile_id: str
    share: tuple
    share_basis: str
    geometry_wkt: str  # EPSG:3414
    raw: dict = field(default_factory=dict)


# ---- Building sites from land-use parcels (pure) ----

def _band(s: float) -> tuple:
    return (0.5 * s, s, min(1.0, 1.5 * s))


def is_air_base(geometry, air_bases: list) -> bool:
    inside = sum(shapely.intersection(geometry, b).area for b in air_bases)
    return geometry.area > 0 and inside / geometry.area > AIR_BASE_OVERLAP


def build_rows(port_airport: list, utility: list, air_bases: list) -> list:
    """port_airport, utility: parcel geometries in EPSG:3414. Returns input_facilities rows with shares."""
    rows, airport_parts, ports = [], {name: [] for name in AIRPORTS}, []
    for g in port_airport:
        if is_air_base(g, air_bases):
            continue
        c = g.representative_point()
        near = next((n for n, (lonlat, radius, *_) in AIRPORTS.items()
                     if c.distance(shapely.Point(_TO_SVY21.transform(*lonlat))) <= radius), None)
        (airport_parts[near] if near else ports).append(g)
    for name, parts in airport_parts.items():
        if parts:
            _, _, share, basis = AIRPORTS[name]
            geometry = shapely.union_all(parts)
            rows.append(dict(site_id=f"facility:{name.lower().replace(' ', '_')}", name=name, profile_id='AVI-PAX',
                             parcels=len(parts), geometry=geometry, share=share, share_basis=basis))
    if ports:
        clusters = shapely.union_all([g.buffer(PORT_JOIN_M) for g in ports])
        clusters = list(getattr(clusters, 'geoms', [clusters]))
        for i, cluster in enumerate(sorted(clusters, key=lambda c: -c.area), 1):
            members = [g for g in ports if g.intersects(cluster)]
            rows.append(dict(site_id=f'facility:port_{i}', name=f'Port area {i}', profile_id='PORT-CONT',
                             parcels=len(members), geometry=shapely.union_all(members),
                             share=_band(1 / len(clusters)), share_basis='equal_split_assumption'))
    total = sum(g.area for g in utility)
    for i, g in enumerate(sorted(utility, key=lambda g: -g.area), 1):
        rows.append(dict(site_id=f'facility:utility_{i}', name=f'Utility parcel {i}', profile_id='UTILITY',
                         parcels=1, geometry=g, share=_band(g.area / total), share_basis='utility_area_share_assumption'))
    return rows


def build_facilities(air_bases: list, landuse: Path = LANDUSE, path: Path = FACILITIES) -> list:
    """Read the cached URA land-use parcels and write input_facilities.csv."""
    parcels = gpd.read_file(landuse).to_crs('EPSG:3414')
    parcels = parcels[parcels.geometry.notna() & ~parcels.geometry.is_empty]
    pick = lambda desc: [shapely.make_valid(g) for g in parcels[parcels.LU_DESC == desc].geometry]
    rows = build_rows(pick('PORT / AIRPORT'), pick('UTILITY'), air_bases)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(site_id=r['site_id'], name=r['name'], profile_id=r['profile_id'], parcels=r['parcels'],
                                 area_m2=round(r['geometry'].area, 1), share_low=r['share'][0],
                                 share_central=r['share'][1], share_high=r['share'][2], share_basis=r['share_basis'],
                                 geometry_wkt=r['geometry'].wkt))
    log.info('Wrote %d critical-sector facility sites -> %s', len(rows), path)
    return rows


# ---- Profiles ----

def load_facilities(path: Path = FACILITIES) -> list:
    out = []
    with path.open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            share = tuple(float(r[f'share_{p}']) for p in ('low', 'central', 'high'))
            out.append(Facility(r['site_id'], r['name'], r['profile_id'], share, r['share_basis'], r['geometry_wkt'],
                                raw={k: r[k] for k in ('name', 'profile_id', 'parcels', 'area_m2', 'share_basis')}))
    return out


def load_evidence(profiles_path: Path = HERE / 'input_profiles.csv', rows_path: Path = SCENARIO_ROWS) -> dict:
    """profile_id -> {'profile': input_profiles row, 'disruption': MAJOR_12H row, 'base': BASE row}."""
    with profiles_path.open(encoding='utf-8') as f:
        evidence = {r['id']: {'profile': r} for r in csv.DictReader(f)}
    with rows_path.open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['scenario_id'] == DISRUPTION:
                evidence[r['profile_id']]['disruption'] = r
            elif r['scenario_id'] == 'BASE':
                evidence[r['profile_id']]['base'] = r
    return evidence


def unsited_profiles(facilities: list, evidence: dict) -> list:
    sited = {EVIDENCE_OF.get(f.profile_id, f.profile_id) for f in facilities}
    return sorted(p for p in evidence if p not in sited)


def _estimate(triple, unit: str, method: str, state: str = 'assumption', grade: str = 'D', source: str = '') -> Estimate:
    return Estimate(triple[0], triple[1], triple[2], unit, state, grade, source=source, method=method)


def _triple(row: dict, low: str, central: str, high: str) -> tuple:
    return float(row[low]), float(row[central]), float(row[high])


def facility_profiles(facility: Facility, evidence: dict) -> list:
    ev = evidence[EVIDENCE_OF.get(facility.profile_id, facility.profile_id)]
    system, disruption = ev['profile'], ev['disruption']
    source = f"critical_sectors {facility.profile_id} ({system['public_basis']})"
    geometry = shapely.from_wkt(facility.geometry_wkt)
    area_km2 = geometry.area / 1e6
    overlap = placeholder_overlap_km2(geometry)
    share = facility.share
    if facility.profile_id in THROUGHPUT:
        method = f"ordinal assumption: {system['unit']} throughput has no person-hour basis"
        beneficiaries = _estimate(THROUGHPUT_E_PERSON_HOURS, 'person-hours equivalent', method)
        loss = _estimate((1.0, 1.0, 1.0), 'fraction', method)
        outage = _estimate((1.0, 1.0, 1.0), 'hours', method)
        alternative = _estimate((0.0, 0.0, 0.0), 'fraction', method)
    else:
        b = float(system['beneficiaries'])
        beneficiaries = _estimate((b, b, b), 'people', f"system beneficiaries ({system['unit']})", 'derived', 'C',
                                  source)
        system_loss = _triple(disruption, 'loss_low', 'loss_fraction', 'loss_high')
        loss = _estimate(tuple(s * l for s, l in zip(share, system_loss)), 'fraction',
                         f'facility share ({facility.share_basis}) x system {DISRUPTION} loss', source=source)
        outage = _estimate(_triple(disruption, 'hours_low', 'outage_hours', 'hours_high'), 'hours',
                           f'system {DISRUPTION} duration', source=source)
        alternative = _estimate(_triple(disruption, 'alt_low', 'alternative_capacity_fraction', 'alt_high'),
                                'fraction', f'system {DISRUPTION} alternative capacity', source=source)
    r = _triple(disruption, 'R_low', 'R_central', 'R_high')
    recovery = _estimate(tuple(R_HOURS[int(v)] for v in r), 'hours', f'builder R band for {DISRUPTION} as hours',
                         source=source)
    airport = facility.profile_id == 'AVI-PAX'
    if airport:
        base = ev['base']
        full = tuple(s * p for s, p in zip(share, _triple(base, 'people_low', 'people_central', 'people_high')))
        how = 'AVI-PAX passengers present x facility share x time coefficient'
    else:
        full = tuple(d * area_km2 for d in WORKFORCE_PER_KM2)
        how = 'generic facility workforce density x continuous-industrial time coefficient'
    how += (f', share of site inside a {PLACEHOLDER_FOOTPRINT_RADIUS_M:.0f} m placeholder footprint'
            ' (uniform density, assumption)')
    profiles = []
    for condition in CONDITIONS:
        k = (AIRPORT_COEFFICIENT if airport else INDUSTRIAL_COEFFICIENT)[condition.condition_id]
        people = tuple(effective_occupancy_areal_density(n * k, area_km2, overlap) for n in full)
        profiles.append(Profile(
            site_id=facility.site_id, condition_id=condition.condition_id, role=ROLE[facility.profile_id],
            geometry_wkt=facility.geometry_wkt, occupancy=_estimate(people, 'people', how),
            beneficiaries_per_hour=beneficiaries, loss_fraction=loss, outage_hours=outage,
            alternative_capacity_fraction=alternative, recovery_t90_hours=recovery,
            categories=CATEGORIES.get(facility.profile_id, (system['sector'],)), raw=facility.raw,
            population_method='areal_density', overlap_area_km2=overlap))
    return profiles
