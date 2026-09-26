import unittest

import shapely

from backend.data_sources.consequence import ProfileError, expected_casualties, validate
from backend.data_sources.consequence.population_disaggregation import (PLACEHOLDER_FOOTPRINT_RADIUS_M,
                                                                        building_level_occupancy,
                                                                        effective_occupancy_areal_density,
                                                                        placeholder_overlap_km2)
from backend.data_sources.consequence.residential import residential
from backend.data_sources.consequence.tests.test_residential import site

SQUARE_4KM2 = 'POLYGON ((0 0, 2000 0, 2000 2000, 0 2000, 0 0))'


class ArealDensity(unittest.TestCase):
    def test_full_overlap_keeps_the_population(self):
        self.assertEqual(effective_occupancy_areal_density(18850, 4.0, 4.0), 18850)

    def test_partial_overlap_scales_and_lands_below_a_hospital(self):
        # BDSZ05-sized landed site: 18,850 residents, 0.02 km2 of 4 km2 inside the footprint.
        n = effective_occupancy_areal_density(18850, 4.0, 0.02)
        self.assertAlmostEqual(n, 18850 * 0.005)
        # A large acute hospital holds well over 1,000 people by day (SGH has about 1,800 beds).
        self.assertLess(expected_casualties(n, 10, 0.01, 3.0), expected_casualties(1000, 10, 0.01, 3.0))

    def test_zero_overlap_is_zero(self):
        self.assertEqual(effective_occupancy_areal_density(18850, 4.0, 0.0), 0.0)

    def test_non_physical_inputs_raise_instead_of_clamping(self):
        for args in ((100, 4.0, -0.1), (-1, 4.0, 1.0), (100, 0.0, 0.0), (100, -4.0, 0.0), (100, 4.0, 4.5),
                     (100, 4.0, float('nan'))):
            with self.assertRaises(ValueError, msg=args):
                effective_occupancy_areal_density(*args)

    def test_float_overshoot_is_clamped(self):
        self.assertEqual(effective_occupancy_areal_density(100, 4.0, 4.0 * (1 + 1e-12)), 100)

    def test_building_level_is_reserved(self):
        with self.assertRaises(NotImplementedError):
            building_level_occupancy()

    def test_placeholder_circle_uses_the_scenario_radius(self):
        self.assertEqual(PLACEHOLDER_FOOTPRINT_RADIUS_M, 100)
        overlap = placeholder_overlap_km2(shapely.from_wkt(SQUARE_4KM2))
        self.assertAlmostEqual(overlap, 3.14159 * 0.01, places=3)  # the whole 100 m circle fits in the square


class ResidentialRows(unittest.TestCase):
    def test_area_sites_are_scaled_and_tagged(self):
        p = residential.residential_profiles(site(role='private_landed', method='floor_area_share', residents=18850.0,
                                                  geometry_wkt=SQUARE_4KM2, max_floor=None))[0]
        self.assertEqual(p.population_method, 'areal_density')
        self.assertAlmostEqual(p.overlap_area_km2, 0.0314, places=3)
        self.assertAlmostEqual(p.beneficiaries_per_hour.central, 18850 * p.overlap_area_km2 / 4.0, places=6)
        self.assertIn('placeholder footprint', p.beneficiaries_per_hour.method)
        self.assertTrue(validate(p))

    def test_direct_rows_are_unchanged_and_tagged_direct(self):
        p = residential.residential_profiles(site())[0]
        self.assertEqual((p.population_method, p.overlap_area_km2), ('direct', None))
        self.assertEqual(p.beneficiaries_per_hour.central, 600)

    def test_unknown_population_method_is_rejected(self):
        from dataclasses import replace
        p = residential.residential_profiles(site())[0]
        with self.assertRaises(ProfileError):
            validate(replace(p, population_method='guess'))


if __name__ == '__main__':
    unittest.main()
