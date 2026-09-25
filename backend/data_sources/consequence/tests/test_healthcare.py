from datetime import date, timedelta
import unittest

from backend.data_sources.consequence import flag_table, pipeline, score_profile, validate
from backend.data_sources.consequence.healthcare import hospitals, schools
from backend.data_sources.consequence.conditions import CONDITIONS


A = hospitals.Hospital('A', 'Hospital A', '100000', (900, 1000, 1100), 'https://example.org/a')
B = hospitals.Hospital('B', 'Hospital B', '200000', (450, 500, 550), 'https://example.org/b')
START = date(2024, 1, 1)  # a Monday


def series(value_fn, days=28):
    return {START + timedelta(days=i): value_fn(START + timedelta(days=i)) for i in range(days)}


def stats(bor_a=0.9, bor_b=0.8):
    bor = {'A': series(lambda d: bor_a if d.weekday() < 5 else bor_a - 0.1), 'B': series(lambda d: bor_b)}
    ed = {'A': series(lambda d: 300.0), 'B': series(lambda d: 150.0)}
    return hospitals.build_stats(bor, ed, (A, B), since=START)


def hospital_site(bor_a=0.9, bor_b=0.8, hospital=A):
    return hospitals.Site(hospital, 'POINT (30000 30000)', stats(bor_a, bor_b)[hospital.code],
                   age65_share=(0.45, 0.45, 0.45), ambulance_share=(0.15, 0.19, 0.21))


def hospital_by_condition(profiles):
    return {p.condition_id: p for p in profiles}


class Stats(unittest.TestCase):
    def test_quantiles_split_by_day_type_and_spare_excludes_self(self):
        s = stats()['A']
        self.assertEqual(s['weekday']['bor'], (0.9, 0.9, 0.9))
        self.assertAlmostEqual(s['weekend']['bor'][1], 0.8)
        self.assertEqual((s['weekday']['days'], s['weekend']['days']), (20, 8))
        # spare for A is B's empty beds only: 500 x (1 - 0.8)
        self.assertAlmostEqual(s['weekday']['spare'][1], 100.0)
        self.assertEqual(s['weekend']['last'], '2024-01-28')

    def test_hospital_missing_a_series_is_skipped(self):
        bor = {'A': series(lambda d: 0.9)}
        self.assertEqual(hospitals.build_stats(bor, {}, (A,), since=START), {})

    def test_hospital_not_reporting_contributes_no_spare(self):
        bor = {'A': series(lambda d: 0.9), 'B': series(lambda d: 0.5, days=7)}
        ed = {'A': series(lambda d: 300.0), 'B': series(lambda d: 150.0)}
        spare = hospitals.build_stats(bor, ed, (A, B), since=START)['A']['weekday']['spare']
        self.assertEqual(spare[0], 0.0)  # days after B stops reporting


class Shares(unittest.TestCase):
    def test_age65_share_weights_rates_by_residents(self):
        rates = [dict(year='2024', facility_type_a='Acute', sex=sex, age=age, rate=rate)
                 for sex in ('Male', 'Female') for age, rate in
                 (('0-14 Years', '100'), ('15-64 years', '100'), ('65 years & over', '300'))]
        rates.append(dict(year='2023', facility_type_a='Acute', sex='Male', age='65 years & over', rate='999'))
        census = {'Males_Total': '99', 'Males_0_4': '10', 'Males_15_19': '10', 'Males_90andOver': '10',
                  'Females_0_4': '10', 'Females_15_19': '10', 'Females_65_69': '10'}
        share, year = hospitals.age65_share(rates, census)
        self.assertEqual(year, '2024')
        self.assertAlmostEqual(share, 6000 / 10000)

    def test_ambulance_share_uses_latest_common_year(self):
        ems = [{'DataSeries': '    Emergency Medical Services - Emergency Calls', '2025': '240', '2024': '200'}]
        attendances = [{'DataSeries': 'Accident & Emergency Departments', '2024': '1000', '2023': '900'}]
        share, year = hospitals.ambulance_share(ems, attendances)
        self.assertEqual(year, '2024')
        self.assertEqual(share, tuple(0.2 * c for c in hospitals.AMBULANCE_CONVEYANCE))


