import csv
from pathlib import Path
import tempfile
import unittest

from backend.data_sources.consequence import flag_table, score_profile, validate
from backend.data_sources.consequence.parks_civic import parks_civic

SITE_COLUMNS = ('site_id', 'name', 'category', 'subtype', 'latitude', 'longitude', 'postal_code', 'area_sqm',
                'facility_count', 'source_id', 'source_native_id', 'source_updated', 'data_confidence')
SCENARIO_COLUMNS = ('site_id', 'scenario_id', 'occupancy_low', 'occupancy_central', 'occupancy_high',
                    'estimate_confidence', 'occupancy_method')


def write_tables(folder: Path, sites: list, occupancy: dict) -> None:
    with (folder / 'input_sites.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SITE_COLUMNS, extrasaction='ignore')
        w.writeheader()
        w.writerows(sites)
    with (folder / 'input_conditions.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SCENARIO_COLUMNS)
        w.writeheader()
        for s in sites:
            for sc in parks_civic.SCENARIOS:
                low, central, high = occupancy[s['subtype']]
                w.writerow(dict(site_id=s['site_id'], scenario_id=sc, occupancy_low=low, occupancy_central=central,
                                occupancy_high=high, estimate_confidence='C', occupancy_method='prior'))


def site(site_id, subtype, updated, category='green_recreation'):
    return dict(site_id=site_id, name=site_id, category=category, subtype=subtype, latitude='1.35',
                longitude='103.85', source_id='d_test', source_updated=updated, data_confidence='A')


def load(sites, occupancy):
    with tempfile.TemporaryDirectory() as tmp:
        write_tables(Path(tmp), sites, occupancy)
        return parks_civic.load_sites(Path(tmp))


class Dates(unittest.TestCase):
    def test_timestamp_and_year(self):
        self.assertEqual(parks_civic.iso_date('20260115000106'), '2026-01-15')
        self.assertEqual(parks_civic.iso_date('2024'), '2024-12-31')
        self.assertIsNone(parks_civic.iso_date(''))


class Profiles(unittest.TestCase):
    def test_every_subtype_has_every_assumption(self):
        for table in (parks_civic.LOSS_FRACTION, parks_civic.USE_HOURS_LOST, parks_civic.ALTERNATIVE,
                      parks_civic.RECOVERY_T90_HOURS, parks_civic.OUTDOORS):
            self.assertEqual(set(table), set(parks_civic.LOSS_FRACTION))

    def test_eight_valid_rankable_profiles_projected_to_svy21(self):
        (s,) = load([site('PARK-0001', 'park', '20260115000106')], {'park': (10, 50, 200)})
        profiles = parks_civic.parks_profiles(s)
        self.assertEqual([p.condition_id for p in profiles], list(parks_civic.SCENARIOS))
        self.assertTrue(all(validate(p) for p in profiles))
        x, y = map(float, s.geometry_wkt[7:-1].split())
        self.assertTrue(20000 < x < 50000 and 25000 < y < 50000)  # inside Singapore in SVY21 metres
        scored = score_profile(profiles[0])
        self.assertIsNone(scored.D)
        self.assertIsNone(scored.X)
        self.assertTrue(scored.rankable)

    def test_open_space_never_scores_above_road_recovery_or_school_service(self):
        # a very large crowd still leaves E below school level (40) and R at road level (30)
        occupancy = {sub: (1000, 6000, 15000) for sub in parks_civic.OPEN}
        sites = load([site(f'S{i}', sub, '20260115000106') for i, sub in enumerate(parks_civic.OPEN)], occupancy)
        for s in sites:
            scored = score_profile(parks_civic.parks_profiles(s)[0])
            self.assertLessEqual(scored.E.central, 25, s.subtype)
            self.assertLessEqual(scored.R.central, 30, s.subtype)

    def test_buildings_recover_no_slower_than_housing(self):
        subs = ('community_club', 'library', 'theatre', 'monument')
        sites = load([site(f'B{i}', sub, '20260115000106', 'commercial_civic') for i, sub in enumerate(subs)],
                     {sub: (100, 300, 800) for sub in subs})
        for s in sites:
            self.assertLessEqual(score_profile(parks_civic.parks_profiles(s)[0]).R.central, 75, s.subtype)

    def test_flags_stale_source_and_capability_unavailable(self):
        old, new = load([site('OLD', 'sport_venue', '2024'), site('NEW', 'sport_venue', '20260903000144')],
                        {'sport_venue': (10, 50, 200)})
        for s, stale in ((old, True), (new, False)):
            p = parks_civic.parks_profiles(s)[0]
            table = flag_table(p, score_profile(p), as_of='2026-09-25')
            self.assertEqual(table['data_stale'], stale)
            self.assertEqual(table['minimum_capability_breach'], 'unavailable')
            self.assertFalse(table['mass_vulnerability_condition'])


if __name__ == '__main__':
    unittest.main()
