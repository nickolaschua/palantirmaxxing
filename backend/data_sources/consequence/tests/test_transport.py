import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point, box, mapping

from backend.data_sources.consequence import FLAG_NAMES, flags, pipeline, score_profile, validate
from backend.data_sources.consequence.transport import datamall, rail, roads
from backend.exposure import prepare_population


def grid_graph():
    """4x4 grid whose left and right halves are joined only by the row-0 edge."""
    G = nx.MultiDiGraph()
    coords, grid = {}, {}
    for row in range(4):
        for col in range(4):
            nid = row * 4 + col
            coords[nid] = (col * 100.0, row * 100.0)
            grid[(row, col)] = nid
            G.add_node(nid, x=coords[nid][0], y=coords[nid][1])

    def add_edge(a, b):
        for u, v in [(a, b), (b, a)]:
            G.add_edge(u, v, key=0, highway='residential', length=100.0,
                       travel_time=100.0 / (40 * 1000 / 3600),
                       geometry=LineString([coords[u], coords[v]]))

    for row in range(4):
        for col in range(3):
            add_edge(grid[(row, col)], grid[(row, col + 1)])
    for row in range(3):
        for col in range(4):
            add_edge(grid[(row, col)], grid[(row + 1, col)])
    for row in range(1, 4):
        a, b = grid[(row, 1)], grid[(row, 2)]
        G.remove_edge(a, b, 0)
        G.remove_edge(b, a, 0)
    return G, grid


def edge_frame(G, trip_share, detour, structure=()):
    rows = []
    for u, v, k, data in G.edges(keys=True, data=True):
        rows.append({'u': u, 'v': v, 'key': k, 'highway': data['highway'], 'lanes': None,
                     'length': data['length'], 'near_structure': (u, v, k) in structure,
                     'trip_share': trip_share[(u, v, k)], 'detour_ratio': detour.get((u, v, k)),
                     'geometry': data['geometry']})
    return gpd.GeoDataFrame(rows, geometry='geometry', crs=roads.CRS)


class RoadProfiles(unittest.TestCase):
    def setUp(self):
        self.G, self.grid = grid_graph()
        self.bottleneck = (self.grid[(0, 1)], self.grid[(0, 2)], 0)

    def test_bottleneck_is_top_trip_share_and_disconnects(self):
        weights = {n: 1.0 for n in self.G}
        share, k = roads.population_betweenness(self.G, weights, k=10 ** 9)
        self.assertEqual(k, 16)
        self.assertEqual(share[self.bottleneck], max(share.values()))
        detour = roads.compute_redundancy(self.G, share, top_n=50)
        self.assertEqual(detour[self.bottleneck], math.inf)

    def test_population_weights_drive_trip_share(self):
        left = {n: 1.0 for n in self.G if n % 4 < 2}
        share_left, _ = roads.population_betweenness(self.G, left, k=10 ** 9)
        self.assertEqual(share_left[self.bottleneck], 0.0)
        # people on both sides: the only link between the halves now carries trips
        both = {**left, self.grid[(0, 3)]: 1.0}
        share_both, _ = roads.population_betweenness(self.G, both, k=10 ** 9)
        self.assertGreater(share_both[self.bottleneck], 0.0)

    def test_no_population_is_an_error(self):
        with self.assertRaises(ValueError):
            roads.population_betweenness(self.G, {})

    def test_profiles_validate_and_flag_single_point_of_failure(self):
        weights = {n: 1.0 for n in self.G}
        share, k = roads.population_betweenness(self.G, weights, k=10 ** 9)
        detour = roads.compute_redundancy(self.G, share, top_n=50)
        edges = edge_frame(self.G, share, detour, structure={self.bottleneck})
        profiles = roads.road_profiles(edges, total_population=1_000_000, k=k)
        self.assertEqual(len(profiles), len(edges) * 6)
        for p in profiles:
            self.assertTrue(validate(p))

        bottleneck_id = 'road:%d-%d-0' % self.bottleneck[:2]
        other_id = 'road:0-4-0'
        pick = lambda site: next(p for p in profiles
                                 if p.site_id == site and p.condition_id == 'weekday_am_peak')
        spof, other = pick(bottleneck_id), pick(other_id)
        self.assertTrue(spof.single_point_of_failure)
        self.assertIn('single_point_of_failure', flags(spof, score_profile(spof)))
        self.assertGreater(score_profile(spof).E.central, score_profile(other).E.central)
        self.assertEqual(spof.alternative_capacity_fraction.central, 0.0)
        self.assertEqual(spof.recovery_t90_hours.central, roads.STRUCTURE_RECOVERY_HOURS[1])

    def test_unevaluated_detour_keeps_full_alternative_range(self):
        estimate = roads._alternative_capacity(None)
        self.assertEqual((estimate.low, estimate.high), (0.0, 1.0))
        self.assertEqual(estimate.state, 'assumption')


