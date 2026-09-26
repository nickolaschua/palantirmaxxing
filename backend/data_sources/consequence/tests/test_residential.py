import csv
import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, box

from backend.data_sources.consequence import flags, pipeline, score_profile, validate
from backend.data_sources.consequence.residential import residential
from backend.data_sources.consequence.conditions import CONDITIONS


HEADERS = ['Number', 'Total', 'HDBDwellings_Total', 'HDBDwellings_1_and2_RoomFlats1', 'HDBDwellings_3_RoomFlats',
           'HDBDwellings_4_RoomFlats', 'HDBDwellings_5_RoomandExecutiveFlats', 'CondominiumsandOtherApartments',
           'LandedProperties', 'Others']


def dwelling_row(name, total, g12='-', g3='-', g4='-', g5='-', condo='-', landed='-', others='-'):
    return dict(zip(HEADERS, [name, total, '-', g12, g3, g4, g5, condo, landed, others]))


def age_row(name, total, young='0', old='0'):
    row = {'Number': name, 'Total_Total': total}
    for c in residential.AGE_VULNERABLE_COLUMNS:
        row[c] = '0'
    row['Total_0_4'], row['Total_65_69'] = young, old
    return row


def feature(area_code, area, sub_code, sub):
    return {'properties': dict(PLN_AREA_C=area_code, PLN_AREA_N=area, SUBZONE_C=sub_code, SUBZONE_N=sub)}


FEATURES = [feature('AA', 'Alpha', 'AA01', 'Alpha East'), feature('AA', 'Alpha', 'AA02', 'Alpha West'),
            feature('BB', 'Beta', 'BB01', 'Beta Centre')]
DWELLING = [dwelling_row('Total', '3000'),
            dwelling_row('Alpha - Total', '2300'),
            dwelling_row('Alpha East', '1300', g3='600', g4='400', condo='200', landed='100'),
            dwelling_row('Alpha West', '1000', g4='700', condo='300'),
            dwelling_row('Beta - Total', '700'),
            dwelling_row('Beta Centre', '700', g5='500', others='200')]
AGE = [age_row('Total', '3000'), age_row('Alpha - Total', '2300'),
       age_row('Alpha East', '1300', young='100', old='200'), age_row('Alpha West', '1000', old='50'),
       age_row('Beta - Total', '700'), age_row('Beta Centre', '700', young='7')]


def block(site_id, subzone, year=1990, **units):
    return dict(site_id=site_id, subzone=subzone, year_completed=year,
                units={g: units.get(g, 0) for g in residential.HDB_GROUPS})


class Census(unittest.TestCase):
    def test_dwelling_and_age_are_joined_per_subzone_and_dashes_stay_unknown(self):
        census = residential.census_by_subzone(DWELLING, AGE, FEATURES)
        self.assertEqual(set(census), {'AA01', 'AA02', 'BB01'})
        self.assertEqual(census['AA01']['residents']['hdb_3'], 600)
        self.assertIsNone(census['AA01']['residents']['hdb_1_2'])
        self.assertAlmostEqual(census['AA01']['age_vulnerable_share'], 300 / 1300)
        self.assertAlmostEqual(census['BB01']['age_vulnerable_share'], 7 / 700)

    def test_unknown_age_total_gives_no_share(self):
        age = [dict(r) for r in AGE]
        age[2]['Total_Total'] = '-'
        self.assertIsNone(residential.census_by_subzone(DWELLING, age, FEATURES)['AA01']['age_vulnerable_share'])

    def test_hdb_units_fold_into_census_groups(self):
        record = {'1room_sold': '1', '2room_sold': '2', '1room_rental': '3', 'studio_apartment_sold': '',
                  '3room_sold': '10', '3room_rental': '4', '4room_sold': '5', 'other_room_rental': '1',
                  '5room_sold': '6', 'exec_sold': '7', 'multigen_sold': 'NA'}
        self.assertEqual(residential.parse_units(record), {'hdb_1_2': 6, 'hdb_3': 14, 'hdb_4': 6, 'hdb_5': 13})


