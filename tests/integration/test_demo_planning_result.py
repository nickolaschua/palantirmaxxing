import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from scripts.benchmark_static_mvp import load_inputs, evaluate
from scripts.export_static_mvp_planning_result import present
from scripts.run_mvp_sensitivity import DEMO_SCENARIO, select_middle

ROOT = Path(__file__).resolve().parents[2]
POPULATION = ROOT / 'data/processed/population-projected.json'


@unittest.skipUnless(POPULATION.exists(), 'Pinned local prepared Singapore population is required')
class DemoPlanningResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario, cls.values = load_inputs(DEMO_SCENARIO)
        cls.result = evaluate(cls.values)
        cls.payload = present(cls.result, cls.scenario)

    def test_demo_acceptance_and_preserved_evidence(self):
        p = self.payload
        self.assertEqual(p['schemaVersion'], 'planning-result/1')
        self.assertEqual(len(p['candidates']), 50)
        self.assertEqual(len(p['threat']['samples']), 50)
        self.assertGreaterEqual(p['diagnostics']['reachableCandidates'], 10)
        self.assertLess(p['diagnostics']['reachableCandidates'], 50)
        self.assertTrue(p['paretoCandidateIds'])
        self.assertGreaterEqual(len(p['representativeCandidateIds']), 2)
        self.assertEqual(len(set(p['representativeCandidateIds'])), len(p['representativeCandidateIds']))
        by_id = {c['id']: c for c in p['candidates']}
        self.assertTrue(set(p['paretoCandidateIds']).issubset(by_id))
        self.assertTrue(set(p['categoryAssignments'].values()).issubset(by_id))
        self.assertEqual(set(p['representativeCandidateIds']), set(p['categoryAssignments'].values()))
        mapping = dict(earliest_viable='earliestViable', highest_success='highestSuccess', lowest_exposure='lowestExposure')
        for c in p['candidates']:
            self.assertEqual(c['categories'], [name for name, key in mapping.items() if p['categoryAssignments'][key] == c['id']])
        for original in self.result.candidates:
            candidate = by_id[original.opportunity.opportunity_id]
            self.assertEqual(candidate['suppliedSuccessProbability'], original.supplied_success_probability)
            self.assertEqual(candidate['exposure'], dict(status=original.exposure.exposure_status,
                peoplePotentiallyExposed=original.exposure.people_potentially_exposed,
                knownAreaExposure=original.exposure.known_area_exposure,
                coveredAreaFraction=original.exposure.covered_area_fraction))
            self.assertEqual(candidate['footprint'], dict(id=original.footprint.footprint_id, radiusM=original.footprint.radius_m))
        for candidate_id in p['representativeCandidateIds']:
            self.assertEqual(by_id[candidate_id]['exposure']['status'], 'complete')
        early = by_id[p['categoryAssignments']['earliestViable']]
        low = by_id[p['categoryAssignments']['lowestExposure']]
        self.assertGreater(low['timeFromStartS'], early['timeFromStartS'])
        self.assertLess(low['exposure']['peoplePotentiallyExposed'], early['exposure']['peoplePotentiallyExposed'] * .8)
        json.dumps(p, allow_nan=False)

    def test_all_frontend_positions_inside_actual_canvas(self):
        source = (ROOT / 'frontend/src/lib/types.ts').read_text()
        body = re.search(r'SINGAPORE_BOUNDS: Bounds = \{([^}]+)', source).group(1)
        bounds = {k: float(v) for k, v in re.findall(r'(west|south|east|north):\s*([\d.]+)', body)}
        for p in self.payload['threat']['samples'] + [c['position'] for c in self.payload['candidates']]:
            self.assertTrue(-180 <= p['lon'] <= 180 and -90 <= p['lat'] <= 90)
            self.assertTrue(bounds['west'] < p['lon'] < bounds['east'])
            self.assertTrue(bounds['south'] < p['lat'] < bounds['north'])

    def test_middle_is_computed_dominated_interior_peak(self):
        middle = select_middle(self.result, self.payload)
        self.assertIsNotNone(middle)
        evidence = middle['evidence']
        self.assertTrue(middle['dominatedByCandidateIds'])
        by_id = {c['id']: c for c in self.payload['candidates']}
        early = by_id[self.payload['categoryAssignments']['earliestViable']]
        low = by_id[self.payload['categoryAssignments']['lowestExposure']]
        self.assertLess(early['timeFromStartS'], evidence['timeFromStartS'])
        self.assertLess(evidence['timeFromStartS'], low['timeFromStartS'])
        self.assertGreater(evidence['peoplePotentiallyExposed'], early['exposure']['peoplePotentiallyExposed'])
        self.assertGreater(evidence['peoplePotentiallyExposed'], low['exposure']['peoplePotentiallyExposed'])
        self.assertNotIn(evidence['id'], self.payload['paretoCandidateIds'])
        # Renaming all identities must not change which evidence is selected.
        from dataclasses import replace
        renamed = copy.deepcopy(self.payload)
        for candidate in renamed['candidates']:
            candidate['id'] = 'renamed-' + candidate['id']
        renamed['categoryAssignments'] = {k: 'renamed-' + v for k, v in renamed['categoryAssignments'].items()}
        result = replace(self.result, pareto_evidence=tuple(replace(e, candidate_id='renamed-' + e.candidate_id,
            dominated_by_candidate_ids=tuple('renamed-' + value for value in e.dominated_by_candidate_ids)) for e in self.result.pareto_evidence))
        self.assertEqual(select_middle(result, renamed)['evidence']['id'], 'renamed-' + evidence['id'])

    def test_cli_golden_regeneration_and_identity_guard(self):
        golden = json.loads((ROOT / 'data/results/demo-planning-result.json').read_text())
        self.assertEqual(golden, self.payload)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'demo.json'
            command = [sys.executable, '-B', str(ROOT / 'scripts/export_static_mvp_planning_result.py'),
                       '--scenario', str(DEMO_SCENARIO), '--output', str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            content = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(content, output.read_bytes())
            self.assertEqual(json.loads(content), golden)
            # A drifted population version fails before replacing any artifact.
            from unittest.mock import patch
            with patch('scripts.benchmark_static_mvp.prepare_population', return_value=__import__('dataclasses').replace(self.values[4], version='unexpected')):
                with self.assertRaisesRegex(ValueError, 'pinned scenario identity'):
                    load_inputs(DEMO_SCENARIO)


if __name__ == '__main__':
    unittest.main()