def record(name, codes, x, y):
    return {'name': name, 'codes': tuple(codes), 'x': float(x), 'y': float(y)}


# NS1=EW1 and NS4=EW3 close a cycle; CC1=NS2 starts a spur ending at CC2.
RECORDS = [
    record('Alpha', ['NS1', 'EW1'], 0, 0),
    record('Bravo', ['NS2', 'CC1'], 2000, 0),
    record('Charlie', ['NS3'], 4000, 0),
    record('Delta', ['NS4', 'EW3'], 6000, 0),
    record('Echo', ['EW2'], 3000, 5000),
    record('Foxtrot', ['CC2'], 2000, 9000),
]


def setup_network():
    stations = rail.merge_sites(RECORDS)
    return stations, rail.build_rail_graph(stations)


def site(stations, code):
    return next(s.site_id for s in stations if code in s.codes)


class Topology(unittest.TestCase):
    def test_parse_code(self):
        self.assertEqual(rail.parse_code('NS24'), ('NS', 24, ''))
        self.assertEqual(rail.parse_code('ns2a'), ('NS', 2, 'A'))
        self.assertIsNone(rail.parse_code('STC'))

    def test_shared_codes_merge_into_interchange(self):
        stations, _ = setup_network()
        self.assertEqual(len(stations), 6)
        self.assertEqual(next(s for s in stations if 'NS2' in s.codes).codes, ('CC1', 'NS2'))

    def test_same_name_nearby_merges_but_far_does_not(self):
        near = rail.merge_sites([record('Dover MRT Station', ['EW1'], 0, 0), record('Dover', ['DT1'], 100, 0)])
        self.assertEqual(len(near), 1)
        far = rail.merge_sites([record('Dover', ['EW1'], 0, 0), record('Dover', ['DT1'], 5000, 0)])
        self.assertEqual(len(far), 2)

    def test_gap_in_numbering_breaks_the_line_unless_known(self):
        stations = rail.merge_sites([record('A', ['NS1'], 0, 0), record('B', ['NS5'], 1, 0),
                                     record('C', ['CC17'], 0, 5), record('D', ['CC19'], 1, 5)])
        G = rail.build_rail_graph(stations)
        self.assertFalse(G.has_edge(site(stations, 'NS1'), site(stations, 'NS5')))
        self.assertTrue(G.has_edge(site(stations, 'CC17'), site(stations, 'CC19')))

    def test_loop_hub_and_branch_edge(self):
        stations = rail.merge_sites([record('Hub', ['STC'], 0, 0), record('S1', ['SE1'], 1, 0),
                                     record('S2', ['SE2'], 2, 0), record('T', ['EW4'], 9, 9),
                                     record('E', ['CG1'], 9, 10)])
        G = rail.build_rail_graph(stations)
        hub = site(stations, 'STC')
        self.assertTrue(G.has_edge(hub, site(stations, 'SE1')))
        self.assertTrue(G.has_edge(hub, site(stations, 'SE2')))
        self.assertTrue(G.has_edge(site(stations, 'EW4'), site(stations, 'CG1')))

    def test_cut_stations_are_flagged_and_line_ends_are_not(self):
        stations, G = setup_network()
        profiles = rail.rail_profiles(stations, G)
        spof = {p.site_id for p in profiles if p.single_point_of_failure}
        self.assertEqual(spof, {site(stations, 'NS2')})
        self.assertNotIn(site(stations, 'CC2'), spof)