class Hdb(unittest.TestCase):
    def setUp(self):
        self.census = residential.census_by_subzone(DWELLING, AGE, FEATURES)

    def test_residents_per_unit_come_from_the_subzone_and_conserve_the_census(self):
        blocks = [block('a', 'AA01', hdb_3=100, hdb_4=50), block('b', 'AA01', hdb_3=200, hdb_4=150)]
        result, remainder = residential.allocate_hdb(blocks, self.census)
        self.assertAlmostEqual(result['a']['residents'], 100 * 2 + 50 * 2)  # 600/300 and 400/200 per unit
        self.assertAlmostEqual(result['a']['residents'] + result['b']['residents'], 1000)
        self.assertEqual(result['a']['method'], 'census_subzone_rate')
        self.assertNotIn('AA01', remainder)  # only subzones with no placed blocks leave a remainder

    def test_block_completed_after_the_census_gets_the_national_rate_as_an_extra(self):
        blocks = [block('old', 'AA01', hdb_3=300), block('old2', 'AA02', hdb_4=350), block('new', 'AA01', 2024, hdb_3=100)]
        result, _ = residential.allocate_hdb(blocks, self.census)
        national_hdb3 = 600 / 300
        self.assertAlmostEqual(result['new']['residents'], 100 * national_hdb3)
        self.assertEqual(result['new']['census_basis'], 0)
        self.assertEqual(result['new']['method'], 'national_rate')
        self.assertAlmostEqual(result['old']['residents'], 600)  # the new block does not dilute the rate

    def test_group_with_units_but_a_census_dash_uses_the_national_rate(self):
        blocks = [block('a', 'AA01', hdb_3=300, hdb_1_2=40), block('b', 'AA02', hdb_4=350)]
        result, _ = residential.allocate_hdb(blocks, self.census)
        self.assertEqual(result['a']['method'], 'census_subzone_rate')  # 1-2 room: no national rate either
        self.assertAlmostEqual(result['a']['residents'], 600)

    def test_census_residents_with_no_placed_units_go_to_the_remainder(self):
        result, remainder = residential.allocate_hdb([block('a', 'AA01', hdb_3=300)], self.census)
        self.assertEqual(remainder, {'AA02': 700, 'BB01': 500, 'AA01': 400})

    def test_reconciliation_is_exact_for_every_placement(self):
        blocks = [block('a', 'AA01', hdb_3=300, hdb_4=200), block('n', 'AA01', 2023, hdb_3=50)]
        parcels = [dict(site_id='p', subzone='AA02', floor_area=1000.0, landed=False),
                   dict(site_id='l', subzone='AA01', floor_area=500.0, landed=True)]
        hdb, hdb_remainder = residential.allocate_hdb(blocks, self.census)
        private, private_remainder = residential.allocate_private(parcels, self.census)
        remainder = {}
        for part in (hdb_remainder, private_remainder):
            for k, v in part.items():
                remainder[k] = remainder.get(k, 0) + v
        report = residential.reconcile(self.census, hdb, private, remainder)
        self.assertEqual(report['census_total'], 600 + 400 + 200 + 100 + 700 + 300 + 500 + 200)
        self.assertAlmostEqual(report['difference'], 0)
        self.assertGreater(report['extra_estimated_national_rate'], 0)


class Private(unittest.TestCase):
    def setUp(self):
        self.census = residential.census_by_subzone(DWELLING, AGE, FEATURES)

    def test_landed_pool_goes_to_landed_parcels_and_condo_pool_to_the_rest(self):
        parcels = [dict(site_id='land', subzone='AA01', floor_area=10.0, landed=True),
                   dict(site_id='c1', subzone='AA01', floor_area=300.0, landed=False),
                   dict(site_id='c2', subzone='AA01', floor_area=100.0, landed=False)]
        residents, remainder = residential.allocate_private(parcels, self.census)
        self.assertAlmostEqual(residents['land'], 100)
        self.assertAlmostEqual(residents['c1'], 150)
        self.assertAlmostEqual(residents['c2'], 50)
        self.assertNotIn('AA01', remainder)

    def test_pool_without_parcels_of_its_own_kind_falls_back_then_to_remainder(self):
        parcels = [dict(site_id='only', subzone='AA01', floor_area=50.0, landed=False)]
        residents, remainder = residential.allocate_private(parcels, self.census)
        self.assertAlmostEqual(residents['only'], 300)  # condo 200 + landed 100 fall back to the only parcel
        self.assertEqual(remainder['BB01'], 200)  # 'Others' with no parcels
        self.assertEqual(remainder['AA02'], 300)

    def test_gpr_interpretation(self):
        self.assertEqual(residential.gpr_value('2.8'), (2.8, 'gpr'))
        self.assertEqual(residential.gpr_value('LND'), (residential.LANDED_GPR, 'landed_assumed'))
        self.assertEqual(residential.gpr_value('EVA'), (residential.UNKNOWN_GPR, 'gpr_unknown_assumed'))


class Spatial(unittest.TestCase):
    def test_points_use_their_subzone_and_boundary_strays_use_the_nearest(self):
        zones = gpd.GeoDataFrame({'SUBZONE_C': ['A', 'B']}, geometry=[box(0, 0, 100, 100), box(100, 0, 200, 100)],
                                 crs='EPSG:3414')
        points = [Point(10, 10), Point(150, 50), Point(100, 50), Point(105, 130), Point(900, 900)]
        self.assertEqual(residential.assign_subzones(points, zones), ['A', 'B', 'A', 'B', None])


