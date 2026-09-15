import copy
from dataclasses import replace
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import re
import unittest

from pyproj import Transformer

from backend.domain import CategoryAssignments
from backend.exposure import prepare_population
from backend.presentation import PresentationSettings, planning_result_to_dict
from backend.presentation.planning_result import _comparison
from scripts.benchmark_static_mvp import DEFAULT_SCENARIO, evaluate, load_inputs
from scripts.export_static_mvp_planning_result import DEFAULT_OUTPUT, present

ROOT = Path(__file__).resolve().parents[2]
CANVAS_BOUNDS = {'west': 103.56, 'south': 1.13, 'east': 104.14, 'north': 1.52}


class PlanningResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario, cls.values = load_inputs(DEFAULT_SCENARIO)
        cls.result = evaluate(cls.values)
        cls.payload = present(cls.result, cls.scenario)

    def test_structure_and_meaningful_trade_space(self):
        p = self.payload
        self.assertEqual(p['schemaVersion'], 'planning-result/1')
        self.assertEqual(p['scenarioId'], self.result.scenario_id)
        self.assertEqual(len(p['candidates']), 50)
        self.assertEqual(len(p['threat']['samples']), 50)
        self.assertEqual(p['diagnostics'], dict(totalCandidates=50, reachableCandidates=36,
                                              eligibleCandidates=36, paretoCandidates=len(p['paretoCandidateIds'])))
        self.assertEqual([c['reachable'] for c in p['candidates']], [False] * 14 + [True] * 36)
        self.assertTrue(p['paretoCandidateIds'])
        self.assertGreaterEqual(len(p['representativeCandidateIds']), 2)
        by_id = {c['id']: c for c in p['candidates']}
        early = by_id[p['categoryAssignments']['earliestViable']]
        low = by_id[p['categoryAssignments']['lowestExposure']]
        self.assertEqual(early['id'], p['categoryAssignments']['highestSuccess'])
        self.assertGreater(low['timeFromStartS'], early['timeFromStartS'])
        self.assertLess(low['suppliedSuccessProbability'], early['suppliedSuccessProbability'])
        self.assertLess(low['exposure']['peoplePotentiallyExposed'],
                        early['exposure']['peoplePotentiallyExposed'] * .5)

    def assert_in_canvas(self, lon, lat):
        self.assertTrue(-180 <= lon <= 180 and -90 <= lat <= 90)
        self.assertTrue(CANVAS_BOUNDS['west'] < lon < CANVAS_BOUNDS['east'])
        self.assertTrue(CANVAS_BOUNDS['south'] < lat < CANVAS_BOUNDS['north'])

    def test_canvas_bounds_and_complete_visible_geometry(self):
        # Read only: catches drift from the actual demo cage without changing TS.
        source = (ROOT / 'frontend/src/lib/types.ts').read_text()
        body = re.search(r'SINGAPORE_BOUNDS: Bounds = \{([^}]+)', source).group(1)
        actual = {k: float(v) for k, v in re.findall(r'(west|south|east|north):\s*([\d.]+)', body)}
        self.assertEqual(actual, CANVAS_BOUNDS)
        for c, sample in zip(self.payload['candidates'], self.payload['threat']['samples']):
            self.assert_in_canvas(c['position']['lon'], c['position']['lat'])
            self.assertEqual(dict(time=c['time'], **c['position']), sample)
        self.assertAlmostEqual(self.payload['threat']['samples'][0]['lon'], 103.85488355427248, places=8)
        self.assertAlmostEqual(self.payload['threat']['samples'][0]['lat'], 1.287583761044758, places=8)
        convert = Transformer.from_crs(3414, 4326, always_xy=True)
        population = json.loads((ROOT / self.scenario['population_fixture']).read_text())
        for zone in population['zones']:
            for x, y in zone['geometry']['coordinates'][0]:
                self.assert_in_canvas(*convert.transform(x, y, errcheck=True))
        for candidate in self.result.candidates:
            footprint = candidate.footprint
            for index in range(64):
                angle = math.tau * index / 64
                self.assert_in_canvas(*convert.transform(
                    footprint.center_x_m + footprint.radius_m * math.cos(angle),
                    footprint.center_y_m + footprint.radius_m * math.sin(angle), errcheck=True))

    def test_absolute_times_and_presentation_settings(self):
        start = datetime.fromisoformat(self.payload['start'].replace('Z', '+00:00'))
        for c in self.payload['candidates']:
            self.assertEqual(datetime.fromisoformat(c['time'].replace('Z', '+00:00')),
                             start + timedelta(seconds=c['timeFromStartS']))
            self.assertTrue(c['time'].endswith('Z'))
            self.assertEqual(c['position']['height'], 1000)
        self.assertEqual(self.payload['end'], self.payload['threat']['samples'][-1]['time'])
        scenario = copy.deepcopy(self.scenario)
        scenario['presentation'] = dict(scenario_start_time='2026-09-15T08:00:00+08:00',
                                        visualization_height_m=2000)
        changed = present(self.result, scenario)
        self.assertEqual(changed['start'], self.payload['start'])
        self.assertEqual(changed['candidates'][0]['position']['height'], 2000)
        for timestamp, height in [('2026-09-15T00:00:00', 1000), ('bad', 1000),
                                  ('2026-09-15T00:00:00Z', float('nan'))]:
            with self.assertRaises(ValueError):
                PresentationSettings(timestamp, height)

    def test_categories_and_pareto_are_backend_assignments(self):
        p = self.payload
        self.assertEqual(p['paretoCandidateIds'], list(self.result.pareto_candidate_ids))
        self.assertEqual(p['representativeCandidateIds'], list(self.result.representative_candidate_ids))
        assignments = p['categoryAssignments']
        mapping = dict(earliest_viable='earliestViable', highest_success='highestSuccess', lowest_exposure='lowestExposure')
        ids = {c['id'] for c in p['candidates']}
        self.assertTrue(set(p['paretoCandidateIds']).issubset(ids))
        self.assertEqual(p['representativeCandidateIds'], list(dict.fromkeys(assignments.values())))
        for c in p['candidates']:
            self.assertEqual(c['categories'], [category for category, key in mapping.items() if assignments[key] == c['id']])
            self.assertEqual(c['paretoEfficient'], c['id'] in p['paretoCandidateIds'])

    def test_evidence_is_preserved_without_fabricated_enrichment(self):
        enriched = {c.opportunity.opportunity_id: c for c in self.result.candidates}
        for c, opportunity in zip(self.payload['candidates'], self.result.candidate_opportunities):
            self.assertEqual(c['requiredTravelTimeS'], opportunity.required_travel_time_s)
            self.assertEqual(c['timeMarginS'], opportunity.time_margin_s)
            if not opportunity.reachable:
                for field in ('suppliedSuccessProbability', 'exposure', 'footprint'):
                    self.assertNotIn(field, c)
                self.assertFalse(c['eligibleForRecommendation'])
                self.assertEqual(c['ineligibilityReasons'], ['unreachable'])
                continue
            original = enriched[c['id']]
            self.assertEqual(c['suppliedSuccessProbability'], original.supplied_success_probability)
            self.assertEqual(c['footprint'], dict(id=original.footprint.footprint_id, radiusM=original.footprint.radius_m))
            self.assertEqual(c['exposure'], dict(status=original.exposure.exposure_status,
                peoplePotentiallyExposed=original.exposure.people_potentially_exposed,
                knownAreaExposure=original.exposure.known_area_exposure,
                coveredAreaFraction=original.exposure.covered_area_fraction))
            self.assertEqual(c['eligibleForRecommendation'], original.eligible)
            self.assertEqual(c['ineligibilityReasons'], list(original.ineligibility_reasons))
        provenance = self.result.population_exposure_provenance
        self.assertEqual(self.payload['populationProvenance'], dict(
            datasetId=provenance['population_dataset_id'], datasetVersion=provenance['population_dataset_version'],
            coordinateReferenceSystem=provenance['coordinate_reference_system'], calculatorVersion=provenance['calculator_version']))

    def test_partial_population_coverage(self):
        population = json.loads((ROOT / self.scenario['population_fixture']).read_text())
        population['zones'].pop()
        values = list(self.values)
        values[4] = prepare_population(population)
        result = evaluate(values)
        payload = present(result, self.scenario)
        originals = {c.opportunity.opportunity_id: c for c in result.candidates}
        partial = [c for c in payload['candidates'] if c.get('exposure', {}).get('status') == 'partial_coverage']
        self.assertTrue(partial)
        for c in partial:
            self.assertIsNone(c['exposure']['peoplePotentiallyExposed'])
            self.assertEqual(c['exposure']['knownAreaExposure'], originals[c['id']].exposure.known_area_exposure)
            self.assertFalse(c['eligibleForRecommendation'])
            self.assertEqual(c['ineligibilityReasons'], ['partial_population_coverage'])
            self.assertNotIn(c['id'], payload['representativeCandidateIds'])
        self.assertTrue(any(c['exposure']['knownAreaExposure'] > 0 for c in partial))

    def test_comparisons_use_unrounded_values(self):
        p = self.payload
        by_id = {c['id']: c for c in p['candidates']}
        self.assertEqual([(c['referenceCandidateId'], c['comparisonCandidateId']) for c in p['comparisons']],
                         [(r, c) for r in p['representativeCandidateIds'] for c in p['representativeCandidateIds'] if r != c])
        for pair in p['comparisons']:
            r, c = by_id[pair['referenceCandidateId']], by_id[pair['comparisonCandidateId']]
            dp = c['suppliedSuccessProbability'] - r['suppliedSuccessProbability']
            de = c['exposure']['peoplePotentiallyExposed'] - r['exposure']['peoplePotentiallyExposed']
            self.assertEqual(pair['deltaTimeS'], c['timeFromStartS'] - r['timeFromStartS'])
            self.assertEqual(pair['deltaSuccessProbability'], dp)
            self.assertEqual(pair['deltaSuccessPercentagePoints'], 100 * dp)
            self.assertEqual(pair['deltaPeoplePotentiallyExposed'], de)
            self.assertEqual(pair['relativeExposureChange'], de / r['exposure']['peoplePotentiallyExposed'])

    def test_comparison_zero_missing_partial_and_nonfinite_semantics(self):
        reference, comparison = copy.deepcopy(self.payload['candidates'][-2:])
        reference['exposure']['peoplePotentiallyExposed'] = 0
        pair = _comparison(reference, comparison)
        self.assertIsNone(pair['relativeExposureChange'])
        self.assertEqual(pair['deltaPeoplePotentiallyExposed'], comparison['exposure']['peoplePotentiallyExposed'])
        for status in ('missing', 'partial_coverage', 'nonfinite'):
            altered = copy.deepcopy(comparison)
            if status == 'missing':
                altered.pop('exposure')
                altered.pop('suppliedSuccessProbability')
            elif status == 'partial_coverage':
                altered['exposure']['status'] = status
                altered['exposure']['peoplePotentiallyExposed'] = None
            else:
                altered['exposure']['peoplePotentiallyExposed'] = float('inf')
            pair = _comparison(reference, altered)
            self.assertIsNone(pair['deltaPeoplePotentiallyExposed'])
            self.assertIsNone(pair['relativeExposureChange'])
            if status == 'missing':
                self.assertIsNone(pair['deltaSuccessProbability'])
                self.assertIsNone(pair['deltaSuccessPercentagePoints'])
            json.dumps(pair, allow_nan=False)

    def test_empty_and_single_representative_results(self):
        values = list(self.values)
        values[0] = replace(values[0], maximum_time_to_go_s=0)
        empty = present(evaluate(values), self.scenario)
        self.assertEqual(empty['start'], empty['end'])
        for field in ('candidates', 'paretoCandidateIds', 'representativeCandidateIds', 'comparisons'):
            self.assertEqual(empty[field], [])
        self.assertTrue(all(value is None for value in empty['categoryAssignments'].values()))
        selected = self.result.representative_candidate_ids[0]
        result = replace(self.result, category_assignments=CategoryAssignments(selected, selected, selected),
                         representative_candidate_ids=(selected,))
        single = present(result, self.scenario)
        self.assertEqual(single['comparisons'], [])
        self.assertEqual(len(next(c for c in single['candidates'] if c['id'] == selected)['categories']), 3)

    def test_translation_preserves_relative_geometry_and_model_evidence(self):
        delta = self.scenario['synthetic_geometry_translation_m']
        original = list(self.values)
        for i in (0, 1):
            original[i] = replace(original[i], position_x_m=original[i].position_x_m - delta['x'],
                                   position_y_m=original[i].position_y_m - delta['y'])
        population = json.loads((ROOT / self.scenario['population_fixture']).read_text())
        for zone in population['zones']:
            for point in zone['geometry']['coordinates'][0]:
                point[0] -= delta['x']
                point[1] -= delta['y']
        original[4] = prepare_population(population)
        result = evaluate(original)
        for before, after in zip(result.candidate_opportunities, self.result.candidate_opportunities):
            self.assertEqual(after.position_x_m - before.position_x_m, delta['x'])
            self.assertEqual(after.position_y_m - before.position_y_m, delta['y'])
            self.assertEqual(after.reachable, before.reachable)
            self.assertAlmostEqual(after.required_travel_time_s, before.required_travel_time_s)
        for before, after in zip(result.candidates, self.result.candidates):
            self.assertEqual(after.supplied_success_probability, before.supplied_success_probability)
            self.assertAlmostEqual(after.exposure.people_potentially_exposed, before.exposure.people_potentially_exposed, places=6)

    def test_golden_artifact_and_determinism(self):
        self.assertEqual(present(self.result, self.scenario), self.payload)
        self.assertEqual(present(evaluate(self.values), self.scenario), self.payload)
        golden = json.loads(DEFAULT_OUTPUT.read_text())
        # Coordinate values may vary at the last decimal between PROJ platforms.
        actual = copy.deepcopy(self.payload)
        for document in (golden, actual):
            points = document['threat']['samples'] + [c['position'] for c in document['candidates']]
            for point in points:
                for axis in ('lon', 'lat'):
                    point[axis] = round(point[axis], 8)
        self.assertEqual(actual, golden)
        self.assertEqual(json.loads(json.dumps(self.payload, allow_nan=False)), self.payload)


if __name__ == '__main__':
    unittest.main()
