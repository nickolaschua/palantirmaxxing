import copy
import json
import math
from pathlib import Path
import unittest
from shapely.geometry import box, mapping
from backend.exposure import prepare_population, calculate_episode, CalculationSettings, PECValidationError
from backend.exposure.calculator import footprint

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


def population(zones=None):
    return dict(schema_version='pec-population/1', dataset_id='synthetic', version='1',
                coordinate_reference_system='EPSG:3414', zones=zones if zones is not None else [zone('a', (-10, -10, 10, 10), 400)])


def zone(zid, bounds, count):
    return dict(zone_id=zid, population=count, geometry=mapping(box(*bounds)))


def event(eid='e1', x=0, y=0, radius=1, fid=None):
    return dict(event_id=eid, footprint_id=fid or eid, center_x_m=x, center_y_m=y, radius_m=radius)


def episode(events=None):
    return dict(schema_version='pec-episode/1', episode_id='example', population_dataset_id='synthetic',
                population_dataset_version='1', coordinate_reference_system='EPSG:3414', events=events or [])


def area(radius=1, edges=128):
    return edges / 2 * radius ** 2 * math.sin(2 * math.pi / edges)


class ExposureTests(unittest.TestCase):
    def run_case(self, events=None, zones=None, edges=128):
        return calculate_episode(prepare_population(population(zones)), episode(events), CalculationSettings(edges))

    def test_empty_episode(self):
        r = self.run_case()
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(r['events'], [])
        for key in ('unique_people_potentially_exposed', 'total_person_exposures', 'people_exposed_to_multiple_events', 'uncovered_area_m2'):
            self.assertEqual(r[key], 0)

    def test_zero_radius_inside_and_outside(self):
        for x in (0, 100):
            r = self.run_case([event(x=x, radius=0)])
            self.assertEqual(r['status'], 'complete')
            e = r['events'][0]
            self.assertEqual(e['footprint_area_m2'], 0)
            self.assertEqual(e['known_area_exposure'], 0)
            self.assertEqual(e['people_potentially_exposed'], 0)
            self.assertEqual(e['zone_breakdown'], [])
            self.assertIsNone(e['covered_area_fraction'])

    def test_zero_population_is_coverage(self):
        r = self.run_case([event()], [zone('zero', (-2, -2, 2, 2), 0)])
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(r['known_area_unique_exposure'], 0)
        self.assertAlmostEqual(r['events'][0]['covered_area_fraction'], 1)
        self.assertEqual(len(r['events'][0]['zone_breakdown']), 1)

    def test_full_zone_and_triple_identical(self):
        r = self.run_case([event(str(i), radius=2, fid='same') for i in range(3)], [zone('a', (-1, -1, 1, 1), 100)])
        self.assertEqual(r['status'], 'partial_coverage')
        self.assertEqual(r['known_area_unique_exposure'], 100)
        self.assertEqual(r['known_area_person_exposures'], 300)
        self.assertEqual(r['known_area_multiple_exposure'], 100)
        self.assertEqual(r['events'][0]['zone_breakdown'][0]['overlap_area_m2'], 4)
        # Also exercise complete totals using a zone exactly equal to the calculation polygon.
        polygon = footprint(event(), CalculationSettings())
        z = dict(zone_id='circle', population=100, geometry=mapping(polygon))
        r = self.run_case([event(str(i), fid='same') for i in range(3)], [z])
        self.assertEqual(r['status'], 'complete')
        self.assertAlmostEqual(r['unique_people_potentially_exposed'], 100)
        self.assertAlmostEqual(r['total_person_exposures'], 300)
        self.assertAlmostEqual(r['people_exposed_to_multiple_events'], 100)

    def test_cross_zone_densities_shared_boundary(self):
        r = self.run_case([event()], [zone('left', (-2, -2, 0, 2), 8), zone('right', (0, -2, 2, 2), 24)])
        self.assertEqual(r['status'], 'complete')
        rows = r['events'][0]['zone_breakdown']
        self.assertEqual([z['zone_id'] for z in rows], ['left', 'right'])
        self.assertAlmostEqual(rows[0]['estimated_people_exposed'], area() / 2)
        self.assertAlmostEqual(rows[1]['estimated_people_exposed'], area() * 1.5)
        self.assertAlmostEqual(r['known_area_unique_exposure'], area() * 2)

    def test_partial_and_uncovered(self):
        for x, fraction in [(0, 0.5), (-5, 0)]:
            r = self.run_case([event(x=x)], [zone('right', (0, -2, 2, 2), 8)])
            self.assertEqual(r['status'], 'partial_coverage')
            e = r['events'][0]
            self.assertAlmostEqual(e['covered_area_fraction'], fraction)
            self.assertAlmostEqual(e['uncovered_area_m2'], area() * (1-fraction))
            self.assertAlmostEqual(e['known_area_exposure'], area() * fraction)
            for key in ('unique_people_potentially_exposed', 'total_person_exposures', 'people_exposed_to_multiple_events'):
                self.assertIsNone(r[key])
            self.assertIsNone(e['people_potentially_exposed'])

    def test_empty_population_and_tolerance(self):
        self.assertEqual(self.run_case([event()], [])['status'], 'partial_coverage')
        self.assertEqual(self.run_case([], [])['status'], 'complete')
        self.assertEqual(self.run_case([event(radius=0.001)], [])['status'], 'partial_coverage')
        r = self.run_case([event(radius=0.0001)], [])
        self.assertEqual(r['status'], 'complete')
        self.assertGreater(r['uncovered_area_m2'], 0)

    def test_disjoint_nested_and_partial_triple_overlap(self):
        r = self.run_case([event('a', x=-3), event('b', x=3)])
        self.assertAlmostEqual(r['known_area_unique_exposure'], 2 * area())
        self.assertEqual(r['known_area_multiple_exposure'], 0)
        r = self.run_case([event('a', radius=1), event('b', radius=2), event('c', radius=3)])
        self.assertAlmostEqual(r['known_area_unique_exposure'], area(3))
        self.assertAlmostEqual(r['known_area_person_exposures'], area(1) + area(2) + area(3))
        self.assertAlmostEqual(r['known_area_multiple_exposure'], area(2))
        # Two identical unit footprints plus a half-overlapping third: M is exactly the unit footprint.
        r = self.run_case([event('a'), event('b'), event('c', x=1)])
        self.assertAlmostEqual(r['known_area_multiple_exposure'], area())
        self.assertGreater(r['known_area_unique_exposure'], area())
        self.assertLess(r['known_area_unique_exposure'], 2 * area())

    def test_order_reproducibility_time_and_invariants(self):
        events = [event('a', x=-1), event('b'), event('c', radius=2)]
        a = self.run_case(events)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(self.run_case(list(reversed(events))), sort_keys=True))
        self.assertEqual(a, self.run_case(events))
        self.assertLessEqual(0, a['known_area_multiple_exposure'])
        self.assertLessEqual(a['known_area_multiple_exposure'], a['known_area_unique_exposure'] + 1e-9)
        self.assertLessEqual(a['known_area_unique_exposure'], a['known_area_person_exposures'] + 1e-9)
        for e in events: e['time_from_episode_start_s'] = 123
        b = self.run_case(events)
        self.assertEqual(a['known_area_multiple_exposure'], b['known_area_multiple_exposure'])
        self.assertEqual(b['events'][0]['time_from_episode_start_s'], 123)
        previous = 0
        for radius in (0, .1, 1, 2, 5, 15):
            r = self.run_case([event(radius=radius)])
            self.assertGreaterEqual(r['known_area_unique_exposure'] + 1e-9, previous)
            previous = r['known_area_unique_exposure']

    def test_circle_sensitivity(self):
        small = footprint(event(), CalculationSettings(128))
        large = footprint(event(), CalculationSettings(256))
        self.assertEqual(len(small.exterior.coords) - 1, 128)
        self.assertEqual(len(large.exterior.coords) - 1, 256)
        self.assertLess(small.difference(large).area, 1e-12)
        for edges in (128, 256):
            r = self.run_case([event()], edges=edges)
            self.assertAlmostEqual(r['events'][0]['footprint_area_m2'], area(edges=edges))
            self.assertAlmostEqual(r['known_area_unique_exposure'], area(edges=edges))
        self.assertLess((area(edges=256) - area()) / area(), 0.000302)

    def test_invalid_events_no_aggregates(self):
        prepared = prepare_population(population())
        for key, values in {
            'event_id': ['', None, True, [], 3], 'footprint_id': ['', None, {}],
            'center_x_m': [True, float('nan'), float('inf'), '2', None, 10**400],
            'center_y_m': [False, float('-inf')], 'radius_m': [-1, True, float('inf')],
            'time_from_episode_start_s': [-1, None, True, float('nan')],
        }.items():
            for value in values:
                with self.subTest(key=key, value=str(value)):
                    bad = event('bad'); bad[key] = value
                    r = calculate_episode(prepared, episode([event(), bad]))
                    self.assertEqual(r['status'], 'invalid_input')
                    self.assertNotIn('events', r)
                    self.assertNotIn('known_area_unique_exposure', r)
                    self.assertIn(key, r['errors'][0]['field'])
                    json.dumps(r, allow_nan=False)
        for events in ([event(), event()], [event('a', fid='x'), event('b', radius=2, fid='x')], [None]):
            self.assertEqual(calculate_episode(prepared, episode(events))['status'], 'invalid_input')
        for key in ('center_x_m', 'radius_m', 'event_id'):
            e = event(); del e[key]
            self.assertEqual(calculate_episode(prepared, episode([e]))['status'], 'invalid_input')
        self.assertEqual(self.run_case([event(radius=1e308)])['status'], 'invalid_input')

    def test_invalid_episode_identity_and_crs(self):
        prepared = prepare_population(population())
        for key, values in {'episode_id': ['', False], 'population_dataset_id': ['wrong', None],
                            'population_dataset_version': ['wrong'], 'schema_version': ['wrong'],
                            'coordinate_reference_system': [None, 'EPSG:4326', 'EPSG:3857', 'EPSG:2263', 'not-a-crs', True],
                            'events': [None, {}]}.items():
            for value in values:
                e = episode(); e[key] = value
                self.assertEqual(calculate_episode(prepared, e)['status'], 'invalid_input')
        self.assertEqual(calculate_episode(prepared, [])['status'], 'invalid_input')

    def test_invalid_population(self):
        for key, values in {'population': [-1, True, None, float('nan'), float('inf')],
                            'zone_id': ['', None, False, []], 'geometry': [None, {}, {'type': 'Point', 'coordinates': [0, 0]},
                            {'type': 'Polygon', 'coordinates': [[[0,0],[1,1],[0,1],[1,0],[0,0]]]},
                            {'type': 'Polygon', 'coordinates': [[[0,0],[1,0],[2,0],[0,0]]]},
                            {'type': 'Polygon', 'coordinates': [[[False,0],[1,0],[1,1],[False,0]]]},
                            {'type': 'Polygon', 'coordinates': [[[0,0,1],[1,0,1],[1,1,1],[0,0,1]]]}]}.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    p = population(); p['zones'][0][key] = value
                    with self.assertRaises(PECValidationError): prepare_population(p)
        for p in [None, [], {}, population([None]), population([zone('a', (0,0,2,2),1), zone('a',(2,0,3,2),1)]),
                  population([zone('a',(0,0,2,2),1), zone('b',(1.999999,0,3,2),1)])]:
            with self.assertRaises(PECValidationError): prepare_population(p)
        for crs in (None, 'EPSG:4326', 'EPSG:3857', 'EPSG:2263', 'not-a-crs'):
            p = population(); p['coordinate_reference_system'] = crs
            with self.assertRaises(PECValidationError): prepare_population(p)

    def test_polygon_hole_and_multipolygon(self):
        polygon = box(-3,-3,3,3).difference(box(-1,-1,1,1))
        p = population([dict(zone_id='hole', population=32, geometry=mapping(polygon))])
        r = calculate_episode(prepare_population(p), episode([event(radius=.5)]))
        self.assertEqual(r['status'], 'partial_coverage')
        self.assertEqual(r['known_area_unique_exposure'], 0)
        multi = box(-3,-1,-1,1).union(box(1,-1,3,1))
        p['zones'][0]['geometry'] = mapping(multi)
        self.assertEqual(len(prepare_population(p).zones), 1)

    def test_prepared_wkt_adapter_without_real_files(self):
        p = dict(format='population-zones-wkt/1', crs='EPSG:3414', units='metre',
                 axis_order=['easting', 'northing'], metadata=dict(dataset_version='test-version'),
                 coverage_status='partial_coverage', zones=[dict(zone_id='a', population=100,
                     geometry_wkt='POLYGON ((-1 -1, 1 -1, 1 1, -1 1, -1 -1))',
                     pec_eligible=True, exclusion_reasons=[], population_status='known',
                     geometry_status='valid', join_status='matched', dataset_version='test-version',
                     zone_area_m2=999, population_density_people_per_m2=999)])
        prepared = prepare_population(p)
        self.assertEqual(prepared.dataset_id, 'sg-residents-2020-mp2019')
        self.assertEqual(prepared.zones[0]['area'], 4)
        self.assertEqual(prepared.zones[0]['density'], 25)
        for key, value in [('geometry_wkt', 'nonsense'), ('geometry_wkt', 'POINT (0 0)'),
                           ('geometry_wkt', 'POLYGON ((0 0, 1 0, NaN 1, 0 0))'),
                           ('pec_eligible', False), ('exclusion_reasons', ['unknown']),
                           ('population_status', 'qualified_nil_or_negligible'), ('dataset_version', 'wrong')]:
            changed = copy.deepcopy(p); changed['zones'][0][key] = value
            with self.assertRaises(PECValidationError): prepare_population(changed)
        for key, value in [('units', 'foot'), ('axis_order', ['northing', 'easting']), ('metadata', None)]:
            changed = copy.deepcopy(p); changed[key] = value
            with self.assertRaises(PECValidationError): prepare_population(changed)

    def test_canonical_required_fields_and_exclusions(self):
        for key in ('schema_version', 'dataset_id', 'version', 'coordinate_reference_system', 'zones'):
            p = population(); del p[key]
            with self.assertRaises(PECValidationError): prepare_population(p)
        for key, value in [('pec_eligible', False), ('exclusion_reasons', ['population_unknown'])]:
            p = population(); p['zones'][0][key] = value
            with self.assertRaises(PECValidationError): prepare_population(p)
        p = population(); p['zones'][0]['geometry'] = dict(type='Polygon', coordinates=[[[0,0],[1,0],[1,1],[0,1]]])
        with self.assertRaises(PECValidationError): prepare_population(p)

    def test_settings(self):
        for edges in (True, 32, 128.0, 512):
            with self.assertRaises(ValueError): CalculationSettings(edges)
        with self.assertRaises(ValueError): CalculationSettings(128, 1)


if __name__ == '__main__':
    unittest.main()