def site(**over):
    base = dict(site_id='hdb:1|X RD', role='hdb_block', geometry_wkt='POINT (30000 30000)', residents=600.0,
                method='census_subzone_rate', age_vulnerable_share=0.2, max_floor=16)
    base.update(over)
    return residential.Site(**base)


def by_condition(profiles):
    return {p.condition_id: p for p in profiles}


class Contract(unittest.TestCase):
    def test_one_valid_rankable_profile_per_transport_condition(self):
        profiles = residential.residential_profiles(site())
        self.assertEqual([p.condition_id for p in profiles], [c.condition_id for c in CONDITIONS])
        for p in profiles:
            self.assertTrue(validate(p))
            self.assertEqual(p.categories, ('residential',))
            self.assertTrue(score_profile(p).rankable)

    def test_scores_are_ordered_and_missing_dimensions_are_recorded(self):
        for p in residential.residential_profiles(site()):
            scored = score_profile(p)
            for score in (scored.C, scored.O_display, scored.E, scored.R, scored.A, scored.secondary):
                self.assertLessEqual(score.low, score.central)
                self.assertLessEqual(score.central, score.high)
            self.assertEqual(scored.dimensions_missing, ('D', 'X'))


class Occupancy(unittest.TestCase):
    def test_night_holds_more_people_than_midday_and_bounds_are_wide(self):
        p = by_condition(residential.residential_profiles(site()))
        night, midday = p['weekday_night'].occupancy, p['weekday_midday'].occupancy
        self.assertGreater(night.central, midday.central)
        self.assertAlmostEqual(night.central, 600 * 0.92 * 1.05)
        self.assertLess(night.low, night.central)
        self.assertGreater(night.high, night.central)
        self.assertEqual((night.state, night.grade), ('derived', 'D'))

    def test_residents_band_widens_for_lower_quality_methods(self):
        census = by_condition(residential.residential_profiles(site()))['weekday_night'].beneficiaries_per_hour
        national = by_condition(residential.residential_profiles(site(method='national_rate')))['weekday_night'] \
            .beneficiaries_per_hour
        self.assertGreater(national.high - national.low, census.high - census.low)
        self.assertEqual((census.grade, national.grade), ('C', 'D'))
        self.assertEqual(census.central, 600)


class Vulnerability(unittest.TestCase):
    def test_unavailable_components_widen_h_instead_of_counting_as_zero(self):
        p = by_condition(residential.residential_profiles(site()))['weekday_night']
        self.assertFalse(p.vulnerability['medically_dependent'].available)
        scored = score_profile(p)
        self.assertGreater(scored.C.high, scored.C.central)

    def test_age_share_rises_by_day_and_missing_share_is_unavailable(self):
        day = by_condition(residential.residential_profiles(site()))['weekday_midday'].vulnerability['age_vulnerable']
        self.assertAlmostEqual(day.high, 0.2 / 0.55)
        self.assertEqual((day.low, day.central), (0.2, 0.2))
        none = residential.residential_profiles(site(age_vulnerable_share=None))[0]
        self.assertFalse(none.vulnerability['age_vulnerable'].available)
        self.assertTrue(validate(none))

    def test_tall_blocks_are_harder_to_evacuate_and_private_sites_have_no_floor_data(self):
        tall = residential.residential_profiles(site(max_floor=40))[0].vulnerability['difficult_to_evacuate']
        low = residential.residential_profiles(site(max_floor=10))[0].vulnerability['difficult_to_evacuate']
        self.assertGreater(tall.central, low.central)
        self.assertEqual(low.central, 0.0)
        private = residential.residential_profiles(site(role='private_residential', max_floor=None))[0]
        self.assertFalse(private.vulnerability['difficult_to_evacuate'].available)


class Service(unittest.TestCase):
    def test_shelter_service_scores_and_all_estimates_are_labelled(self):
        p = residential.residential_profiles(site(residents=3000.0))[0]
        scored = score_profile(p)
        self.assertGreater(scored.E.central, 10)  # 3000 x 0.5 x 720 x 0.5 = 540k person-hours -> 60
        self.assertEqual(scored.E.central, 60)
        for name in ('loss_fraction', 'outage_hours', 'alternative_capacity_fraction', 'recovery_t90_hours'):
            e = getattr(p, name)
            self.assertEqual((e.state, e.grade), ('assumption', 'D'))

    def test_hard_flags_survive_and_casualties_are_not_capped(self):
        huge = by_condition(residential.residential_profiles(site(residents=200000.0, role='subzone_remainder',
                                                                  geometry_wkt='POLYGON ((0 0, 1000 0, 1000 1000, 0 1000, 0 0))')))['weekday_night']
        scored = score_profile(huge)
        raised = flags(huge, scored, '2026-09-25')
        self.assertIn('essential_service_floor_breach', raised)
        self.assertIn('high_human_exposure', raised)
        # C is linear in people: no log cap hides a mass-casualty site.
        self.assertAlmostEqual(scored.C.central, huge.occupancy.central * 0.01 * (1 + 3.0 * scored.V.central / 100), places=6)
        self.assertGreaterEqual(scored.C.high, scored.C.central)