class HospitalProfiles(unittest.TestCase):
    def test_one_valid_rankable_profile_per_condition(self):
        profiles = hospitals.hospital_profiles(hospital_site())
        self.assertEqual([p.condition_id for p in profiles], [c.condition_id for c in CONDITIONS])
        for p in profiles:
            self.assertTrue(validate(p))
            self.assertEqual((p.categories, p.role, p.site_id), (('health_emergency',), 'acute_hospital', 'hospital:A'))
            scored = score_profile(p)
            self.assertTrue(scored.rankable)
            self.assertEqual(scored.dimensions_missing, ('D', 'X'))
            for score in (scored.H, scored.E, scored.R, scored.A, scored.total):
                self.assertLessEqual(score.low, score.central)
                self.assertLessEqual(score.central, score.high)

    def test_night_has_fewer_people_but_inpatients_remain(self):
        p = hospital_by_condition(hospitals.hospital_profiles(hospital_site()))
        night, midday = p['weekday_night'], p['weekday_midday']
        self.assertLess(night.occupancy.central, midday.occupancy.central)
        self.assertGreater(night.occupancy.low, 900 * 0.9)  # at least the inpatients
        self.assertGreater(night.vulnerability['medically_dependent'].central,
                           midday.vulnerability['medically_dependent'].central)

    def test_spare_capacity_elsewhere_lowers_service_loss(self):
        crowded = hospital_by_condition(hospitals.hospital_profiles(hospital_site(bor_b=0.99)))['weekday_midday']
        roomy = hospital_by_condition(hospitals.hospital_profiles(hospital_site(bor_b=0.5)))['weekday_midday']
        self.assertLess(crowded.alternative_capacity_fraction.central, roomy.alternative_capacity_fraction.central)
        self.assertGreaterEqual(score_profile(crowded).E.central, score_profile(roomy).E.central)
        self.assertTrue(crowded.single_point_of_failure)

    def test_alternative_capacity_is_capped_at_one(self):
        small = hospital_by_condition(hospitals.hospital_profiles(hospital_site(bor_b=0.1, hospital=A)))['weekday_midday']
        self.assertLessEqual(small.alternative_capacity_fraction.high, 1.0)

    def test_missing_day_type_is_unavailable_not_zero(self):
        s = hospitals.Site(A, 'POINT (0 0)', {'weekday': stats()['A']['weekday']}, (0.45,) * 3, (0.2,) * 3)
        p = hospital_by_condition(hospitals.hospital_profiles(s))
        self.assertFalse(p['weekend_day'].occupancy.available)
        self.assertFalse(validate(p['weekend_day']))
        self.assertTrue(validate(p['weekday_midday']))

    def test_flags_and_staleness_use_latest_observation(self):
        p = hospital_by_condition(hospitals.hospital_profiles(hospital_site()))['weekday_midday']
        self.assertEqual(p.occupancy.source_date, '2024-01-26')
        self.assertTrue(flag_table(p, score_profile(p), as_of='2026-09-25')['data_stale'])
        self.assertFalse(flag_table(p, score_profile(p), as_of='2024-02-01')['data_stale'])
        self.assertIn(flag_table(p, score_profile(p))['mass_vulnerability_condition'], (True, False))


def school_site(**over):
    base = dict(site_id='school:X PRIMARY SCHOOL', name='X PRIMARY SCHOOL', level='Primary',
                geometry_wkt='POINT (30000 30000)', students=1240.0, staff=100.0, primary_share=1.0, year='2024')
    base.update(over)
    return schools.Site(**base)


def school_by_condition(profiles):
    return {p.condition_id: p for p in profiles}


