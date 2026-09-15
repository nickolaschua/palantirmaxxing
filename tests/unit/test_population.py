import copy
import json
from pathlib import Path
import unittest
from shapely.geometry import Polygon, box, mapping
from pyproj import Transformer
from backend.data_sources.population import load_population, parse_hierarchy, parse_value, normalise_name, join_boundaries
from backend.data_sources.geography import area_density, prepare_geometry

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class PopulationTests(unittest.TestCase):
    def test_ordered_hierarchy_with_actual_changi_heading(self):
        rows = [{'Number': n, 'Total_Total': v} for n, v in [('Total','20'), ('Central Water Catchment - Total','-'), ('Central Water Catchment','-'), ('Changi- Total','20'), ('Changi Airport','20')]]
        zones, totals = parse_hierarchy(rows)
        self.assertEqual(zones[-1]['planning_area'], 'Changi')
        self.assertEqual(len(totals), 3)
        self.assertEqual(len(zones), 2)
        self.assertIsNone(zones[0]['population'])

    def test_invalid_hierarchy_is_not_silently_guessed(self):
        for labels in [('Total','Orphan'), ('Total','A - Total','A - Total'), ('Total','A - Total','Total')]:
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                parse_hierarchy([{'Number': n, 'Total_Total':'10'} for n in labels])

    def test_special_values_and_zero(self):
        for raw, result in [('0',(0,'known_zero')), ('1,230',(1230,'known')), ('-',(None,'qualified_nil_or_negligible')), (None,(None,'missing')), ('',(None,'missing')), ('na',(None,'not_available_or_applicable')), ('*',(None,'qualified_uninterpreted')), ('-10',(None,'invalid')), ('1,2',(None,'invalid'))]:
            with self.subTest(raw=raw): self.assertEqual(parse_value(raw),result)

    def test_conservative_names(self):
        self.assertEqual(normalise_name('  ang  mo Kio '),'ANG MO KIO')
        self.assertNotEqual(normalise_name('North-East'),normalise_name('North East'))

    def test_exact_composite_join_and_ambiguity(self):
        rows = load_population(FIXTURES/'population-sample.json')
        zones,_ = parse_hierarchy(rows)
        boundaries = json.loads((FIXTURES/'boundary-sample.geojson').read_text())['features']
        matched,report=join_boundaries(zones,boundaries)
        self.assertTrue(all(status=='matched' for _,status in matched))
        self.assertEqual(report['unmatched_population'],[])
        duplicated = zones + [copy.deepcopy(zones[0])]
        matches, report = join_boundaries(duplicated,boundaries)
        self.assertEqual(len(report['ambiguous_boundaries']),1)
        self.assertTrue(any(row is None and status=='ambiguous' for row,status in matches))
        _, report = join_boundaries(zones,boundaries+[copy.deepcopy(boundaries[0])])
        self.assertEqual(len(report['duplicate_zone_ids']),1)
        self.assertEqual(len(report['ambiguous_boundaries']),2)
        _,report=join_boundaries(zones[1:],boundaries)
        self.assertEqual(len(report['unmatched_boundaries']),1)
        _,report=join_boundaries(zones,boundaries[1:])
        self.assertEqual(len(report['unmatched_population']),1)

    def test_area_density_units_and_projection_origin(self):
        area,density=area_density(box(0,0,1000,1000),2000)
        self.assertEqual(area,1_000_000)
        self.assertEqual(density,.002)
        self.assertEqual(density*1_000_000,2000)
        self.assertIsNone(area_density(box(0,0,1,1),None)[1])
        self.assertEqual(area_density(box(0,0,1,1),0)[1],0)
        with self.assertRaises(ValueError): area_density(Polygon(),1)
        east,north=Transformer.from_crs(4326,3414,always_xy=True).transform(103+50/60,1+22/60)
        self.assertAlmostEqual(east,28001.642,places=4)
        self.assertAlmostEqual(north,38744.572,places=4)

    def test_overlap_and_invalid_geometry_exclusion_without_repair(self):
        shapes=[box(103.80,1.3,103.81,1.31),box(103.805,1.3,103.815,1.31),Polygon([(103.82,1.3),(103.83,1.31),(103.83,1.3),(103.82,1.31),(103.82,1.3)])]
        collection={'type':'FeatureCollection','features':[{'geometry':mapping(g),'properties':{'SUBZONE_C':str(i)}} for i,g in enumerate(shapes)]}
        _,issues,overlaps,report=prepare_geometry(collection)
        self.assertEqual(overlaps,{0,1})
        self.assertTrue(issues[2])
        self.assertEqual(len(report['overlaps']),1)
        self.assertEqual(report['repairs'],[])


if __name__=='__main__': unittest.main()
