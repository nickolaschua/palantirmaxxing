import unittest

from backend.data_sources.consequence import flag_table, score_profile, validate, veto
from backend.data_sources.consequence.defence import military

SQUARE = 'POLYGON ((0 0, 2000 0, 2000 2000, 0 2000, 0 0))'  # 4 km2 in EPSG:3414 metres


def site(air_base=False, geometry_wkt=SQUARE):
    return military.Site('military-1', 'Test Camp', air_base, geometry_wkt, {'name': 'Test Camp'})


def judged(p):
    return veto(flag_table(p, score_profile(p)), p.priority_asset, p.capability.available)


class AirBases(unittest.TestCase):
    def test_air_base_is_vetoed_as_unassessed_priority_even_when_nearly_empty(self):
        for p in military.military_profiles(site(air_base=True)):
            self.assertTrue(validate(p))
            self.assertTrue(p.priority_asset)
            status, civilian, capability = judged(p)
            self.assertEqual(status, 'vetoed')
            self.assertEqual(civilian, ())
            self.assertEqual(capability, ('priority_asset_capability_not_assessed',))
        night = military.military_profiles(site(air_base=True))[3]
        self.assertLess(score_profile(night).C.central, 1)


class OtherAreas(unittest.TestCase):
    def test_other_military_areas_are_ranked_on_civilian_c(self):
        p = military.military_profiles(site())[1]  # weekday_midday
        self.assertEqual((p.role, p.population_method), ('military_area', 'areal_density'))
        self.assertFalse(p.priority_asset)
        scored = score_profile(p)
        self.assertTrue(scored.rankable)
        self.assertEqual(scored.E.central, 10)  # no attributable civilian service: lowest band by assumption
        self.assertEqual(judged(p)[0], 'unknown')  # D unavailable: never a silent pass
        # generic density x office coefficient x the placeholder circle inside the 4 km2 site
        expected = 500 * 0.85 * p.overlap_area_km2
        self.assertAlmostEqual(p.occupancy.central, expected, places=6)

    def test_density_is_the_same_for_every_site(self):
        big = military.military_profiles(site(geometry_wkt='POLYGON ((0 0, 4000 0, 4000 4000, 0 4000, 0 0))'))[1]
        small = military.military_profiles(site())[1]
        self.assertAlmostEqual(big.occupancy.central / big.overlap_area_km2,
                               small.occupancy.central / small.overlap_area_km2, places=6)


if __name__ == '__main__':
    unittest.main()
