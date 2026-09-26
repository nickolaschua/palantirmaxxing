"""Road-segment consequence profiles for Singapore's OSM drive network.

Builds the drive graph, measures how much of the population-weighted trip demand
each segment carries (sampled edge betweenness) and how badly a closure would
reroute (detour cost), then turns those into conditional consequence profiles
(backend/consequence). Singapore publishes no link-level traffic volumes, so
every service-loss and occupancy input here is a grade-D proxy or assumption;
the raw betweenness and detour values are kept as evidence.

Method background: edge betweenness with targeted-disruption framing (Chung et
al. 2025; Freeman 1977; Brandes & Pich 2007) and a Network Robustness
Index-style detour cost (Scott et al. 2006).
"""
from __future__ import annotations

import logging
import math
import os

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import requests
from shapely.geometry import LineString

from backend.data_sources.consequence import Estimate, Profile
from backend.data_sources.consequence.profile import HAZARD_COMPONENTS

from . import datamall as dm
from backend.data_sources.consequence.conditions import CONDITIONS
from backend.data_sources.consequence.paths import OSMNX_CACHE

log = logging.getLogger(__name__)
ox.settings.cache_folder = str(OSMNX_CACHE)

# --- Network extraction ------------------------------------------------------
PLACE_NAME = "Singapore"
BBOX_NORTH, BBOX_SOUTH, BBOX_EAST, BBOX_WEST = 1.4784, 1.1304, 104.1414, 103.6057
NETWORK_TYPE = "drive"
CRS = "EPSG:3414"  # SVY21, Singapore's metric CRS
FALLBACK_SPEED_KPH = 40

# --- Structure overlay -------------------------------------------------------
BRIDGE_DATASET_ID = os.environ.get("SG_BRIDGE_DATASET_ID")
BRIDGE_DIRECT_URL = os.environ.get("SG_BRIDGE_DIRECT_URL")
BRIDGE_BUFFER_M = 25

# --- Edge weighting ----------------------------------------------------------
SNAP_TOLERANCE_M = 30

# Ordinal design-intent weights by OSM highway class (not measured traffic).
HIGHWAY_CLASS_WEIGHTS = {
    "motorway": 10, "motorway_link": 8,
    "trunk": 8, "trunk_link": 6,
    "primary": 6, "primary_link": 5,
    "secondary": 4, "secondary_link": 3,
    "tertiary": 3, "tertiary_link": 2,
    "unclassified": 1.5,
    "residential": 1,
    "living_street": 0.5,
}
DEFAULT_HIGHWAY_WEIGHT = 1.0

# --- Centrality --------------------------------------------------------------
BETWEENNESS_K = int(os.environ.get("BETWEENNESS_K", 500))
BETWEENNESS_SEED = 42
PATH_WEIGHT = "travel_time"
REDUNDANCY_TOP_N_EDGES = int(os.environ.get("REDUNDANCY_TOP_N_EDGES", 1500))

# --- Profile assumptions (ALL uncalibrated; grade D; each is (low, central, high)) -------
# Daily trips per resident, applied to the population-weighted trip share of a segment.
TRIPS_PER_PERSON_PER_DAY = (1.5, 2.0, 2.5)
# Share of a day's trips falling in each hour of the condition window.
HOURLY_TRIP_SHARE = {
    "weekday_am_peak": (0.07, 0.09, 0.11),
    "weekday_midday": (0.04, 0.05, 0.06),
    "weekday_pm_peak": (0.06, 0.08, 0.10),
    "weekday_night": (0.005, 0.015, 0.03),
    "weekend_day": (0.04, 0.05, 0.06),
    "weekend_night": (0.005, 0.015, 0.03),
}
# Vehicles on the road per lane-km at once, by condition.
VEHICLES_PER_LANE_KM = {
    "weekday_am_peak": (20, 40, 60),
    "weekday_midday": (10, 20, 30),
    "weekday_pm_peak": (20, 40, 60),
    "weekday_night": (2, 5, 10),
    "weekend_day": (10, 20, 30),
    "weekend_night": (2, 5, 10),
}
PERSONS_PER_VEHICLE = (1.2, 1.4, 1.8)
# Lanes per direction when OSM has no lanes tag.
DEFAULT_LANES = {"motorway": 3, "trunk": 2, "primary": 2}
DEFAULT_LANES_OTHER = 1
# Hours until 90% function: surface closure vs structure-dependent (bridge/flyover/underpass) closure.
SURFACE_RECOVERY_HOURS = (6, 12, 24)
STRUCTURE_RECOVERY_HOURS = (96, 168, 336)
# Sampling noise on the betweenness estimate; the high side is floored at one sampled pair.
TRIP_SHARE_BAND = (0.5, 1.0, 2.0)
# Detour-derived alternative capacity is a proxy, not a measured capacity.
ALTERNATIVE_CAPACITY_BAND = (0.5, 1.0, 1.5)
# Segment loss: full closure.
LOSS_FRACTION = (1.0, 1.0, 1.0)
# Hazard components for a plain road segment (no fuel or toxic inventory on the road itself).
HAZARD_ASSUMPTION = (0.0, 0.0, 10.0)

