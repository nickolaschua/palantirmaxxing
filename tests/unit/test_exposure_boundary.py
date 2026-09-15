"""Coverage means coverage of the declared calculation polygon, not ideal circle."""
import json
import math
from pathlib import Path
import unittest
from shapely.geometry import Polygon, box, mapping, Point
from shapely.affinity import translate
from backend.exposure import prepare_population, calculate_episode, CalculationSettings
from backend.exposure.calculator import footprint
from scripts.investigate_pec_coverage import InvestigationSettings

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/pec-boundary-gap.json'


def evaluate(coverage, radius=1, edges=128, center=(0,0)):
    dataset=prepare_population(dict(schema_version='pec-population/1',dataset_id='boundary',version='1',
        coordinate_reference_system='EPSG:3414',zones=[dict(zone_id='known',population=coverage.area,geometry=mapping(coverage))]))
    event=dict(event_id='boundary-event',footprint_id='boundary-circle',center_x_m=center[0],center_y_m=center[1],radius_m=radius)
    episode=dict(schema_version='pec-episode/1',episode_id='boundary-test',population_dataset_id='boundary',
                 population_dataset_version='1',coordinate_reference_system='EPSG:3414',events=[event])
    settings=CalculationSettings(edges) if edges in (128,256) else InvestigationSettings(edges)
    result=calculate_episode(dataset,episode,settings)
    return result,footprint(event,settings)


class BoundaryTests(unittest.TestCase):
    def assert_semantics(self,result,polygon,coverage):
        event=result['events'][0]
        missing=polygon.difference(coverage).area
        self.assertAlmostEqual(event['footprint_area_m2'],polygon.area,places=9)
        self.assertAlmostEqual(event['uncovered_area_m2'],missing,places=9)
        self.assertAlmostEqual(event['known_area_exposure'],polygon.intersection(coverage).area,places=9)
        expected='partial_coverage' if missing > 1e-6 else 'complete'
        self.assertEqual(event['status'],expected)
        self.assertEqual(result['status'],expected)
        self.assertEqual(result['metadata']['numerical_tolerances']['coverage_area_m2'],1e-6)
        if expected=='partial_coverage':
            self.assertIsNone(event['people_potentially_exposed'])
            self.assertIsNone(result['unique_people_potentially_exposed'])
        else:
            self.assertEqual(event['people_potentially_exposed'],event['known_area_exposure'])

    def test_circle_strictly_inside(self):
        for n in (64,128,256,512,1024):
            coverage=box(-2,-2,2,2)
            result,polygon=evaluate(coverage,edges=n)
            self.assert_semantics(result,polygon,coverage)
            self.assertEqual(result['events'][0]['uncovered_area_m2'],0)

    def test_touching_straight_boundary(self):
        for n in (128,256):
            coverage=box(-2,-2,1,2)
            result,polygon=evaluate(coverage,edges=n)
            self.assert_semantics(result,polygon,coverage)
            self.assertTrue(polygon.boundary.intersects(coverage.boundary))
            self.assertEqual(result['status'],'complete')

    def test_slightly_beyond_straight_boundary(self):
        for n in (128,256):
            coverage=box(-2,-2,.999,2)
            result,polygon=evaluate(coverage,edges=n)
            self.assert_semantics(result,polygon,coverage)
            self.assertGreater(result['events'][0]['uncovered_area_m2'],1e-6)
            self.assertEqual(result['status'],'partial_coverage')

    def test_small_internal_gap_known_answer(self):
        coverage=box(-2,-2,2,2).difference(box(-.05,-.05,.05,.05))
        for n in (128,256):
            result,polygon=evaluate(coverage,edges=n)
            self.assert_semantics(result,polygon,coverage)
            self.assertAlmostEqual(result['events'][0]['uncovered_area_m2'],.01,places=12)
            self.assertAlmostEqual(result['events'][0]['known_area_exposure'],polygon.area-.01,places=12)

    def test_gap_between_chord_and_circle_explains_status_change(self):
        fixture=json.loads(FIXTURE.read_text())
        gap=Polygon(fixture['gap_ring']); coverage=box(*fixture['outer_bounds_m']).difference(gap)
        radius=fixture['circle_radius_m']; apex=Point(fixture['gap_ring'][0])
        # Analytic explanation: apex lies beyond the 128-edge chord, inside
        # radius R; its angular midpoint is a new vertex direction at 256.
        self.assertGreater(apex.distance(Point(0,0)),radius*math.cos(math.pi/128))
        self.assertLess(apex.distance(Point(0,0)),radius)
        previous=None
        for n in (64,128,256,512,1024):
            result,polygon=evaluate(coverage,radius,n)
            self.assert_semantics(result,polygon,coverage)
            self.assertEqual(result['status'],'complete' if n<=128 else 'partial_coverage')
            if previous is not None:
                self.assertLess(previous.difference(polygon).area,1e-10)
            if n==128:
                self.assertFalse(polygon.intersects(gap))
            if n>=256:
                self.assertTrue(apex.within(polygon))
                self.assertGreater(polygon.intersection(gap).area,1e-6)
            previous=polygon
        # The same interpretation survives moving the synthetic geometry to
        # Singapore-scale projected coordinates; it is not an origin artefact.
        shifted=translate(coverage,xoff=30000,yoff=35000)
        for n in (128,256):
            original,_=evaluate(coverage,radius,n)
            moved,_=evaluate(shifted,radius,n,(30000,35000))
            self.assertEqual(original['status'],moved['status'])
            self.assertAlmostEqual(original['events'][0]['uncovered_area_m2'],moved['events'][0]['uncovered_area_m2'],places=9)

    def test_diagnostic_resolutions_do_not_change_public_policy(self):
        self.assertEqual(CalculationSettings().circle_edges,128)
        for n in (64,512,1024):
            with self.assertRaises(ValueError): CalculationSettings(n)
        with self.assertRaises(ValueError): InvestigationSettings(128,1e-3)


if __name__=='__main__':
    unittest.main()