ZONES = gpd.GeoDataFrame({'SUBZONE_C': ['AA01', 'AA02', 'BB01']},
                         geometry=[box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000), box(2000, 0, 3000, 1000)],
                         crs=residential.CRS)


def hdb_row(blk, street, year='1990', floor='16', **units):
    row = {'blk_no': blk, 'street': street, 'max_floor_lvl': floor, 'year_completed': year, 'residential': 'Y'}
    row.update({c: '0' for cols in residential.HDB_UNIT_COLUMNS.values() for c in cols})
    row.update({k: str(v) for k, v in units.items()})
    return row


ROWS = [hdb_row('1', 'A RD', **{'3room_sold': 300}), hdb_row('2', 'A RD', **{'4room_sold': 200}),
        hdb_row('3', 'A RD', year='2023', **{'3room_sold': 100}),
        hdb_row('9', 'LOST ST', **{'3room_sold': 50}), dict(hdb_row('10', 'A RD'), residential='N')]
GEOCODE = {'1|A RD': dict(x=100, y=100, postal='100001', address='1 A ROAD'),
           '2|A RD': dict(x=200, y=100, postal='100002', address='2 A ROAD'),
           '3|A RD': dict(x=300, y=100, postal='100003', address='3 A ROAD'), '9|LOST ST': None}
PARCELS = gpd.GeoDataFrame(
    {'OBJECTID': [1, 2, 3, 4], 'LU_DESC': ['RESIDENTIAL'] * 4, 'GPR': ['2.8', '3.5', 'LND', 'LND']},
    geometry=[box(90, 90, 110, 110),  # holds HDB block 1: dropped
              box(1100, 100, 1200, 200),  # condo parcel in AA02
              box(500, 500, 520, 520), box(600, 600, 620, 620)],  # two landed lots in AA01
    crs=residential.CRS)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.census = residential.census_by_subzone(DWELLING, AGE, FEATURES)
        self.blocks, self.misses = residential.hdb_blocks(ROWS, GEOCODE, ZONES)

    def test_blocks_skip_nonresidential_and_report_geocode_misses(self):
        self.assertEqual([b['site_id'] for b in self.blocks], ['hdb:1|A RD', 'hdb:2|A RD', 'hdb:3|A RD'])
        self.assertEqual(self.misses, ['9|LOST ST'])
        self.assertTrue(all(b['subzone'] == 'AA01' for b in self.blocks))

    def test_sites_reconcile_and_cover_every_role(self):
        sites, report = residential.build_sites(self.census, self.blocks, PARCELS, ZONES)
        self.assertAlmostEqual(report['difference'], 0)
        self.assertEqual(report['parcels_dropped_as_hdb'], 1)
        roles = {s.role for s in sites}
        self.assertEqual(roles, {'hdb_block', 'private_residential', 'private_landed', 'subzone_remainder'})
        landed = [s for s in sites if s.role == 'private_landed']
        self.assertEqual(len(landed), 1)  # two lots merged into one site
        self.assertEqual(landed[0].raw['lots'], 2)
        self.assertAlmostEqual(landed[0].residents, 300)  # landed 100 + AA01 condo 200 (no condo parcel: falls back)
        new = next(s for s in sites if s.site_id == 'hdb:3|A RD')
        self.assertEqual(new.method, 'national_rate')
        self.assertGreater(report['extra_estimated_national_rate'], 0)

    def test_write_outputs(self):
        sites, report = residential.build_sites(self.census, self.blocks, PARCELS, ZONES)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pipeline.write_residential(sites, out, {'reconciliation': report})
            with (out / 'residential_output.csv').open(encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            geo = json.loads((out / 'residential_output_sites.geojson').read_text(encoding='utf-8'))
            prov = json.loads((out / 'residential_output_provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows), len(sites) * 6)
        self.assertEqual(list(rows[0])[-1], pipeline.LAST_COLUMN)
        self.assertEqual(len(geo['features']), len(sites))
        self.assertEqual(prov['profile_rows'], len(rows))
        self.assertTrue(all(r['rankable'] == 'True' for r in rows))
        block = {r['condition_id']: r for r in rows if r['site_id'] == 'hdb:1|A RD'}
        self.assertGreater(float(block['weekday_night']['C_central']), float(block['weekday_midday']['C_central']))
        for r in rows:
            self.assertLessEqual(float(r['secondary_low']), float(r['secondary_central']))
            self.assertLessEqual(float(r['secondary_central']), float(r['secondary_high']))


if __name__ == '__main__':
    unittest.main()
