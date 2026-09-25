import math
import unittest

from backend.data_sources.consequence import (Estimate, Profile, ProfileError, flags, occupancy_score,
                                 recovery_score, score_profile, service_score, validate)


def est(low, central=None, high=None, unit='x', state='assumption', grade='D', **kw):
    central = low if central is None else central
    high = central if high is None else high
    return Estimate(low, central, high, unit, state, grade, **kw)


def profile(**over):
    base = dict(
        site_id='s1', condition_id='weekday_am_peak', role='road_segment', geometry_wkt='POINT (0 0)',
        occupancy=est(900, 1000, 1100, 'people'),
        beneficiaries_per_hour=est(1000, 2000, 3000, 'people/h'),
        loss_fraction=est(1.0),
        outage_hours=est(6, 12, 24, 'h'),
        alternative_capacity_fraction=est(0.0, 0.2, 0.5),
        recovery_t90_hours=est(6, 12, 24, 'h'),
    )
    base.update(over)
    return Profile(**base)


class SpecExamples(unittest.TestCase):
    def test_occupancy_score_matches_spec_table(self):
        self.assertAlmostEqual(occupancy_score(10), 20.83, places=1)
        self.assertAlmostEqual(occupancy_score(100), 40.09, places=1)
        self.assertAlmostEqual(occupancy_score(1000), 60.0, places=1)
        self.assertAlmostEqual(occupancy_score(10000), 80.0, places=1)
        self.assertEqual(occupancy_score(10 ** 6), 100)

    def test_service_bands(self):
        for hours, score in [(999, 10), (1000, 25), (9999, 25), (10000, 40), (99999, 40),
                             (100000, 60), (999999, 60), (1e6, 80), (9.99e6, 80), (1e7, 100)]:
            self.assertEqual(service_score(hours), score, hours)

    def test_recovery_bands(self):
        for hours, score in [(5, 5), (6, 15), (24, 15), (48, 30), (96, 50), (336, 50),
                             (400, 75), (2160, 75), (3000, 100)]:
            self.assertEqual(recovery_score(hours), score, hours)


class Scoring(unittest.TestCase):
    def test_bounds_are_ordered_and_unknown_vulnerability_widens_h(self):
        scored = score_profile(profile())
        self.assertLessEqual(scored.H.low, scored.H.central)
        self.assertLessEqual(scored.H.central, scored.H.high)
        # V unknown: low/central use V=0, high uses V=100.
        o = occupancy_score(1000)
        self.assertAlmostEqual(scored.H.central, o * 0.6, places=6)
        self.assertGreater(scored.H.high, scored.H.central)

    def test_alternative_capacity_reduces_service_loss(self):
        with_alt = score_profile(profile(alternative_capacity_fraction=est(0.9)))
        without = score_profile(profile(alternative_capacity_fraction=est(0.0)))
        self.assertGreater(without.E.central, with_alt.E.central)
        self.assertLessEqual(with_alt.E.low, with_alt.E.central)
        self.assertLessEqual(with_alt.E.central, with_alt.E.high)

    def test_unavailable_is_never_zero(self):
        p = profile(occupancy=Estimate.unavailable('no key', 'people'))
        scored = score_profile(p)
        self.assertIsNone(scored.H)
        self.assertIsNone(scored.total)
        self.assertFalse(scored.rankable)
        self.assertIn('H', scored.dimensions_missing)

    def test_missing_D_and_X_renormalise_and_are_recorded(self):
        scored = score_profile(profile())
        self.assertIn('D', scored.dimensions_missing)
        self.assertIn('X', scored.dimensions_missing)
        self.assertTrue(scored.rankable)
        h, e, r, a = scored.H.central, scored.E.central, scored.R.central, scored.A.central
        weighted = (0.35 * h + 0.20 * e + 0.05 * r + 0.05 * a) / 0.65
        expected = 0.70 * weighted + 0.30 * max(h, e)
        self.assertAlmostEqual(scored.total.central, expected, places=6)

    def test_hazard_unknown_components_widen_a(self):
        scored = score_profile(profile())
        self.assertEqual(scored.A.central, 0)
        self.assertGreater(scored.A.high, 0)

    def test_flags_are_independent_of_total(self):
        from backend.data_sources.consequence.profile import VULNERABILITY_COMPONENTS
        vulnerable = {k: est(1.0, unit='fraction') for k in VULNERABILITY_COMPONENTS}
        p = profile(occupancy=est(200000), vulnerability=vulnerable, beneficiaries_per_hour=est(1),
                    single_point_of_failure=True)
        scored = score_profile(p)
        got = flags(p, scored)
        self.assertIn('high_human_exposure', got)
        self.assertIn('single_point_of_failure', got)

    def test_flag_table_reports_all_eight_flags_with_unavailable_where_unjudgeable(self):
        from backend.data_sources.consequence import FLAG_NAMES, flag_table
        p = profile()
        table = flag_table(p, score_profile(p))
        self.assertEqual(tuple(table), FLAG_NAMES)
        self.assertEqual(table['minimum_capability_breach'], 'unavailable')
        self.assertEqual(table['mass_vulnerability_condition'], 'unavailable')
        self.assertEqual(table['data_stale'], 'unavailable')
        self.assertIs(table['single_point_of_failure'], False)
        self.assertEqual(flag_table(p, score_profile(p), as_of='2026-09-25')['data_stale'], False)

    def test_uncertainty_high_flag(self):
        p = profile(beneficiaries_per_hour=est(1, 5000, 500000))
        self.assertIn('uncertainty_high', flags(p, score_profile(p)))

    def test_stale_flag_needs_as_of(self):
        p = profile(occupancy=est(1000, source_date='2020-01-01'))
        self.assertNotIn('data_stale', flags(p, score_profile(p)))
        self.assertIn('data_stale', flags(p, score_profile(p), as_of='2026-09-25'))


class Contract(unittest.TestCase):
    def test_valid_profile_is_rankable(self):
        self.assertTrue(validate(profile()))

    def test_unavailable_profile_valid_but_not_rankable(self):
        self.assertFalse(validate(profile(occupancy=Estimate.unavailable('x'))))

    def test_missing_value_without_unavailable_state_rejected(self):
        with self.assertRaises(ProfileError):
            validate(profile(occupancy=Estimate(None, None, None, 'people', 'derived', 'D')))

    def test_unordered_bounds_rejected(self):
        with self.assertRaises(ProfileError):
            validate(profile(occupancy=est(10, 5, 20)))

    def test_bad_grade_and_nan_rejected(self):
        with self.assertRaises(ProfileError):
            validate(profile(occupancy=est(1, grade='Z')))
        with self.assertRaises(ProfileError):
            validate(profile(occupancy=est(math.nan)))

    def test_unavailable_with_values_rejected(self):
        with self.assertRaises(ProfileError):
            validate(profile(occupancy=Estimate(1, 1, 1, 'people', 'unavailable')))


if __name__ == '__main__':
    unittest.main()
