"""Residential consequence profiles: HDB blocks and private housing.

Sites: subzone residents from Census 2020 are allocated to HDB blocks and private residential parcels (pure
functions plus geopandas spatial joins). Every census resident is placed on a site or on a `subzone_remainder`
site, so `reconcile` can prove that nothing is dropped or invented. Residents that a site receives from a national
rate (a block completed after the 2020 census, or a group the census left blank) are extra estimates, reported
separately from the census-basis total.

Profiles: one Profile per site and transport condition. Every number marked (assumption) is uncalibrated and
grade D. Census-derived resident counts carry the census vintage in `source`; source_date is left empty because
the shared staleness flag uses a 400-day window that suits monthly feeds, not a decennial census.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd
import shapely

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.conditions import CONDITIONS
from backend.data_sources.consequence.population_disaggregation import (PLACEHOLDER_FOOTPRINT_RADIUS_M,
                                                                        effective_occupancy_areal_density,
                                                                        placeholder_overlap_km2)
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS
from backend.data_sources.population import join_boundaries, parse_hierarchy, parse_value

CENSUS_YEAR = 2020
GROUP_COLUMNS = {  # census dwelling-type table column for each group
    'hdb_1_2': 'HDBDwellings_1_and2_RoomFlats1',
    'hdb_3': 'HDBDwellings_3_RoomFlats',
    'hdb_4': 'HDBDwellings_4_RoomFlats',
    'hdb_5': 'HDBDwellings_5_RoomandExecutiveFlats',
    'condo': 'CondominiumsandOtherApartments',
    'landed': 'LandedProperties',
    'others': 'Others',
}
HDB_GROUPS = ('hdb_1_2', 'hdb_3', 'hdb_4', 'hdb_5')
# HDB Property Information unit columns folded into each census group. other_room_rental (185 units
# nationally) has no census counterpart and is folded into 4-room, an assumption.
HDB_UNIT_COLUMNS = {
    'hdb_1_2': ('1room_sold', '2room_sold', 'studio_apartment_sold', '1room_rental', '2room_rental'),
    'hdb_3': ('3room_sold', '3room_rental'),
    'hdb_4': ('4room_sold', 'other_room_rental'),
    'hdb_5': ('5room_sold', 'exec_sold', 'multigen_sold'),
}
AGE_VULNERABLE_COLUMNS = ('Total_0_4', 'Total_65_69', 'Total_70_74', 'Total_75_79', 'Total_80_84',
                          'Total_85_89', 'Total_90andOver')
# Uncalibrated assumptions for parcels whose land-use GPR is not a number.
LANDED_GPR = 1.4
UNKNOWN_GPR = 1.0


def parse_units(record: dict) -> dict:
    """Dwelling units per census group for one HDB Property Information row."""
    def whole(value):
        try:
            return int(str(value).strip())
        except ValueError:
            return 0
    return {g: sum(whole(record.get(c)) for c in cols) for g, cols in HDB_UNIT_COLUMNS.items()}


def _by_subzone(rows: list, columns: list, features: list, total_key: str) -> dict:
    rows = [dict(r) for r in rows]
    for r in rows:
        if 'Total_Total' not in r and total_key in r:
            r['Total_Total'] = r[total_key]
    zones, _ = parse_hierarchy(rows)
    matches, _ = join_boundaries(zones, features)
    out = {}
    for feature, (zone, _status) in zip(features, matches):
        if zone is not None:
            row = rows[zone['source_row'] - 1]
            out[feature['properties']['SUBZONE_C']] = {c: parse_value(row.get(c))[0] for c in columns}
    return out


def census_by_subzone(dwelling_rows: list, age_rows: list, features: list) -> dict:
    """{SUBZONE_C: {residents: {group: int|None}, total, age_vulnerable_share, ...}} for matched subzones.

    None means the census gave no number (a dash: nil, negligible or not significant), never zero.
    """
    dwelling = _by_subzone(dwelling_rows, list(GROUP_COLUMNS.values()) + ['Total_Total'], features, 'Total')
    age = _by_subzone(age_rows, list(AGE_VULNERABLE_COLUMNS) + ['Total_Total'], features, 'Total_Total')
    names = {f['properties']['SUBZONE_C']: (f['properties']['PLN_AREA_N'], f['properties']['SUBZONE_N'])
             for f in features}
    out = {}
    for code, row in dwelling.items():
        ages = age.get(code, {})
        parts = [ages.get(c) for c in AGE_VULNERABLE_COLUMNS]
        total = ages.get('Total_Total')
        share = sum(parts) / total if total and None not in parts else None
        out[code] = dict(planning_area=names[code][0], subzone=names[code][1],
                         residents={g: row[c] for g, c in GROUP_COLUMNS.items()},
                         total=row['Total_Total'], age_vulnerable_share=share)
    return out


def assign_subzones(geometries: list, subzones: gpd.GeoDataFrame, nearest_m: float = 200) -> list:
    """SUBZONE_C for each geometry (EPSG:3414), or None. Points on a boundary or just outside
    every subzone take the nearest one within nearest_m. `subzones` needs SUBZONE_C and geometry."""
    zones = subzones[['SUBZONE_C', 'geometry']]
    left = gpd.GeoDataFrame({'i': range(len(geometries))}, geometry=list(geometries), crs=zones.crs)
    joined = gpd.sjoin(left, zones, how='left', predicate='intersects')
    joined = joined[~joined.index.duplicated()]
    codes = dict(zip(joined['i'], joined['SUBZONE_C']))
    missing = left[[pd.isna(codes[i]) for i in left['i']]]
    if len(missing):
        near = gpd.sjoin_nearest(missing, zones, how='left', max_distance=nearest_m)
        near = near[~near.index.duplicated()]
        codes.update(zip(near['i'], near['SUBZONE_C']))
    return [None if pd.isna(codes[i]) else codes[i] for i in range(len(geometries))]


def allocate_hdb(blocks: list, census: dict, census_year: int = CENSUS_YEAR) -> tuple:
    """Residents per HDB block; returns ({site_id: {...}}, {subzone: unplaced HDB residents}).

    blocks: dicts with site_id, subzone, units {group: n}, year_completed (int or None).
    Residents per unit = census residents of the group / units of that group in blocks completed by the
    census year, per subzone. Other blocks and groups use the national rate for that group.
    """
    def eligible(b):
        return b['year_completed'] is None or b['year_completed'] <= census_year

    units = defaultdict(lambda: dict.fromkeys(HDB_GROUPS, 0))
    for b in blocks:
        if eligible(b):
            for g in HDB_GROUPS:
                units[b['subzone']][g] += b['units'].get(g, 0)
    rate, res_sum, unit_sum = {}, dict.fromkeys(HDB_GROUPS, 0.0), dict.fromkeys(HDB_GROUPS, 0)
    for sz, u in units.items():
        for g in HDB_GROUPS:
            residents = census.get(sz, {}).get('residents', {}).get(g)
            if residents is not None and u[g] > 0:
                rate[(sz, g)] = residents / u[g]
                res_sum[g] += residents
                unit_sum[g] += u[g]
    national = {g: res_sum[g] / unit_sum[g] for g in HDB_GROUPS if unit_sum[g]}

    result = {}
    for b in blocks:
        census_basis = national_basis = 0.0
        for g in HDB_GROUPS:
            n = b['units'].get(g, 0)
            if not n:
                continue
            r = rate.get((b['subzone'], g)) if eligible(b) else None
            if r is not None:
                census_basis += n * r
            else:
                national_basis += n * national.get(g, 0.0)
        method = ('census_subzone_rate' if not national_basis
                  else 'national_rate' if not census_basis else 'mixed_rate')
        result[b['site_id']] = dict(residents=census_basis + national_basis, census_basis=census_basis,
                                    national_basis=national_basis, method=method)
    remainder = defaultdict(float)
    for sz, c in census.items():
        for g in HDB_GROUPS:
            if c['residents'].get(g) and not units.get(sz, {}).get(g):
                remainder[sz] += c['residents'][g]
    return result, dict(remainder)


def gpr_value(gpr) -> tuple:
    """(plot ratio, basis). LND marks landed housing; other non-numbers are an assumed ratio."""
    text = str(gpr).strip().upper()
    if text == 'LND':
        return LANDED_GPR, 'landed_assumed'
    try:
        return float(text), 'gpr'
    except ValueError:
        return UNKNOWN_GPR, 'gpr_unknown_assumed'


def allocate_private(parcels: list, census: dict) -> tuple:
    """Condominium, landed and other residents shared out by floor area within each subzone.

    parcels: dicts with site_id, subzone, floor_area, landed. Landed residents go to landed parcels and
    condominium+other residents to the rest; a pool with no parcels of its own falls back to the
    other kind, and to the remainder when the subzone has no parcels at all.
    Returns ({site_id: residents}, {subzone: unplaced residents}).
    """
    by_zone = defaultdict(list)
    for p in parcels:
        by_zone[p['subzone']].append(p)
    residents, remainder = defaultdict(float), defaultdict(float)
    for sz, c in census.items():
        res = c['residents']
        landed = [p for p in by_zone.get(sz, ()) if p['landed']]
        other = [p for p in by_zone.get(sz, ()) if not p['landed']]
        for pool, primary, secondary in ((res.get('landed') or 0, landed, other),
                                         (sum(res.get(g) or 0 for g in ('condo', 'others')), other, landed)):
            targets = primary or secondary
            area = sum(p['floor_area'] for p in targets)
            if not pool:
                continue
            if not targets or area <= 0:
                remainder[sz] += pool
                continue
            for p in targets:
                residents[p['site_id']] += pool * p['floor_area'] / area
    return dict(residents), dict(remainder)


def reconcile(census: dict, hdb: dict, private: dict, remainder: dict) -> dict:
    """Census-basis residents in must equal residents placed on sites (plus remainder)."""
    census_total = sum(v for c in census.values() for v in c['residents'].values() if v is not None)
    hdb_census = sum(a['census_basis'] for a in hdb.values())
    placed = hdb_census + sum(private.values()) + sum(remainder.values())
    return dict(census_total=census_total, allocated_census_basis=placed, difference=placed - census_total,
                hdb_census_basis=hdb_census, private=sum(private.values()), remainder=sum(remainder.values()),
                extra_estimated_national_rate=sum(a['national_basis'] for a in hdb.values()))


# ---- Profiles ----

CENSUS_SOURCE = 'SingStat Census of Population 2020 (residents, MP2019 subzones)'
Triple = tuple  # (low, central, high)

# Share of residents at home in each condition (spec §9 residential row, mapped onto the six windows).
HOME_FRACTION = {
    'weekday_am_peak': (0.55, 0.70, 0.85),
    'weekday_midday': (0.40, 0.55, 0.70),
    'weekday_pm_peak': (0.60, 0.75, 0.90),
    'weekday_night': (0.85, 0.92, 0.98),
    'weekend_day': (0.60, 0.75, 0.90),
    'weekend_night': (0.85, 0.92, 0.98),
}
NON_RESIDENT_UPLIFT = (1.00, 1.05, 1.15)  # visitors, domestic workers and others not counted as residents
# Multipliers on the allocated resident count, by how the count was obtained.
RESIDENTS_BAND = {
    'census_subzone_rate': (0.90, 1.00, 1.10),  # census rounding at subzone level
    'mixed_rate': (0.80, 1.00, 1.20),
    'national_rate': (0.70, 1.00, 1.30),  # block completed after the 2020 census, or group left blank
    'floor_area_share': (0.60, 1.00, 1.50),  # private housing shared out by plot area x GPR
    'subzone_remainder': (0.90, 1.00, 1.10),
}
# Area sites (merged landed lots, subzone remainders) carry a whole area's residents; only the share inside the
# placeholder footprint is scored (population_disaggregation.py, areal density). Blocks and parcels are direct.
AREAL_ROLES = ('private_landed', 'subzone_remainder')
RESIDENTS_GRADE = {'census_subzone_rate': 'C', 'mixed_rate': 'D', 'national_rate': 'D',
                   'floor_area_share': 'D', 'subzone_remainder': 'C'}
# Shelter displacement service (E): residents who lose their home, for how long, and with what fallback.
LOSS_FRACTION = (0.1, 0.5, 1.0)  # share of residents displaced
DISPLACEMENT_HOURS = (72, 720, 4320)  # 3 days, 30 days, 180 days
ALTERNATIVE_ACCOMMODATION = (0.2, 0.5, 0.8)  # stay with family or temporary shelter
RECOVERY_T90_HOURS = (72, 720, 4320)
HIGH_FLOOR = 12  # floors above this depend on lifts and stairs for evacuation
HIGH_FLOOR_BAND = 0.10
OUTDOORS_EXPOSURE = (0.0, 0.0, 0.05)  # residents insufficiently sheltered (assumption)
HAZARD_FLAMMABLE = (0.0, 10.0, 30.0)  # piped gas and LPG
HAZARD_OTHER = (0.0, 0.0, 10.0)


@dataclass(frozen=True)
class Site:
    site_id: str
    role: str  # hdb_block | private_residential | private_landed | subzone_remainder
    geometry_wkt: str  # EPSG:3414
    residents: float
    method: str  # key of RESIDENTS_BAND
    age_vulnerable_share: float | None
    max_floor: int | None = None
    raw: dict = field(default_factory=dict)


def _estimate(triple: Triple, unit: str, state: str, grade: str, method: str,
              source: str = 'assumption') -> Estimate:
    return Estimate(triple[0], triple[1], triple[2], unit, state, grade, source=source, method=method)


def _times(*triples: Triple) -> Triple:
    out = [1.0, 1.0, 1.0]
    for t in triples:
        out = [o * v for o, v in zip(out, t)]
    return tuple(out)


def residential_profiles(site: Site) -> list:
    band = RESIDENTS_BAND[site.method]
    population_method, overlap, present, how = 'direct', None, site.residents, f'residents allocated by {site.method}'
    if site.role in AREAL_ROLES:
        geometry = shapely.from_wkt(site.geometry_wkt)
        overlap = placeholder_overlap_km2(geometry)
        present = effective_occupancy_areal_density(site.residents, geometry.area / 1e6, overlap)
        population_method = 'areal_density'
        how += (f', x share of site area inside a {PLACEHOLDER_FOOTPRINT_RADIUS_M:.0f} m placeholder footprint'
                ' (uniform density, assumption)')
    residents = _times((present,) * 3, band)
    grade = RESIDENTS_GRADE[site.method]
    beneficiaries = _estimate(residents, 'people', 'derived', grade, how, CENSUS_SOURCE)
    loss = _estimate(LOSS_FRACTION, 'fraction', 'assumption', 'D', 'share of residents displaced')
    outage = _estimate(DISPLACEMENT_HOURS, 'hours', 'assumption', 'D', 'displacement duration')
    alternative = _estimate(ALTERNATIVE_ACCOMMODATION, 'fraction', 'assumption', 'D',
                            'family or temporary shelter available')
    recovery = _estimate(RECOVERY_T90_HOURS, 'hours', 'assumption', 'D', 'time to 90% of housing function')
    hazard = {name: _estimate(HAZARD_FLAMMABLE if name == 'flammable' else HAZARD_OTHER, 'score_0_100',
                              'assumption', 'D', 'gas and LPG in homes' if name == 'flammable' else 'none assumed')
              for name in HAZARD_COMPONENTS}
    sheltered = _estimate(OUTDOORS_EXPOSURE, 'fraction', 'assumption', 'D', 'residents outdoors or unsheltered')
    if site.max_floor:
        share = max(0.0, (site.max_floor - HIGH_FLOOR) / site.max_floor)
        evacuate = Estimate(max(0.0, share - HIGH_FLOOR_BAND), share, min(1.0, share + HIGH_FLOOR_BAND), 'fraction',
                            'derived', 'D', source='HDB Property Information max_floor_lvl',
                            method=f'share of floors above level {HIGH_FLOOR}')
    else:
        evacuate = Estimate.unavailable('no floor data for this site type', 'fraction')

    profiles = []
    for condition in CONDITIONS:
        cid = condition.condition_id
        home = HOME_FRACTION[cid]
        occupancy = _estimate(_times(residents, home, NON_RESIDENT_UPLIFT), 'people', 'derived', 'D',
                              'residents x share at home x non-resident uplift', CENSUS_SOURCE)
        vulnerability = {'insufficiently_sheltered_or_outdoors': sheltered, 'difficult_to_evacuate': evacuate}
        if site.age_vulnerable_share is not None:
            s = site.age_vulnerable_share
            # Children and older people are likelier than others to be home in daytime conditions.
            vulnerability['age_vulnerable'] = Estimate(
                s, s, min(1.0, s / home[1]), 'fraction', 'official_aggregate', 'C', source=CENSUS_SOURCE,
                method='residents aged under 5 or 65 and over, by subzone', resolution='subzone')
        else:
            vulnerability['age_vulnerable'] = Estimate.unavailable('census gave no age counts for the subzone',
                                                                   'fraction')
        for name in ('unable_to_self_evacuate', 'medically_dependent'):
            vulnerability[name] = Estimate.unavailable('no public subzone or block-level source', 'fraction')
        profiles.append(Profile(
            site_id=site.site_id, condition_id=cid, role=site.role, geometry_wkt=site.geometry_wkt,
            occupancy=occupancy, beneficiaries_per_hour=beneficiaries, loss_fraction=loss, outage_hours=outage,
            alternative_capacity_fraction=alternative, recovery_t90_hours=recovery, vulnerability=vulnerability,
            hazard=hazard, categories=('residential',), raw=site.raw,
            population_method=population_method, overlap_area_km2=overlap))
    return profiles


# ---- Site building ----

CRS = 'EPSG:3414'
RESIDENTIAL_LAND_USE = ('RESIDENTIAL', 'RESIDENTIAL WITH COMMERCIAL AT 1ST STOREY', 'RESIDENTIAL / INSTITUTION',
                        'COMMERCIAL & RESIDENTIAL')


def build_subzones(features: list) -> tuple:
    """Subzone polygons in EPSG:3414, repaired for spatial lookup only; returns (frame, invalid count)."""
    frame = gpd.GeoDataFrame.from_features(features, crs='EPSG:4326').to_crs(CRS)
    invalid = int((~frame.geometry.is_valid).sum())
    frame['geometry'] = frame.geometry.make_valid()
    return frame, invalid


def load_parcels(path: Path) -> gpd.GeoDataFrame:
    """URA MP2019 residential land-use parcels in EPSG:3414."""
    where = 'LU_DESC IN (%s)' % ', '.join(f"'{v}'" for v in RESIDENTIAL_LAND_USE)
    return gpd.read_file(path, where=where)[['OBJECTID', 'LU_DESC', 'GPR', 'geometry']].to_crs(CRS)


def _whole(value) -> int | None:
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def hdb_blocks(rows: list, geocode: dict, subzones: gpd.GeoDataFrame) -> tuple:
    """Placed HDB blocks (dicts for allocate_hdb) and the keys that could not be geocoded or placed."""
    candidates, misses = [], []
    for r in rows:
        if r.get('residential') != 'Y':
            continue
        units = parse_units(r)
        if not sum(units.values()):
            continue
        key = f"{r['blk_no']}|{r['street']}"
        hit = geocode.get(key)
        if hit is None:
            misses.append(key)
        else:
            candidates.append((key, r, units, hit))
    points = [shapely.Point(h['x'], h['y']) for _, _, _, h in candidates]
    blocks = []
    for (key, r, units, hit), point, sz in zip(candidates, points, assign_subzones(points, subzones)):
        if sz is None:
            misses.append(key)
            continue
        blocks.append(dict(site_id=f'hdb:{key}', subzone=sz, units=units, year_completed=_whole(r['year_completed']),
                           max_floor=_whole(r['max_floor_lvl']), point=point, record=r, geocode=hit))
    return blocks, misses


def parcel_sites(parcels: gpd.GeoDataFrame, block_points: list, subzones: gpd.GeoDataFrame) -> tuple:
    """Private parcels for allocate_private, plus geometry/raw evidence per site.

    Parcels containing an HDB block are dropped (HDB estates are zoned residential). Landed lots (GPR
    'LND') are merged into one site per subzone, since one row per house would dominate the output.
    """
    read, hdb = len(parcels), set()
    if block_points:
        blocks = gpd.GeoDataFrame(geometry=block_points, crs=CRS)
        hdb = set(gpd.sjoin(parcels.reset_index(drop=True), blocks, predicate='contains')['OBJECTID'])
        parcels = parcels[~parcels['OBJECTID'].isin(hdb)]
    parcels = parcels.reset_index(drop=True)
    zones = assign_subzones(list(parcels.geometry.representative_point()), subzones)
    singles, landed = [], {}
    for (_, row), sz in zip(parcels.iterrows(), zones):
        if sz is None:
            continue
        ratio, basis = gpr_value(row['GPR'])
        area = row.geometry.area
        if str(row['GPR']).strip().upper() == 'LND':
            lot = landed.setdefault(sz, dict(area=0.0, lots=0, geometries=[]))
            lot['area'] += area
            lot['lots'] += 1
            lot['geometries'].append(row.geometry)
            continue
        singles.append(dict(site_id=f"private:{row['OBJECTID']}", subzone=sz, floor_area=area * ratio, landed=False,
                            geometry=row.geometry, raw=dict(land_use=row['LU_DESC'], gpr=str(row['GPR']),
                                                             gpr_basis=basis, plot_area_m2=round(area, 1))))
    merged = [dict(site_id=f'private_landed:{sz}', subzone=sz, floor_area=v['area'] * LANDED_GPR, landed=True,
                   geometry=shapely.union_all(v['geometries']),
                   raw=dict(land_use='landed lots merged', gpr='LND', gpr_basis='landed_assumed',
                            plot_area_m2=round(v['area'], 1), lots=v['lots'])) for sz, v in landed.items()]
    return singles + merged, read, len(hdb)


def build_sites(census: dict, blocks: list, parcels: gpd.GeoDataFrame, subzones: gpd.GeoDataFrame) -> tuple:
    """Every site with its residents, and the reconciliation of census residents against them."""
    hdb, hdb_remainder = allocate_hdb(blocks, census)
    private_parcels, parcel_count, hdb_parcels = parcel_sites(parcels, [b['point'] for b in blocks], subzones)
    private, private_remainder = allocate_private(private_parcels, census)
    remainder: dict = {}
    for part in (hdb_remainder, private_remainder):
        for sz, residents in part.items():
            remainder[sz] = remainder.get(sz, 0.0) + residents

    def zone(sz):
        return census[sz]['planning_area'], census[sz]['subzone'], census[sz]['age_vulnerable_share']

    sites = []
    for b in blocks:
        alloc, r = hdb[b['site_id']], b['record']
        area, name, share = zone(b['subzone'])
        raw = dict(subzone_code=b['subzone'], planning_area=area, subzone=name, blk_no=r['blk_no'], street=r['street'],
                   postal=b['geocode']['postal'], year_completed=b['year_completed'], max_floor=b['max_floor'],
                   units_total=sum(b['units'].values()), residents_census_basis=round(alloc['census_basis'], 2),
                   residents_national_basis=round(alloc['national_basis'], 2),
                   **{f'units_{g}': n for g, n in b['units'].items()})
        sites.append(Site(b['site_id'], 'hdb_block', b['point'].wkt, alloc['residents'], alloc['method'],
                                   share, b['max_floor'], raw))
    for p in private_parcels:
        area, name, share = zone(p['subzone'])
        role = 'private_landed' if p['landed'] else 'private_residential'
        sites.append(Site(p['site_id'], role, p['geometry'].wkt, private.get(p['site_id'], 0.0),
                                   'floor_area_share', share, None,
                                   dict(subzone_code=p['subzone'], planning_area=area, subzone=name,
                                        floor_area_m2=round(p['floor_area'], 1), **p['raw'])))
    geometry = subzones.set_index('SUBZONE_C').geometry
    for sz, residents in sorted(remainder.items()):
        area, name, share = zone(sz)
        sites.append(Site(f'subzone_remainder:{sz}', 'subzone_remainder', geometry[sz].wkt, residents,
                                   'subzone_remainder', share, None,
                                   dict(subzone_code=sz, planning_area=area, subzone=name)))
    report = reconcile(census, hdb, private, remainder)
    report.update(hdb_blocks=len(blocks), private_parcels=len(private_parcels), residential_parcels_read=parcel_count,
                  parcels_dropped_as_hdb=hdb_parcels, remainder_sites=len(remainder))
    return [s for s in sites if s.residents > 0], report