class Volumes(unittest.TestCase):
    MONTH = '202603'  # 22 weekdays, 9 weekend days

    def test_day_counts(self):
        self.assertEqual(datamall.day_counts(self.MONTH), {'weekday': 22, 'weekend': 9})

    def test_station_hourly_flows(self):
        df = pd.DataFrame([
            {'DAY_TYPE': 'WEEKDAY', 'TIME_PER_HOUR': 8, 'PT_CODE': 'NS2', 'TOTAL_TAP_IN_VOLUME': 2200,
             'TOTAL_TAP_OUT_VOLUME': 2200},
            {'DAY_TYPE': 'WEEKENDS/HOLIDAY', 'TIME_PER_HOUR': 10, 'PT_CODE': 'NS2',
             'TOTAL_TAP_IN_VOLUME': 900, 'TOTAL_TAP_OUT_VOLUME': 0},
        ])
        flows = datamall.station_hourly_flows(df, self.MONTH)
        # AM peak covers hours 7 and 8; only hour 8 has data: 4400 / 2 hours / 22 days
        self.assertAlmostEqual(flows[('NS2', 'weekday_am_peak')], 100.0)
        # weekend day covers 13 hours: 900 / 13 / 9 days
        self.assertAlmostEqual(flows[('NS2', 'weekend_day')], 900 / 13 / 9)
        self.assertNotIn(('NS2', 'weekday_night'), flows)

    def test_od_hourly_trips(self):
        df = pd.DataFrame([{'DAY_TYPE': 'WEEKDAY', 'TIME_PER_HOUR': 8, 'ORIGIN_PT_CODE': 'CC2',
                            'DESTINATION_PT_CODE': 'NS3', 'TOTAL_TRIPS': 880}])
        trips = datamall.od_hourly_trips(df, self.MONTH)
        self.assertAlmostEqual(trips[('CC2', 'NS3', 'weekday_am_peak')], 880 / 2 / 22)

    def test_through_passengers_count_interior_stations_only(self):
        stations, G = setup_network()
        through, unmatched = rail.through_passengers(
            G, stations, {('CC2', 'NS3', 'weekday_am_peak'): 40.0, ('XX9', 'NS3', 'weekday_am_peak'): 5.0})
        self.assertEqual(through, {(site(stations, 'NS2'), 'weekday_am_peak'): 40.0})
        self.assertEqual(unmatched, 1)


class Profiles(unittest.TestCase):
    def test_without_volumes_uses_category_prior_grade_d(self):
        stations, G = setup_network()
        profiles = rail.rail_profiles(stations, G)
        for p in profiles:
            self.assertTrue(validate(p))
            self.assertEqual((p.occupancy.state, p.occupancy.grade), ('assumption', 'D'))
            self.assertTrue(score_profile(p).rankable)
        am = {p.site_id: p for p in profiles if p.condition_id == 'weekday_am_peak'}
        interchange = am[site(stations, 'NS2')]  # NS2/CC1 -> two lines
        terminal = am[site(stations, 'CC2')]     # CC line only -> plain MRT class
        self.assertEqual(interchange.raw['station_class'], 'interchange')
        self.assertEqual(terminal.raw['station_class'], 'mrt')
        self.assertGreater(interchange.beneficiaries_per_hour.central, terminal.beneficiaries_per_hour.central)

    def test_lrt_only_and_hub_classification(self):
        lrt = rail.merge_sites([record('S1', ['SE1'], 0, 0), record('Hub', ['NE16', 'STC'], 5, 5)])
        classes = {s.codes[0]: rail.station_class(s) for s in lrt}
        self.assertEqual(classes, {'SE1': 'lrt', 'NE16': 'interchange'})

    def test_prior_disabled_leaves_occupancy_unavailable_and_not_rankable(self):
        stations, G = setup_network()
        for p in rail.rail_profiles(stations, G, prior=False):
            self.assertFalse(validate(p))
            self.assertFalse(p.occupancy.available)
            self.assertFalse(score_profile(p).rankable)

    def test_with_volumes_occupancy_is_grade_c_and_rankable(self):
        stations, G = setup_network()
        flows = {(c, 'weekday_am_peak'): 1000.0 for s in stations for c in s.codes}
        through = {(site(stations, 'NS2'), 'weekday_am_peak'): 500.0}
        profiles = rail.rail_profiles(stations, G, flows, through, volume_month='202603')
        am = {p.site_id: p for p in profiles if p.condition_id == 'weekday_am_peak'}
        bravo = am[site(stations, 'NS2')]  # NS2 and CC1 both report 1000
        self.assertTrue(validate(bravo))
        self.assertEqual((bravo.occupancy.state, bravo.occupancy.grade), ('derived', 'C'))
        self.assertEqual(bravo.occupancy.source_date, '2026-03-01')
        self.assertAlmostEqual(bravo.occupancy.central, 2000 * (10 / 60))
        self.assertAlmostEqual(bravo.beneficiaries_per_hour.central, 2500.0)
        scored = score_profile(bravo)
        self.assertTrue(scored.rankable)
        self.assertIn('single_point_of_failure', flags(bravo, scored))
        # hours with no data stay unavailable rather than becoming zero
        night = next(p for p in profiles if p.site_id == bravo.site_id and p.condition_id == 'weekday_night')
        self.assertFalse(night.occupancy.available)


