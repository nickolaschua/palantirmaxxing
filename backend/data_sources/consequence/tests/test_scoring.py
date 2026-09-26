import math
import unittest

from backend.data_sources.consequence import (POLICY_DEMO_V2, Estimate, Profile, ProfileError, expected_casualties,
                                 flag_table, flags, occupancy_score, rank_sites, recovery_score, score_profile,
                                 service_score, validate, veto)


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
    def test_bounds_are_ordered_and_unknown_vulnerability_widens_c(self):
        scored = score_profile(profile())
        self.assertLessEqual(scored.C.low, scored.C.central)
        self.assertLessEqual(scored.C.central, scored.C.high)
        # V unknown: low/central use V=0, high uses V=100.
        self.assertAlmostEqual(scored.C.central, 1000 * 0.01, places=6)
        self.assertAlmostEqual(scored.C.high, 1100 * 0.01 * (1 + 3.0), places=6)
        self.assertAlmostEqual(scored.O_display.central, occupancy_score(scored.C.central), places=6)

    def test_casualties_are_linear_in_people_and_rise_with_vulnerability(self):
        one = score_profile(profile(occupancy=est(1000))).C.central
        two = score_profile(profile(occupancy=est(2000))).C.central
        self.assertAlmostEqual(two, 2 * one, places=9)
        self.assertAlmostEqual(expected_casualties(1000, 50, 0.01, 3.0), 25.0)
        self.assertGreater(expected_casualties(1000, 100, 0.01, 3.0), expected_casualties(1000, 0, 0.01, 3.0))

    def test_alternative_capacity_reduces_service_loss(self):
        with_alt = score_profile(profile(alternative_capacity_fraction=est(0.9)))
        without = score_profile(profile(alternative_capacity_fraction=est(0.0)))
        self.assertGreater(without.E.central, with_alt.E.central)
        self.assertLessEqual(with_alt.E.low, with_alt.E.central)
        self.assertLessEqual(with_alt.E.central, with_alt.E.high)

    def test_unavailable_is_never_zero(self):
        p = profile(occupancy=Estimate.unavailable('no key', 'people'))
        scored = score_profile(p)
        self.assertIsNone(scored.C)
        self.assertIsNone(scored.O_display)
        self.assertIsNone(scored.secondary)
        self.assertFalse(scored.rankable)
        self.assertIn('C', scored.dimensions_missing)

    def test_missing_D_and_X_renormalise_and_are_recorded(self):
        scored = score_profile(profile())
        self.assertIn('D', scored.dimensions_missing)
        self.assertIn('X', scored.dimensions_missing)
        self.assertTrue(scored.rankable)
        e, r, a = scored.E.central, scored.R.central, scored.A.central
        expected = (0.30 * e + 0.10 * r + 0.05 * a) / 0.45
        self.assertAlmostEqual(scored.secondary.central, expected, places=6)

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

    def test_priority_asset_flag_is_declared_and_survives_a_low_score(self):
        p = profile(priority_asset=True, role='military_airbase', categories=('defence_security', 'aviation'))
        got = flags(p, score_profile(p))
        self.assertIn('priority_asset', got)
        self.assertNotIn('priority_asset', flags(profile(), score_profile(profile())))

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



class VetoThenRank(unittest.TestCase):
    def test_high_casualties_veto_and_essential_sites_trip_at_a_lower_magnitude(self):
        ordinary = profile(occupancy=est(700), categories=('residential',))
        hospital = profile(occupancy=est(700), categories=('health_emergency',))
        self.assertNotIn('high_human_exposure', flags(ordinary, score_profile(ordinary)))  # C = 7 < 10
        self.assertIn('high_human_exposure', flags(hospital, score_profile(hospital)))  # C = 7 >= 5
        small = profile(occupancy=est(10), categories=('health_emergency',))
        self.assertNotIn('high_human_exposure', flags(small, score_profile(small)))  # category alone never trips

    def test_veto_separates_civilian_and_capability_reasons_and_unavailable_is_unknown(self):
        table = dict(high_human_exposure=True, essential_service_floor_breach=False,
                     minimum_capability_breach=True)
        self.assertEqual(veto(table), ('vetoed', ('high_human_exposure',), ('minimum_capability_breach',)))
        table = dict(high_human_exposure=False, essential_service_floor_breach=False,
                     minimum_capability_breach='unavailable')
        self.assertEqual(veto(table), ('unknown', (), ()))
        table['minimum_capability_breach'] = False
        self.assertEqual(veto(table)[0], 'pass')
        p = profile(occupancy=est(100))
        self.assertEqual(veto(flag_table(p, score_profile(p)))[0], 'unknown')  # no D: never a silent pass

    def test_unassessed_priority_asset_is_vetoed_until_an_authorised_d_arrives(self):
        table = dict(high_human_exposure=False, essential_service_floor_breach=False,
                     minimum_capability_breach='unavailable')
        self.assertEqual(veto(table, priority_asset=True, capability_available=False),
                         ('vetoed', (), ('priority_asset_capability_not_assessed',)))
        table['minimum_capability_breach'] = False
        self.assertEqual(veto(table, priority_asset=True, capability_available=True)[0], 'pass')

    def test_lower_casualties_win_and_secondary_breaks_ties_inside_the_band(self):
        rows = [dict(id='a', C_central=10.0, secondary_central=50, veto_status='pass'),
                dict(id='b', C_central=10.5, secondary_central=20, veto_status='unknown'),
                dict(id='c', C_central=30.0, secondary_central=1, veto_status='pass'),
                dict(id='d', C_central=1.0, secondary_central=99, veto_status='vetoed'),
                dict(id='e', C_central='', secondary_central='', veto_status='unknown')]
        ranked = rank_sites(rows)
        self.assertEqual([r['id'] for r in ranked], ['b', 'a', 'c', 'd', 'e'])
        self.assertEqual([r['rank'] for r in ranked], [1, 2, 3, 4, 5])

    def test_all_vetoed_still_returns_an_ordered_list(self):
        rows = [dict(id=i, C_central=c, secondary_central=0, veto_status='vetoed') for i, c in (('x', 50), ('y', 20))]
        self.assertEqual([r['id'] for r in rank_sites(rows)], ['y', 'x'])

    def test_ranking_does_not_depend_on_p_base(self):
        people = (100, 5000, 800, 2400, 60)

        def order(p_base):
            policy = dict(POLICY_DEMO_V2, p_base=p_base, tie_floor=0)
            rows = []
            for i, n in enumerate(people):
                s = score_profile(profile(occupancy=est(n)), policy)
                rows.append(dict(id=i, C_central=s.C.central, secondary_central=s.secondary.central,
                                 veto_status='pass'))
            return [r['id'] for r in rank_sites(rows, policy)]
        self.assertEqual(order(0.01), order(0.2))

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
