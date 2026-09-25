"""Build consequence profiles for every sector and write them to disk.

Usage (from the repo root):
    python -m backend.data_sources.consequence.pipeline transport [--out-dir <output/transport>]
        [--only roads|rail] [--population data/processed/population-projected.json] [--volume-month YYYYMM]
    python -m backend.data_sources.consequence.pipeline residential [--out-dir <output/residential>]
    python -m backend.data_sources.consequence.pipeline healthcare [--out-dir <output/healthcare>] [--refresh]
    python -m backend.data_sources.consequence.pipeline parks_civic [--out-dir <output/parks_civic>]
    python -m backend.data_sources.consequence.pipeline military [--out-dir <output/defence>]
    python -m backend.data_sources.consequence.pipeline critical_sectors [--out-dir <output/critical_sectors>] [--rebuild]
    python -m backend.data_sources.consequence.pipeline rank [--condition weekday_midday|all]

transport: needs network access to OpenStreetMap. Roads also need the prepared population file
    (scripts/population_data.py acquire, then prepare). Station volumes need LTA_ACCOUNT_KEY and --volume-month;
    without them stations use a category prior (grade D assumption).
residential: needs network on the first run: data.gov.sg (census, HDB, URA land use) and OneMap (geocoding about
    10,800 HDB blocks, roughly 45 minutes at OneMap's 250 calls/minute, cached and resumable). No API key.
healthcare: hospitals and schools. Needs network on the first run: moh.gov.sg (two weekly XLSX files), data.gov.sg
    (MOE, MOH, SingStat, SCDF tables and the Census 2020 age table) and OneMap (about 350 postal codes, roughly
    6 minutes, cached and resumable). No API key. --refresh re-downloads the MOH workbooks.
parks_civic: no network; reads the committed parks_civic/ evidence tables (8 parks scenarios per site).
military: no network; reads output/defence/defence_output.csv (defence/geography/build_military_areas.py).
critical_sectors: no network; reads critical_sectors/input_facilities.csv, building it first (or with --rebuild) from the
    URA land-use parcels cached by the residential sector, plus the builder's output/critical_sectors scenario rows.
rank: reads every sector's *_output.csv for one condition and writes output/ranking_<condition>.csv (veto, then C);
    --condition all ranks each condition separately and stacks them in output/ranking_all.csv.

Outputs in --out-dir:
    transport:    transport_output_sites.geojson, transport_output.csv (43 columns: expected casualties C, O_display, E/D/X/R/A
                  and the secondary tie-breaker with bounds, veto status and reasons, population_method, overlap_area_km2, all eight flags,
                  dimensions_missing, policy_version),
                  transport_output_inputs.csv (name, station codes, lat/lon, then raw inputs with states/grades), <sector>_output_provenance.json
    residential:  residential_output_sites.geojson, residential_output.csv (id, vector, secondary and veto columns), <sector>_output_provenance.json
    healthcare:   healthcare_* and education_* sites.geojson and profiles.csv (as residential), <sector>_output_provenance.json
    parks_civic:  parks_civic_output_sites.geojson, parks_civic_output.csv (43 columns as transport_output.csv), <sector>_output_provenance.json
    military:     military_output_sites.geojson, military_output.csv (43 columns), military_output_provenance.json
    critical_sectors: facilities_output_sites.geojson, facilities_output.csv (43 columns), facilities_output_provenance.json
`<sector>_output_provenance.json` records inputs, versions, checksums, reconciliations and every assumption constant.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

import geopandas as gpd
import shapely
from shapely import from_wkt

from backend.data_sources.consequence import FLAG_NAMES, Estimate, flag_table, rank_sites, score_profile, validate, veto
from backend.data_sources.consequence import sources
from backend.data_sources.consequence.critical_sectors import facilities
from backend.data_sources.consequence.defence import military
from backend.data_sources.consequence.healthcare import hospitals, schools
from backend.data_sources.consequence.parks_civic import parks_civic
from backend.data_sources.consequence.residential import residential
from backend.data_sources.consequence.conditions import CONDITIONS
from backend.data_sources.consequence.paths import OUTPUT, POPULATION
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS, VULNERABILITY_COMPONENTS
from backend.data_sources.consequence.transport import datamall, rail, roads
from backend.exposure import prepare_population

log = logging.getLogger(__name__)

CRS = "EPSG:3414"
VECTOR_DIMENSIONS = ("C", "O_display", "E", "D", "X", "R", "A")  # spec §6-7: the full consequence vector
INPUTS = ("occupancy", "beneficiaries_per_hour", "loss_fraction", "outage_hours",
          "alternative_capacity_fraction", "recovery_t90_hours")
DIMENSION_REASON = {"D": "no authorised capability input", "X": "no dependency records supplied"}
LAST_COLUMN = "overlap_area_km2"  # residential and healthcare CSVs stop here; flags and raw inputs are not written
# transport_output.csv keeps MAIN_COLUMNS (43); everything else goes to transport_output_inputs.csv.
KEY_COLUMNS = ("site_id", "condition_id")
LOCATION_COLUMNS = ("name", "codes", "lat", "lon")  # readable location, first in transport_output_inputs.csv
VETO_COLUMNS = ("veto_status", "veto_reasons_civilian", "veto_reasons_capability")
POPULATION_COLUMNS = ("population_method", "overlap_area_km2")  # how N was obtained
MAIN_COLUMNS = (
    ("site_id", "condition_id", "role", "rankable")
    + tuple(f"{dim}_{part}" for dim in VECTOR_DIMENSIONS + ("secondary",) for part in ("low", "central", "high"))
    + VETO_COLUMNS
    + POPULATION_COLUMNS
    + tuple(f"flag_{name}" for name in FLAG_NAMES)
    + ("dimensions_missing", "policy_version")
)
assert len(MAIN_COLUMNS) == 43


# ---- Shared row and file helpers ----

def _blank(v):
    return "" if v is None else v


def _round(v, places=6):
    return None if v is None else round(v, places)


def _estimate_columns(row: dict, name: str, estimate) -> None:
    for part, value in zip(("low", "central", "high"), estimate.bounds):
        row[f"{name}_{part}"] = _blank(_round(value))
    row[f"{name}_state"] = estimate.state
    row[f"{name}_grade"] = _blank(estimate.grade)


def profile_row(profile, as_of: str) -> dict:
    """One CSV row: the whole vector (C, O_display, E, D, X, R, A, secondary), veto, all eight flags, raw inputs.

    A dimension with no defensible value is blank with status `unavailable`, never zero.
    """
    scored = score_profile(profile)
    table = flag_table(profile, scored, as_of)
    row = {
        "site_id": profile.site_id, "condition_id": profile.condition_id, "role": profile.role,
        "rankable": scored.rankable and validate(profile), "policy_version": scored.policy_version,
        "dimensions_missing": "|".join(scored.dimensions_missing),
    }
    for name in VECTOR_DIMENSIONS + ("secondary",):
        score = getattr(scored, name)
        for i, part in enumerate(("low", "central", "high")):
            row[f"{name}_{part}"] = _blank(None if score is None else round(score[i], 3))
        row[f"{name}_status"] = "unavailable" if score is None else "available"
    status, civilian, capability = veto(table, profile.priority_asset, profile.capability.available)
    row.update(veto_status=status, veto_reasons_civilian="|".join(civilian),
               veto_reasons_capability="|".join(capability))
    row.update(population_method=profile.population_method,
               overlap_area_km2=_blank(None if profile.overlap_area_km2 is None else round(profile.overlap_area_km2, 6)))
    for name in ("D", "X"):
        row[f"{name}_reason"] = DIMENSION_REASON[name] if getattr(scored, name) is None else ""
    for flag, value in table.items():
        row[f"flag_{flag}"] = value
    raised = [k for k, v in table.items() if v is True] + (["priority_asset"] if profile.priority_asset else [])
    row["flags_raised"] = "|".join(raised)
    for name in INPUTS:
        _estimate_columns(row, name, getattr(profile, name))
    for name in ("occupancy", "beneficiaries_per_hour"):
        estimate = getattr(profile, name)
        row[f"{name}_note"] = estimate.source if not estimate.available else estimate.method
    for name in VULNERABILITY_COMPONENTS:
        _estimate_columns(row, f"vulnerability_{name}", profile.vulnerability.get(name) or Estimate.unavailable("not supplied"))
    for name in HAZARD_COMPONENTS:
        _estimate_columns(row, f"hazard_{name}", profile.hazard.get(name) or Estimate.unavailable("not supplied"))
    return row


def trim_row(row: dict) -> dict:
    """Keep the columns up to and including LAST_COLUMN; flags and raw inputs are not written."""
    keys = list(row)
    return {k: row[k] for k in keys[:keys.index(LAST_COLUMN) + 1]}


def write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")


# ---- Transport ----

def write_transport(profiles: list, out_dir: Path, provenance: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).date().isoformat()

    sites = {}
    for p in profiles:
        sites.setdefault(p.site_id, p)
    frame = gpd.GeoDataFrame(
        [{"site_id": p.site_id, "role": p.role, **{f"raw_{k}": v for k, v in p.raw.items()}} for p in sites.values()],
        geometry=[from_wkt(p.geometry_wkt) for p in sites.values()], crs=roads.CRS).to_crs("EPSG:4326")
    frame.to_file(out_dir / "transport_output_sites.geojson", driver="GeoJSON")
    points = gpd.GeoSeries([from_wkt(p.geometry_wkt) for p in sites.values()], crs=roads.CRS)
    points = points.representative_point().to_crs("EPSG:4326")
    locations = {
        site_id: {"name": _blank(p.raw.get("name")), "codes": _blank(p.raw.get("codes")),
                  "lat": round(pt.y, 6), "lon": round(pt.x, 6)}
        for (site_id, p), pt in zip(sites.items(), points)}

    count = 0
    with (out_dir / "transport_output.csv").open("w", newline="", encoding="utf-8") as main,             (out_dir / "transport_output_inputs.csv").open("w", newline="", encoding="utf-8") as inputs:
        main_writer = inputs_writer = None
        for p in profiles:
            row = profile_row(p, as_of)
            if main_writer is None:
                extra = [c for c in row if c not in MAIN_COLUMNS]
                main_writer = csv.DictWriter(main, fieldnames=list(MAIN_COLUMNS))
                inputs_writer = csv.DictWriter(inputs, fieldnames=list(KEY_COLUMNS) + list(LOCATION_COLUMNS) + extra)
                main_writer.writeheader()
                inputs_writer.writeheader()
            main_writer.writerow({c: row[c] for c in MAIN_COLUMNS})
            inputs_writer.writerow({**{c: v for c, v in row.items() if c in KEY_COLUMNS or c not in MAIN_COLUMNS},
                                    **locations[p.site_id]})
            count += 1
    provenance.update(generated_at=datetime.now(timezone.utc).isoformat(), site_count=len(sites),
                      profile_rows=count, conditions=[c.condition_id for c in CONDITIONS])
    write_json(out_dir / "transport_output_provenance.json", provenance)
    log.info("Wrote %d sites and %d profile rows -> %s", len(sites), count, out_dir)


def road_stage(population_path: Path, provenance: dict) -> list:
    prepared = prepare_population(json.loads(population_path.read_text(encoding="utf-8")))
    G, nodes, edges = roads.build_network()
    edges = roads.weight_edges(roads.overlay_structures(edges))

    weights = roads.node_population_weights(nodes, prepared)
    trip_share, k = roads.population_betweenness(G, weights)
    detour = roads.compute_redundancy(G, trip_share)

    keys = list(zip(edges["u"], edges["v"], edges["key"]))
    edges["trip_share"] = [trip_share.get(key, 0.0) for key in keys]
    edges["detour_ratio"] = [detour.get(key) for key in keys]
    provenance["roads"] = {
        "population_dataset_id": prepared.dataset_id, "population_dataset_version": prepared.version,
        "population_checksum": prepared.checksum, "population_weighted_nodes": len(weights),
        "graph_nodes": len(G.nodes), "graph_edges": len(G.edges), "betweenness_k": k,
        "detour_edges_evaluated": len(detour), "weight_source": "datamall" if datamall.LTA_ACCOUNT_KEY else "osm_proxy",
        "assumptions": {name: getattr(roads, name) for name in (
            "TRIPS_PER_PERSON_PER_DAY", "HOURLY_TRIP_SHARE", "VEHICLES_PER_LANE_KM", "PERSONS_PER_VEHICLE",
            "DEFAULT_LANES", "SURFACE_RECOVERY_HOURS", "STRUCTURE_RECOVERY_HOURS", "TRIP_SHARE_BAND",
            "ALTERNATIVE_CAPACITY_BAND", "LOSS_FRACTION", "HAZARD_ASSUMPTION")},
    }
    return roads.road_profiles(edges, sum(weights.values()), k)


def rail_stage(volume_month: str | None, provenance: dict) -> list:
    stations = rail.merge_sites(rail.fetch_osm_station_records())
    G = rail.build_rail_graph(stations)
    flows = through = None
    info = {"station_sites": len(stations), "rail_edges": G.number_of_edges(), "volume_month": None}
    if datamall.LTA_ACCOUNT_KEY and volume_month:
        volumes, volume_sha = datamall.fetch_passenger_volume("Train", volume_month)
        od, od_sha = datamall.fetch_passenger_volume("ODTrain", volume_month)
        flows = datamall.station_hourly_flows(volumes, volume_month)
        through, unmatched = rail.through_passengers(G, stations, datamall.od_hourly_trips(od, volume_month))
        info.update(volume_month=volume_month, train_sha256=volume_sha, odtrain_sha256=od_sha,
                    od_rows_unmatched=unmatched)
    else:
        log.warning("No LTA_ACCOUNT_KEY / --volume-month: stations use the category prior (grade D)")
    info["assumptions"] = {name: getattr(rail, name) for name in (
        "DWELL_HOURS", "STATION_RECOVERY_HOURS", "LOSS_FRACTION", "ALTERNATIVE_NEARBY", "ALTERNATIVE_NONE",
        "HAZARD_HIGH_ENERGY", "HAZARD_OTHER", "ALTERNATIVE_WALK_M", "MERGE_DISTANCE_M",
        "STATION_DAILY_TAPS")}
    provenance["rail"] = info
    return rail.rail_profiles(stations, G, flows, through, volume_month if flows is not None else None)


def run_transport(out_dir: Path, population_path: Path, only: str | None, volume_month: str | None) -> None:
    provenance: dict = {"code": "backend/data_sources/consequence/transport"}
    profiles = []
    if only in (None, "roads"):
        profiles += road_stage(population_path, provenance)
    if only in (None, "rail"):
        profiles += rail_stage(volume_month, provenance)
    write_transport(profiles, out_dir, provenance)


# ---- Residential ----

def write_residential(sites: list, out_dir: Path, provenance: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).date().isoformat()
    frame = gpd.GeoDataFrame(
        [dict(site_id=s.site_id, role=s.role, residents=round(s.residents, 2), **{f'raw_{k}': v for k, v in s.raw.items()})
         for s in sites], geometry=[from_wkt(s.geometry_wkt) for s in sites], crs=CRS).to_crs('EPSG:4326')
    frame.to_file(out_dir / 'residential_output_sites.geojson', driver='GeoJSON', COORDINATE_PRECISION=6)
    rows = 0
    with (out_dir / 'residential_output.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = None
        for s in sites:
            for p in residential.residential_profiles(s):
                row = trim_row(profile_row(p, as_of))
                if writer is None:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                rows += 1
    roles: dict = {}
    for s in sites:
        roles[s.role] = roles.get(s.role, 0) + 1
    provenance.update(generated_at=datetime.now(timezone.utc).isoformat(), site_count=len(sites), profile_rows=rows,
                      sites_by_role=roles, conditions=[c.condition_id for c in CONDITIONS])
    write_json(out_dir / 'residential_output_provenance.json', provenance)
    log.info('Wrote %d sites and %d profile rows -> %s', len(sites), rows, out_dir)


def residential_assumptions() -> dict:
    names = ('HOME_FRACTION', 'NON_RESIDENT_UPLIFT', 'RESIDENTS_BAND', 'RESIDENTS_GRADE', 'LOSS_FRACTION',
             'DISPLACEMENT_HOURS', 'ALTERNATIVE_ACCOMMODATION', 'RECOVERY_T90_HOURS', 'HIGH_FLOOR', 'HIGH_FLOOR_BAND',
             'OUTDOORS_EXPOSURE', 'HAZARD_FLAMMABLE', 'HAZARD_OTHER', 'LANDED_GPR', 'UNKNOWN_GPR', 'HDB_UNIT_COLUMNS',
             'CENSUS_YEAR')
    return {n: getattr(residential, n) for n in names}


def run_residential(out_dir: Path) -> None:
    census_sources = sources.load_census()
    dwelling = sources.datastore_rows(sources.DWELLING_ID)
    hdb = sources.datastore_rows(sources.HDB_ID)
    landuse = sources.landuse_path()
    census = residential.census_by_subzone(dwelling['rows'], census_sources['age_rows'], census_sources['features'])
    log.info('Census: %d subzones matched to boundaries', len(census))
    subzones, invalid = residential.build_subzones(census_sources['features'])
    keys = [f"{r['blk_no']}|{r['street']}" for r in hdb['rows'] if r.get('residential') == 'Y']
    geocode = sources.geocode_blocks(keys)
    blocks, misses = residential.hdb_blocks(hdb['rows'], geocode, subzones)
    parcels = residential.load_parcels(landuse)
    sites, report = residential.build_sites(census, blocks, parcels, subzones)
    provenance = dict(
        code='backend/data_sources/consequence/residential.py',
        sources=dict(
            census_age=census_sources['manifest']['sources'], dwelling_table=dict(
                dataset_id=sources.DWELLING_ID, rows=dwelling['total'], retrieved_at=dwelling['retrieved_at']),
            hdb_property=dict(dataset_id=sources.HDB_ID, rows=hdb['total'], retrieved_at=hdb['retrieved_at']),
            land_use=dict(dataset_id=sources.LANDUSE_ID, sha256=sources.file_sha256(landuse)),
            geocoder='OneMap Search API (SVY21 coordinates)'),
        subzone_geometries_repaired_for_lookup=invalid,
        geocode=dict(attempted=len(keys), missed_or_unplaced=len(misses), missed_keys=misses[:500]),
        reconciliation=report, assumptions=residential_assumptions())
    write_residential(sites, out_dir, provenance)


# ---- Healthcare and education ----

def write_category(sites: list, build, stem: str, out_dir: Path, as_of: str, columns=None) -> int:
    """columns: keep exactly these profile columns; default trims at LAST_COLUMN."""
    built = [build(s) for s in sites]
    frame = gpd.GeoDataFrame(
        [dict(site_id=p[0].site_id, role=p[0].role, **{f'raw_{k}': v for k, v in s.raw.items()})
         for s, p in zip(sites, built)],
        geometry=[shapely.from_wkt(s.geometry_wkt) for s in sites], crs=CRS).to_crs('EPSG:4326')
    frame.to_file(out_dir / f'{stem}_output_sites.geojson', driver='GeoJSON', COORDINATE_PRECISION=6)
    rows = 0
    with (out_dir / f'{stem}_output.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = None
        for profiles in built:
            for p in profiles:
                row = profile_row(p, as_of)
                row = trim_row(row) if columns is None else {c: row[c] for c in columns}
                if writer is None:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                rows += 1
    return rows


def healthcare_assumptions() -> dict:
    h = ('SINCE', 'QUANTILES', 'ED_STAY_HOURS', 'ED_HOUR_FACTOR', 'STAFF_PER_BED', 'SHIFT_FRACTION',
         'VISITORS_PER_INPATIENT', 'NON_AMBULANT_INPATIENTS', 'AMBULANCE_CONVEYANCE', 'AGE65_BEDDAY_UPLIFT',
         'DIFFICULT_TO_EVACUATE', 'OUTDOORS', 'LOSS_FRACTION', 'OUTAGE_HOURS', 'RECOVERY_T90_HOURS', 'HAZARD')
    s = ('SIZE_BAND', 'PRESENCE', 'PRIMARY_SHARE_MIXED_P1_S4', 'SUPERVISION_NEED', 'OUTDOORS', 'LOSS_FRACTION',
         'INSTRUCTION_HOURS_LOST', 'ALTERNATIVE', 'RECOVERY_T90_HOURS', 'HAZARD')
    return dict(hospitals={n: getattr(hospitals, n) for n in h}, schools={n: getattr(schools, n) for n in s},
                bed_table=[dict(code=x.code, name=x.name, postal=x.postal, beds=x.beds, source=x.bed_source)
                           for x in hospitals.HOSPITALS])


def run_healthcare(out_dir: Path, refresh: bool = False) -> None:
    bor_path, bor_meta = sources.moh_workbook(sources.BOR_PAGE, 'moh-bor', refresh=refresh)
    emd_path, emd_meta = sources.moh_workbook(sources.EMD_PAGE, 'moh-emd', refresh=refresh)
    bor, ed = sources.daily_series(bor_path), sources.daily_series(emd_path)
    tables = {name: sources.datastore_rows(rid) for name, rid in (
        ('beds', sources.BEDS_ID), ('attendances', sources.ATTENDANCES_ID), ('admission_rate', sources.ADMISSION_RATE_ID),
        ('ems', sources.EMS_ID), ('schools', sources.SCHOOLS_ID), ('moe_levels', sources.MOE_LEVEL_ID))}
    census_total = sources.load_census_age()
    postals = [h.postal for h in hospitals.HOSPITALS] + [r['postal_code'] for r in tables['schools']['rows']]  # padded by geocode_postals
    geocode = sources.geocode_postals(postals)

    h_sites, h_skipped, shares = hospitals.hospital_sites(bor, ed, census_total, tables['admission_rate']['rows'],
                                                tables['ems']['rows'], tables['attendances']['rows'], geocode)
    s_sites, s_skipped, counts = schools.school_sites(tables['schools']['rows'], tables['moe_levels']['rows'], geocode)
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).date().isoformat()
    h_rows = write_category(h_sites, hospitals.hospital_profiles, 'healthcare', out_dir, as_of)
    s_rows = write_category(s_sites, schools.school_profiles, 'education', out_dir, as_of)
    provenance = dict(
        code='backend/data_sources/consequence/hospitals.py, schools.py', generated_at=datetime.now(timezone.utc).isoformat(),
        as_of=as_of, conditions=[c.condition_id for c in CONDITIONS],
        sources=dict(moh_bor=bor_meta, moh_emd=emd_meta,
                     **{name: dict(dataset_id=t['resource_id'], rows=t['total'], retrieved_at=t['retrieved_at'])
                        for name, t in tables.items()},
                     census_age='SingStat Census 2020 residents by age and sex (national Total row)',
                     geocoder='OneMap Search API by postal code (SVY21)'),
        hospitals=dict(sites=len(h_sites), profile_rows=h_rows, skipped=h_skipped, shares=shares,
                       reconciliation=hospitals.reconcile(bor, ed, tables['beds']['rows'], tables['attendances']['rows'])),
        schools=dict(directory=len(tables['schools']['rows']), sites=len(s_sites), profile_rows=s_rows,
                     skipped=s_skipped, per_school_by_level=counts),
        assumptions=healthcare_assumptions())
    write_json(out_dir / 'healthcare_output_provenance.json', provenance)
    log.info('Wrote %d hospitals (%d rows), %d schools (%d rows) -> %s', len(h_sites), h_rows, len(s_sites), s_rows,
             out_dir)


# ---- Parks and civic venues ----

def run_parks_civic(out_dir: Path) -> None:
    sites = parks_civic.load_sites()
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).date().isoformat()
    rows = write_category(sites, parks_civic.parks_profiles, 'parks_civic', out_dir, as_of, MAIN_COLUMNS)
    subtypes: dict = {}
    for s in sites:
        subtypes[s.subtype] = subtypes.get(s.subtype, 0) + 1
    names = ('SCENARIOS', 'USERS_SCENARIO', 'LOSS_FRACTION', 'USE_HOURS_LOST', 'ALTERNATIVE', 'RECOVERY_T90_HOURS',
             'OUTDOORS', 'HAZARD_BASE', 'HAZARD')
    provenance = dict(
        code='backend/data_sources/consequence/parks_civic/parks_civic.py',
        generated_at=datetime.now(timezone.utc).isoformat(), as_of=as_of, conditions=list(parks_civic.SCENARIOS),
        sources=dict(sites='parks_civic/input_sites.csv', scenarios='parks_civic/input_conditions.csv',
                     metadata='parks_civic/input_metadata.json'),
        site_count=len(sites), profile_rows=rows, sites_by_subtype=subtypes,
        assumptions={n: getattr(parks_civic, n) for n in names})
    write_json(out_dir / 'parks_civic_output_provenance.json', provenance)
    log.info('Wrote %d parks/civic sites and %d profile rows -> %s', len(sites), rows, out_dir)


def run_military(out_dir: Path) -> None:
    sites = military.load_sites()
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).date().isoformat()
    rows = write_category(sites, military.military_profiles, 'military', out_dir, as_of, MAIN_COLUMNS)
    names = ('DENSITY_PER_KM2', 'TIME_COEFFICIENT', 'RECOVERY_T90_HOURS')
    write_json(out_dir / 'military_output_provenance.json', dict(
        code='backend/data_sources/consequence/defence/military.py', generated_at=datetime.now(timezone.utc).isoformat(),
        as_of=as_of, source=str(military.SOURCE.relative_to(OUTPUT.parent)), site_count=len(sites),
        air_bases=[s.name for s in sites if s.air_base], profile_rows=rows,
        assumptions={n: getattr(military, n) for n in names}))
    log.info('Wrote %d military sites and %d profile rows -> %s', len(sites), rows, out_dir)


def run_critical_sectors(out_dir: Path, rebuild: bool = False) -> None:
    if rebuild or not facilities.FACILITIES.exists():
        facilities.build_facilities([shapely.from_wkt(s.geometry_wkt) for s in military.load_sites() if s.air_base])
    sites = facilities.load_facilities()
    evidence = facilities.load_evidence()
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).date().isoformat()
    rows = write_category(sites, lambda f: facilities.facility_profiles(f, evidence), 'facilities', out_dir, as_of,
                          MAIN_COLUMNS)
    kinds: dict = {}
    for f in sites:
        kinds[f.profile_id] = kinds.get(f.profile_id, 0) + 1
    names = ('DISRUPTION', 'AIRPORTS', 'PORT_JOIN_M', 'THROUGHPUT_E_PERSON_HOURS', 'WORKFORCE_PER_KM2',
             'INDUSTRIAL_COEFFICIENT', 'AIRPORT_COEFFICIENT', 'R_HOURS')
    write_json(out_dir / 'facilities_output_provenance.json', dict(
        code='backend/data_sources/consequence/critical_sectors/facilities.py',
        generated_at=datetime.now(timezone.utc).isoformat(), as_of=as_of,
        sources=dict(sites='critical_sectors/input_facilities.csv (URA Master Plan 2019 land use)',
                     profiles='critical_sectors/input_profiles.csv',
                     scenarios='output/critical_sectors/critical_sectors_output.csv'),
        site_count=len(sites), sites_by_profile=kinds, profile_rows=rows,
        unsited_profiles=facilities.unsited_profiles(sites, evidence),
        assumptions={n: getattr(facilities, n) for n in names}))
    log.info('Wrote %d critical-sector facilities and %d profile rows -> %s', len(sites), rows, out_dir)


# Scored outputs that join the cross-sector ranking; parks scenario ids map onto the shared conditions.
RANKED_OUTPUTS = ('residential/residential_output.csv', 'healthcare/healthcare_output.csv',
                  'healthcare/education_output.csv', 'transport/transport_output.csv',
                  'parks_civic/parks_civic_output.csv', 'defence/military_output.csv',
                  'critical_sectors/facilities_output.csv')
PARKS_CONDITION = {'WD_AM': 'weekday_am_peak', 'WD_DAY': 'weekday_midday', 'WD_PM': 'weekday_pm_peak',
                   'WD_NIGHT': 'weekday_night', 'WE_DAY': 'weekend_day'}
RANK_COLUMNS = ('condition_id', 'rank', 'site_id', 'role', 'source', 'C_low', 'C_central', 'C_high',
                'secondary_central', 'veto_status', 'veto_reasons_civilian', 'veto_reasons_capability')


def run_rank(condition: str, out: Path) -> None:
    """Rank one condition, or every condition ('all') ranked separately and stacked in one file."""
    wanted = [c.condition_id for c in CONDITIONS] if condition == 'all' else [condition]
    rows = {c: [] for c in wanted}
    for name in RANKED_OUTPUTS:
        path = OUTPUT / name
        if not path.exists():
            log.warning('Skipping %s: not built yet', name)
            continue
        with path.open(encoding='utf-8') as stream:
            for r in csv.DictReader(stream):
                c = PARKS_CONDITION.get(r['condition_id'], r['condition_id'])
                if c in rows:
                    rows[c].append(dict({k: r.get(k, '') for k in RANK_COLUMNS if k not in ('rank', 'source')},
                                        condition_id=c, source=name.split('/')[-1].replace('_output.csv', '')))
    ranked = [r for c in wanted for r in rank_sites(rows[c])]
    with out.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(RANK_COLUMNS))
        writer.writeheader()
        writer.writerows({k: r[k] for k in RANK_COLUMNS} for r in ranked)
    log.info('Ranked %d rows for %s -> %s', len(ranked), condition, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="sector", required=True)
    tp = sub.add_parser("transport", help="roads and MRT/LRT stations")
    tp.add_argument("--out-dir", type=Path, default=OUTPUT / "transport")
    tp.add_argument("--population", type=Path, default=POPULATION)
    tp.add_argument("--only", choices=("roads", "rail"))
    tp.add_argument("--volume-month", help="YYYYMM of DataMall passenger volumes")
    rp = sub.add_parser("residential", help="HDB blocks and private housing")
    rp.add_argument("--out-dir", type=Path, default=OUTPUT / "residential")
    hp = sub.add_parser("healthcare", help="public acute hospitals and MOE schools")
    hp.add_argument("--out-dir", type=Path, default=OUTPUT / "healthcare")
    hp.add_argument("--refresh", action="store_true", help="re-download the weekly MOH workbooks")
    pp = sub.add_parser("parks_civic", help="parks, sport and civic venues (committed evidence tables)")
    pp.add_argument("--out-dir", type=Path, default=OUTPUT / "parks_civic")
    mp = sub.add_parser("military", help="OSM military areas; air bases are precautionary vetoes")
    mp.add_argument("--out-dir", type=Path, default=OUTPUT / "defence")
    cp = sub.add_parser("critical_sectors", help="airports, ports and utilities from URA land use")
    cp.add_argument("--out-dir", type=Path, default=OUTPUT / "critical_sectors")
    cp.add_argument("--rebuild", action="store_true", help="rebuild input_facilities.csv from the land-use cache")
    kp = sub.add_parser("rank", help="cross-sector veto-then-rank for one condition")
    kp.add_argument("--condition", default="weekday_midday", choices=[c.condition_id for c in CONDITIONS] + ["all"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    if args.sector == "transport":
        run_transport(args.out_dir, args.population, args.only, args.volume_month)
    elif args.sector == "residential":
        run_residential(args.out_dir)
    elif args.sector == "parks_civic":
        run_parks_civic(args.out_dir)
    elif args.sector == "military":
        run_military(args.out_dir)
    elif args.sector == "critical_sectors":
        run_critical_sectors(args.out_dir, args.rebuild)
    elif args.sector == "rank":
        run_rank(args.condition, OUTPUT / f"ranking_{args.condition}.csv")
    else:
        run_healthcare(args.out_dir, args.refresh)


if __name__ == "__main__":
    main()