class Levels(unittest.TestCase):
    def test_directory_codes_map_to_moe_level_rows(self):
        self.assertEqual(schools.school_level('PRIMARY'), 'Primary')
        self.assertEqual(schools.school_level('SECONDARY (S1-S5)'), 'Secondary')
        self.assertEqual(schools.school_level('CENTRALISED INSTITUTE'), 'Junior College/Centralised Institute')
        self.assertEqual(schools.school_level('MIXED LEVEL (P1-S4)'), 'Mixed Level')
        self.assertIsNone(schools.school_level('KINDERGARTEN'))
        self.assertEqual(schools.primary_share('MIXED LEVEL (P1-S4)'), 0.6)
        self.assertEqual(schools.primary_share('MIXED LEVEL (S1-JC2)'), 0.0)

    def test_per_school_counts_divide_latest_level_totals(self):
        rows = [dict(year='2024', school='Primary', sex='MF', student_enrolment='1000', no_of_teacher='60',
                     no_of_vice_principal='4', no_of_principal='2', no_of_education_partners='14'),
                dict(year='2024', school='Primary', sex='F', student_enrolment='480'),
                dict(year='2023', school='Primary', sex='MF', student_enrolment='9999'),
                dict(year='2024', school='Secondary', sex='MF', student_enrolment='600')]
        directory = [dict(mainlevel_code='PRIMARY'), dict(mainlevel_code='PRIMARY')]
        counts = schools.per_school_counts(rows, directory)
        self.assertEqual(counts, {'Primary': dict(students=500.0, staff=40.0, schools=2, year='2024')})


class SchoolProfiles(unittest.TestCase):
    def test_one_valid_rankable_profile_per_condition(self):
        profiles = schools.school_profiles(school_site())
        self.assertEqual([p.condition_id for p in profiles], [c.condition_id for c in CONDITIONS])
        for p in profiles:
            self.assertTrue(validate(p))
            self.assertEqual((p.categories, p.role), (('commercial_civic',), 'education_primary'))
            scored = score_profile(p)
            for score in (scored.H, scored.E, scored.R, scored.A, scored.total):
                self.assertLessEqual(score.low, score.central)
                self.assertLessEqual(score.central, score.high)

    def test_school_is_nearly_empty_at_night(self):
        p = school_by_condition(schools.school_profiles(school_site()))
        self.assertLess(p['weekday_night'].occupancy.central, 0.05 * p['weekday_midday'].occupancy.central)
        self.assertLess(score_profile(p['weekday_night']).H.central, score_profile(p['weekday_midday']).H.central)
        self.assertEqual(p['weekday_night'].beneficiaries_per_hour, p['weekday_midday'].beneficiaries_per_hour)

    def test_primary_pupils_raise_vulnerability_over_secondary(self):
        primary = schools.school_profiles(school_site())[1]
        secondary = schools.school_profiles(school_site(level='Secondary', primary_share=0.0))[1]
        self.assertAlmostEqual(primary.vulnerability['age_vulnerable'].central, 1240 / 1340)
        self.assertEqual(secondary.vulnerability['age_vulnerable'].central, 0.0)
        self.assertGreater(score_profile(primary).H.central, score_profile(secondary).H.central)
        self.assertEqual(secondary.role, 'education_secondary')

    def test_unsourced_vulnerability_stays_unavailable(self):
        v = schools.school_profiles(school_site())[0].vulnerability
        for name in ('unable_to_self_evacuate', 'medically_dependent'):
            self.assertFalse(v[name].available)


class TrimRow(unittest.TestCase):
    def test_columns_after_total_status_are_dropped(self):
        row = {'site_id': 'a', 'total_central': 1, 'total_status': 'available', 'D_reason': 'x', 'flags_raised': ''}
        self.assertEqual(list(pipeline.trim_row(row)), ['site_id', 'total_central', 'total_status'])


if __name__ == '__main__':
    unittest.main()
