"""MRT/LRT station consequence profiles.

Stations come from OpenStreetMap; the rail graph is inferred from station codes
(consecutive numbers on a line prefix), with a small documented table of
exceptions. Occupancy and service demand need LTA DataMall passenger volumes; without
them those inputs are `unavailable` (never zero) and the station is not rankable.

Topology limits: the graph is an approximation built from codes, not from track
geometry. LRT loop and branch layouts beyond the loops listed in LOOPS are treated
as simple chains.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import re

import networkx as nx

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS

from backend.data_sources.consequence.conditions import CONDITIONS
from backend.data_sources.consequence.paths import OSMNX_CACHE
from .roads import HOURLY_TRIP_SHARE

log = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"^([A-Z]{2})(\d+)([A-Z]?)$")
# Loop lines: hub code -> line prefixes that start and end at that hub.
LOOPS = {"STC": ("SE", "SW"), "PTC": ("PE", "PW")}
# Edges not implied by consecutive numbering (the Changi Airport branch leaves EW4).
EXTRA_EDGES = (("EW4", "CG1"),)
# Numbers deliberately skipped in a line's numbering; consecutive stations bridge them.
KNOWN_SKIPPED = {"CC": {18}}
MERGE_DISTANCE_M = 500  # same-name stations closer than this are one interchange site
ALTERNATIVE_WALK_M = 800

# Uncalibrated assumptions (grade D), each (low, central, high).
DWELL_HOURS = (5 / 60, 10 / 60, 15 / 60)  # average time a tapping passenger spends in the station
STATION_RECOVERY_HOURS = (24, 72, 336)  # underground vs elevated damage not distinguished
LOSS_FRACTION = (1.0, 1.0, 1.0)
ALTERNATIVE_NEARBY = (0.1, 0.3, 0.5)  # another line's station within walking distance
ALTERNATIVE_NONE = (0.0, 0.05, 0.15)
HAZARD_HIGH_ENERGY = (0.0, 10.0, 30.0)  # traction power
HAZARD_OTHER = (0.0, 0.0, 10.0)
# Category prior used when no DataMall volumes are supplied (spec §9): daily tap-in + tap-out by station
# class, spread over the day with the same hourly shares as road trips. Uncalibrated guesses (grade D).
STATION_DAILY_TAPS = {
    "lrt": (1_000, 5_000, 15_000),
    "mrt": (10_000, 40_000, 90_000),
    "interchange": (30_000, 100_000, 250_000),
}
LRT_PREFIXES = {"BP", "SE", "SW", "PE", "PW"}
MISSING_VOLUMES = "no LTA DataMall passenger volume supplied (set LTA_ACCOUNT_KEY)"


@dataclass(frozen=True)
class Station:
    site_id: str
    name: str
    codes: tuple
    x: float
    y: float

    @property
    def lines(self) -> frozenset:
        return frozenset(p for p, _, _ in filter(None, map(parse_code, self.codes)))


def station_class(station: Station) -> str:
    """'lrt' (LRT lines only), 'interchange' (two or more lines) or 'mrt'."""
    lines = set(station.lines) | {"hub" for c in station.codes if c in LOOPS}
    if len(lines) >= 2:
        return "interchange"
    return "lrt" if lines and lines <= (LRT_PREFIXES | {"hub"}) else "mrt"


def parse_code(code: str):
    """'NS24' -> ('NS', 24, ''); hub codes STC/PTC have no number and return None."""
    m = CODE_PATTERN.match(code.strip().upper())
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


def _normalise(name: str) -> str:
    return re.sub(r"\s+(mrt|lrt)?\s*station$", "", name.strip().lower())


def merge_sites(records: list) -> list:
    """Group OSM station records into sites: shared codes, or same name within MERGE_DISTANCE_M.

    Each record is {name, codes, x, y} with x, y in EPSG:3414 metres.
    """
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    by_code = {}
    for i, r in enumerate(records):
        for code in r["codes"]:
            union(i, by_code.setdefault(code, i))
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            if (_normalise(a["name"]) == _normalise(b["name"])
                    and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) <= MERGE_DISTANCE_M):
                union(i, j)

    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(records[i])
    sites = []
    for members in groups.values():
        codes = tuple(sorted({c for m in members for c in m["codes"]}))
        sites.append(Station(
            site_id="station:" + "/".join(codes) if codes else "station:" + _normalise(members[0]["name"]),
            name=members[0]["name"], codes=codes,
            x=sum(m["x"] for m in members) / len(members),
            y=sum(m["y"] for m in members) / len(members)))
    return sorted(sites, key=lambda s: s.site_id)


def build_rail_graph(stations: list) -> nx.Graph:
    """Undirected station graph; nodes are site_ids."""
    G = nx.Graph()
    code_to_site = {}
    for s in stations:
        G.add_node(s.site_id)
        for code in s.codes:
            code_to_site[code] = s.site_id

    by_line = {}
    for code in code_to_site:
        parsed = parse_code(code)
        if parsed:
            by_line.setdefault(parsed[0], []).append((parsed[1], parsed[2], code))
    for prefix, members in by_line.items():
        members.sort()
        skipped = KNOWN_SKIPPED.get(prefix, set())
        for (n1, _, c1), (n2, _, c2) in zip(members, members[1:]):
            if all(n in skipped for n in range(n1 + 1, n2)) and code_to_site[c1] != code_to_site[c2]:
                G.add_edge(code_to_site[c1], code_to_site[c2])
    for hub, prefixes in LOOPS.items():
        if hub not in code_to_site:
            continue
        for prefix in prefixes:
            chain = sorted(by_line.get(prefix, []))
            if chain:
                G.add_edge(code_to_site[hub], code_to_site[chain[0][2]])
                G.add_edge(code_to_site[hub], code_to_site[chain[-1][2]])
    for a, b in EXTRA_EDGES:
        if a in code_to_site and b in code_to_site:
            G.add_edge(code_to_site[a], code_to_site[b])
    isolated = [n for n in G if G.degree(n) == 0]
    if isolated:
        log.warning("%d station(s) have no rail neighbours: %s", len(isolated), isolated[:10])
    return G


def through_passengers(G: nx.Graph, stations: list, od_trips: dict) -> tuple:
    """Assign origin-destination trips to hop-shortest paths and sum interior passengers.

    od_trips is {(origin_code, destination_code, condition_id): trips/hour}.
    Returns ({(site_id, condition_id): through trips/hour}, number of unmatched OD rows).
    Transfers and timetables are ignored: shortest path by station count only.
    """
    code_to_site = {c: s.site_id for s in stations for c in s.codes}
    through, unmatched, paths = {}, 0, {}
    for (origin, destination, cid), trips in od_trips.items():
        a, b = code_to_site.get(origin), code_to_site.get(destination)
        if a is None or b is None or a == b:
            unmatched += a is None or b is None
            continue
        if (a, b) not in paths:
            try:
                paths[(a, b)] = nx.shortest_path(G, a, b)
            except nx.NetworkXNoPath:
                paths[(a, b)] = None
        path = paths[(a, b)]
        if path is None:
            unmatched += 1
            continue
        for site in path[1:-1]:
            through[(site, cid)] = through.get((site, cid), 0.0) + trips
    return through, unmatched


def _proxy(triple, unit, state, grade, method, source="transport rail proxy", source_date=None) -> Estimate:
    low, central, high = triple
    return Estimate(low, central, high, unit, state, grade, source=source, source_date=source_date,
                    method=method, resolution="station")


def _scale(triple, factor_triple) -> tuple:
    return tuple(t * f for t, f in zip(triple, factor_triple))


def rail_profiles(stations: list, G: nx.Graph, flows: dict | None = None, through: dict | None = None,
                  volume_month: str | None = None, variation: tuple = (0.85, 1.0, 1.15),
                  prior: bool = True) -> list:
    """One Profile per station and condition.

    flows is {(station_code, condition_id): people tapping in+out per hour}; through is
    {(site_id, condition_id): passing trips/hour}. With flows=None the volume-based inputs are
    filled from the category prior (STATION_DAILY_TAPS), or unavailable when prior=False. When flows
    is given, an hour with no data stays unavailable. volume_month is YYYYMM and becomes the source date. variation is the
    month-to-month band around the monthly mean (assumption).
    """
    cut_stations = set(nx.articulation_points(G))
    source_date = f"{volume_month[:4]}-{volume_month[4:6]}-01" if volume_month else None
    positions = {s.site_id: (s.x, s.y) for s in stations}
    lines = {s.site_id: s.lines for s in stations}
    profiles = []
    for s in stations:
        near = any(
            other != s.site_id and not (lines[other] & lines[s.site_id])
            and math.hypot(positions[other][0] - s.x, positions[other][1] - s.y) <= ALTERNATIVE_WALK_M
            for other in positions)
        alternative = _proxy(ALTERNATIVE_NEARBY if near else ALTERNATIVE_NONE, "fraction", "assumption", "D",
                             "another line's station within %d m" % ALTERNATIVE_WALK_M if near
                             else "no other line's station within %d m" % ALTERNATIVE_WALK_M)
        recovery = _proxy(STATION_RECOVERY_HOURS, "hours", "assumption", "D", "station closure")
        loss = _proxy(LOSS_FRACTION, "fraction", "assumption", "D", "full station closure")
        hazard = {name: _proxy(HAZARD_HIGH_ENERGY if name == "explosive_or_high_energy" else HAZARD_OTHER,
                               "score_0_100", "assumption", "D",
                               "traction power" if name == "explosive_or_high_energy" else "none assumed")
                  for name in HAZARD_COMPONENTS}
        raw = {"name": s.name, "codes": "/".join(s.codes), "station_class": station_class(s),
               "neighbours": G.degree(s.site_id),
               "cut_station": s.site_id in cut_stations}
        for condition in CONDITIONS:
            cid = condition.condition_id
            tap = None
            if flows is not None:
                seen = [flows[(c, cid)] for c in s.codes if (c, cid) in flows]
                tap = sum(seen) if seen else None
            if tap is None and flows is None and prior:
                hourly = _scale(STATION_DAILY_TAPS[station_class(s)], HOURLY_TRIP_SHARE[cid])
                method = "%s station prior: daily taps x hourly share" % station_class(s)
                occupancy = _proxy(_scale(hourly, DWELL_HOURS), "people", "assumption", "D", method,
                                   "category prior (no DataMall volumes)")
                beneficiaries = _proxy(hourly, "people/hour", "assumption", "D", method,
                                       "category prior (no DataMall volumes)")
            elif tap is None:
                occupancy = Estimate.unavailable(MISSING_VOLUMES, "people")
                beneficiaries = Estimate.unavailable(MISSING_VOLUMES, "people/hour")
            else:
                passing = (through or {}).get((s.site_id, cid), 0.0)
                occupancy = _proxy(_scale(_scale((tap,) * 3, DWELL_HOURS), variation), "people", "derived", "C",
                                   "DataMall tap in+out per hour x dwell time",
                                   "LTA DataMall PV/Train", source_date)
                beneficiaries = _proxy(_scale((tap + passing,) * 3, variation), "people/hour", "derived", "C",
                                       "DataMall tap in+out plus through passengers from PV/ODTrain",
                                       "LTA DataMall PV/Train, PV/ODTrain", source_date)
            profiles.append(Profile(
                site_id=s.site_id, condition_id=cid, role="rail_station",
                geometry_wkt=f"POINT ({s.x} {s.y})", occupancy=occupancy,
                beneficiaries_per_hour=beneficiaries, loss_fraction=loss, outage_hours=recovery,
                alternative_capacity_fraction=alternative, recovery_t90_hours=recovery, hazard=hazard,
                single_point_of_failure=s.site_id in cut_stations, raw=raw))
    return profiles


def fetch_osm_station_records() -> list:
    """MRT/LRT stations from OpenStreetMap as {name, codes, x, y} (EPSG:3414). Needs network."""
    import osmnx as ox
    ox.settings.cache_folder = str(OSMNX_CACHE)
    gdf = ox.features_from_place("Singapore", tags={"railway": "station", "station": ["subway", "light_rail"]})
    gdf = gdf.to_crs("EPSG:3414")
    records = []
    for _, row in gdf.iterrows():
        raw_ref = row.get("ref")
        codes = tuple(c for c in re.split(r"[;/,\s]+", raw_ref.upper()) if parse_code(c) or c in LOOPS) \
            if isinstance(raw_ref, str) else ()
        name = row.get("name")
        if not codes or not isinstance(name, str):
            continue
        point = row.geometry.centroid
        records.append({"name": name, "codes": codes, "x": point.x, "y": point.y})
    log.info("OSM returned %d MRT/LRT station records", len(records))
    return records