# =============================================================================
# Network
# =============================================================================
def download_graph() -> nx.MultiDiGraph:
    """Place-name query, falling back to a bounding box if Nominatim fails."""
    try:
        log.info("Requesting OSM extract for place=%r", PLACE_NAME)
        G = ox.graph_from_place(PLACE_NAME, network_type=NETWORK_TYPE)
    except Exception as exc:  # noqa: BLE001 -- any geocoding failure falls back
        log.warning("Place-name query failed (%s); falling back to bounding box", exc)
        G = ox.graph_from_bbox(
            (BBOX_NORTH, BBOX_SOUTH, BBOX_EAST, BBOX_WEST), network_type=NETWORK_TYPE
        )
    log.info("Downloaded %d nodes, %d edges", len(G.nodes), len(G.edges))
    return G


def _collapse_highway(v):
    if isinstance(v, list):
        return max(v, key=lambda t: HIGHWAY_CLASS_WEIGHTS.get(t, DEFAULT_HIGHWAY_WEIGHT))
    return v


def _collapse_lanes(v):
    if isinstance(v, list):
        try:
            return max(float(x) for x in v)
        except (TypeError, ValueError):
            return None
    return v


def build_network() -> tuple[nx.MultiDiGraph, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Largest strongly connected component of the projected drive network.

    Returns the graph plus node and edge GeoDataFrames (edges keep u, v, key
    as columns).
    """
    G = download_graph()
    G = ox.truncate.largest_component(G, strongly=True)
    G = ox.add_edge_speeds(G, fallback=FALLBACK_SPEED_KPH)
    G = ox.add_edge_travel_times(G)
    G = ox.project_graph(G, to_crs=CRS)

    for _, _, data in G.edges(data=True):
        if not data.get(PATH_WEIGHT) or data[PATH_WEIGHT] <= 0:
            data[PATH_WEIGHT] = max(data.get("length", 1.0), 1.0) / (FALLBACK_SPEED_KPH * 1000 / 3600)

    nodes, edges = ox.graph_to_gdfs(G)
    edges["highway"] = edges["highway"].map(_collapse_highway)
    if "lanes" in edges.columns:
        edges["lanes"] = edges["lanes"].map(_collapse_lanes)
    return G, nodes.reset_index(), edges.reset_index()


# =============================================================================
# Structure overlay
# =============================================================================
def fetch_bridge_geometries() -> gpd.GeoDataFrame | None:
    """LTA bridge/flyover/underpass layer, or None if not configured/available."""
    if BRIDGE_DIRECT_URL:
        return gpd.read_file(BRIDGE_DIRECT_URL)

    if BRIDGE_DATASET_ID:
        poll_url = (
            "https://api-open.data.gov.sg/v1/public/api/datasets/"
            f"{BRIDGE_DATASET_ID}/poll-download"
        )
        try:
            resp = requests.get(poll_url, timeout=30)
            resp.raise_for_status()
            return gpd.read_file(resp.json()["data"]["url"])
        except Exception as exc:  # noqa: BLE001
            log.warning("data.gov.sg bridge download failed (%s); skipping overlay", exc)
            return None

    log.warning("No bridge dataset configured; near_structure=False for all edges")
    return None


def overlay_structures(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Flag edges within BRIDGE_BUFFER_M of a bridge, flyover or underpass."""
    edges = edges.copy()
    edges["near_structure"] = False
    edges["structure_name"] = None

    bridges = fetch_bridge_geometries()
    if bridges is None or bridges.empty:
        return edges

    bridges = bridges.to_crs(edges.crs)
    bridges["geometry"] = bridges.geometry.buffer(BRIDGE_BUFFER_M)
    name_col = next(
        (c for c in ("STRUCTURE_NAME", "structure_name", "NAME", "name") if c in bridges.columns),
        None,
    )

    joined = gpd.sjoin(
        edges[["geometry"]],
        bridges[["geometry"] + ([name_col] if name_col else [])],
        how="inner",
        predicate="intersects",
    )
    edges.loc[joined.index.unique(), "near_structure"] = True
    if name_col:
        names = joined.groupby(level=0)[name_col].first()
        edges.loc[names.index, "structure_name"] = names.values

    log.info(
        "Flagged %d/%d edges as structure-dependent", edges["near_structure"].sum(), len(edges)
    )
    return edges


# =============================================================================
# Edge weighting
# =============================================================================
def _speedbands_to_gdf(df: pd.DataFrame, target_crs) -> gpd.GeoDataFrame:
    """DataMall Location is 'startLat startLon endLat endLon'."""

    def parse_line(loc: str) -> LineString:
        s_lat, s_lon, e_lat, e_lon = (float(x) for x in loc.split())
        return LineString([(s_lon, s_lat), (e_lon, e_lat)])

    df = df.copy()
    df["geometry"] = df["Location"].apply(parse_line)
    return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326").to_crs(target_crs)


def _osm_class_weight(edges: gpd.GeoDataFrame) -> pd.Series:
    return edges["highway"].map(HIGHWAY_CLASS_WEIGHTS).fillna(DEFAULT_HIGHWAY_WEIGHT)


def weight_from_osm_proxy(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """OSM highway class, nudged up ~15% per extra lane."""
    edges = edges.copy()
    edges["importance_weight"] = _osm_class_weight(edges)

    if "lanes" in edges.columns:

        def lane_multiplier(v):
            try:
                return 1.0 + 0.15 * max(float(v) - 1, 0)
            except (TypeError, ValueError):
                return 1.0

        edges["importance_weight"] *= edges["lanes"].map(lane_multiplier)

    edges["road_category"] = None
    edges["weight_source"] = "osm_proxy"
    return edges


def weight_from_datamall(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Snap DataMall speed-band links to the nearest OSM edge and weight by
    LTA RoadCategory (lower category = more important, so inverted)."""
    speedbands = dm.fetch_speedbands()
    if speedbands.empty:
        log.warning("DataMall returned no speed-band rows; using OSM proxy")
        return weight_from_osm_proxy(edges)

    joined = gpd.sjoin_nearest(
        edges.reset_index(),
        _speedbands_to_gdf(speedbands, edges.crs),
        how="left",
        max_distance=SNAP_TOLERANCE_M,
        distance_col="snap_dist_m",
    )
    joined = joined.sort_values("snap_dist_m").drop_duplicates("index", keep="first").set_index("index")

    edges = edges.copy()
    edges["road_category"] = joined["RoadCategory"]
    category = pd.to_numeric(edges["road_category"], errors="coerce")
    edges["importance_weight"] = ((category.max() + 1) - category).fillna(_osm_class_weight(edges))
    edges["weight_source"] = np.where(edges["road_category"].notna(), "datamall_speedbands", "osm_fallback")
    log.info(
        "Matched %d/%d edges to a DataMall link", edges["road_category"].notna().sum(), len(edges)
    )
    return edges


def weight_edges(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if dm.LTA_ACCOUNT_KEY:
        try:
            return weight_from_datamall(edges)
        except Exception as exc:  # noqa: BLE001
            log.warning("DataMall weighting failed (%s); using OSM proxy", exc)
    return weight_from_osm_proxy(edges)


def compute_redundancy(
    G: nx.MultiDiGraph, edge_bc: dict, top_n: int = REDUNDANCY_TOP_N_EDGES
) -> dict:
    """Detour ratio for the top_n edges by betweenness.

    Removes each edge and measures how much longer the trip between its own
    endpoints becomes: (rerouted / original) - 1, or inf if the endpoints
    become disconnected. Edges outside the top_n (and edges whose endpoints
    have no path to begin with) are absent from the result.
    """
    ranked = sorted(edge_bc, key=edge_bc.get, reverse=True)[:top_n]
    log.info("Detour cost for the top %d edges by betweenness", len(ranked))

    detour = {}
    for u, v, key in ranked:
        try:
            original = nx.shortest_path_length(G, u, v, weight=PATH_WEIGHT)
        except nx.NetworkXNoPath:
            continue

        edge_data = G.get_edge_data(u, v, key)
        G.remove_edge(u, v, key)
        try:
            rerouted = nx.shortest_path_length(G, u, v, weight=PATH_WEIGHT)
            detour[(u, v, key)] = (rerouted / original) - 1 if original > 0 else 0.0
        except nx.NetworkXNoPath:
            detour[(u, v, key)] = float("inf")
        finally:
            G.add_edge(u, v, key, **edge_data)
    return detour



# =============================================================================
# Population-weighted trip share
# =============================================================================
def node_population_weights(nodes: gpd.GeoDataFrame, prepared) -> dict:
    """Split each eligible subzone's residents evenly over the graph nodes inside it.

    prepared is a backend.exposure.PreparedPopulation, so the population dataset
    identity and its eligibility rules are shared with the exposure calculator.
    Nodes outside every eligible subzone, and subzones containing no node, carry
    no weight (their residents drop out of the demand model).
    """
    hits = prepared.tree.query(nodes.geometry.values, predicate="intersects")
    pairs = pd.DataFrame({"node": hits[0], "zone": hits[1]}).drop_duplicates("node")
    per_zone = pairs.groupby("zone")["node"].transform("size")
    pairs["weight"] = np.array([prepared.zones[z]["population"] for z in pairs["zone"]]) / per_zone
    osmids = nodes["osmid"].to_numpy()
    return {int(osmids[n]): float(w) for n, w in zip(pairs["node"], pairs["weight"]) if w > 0}


def population_betweenness(G: nx.MultiDiGraph, node_weight: dict, k: int = BETWEENNESS_K,
                           seed: int = BETWEENNESS_SEED) -> tuple[dict, int]:
    """Share of population-weighted origin-destination pairs whose shortest path uses each edge.

    Draws k origins and k destinations with probability proportional to node
    population (without replacement), runs subset betweenness between them, and
    divides by k*k pairs. Demand is population x population with no distance
    decay, which over-weights long trips; it is a topological proxy, not a
    calibrated trip matrix. Returns ({(u, v, key): trip_share}, k used).
    """
    nodes = [n for n in G if node_weight.get(n, 0) > 0]
    if not nodes:
        raise ValueError("No graph node carries population weight")
    k = min(k, len(nodes))
    p = np.array([node_weight[n] for n in nodes], dtype=float)
    p /= p.sum()
    rng = np.random.default_rng(seed)
    sources = [nodes[i] for i in rng.choice(len(nodes), size=k, replace=False, p=p)]
    targets = [nodes[i] for i in rng.choice(len(nodes), size=k, replace=False, p=p)]
    log.info("Population-weighted betweenness: %d origins x %d destinations on %d nodes / %d edges",
             k, k, G.number_of_nodes(), G.number_of_edges())
    bc = nx.edge_betweenness_centrality_subset(G, sources, targets, normalized=False, weight=PATH_WEIGHT)
    return {edge: value / (k * k) for edge, value in bc.items()}, k


# =============================================================================
# Profiles
# =============================================================================
def _times(a: tuple, b: tuple) -> tuple:
    return tuple(x * y for x, y in zip(a, b))


def _proxy(triple, unit, state, grade, method) -> Estimate:
    low, central, high = triple
    return Estimate(low, central, high, unit, state, grade, source="transport road proxy",
                    method=method, resolution="road segment")


def _lanes(row) -> float:
    try:
        lanes = float(row.get("lanes"))
        if math.isfinite(lanes) and lanes > 0:
            return lanes
    except (TypeError, ValueError):
        pass
    return float(DEFAULT_LANES.get(row.get("highway"), DEFAULT_LANES_OTHER))


def _alternative_capacity(detour_ratio) -> Estimate:
    if detour_ratio is None:
        return _proxy((0.0, 0.5, 1.0), "fraction", "assumption", "D",
                      "detour not evaluated (outside top-N by betweenness): full range")
    if math.isinf(detour_ratio):
        return _proxy((0.0, 0.0, 0.0), "fraction", "derived", "D",
                      "edge removal disconnects its endpoints: no alternative route")
    capacity = 1.0 / (1.0 + detour_ratio)
    low, high = capacity * ALTERNATIVE_CAPACITY_BAND[0], min(1.0, capacity * ALTERNATIVE_CAPACITY_BAND[2])
    return _proxy((low, capacity, high), "fraction", "derived", "D", "1/(1+detour_ratio) from removing the edge")


def _clean(value):
    """JSON-safe scalar: NaN/None -> None, +inf -> "inf" (a disconnecting detour), numpy -> python."""
    value = value.item() if hasattr(value, "item") else value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf"
    return value


def road_evidence(row) -> dict:
    """Source-native columns kept alongside the scores."""
    keys = ("name", "highway", "lanes", "length", "importance_weight", "weight_source",
            "road_category", "near_structure", "structure_name", "trip_share", "detour_ratio")
    return {k: _clean(row.get(k)) for k in keys}


def road_profiles(edges: gpd.GeoDataFrame, total_population: float, k: int) -> list[Profile]:
    """One Profile per edge and transport condition.

    edges needs u, v, key, length and geometry (EPSG:3414) plus the columns from
    overlay_structures/weight_edges, and trip_share and detour_ratio.
    """
    floor = 1.0 / (k * k)
    profiles = []
    for row in edges.to_dict("records"):
        detour = row.get("detour_ratio")
        detour = None if detour is None or math.isnan(detour) else float(detour)
        spof = detour is not None and math.isinf(detour)
        share = row["trip_share"]
        share3 = (share * TRIP_SHARE_BAND[0], share, max(share * TRIP_SHARE_BAND[2], floor))
        structure = bool(row.get("near_structure"))
        recovery = _proxy(STRUCTURE_RECOVERY_HOURS if structure else SURFACE_RECOVERY_HOURS, "hours",
                          "assumption", "D", "structure-dependent closure" if structure else "surface closure")
        alternative = _alternative_capacity(detour)
        loss = _proxy(LOSS_FRACTION, "fraction", "assumption", "D", "full segment closure")
        hazard = {name: _proxy(HAZARD_ASSUMPTION, "score_0_100", "assumption", "D",
                               "no on-road hazardous inventory assumed")
                  for name in HAZARD_COMPONENTS}
        lane_km = _lanes(row) * row["length"] / 1000.0
        evidence = road_evidence(row)
        site_id = f"road:{row['u']}-{row['v']}-{row['key']}"
        wkt = row["geometry"].wkt
        for condition in CONDITIONS:
            cid = condition.condition_id
            occupancy = _proxy(_times(_times((lane_km,) * 3, VEHICLES_PER_LANE_KM[cid]), PERSONS_PER_VEHICLE),
                               "people", "assumption", "D",
                               "lane-km x vehicles per lane-km x persons per vehicle")
            demand = _times(_times(share3, (total_population,) * 3),
                            _times(TRIPS_PER_PERSON_PER_DAY, HOURLY_TRIP_SHARE[cid]))
            beneficiaries = _proxy(demand, "people/hour", "derived", "D",
                                   "population-weighted trip share x residents x trips/day x hourly share")
            profiles.append(Profile(
                site_id=site_id, condition_id=cid, role="road_segment", geometry_wkt=wkt,
                occupancy=occupancy, beneficiaries_per_hour=beneficiaries, loss_fraction=loss,
                outage_hours=recovery, alternative_capacity_fraction=alternative,
                recovery_t90_hours=recovery, hazard=hazard, single_point_of_failure=spof,
                raw=evidence))
    return profiles