class PopulationWeights(unittest.TestCase):
    def test_zone_population_is_split_over_its_nodes_and_outside_nodes_get_none(self):
        dataset = dict(schema_version='pec-population/1', dataset_id='synthetic', version='1',
                       coordinate_reference_system='EPSG:3414',
                       zones=[dict(zone_id='z', population=300, geometry=mapping(box(0, 0, 100, 100)))])
        nodes = gpd.GeoDataFrame({'osmid': [1, 2, 3, 4]},
                                 geometry=[Point(10, 10), Point(20, 20), Point(30, 30), Point(500, 500)],
                                 crs='EPSG:3414')
        weights = roads.node_population_weights(nodes, prepare_population(dataset))
        self.assertEqual(weights, {1: 100.0, 2: 100.0, 3: 100.0})


class Outputs(unittest.TestCase):
    def test_write_outputs_for_roads_and_rail(self):
        G, grid = grid_graph()
        share, k = roads.population_betweenness(G, {n: 1.0 for n in G}, k=10 ** 9)
        detour = roads.compute_redundancy(G, share, top_n=50)
        profiles = roads.road_profiles(edge_frame(G, share, detour), 1_000_000, k)
        stations = rail.merge_sites(RECORDS)
        profiles += rail.rail_profiles(stations, rail.build_rail_graph(stations))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pipeline.write_transport(profiles, out, {'test': True})
            with (out / 'transport_output.csv').open(encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                header = reader.fieldnames
                rows = list(reader)
            with (out / 'transport_output_inputs.csv').open(encoding='utf-8') as stream:
                input_rows = list(csv.DictReader(stream))
            sites = json.loads((out / 'transport_output_sites.geojson').read_text(encoding='utf-8'))
            provenance = json.loads((out / 'transport_output_provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(len(header), 43)  # pipeline.MAIN_COLUMNS
        self.assertEqual(header[-1], 'policy_version')
        self.assertEqual(len(rows), len(profiles))
        self.assertEqual(len(input_rows), len(profiles))
        self.assertEqual(len(sites['features']), len(profiles) // 6)
        self.assertEqual(provenance['profile_rows'], len(profiles))
        road_rows = [r for r in rows if r['role'] == 'road_segment']
        station_rows = [r for r in rows if r['role'] == 'rail_station']
        self.assertTrue(all(r['rankable'] == 'True' for r in road_rows + station_rows))
        station_inputs = [r for r in input_rows if r['site_id'].startswith('station:')]
        self.assertTrue(all(r['occupancy_state'] == 'assumption' and r['occupancy_grade'] == 'D'
                            for r in station_inputs))
        for r in rows:
            # the whole vector is present: D and X are explicit gaps, never zero and never dropped
            for dim in ('C', 'O_display', 'E', 'R', 'A', 'secondary'):
                self.assertNotEqual(r[f'{dim}_central'], '')
            for dim in ('D', 'X'):
                self.assertEqual((r[f'{dim}_central'], r[f'{dim}_low'], r[f'{dim}_high']), ('', '', ''))
            self.assertEqual(r['dimensions_missing'], 'D|X')
            for flag in FLAG_NAMES:
                self.assertIn(r[f'flag_{flag}'], ('True', 'False', 'unavailable'))
            self.assertEqual(r['flag_minimum_capability_breach'], 'unavailable')
            self.assertEqual(r['flag_mass_vulnerability_condition'], 'unavailable')
        for r in input_rows:
            self.assertTrue(r['lat'] and r['lon'])  # every row is locatable
            float(r['lat']), float(r['lon'])
        self.assertEqual({r['name'] for r in station_inputs},
                         {'Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot'})
        self.assertIn('CC1/NS2', {r['codes'] for r in station_inputs})
        for r in input_rows:
            self.assertEqual(r['vulnerability_age_vulnerable_state'], 'unavailable')
            self.assertEqual((r['D_status'], r['X_status']), ('unavailable', 'unavailable'))
            self.assertTrue(r['D_reason'] and r['X_reason'])
            self.assertNotEqual(r['hazard_toxic_high'], '')
        self.assertTrue(any(r['flag_single_point_of_failure'] == 'True' for r in road_rows))
        for r in road_rows:
            self.assertLessEqual(float(r['secondary_low']), float(r['secondary_central']))
            self.assertLessEqual(float(r['secondary_central']), float(r['secondary_high']))


if __name__ == '__main__':
    unittest.main()
