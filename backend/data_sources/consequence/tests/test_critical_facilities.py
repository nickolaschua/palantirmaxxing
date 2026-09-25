import unittest

import shapely

from backend.data_sources.consequence import score_profile, validate
from backend.data_sources.consequence.critical_sectors import facilities as fa


def box_at(lonlat, half_m=300.0):
    x, y = fa._TO_SVY21.transform(*lonlat)
    return shapely.box(x - half_m, y - half_m, x + half_m, y + half_m)


CHANGI = fa.AIRPORTS['Changi Airport'][0]
PORT = box_at((103.62, 1.29), 800)  # Tuas, far from both airports


def evidence():
    disruption = dict(loss_low='0.42', loss_fraction='0.6', loss_high='0.78', hours_low='6', outage_hours='12',
                      hours_high='24', alt_low='0.05', alternative_capacity_fraction='0.2', alt_high='0.35',
                      R_low='30', R_central='30', R_high='30')
    base = dict(people_low='14400', people_central='24000', people_high='36000')
    def entry(pid, sector, beneficiaries, unit='people served'):
        return {'profile': dict(id=pid, sector=sector, beneficiaries=str(beneficiaries), unit=unit,
                                public_basis='test'), 'disruption': disruption, 'base': base}
    return {'AVI-PAX': entry('AVI-PAX', 'aviation', 191726, 'passenger movements'),
            'ENE-ELEC': entry('ENE-ELEC', 'energy', 6111200),
            'PORT-CONT': entry('PORT-CONT', 'port', 100000, 'TEU'),
            'WAT-DRAIN': entry('WAT-DRAIN', 'water', 6111200)}


def facility(row):
    return fa.Facility(row['site_id'], row['name'], row['profile_id'], row['share'], row['share_basis'],
                       row['geometry'].wkt, {'name': row['name']})


class Building(unittest.TestCase):
    def test_airport_parcels_merge_ports_group_and_air_bases_drop(self):
        changi_a, changi_b = box_at(CHANGI), box_at((CHANGI[0] + 0.01, CHANGI[1]))
        air_base_parcel = box_at((103.72, 1.39))  # e.g. a military airfield parcel
        rows = fa.build_rows([changi_a, changi_b, PORT, air_base_parcel], [], [air_base_parcel.buffer(10)])
        by_id = {r['site_id']: r for r in rows}
        self.assertEqual(set(by_id), {'facility:changi_airport', 'facility:port_1'})
        self.assertEqual(by_id['facility:changi_airport']['parcels'], 2)
        self.assertEqual(by_id['facility:changi_airport']['share'], (1.0, 1.0, 1.0))

    def test_utility_shares_follow_land_area_and_sum_to_one(self):
        rows = fa.build_rows([], [shapely.box(0, 0, 100, 100), shapely.box(500, 0, 800, 100)], [])
        central = sorted(r['share'][1] for r in rows)
        self.assertAlmostEqual(sum(central), 1.0)
        self.assertAlmostEqual(central[1] / central[0], 3.0)
        self.assertTrue(all(r['share_basis'] == 'utility_area_share_assumption' for r in rows))


class Profiles(unittest.TestCase):
    def test_changi_occupancy_comes_from_avi_pax_and_is_areal(self):
        row = fa.build_rows([box_at(CHANGI, 2000)], [], [])[0]
        p = fa.facility_profiles(facility(row), evidence())[1]  # weekday_midday
        self.assertTrue(validate(p))
        self.assertEqual((p.role, p.population_method), ('airport', 'areal_density'))
        area = row['geometry'].area / 1e6
        self.assertAlmostEqual(p.occupancy.central, 24000 * p.overlap_area_km2 / area, places=6)

    def test_utility_uses_energy_evidence_scaled_by_share(self):
        row = fa.build_rows([], [shapely.box(0, 0, 100, 100), shapely.box(500, 0, 600, 100)], [])[0]
        p = fa.facility_profiles(facility(row), evidence())[0]
        self.assertEqual(p.categories, ('energy', 'water'))
        self.assertAlmostEqual(p.loss_fraction.central, 0.5 * 0.6)
        self.assertEqual(p.beneficiaries_per_hour.central, 6111200)
        self.assertEqual(p.recovery_t90_hours.central, 48)
        self.assertTrue(score_profile(p).rankable)

    def test_port_service_is_an_ordinal_assumption(self):
        row = fa.build_rows([PORT], [], [])[0]
        p = fa.facility_profiles(facility(row), evidence())[0]
        self.assertIn('ordinal assumption', p.beneficiaries_per_hour.method)
        self.assertEqual(tuple(score_profile(p).E), (40, 60, 80))

    def test_unsited_profiles_are_reported(self):
        rows = fa.build_rows([box_at(CHANGI)], [shapely.box(0, 0, 10, 10)], [])
        unsited = fa.unsited_profiles([facility(r) for r in rows], evidence())
        self.assertEqual(unsited, ['PORT-CONT', 'WAT-DRAIN'])


if __name__ == '__main__':
    unittest.main()
