import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from backend.exposure import prepare_population, calculate_episode, PECValidationError

ROOT = Path(__file__).resolve().parents[2]


class ExposureFileTests(unittest.TestCase):
    def invoke(self, population, episode, output, *extra):
        return subprocess.run([sys.executable, str(ROOT/'scripts/population_exposure.py'),
                               '--population', str(population), '--episode', str(episode), '--output', str(output), *extra],
                              cwd=ROOT, capture_output=True, text=True)

    def test_example_reproducibility_and_errors(self):
        population = ROOT/'tests/fixtures/pec-population.json'
        episode = ROOT/'data/scenarios/pec-example.json'
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'result.json'
            run = self.invoke(population, episode, output)
            self.assertEqual(run.returncode, 0, run.stderr)
            first = output.read_bytes()
            result = json.loads(first)
            self.assertEqual(result['status'], 'complete')
            self.assertAlmostEqual(result['known_area_multiple_exposure'], 0)
            expected = 16 * (128 / 2 * math.sin(2 * math.pi / 128))
            self.assertAlmostEqual(result['unique_people_potentially_exposed'], expected)
            self.assertAlmostEqual(result['total_person_exposures'], expected)
            self.assertEqual(self.invoke(population, episode, output).returncode, 0)
            self.assertEqual(first, output.read_bytes())
            scenario = json.loads(episode.read_text())
            invalid = Path(tmp)/'invalid.json'
            scenario['events'][0]['radius_m'] = -1
            invalid.write_text(json.dumps(scenario))
            self.assertEqual(self.invoke(population, invalid, output).returncode, 2)
            result = json.loads(output.read_text())
            self.assertEqual(result['status'], 'invalid_input')
            self.assertNotIn('events', result)
            for text in ('{"events": NaN}', '{"events": [], "events": []}', 'not JSON'):
                invalid.write_text(text)
                self.assertEqual(self.invoke(population, invalid, output).returncode, 2)
                self.assertEqual(json.loads(output.read_text())['errors'][0]['code'], 'invalid_json')
            scenario['events'][0]['radius_m'] = 100
            invalid.write_text(json.dumps(scenario))
            self.assertEqual(self.invoke(population, invalid, output).returncode, 0)
            self.assertEqual(json.loads(output.read_text())['status'], 'partial_coverage')
            original = population.read_bytes()
            self.assertEqual(self.invoke(population, episode, population).returncode, 2)
            self.assertEqual(population.read_bytes(), original)
            invalid.write_text('{}')
            self.assertEqual(self.invoke(invalid, episode, output).returncode, 2)
            self.assertEqual(json.loads(output.read_text())['status'], 'invalid_input')
            self.assertEqual(self.invoke(Path(tmp)/'missing', episode, output).returncode, 1)

    def test_real_prepared_dataset_offline(self):
        path = ROOT/'data/processed/population-projected.json'
        report_path = ROOT/'data/processed/validation-report.json'
        if not path.exists() or not report_path.exists():
            self.skipTest('Local prepared dataset/report absent; run documented offline population preparation')
        raw = json.loads(path.read_text())
        prepared = prepare_population(raw)
        report = json.loads(report_path.read_text())
        self.assertEqual(len(prepared.zones), report['counts']['eligible'])
        self.assertEqual(sum(z['population'] for z in prepared.zones), report['totals']['eligible_population'])
        excluded = {z['zone_id'] for z in report['excluded']}
        self.assertFalse(excluded.intersection(z['zone_id'] for z in prepared.zones))
        point = prepared.geometries[0].representative_point()
        radius = point.distance(prepared.geometries[0].boundary) / 2
        episode = dict(schema_version='pec-episode/1', episode_id='real-offline', population_dataset_id=prepared.dataset_id,
                       population_dataset_version=prepared.version, coordinate_reference_system='EPSG:3414',
                       events=[dict(event_id='inside', footprint_id='inside', center_x_m=point.x, center_y_m=point.y, radius_m=radius)])
        result = calculate_episode(prepared, episode)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result, calculate_episode(prepared, episode))
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)/'scenario.json'; scenario.write_text(json.dumps(episode))
            output = Path(tmp)/'result.json'
            self.assertEqual(self.invoke(path, scenario, output).returncode, 0)
            self.assertEqual(json.loads(output.read_text()), result)
        for key, value in [('pec_eligible', False), ('exclusion_reasons', ['unknown']), ('population', None),
                           ('dataset_version', 'wrong'), ('population_status', 'qualified_nil_or_negligible')]:
            changed = copy.deepcopy(raw); changed['zones'][0][key] = value
            with self.assertRaises(PECValidationError): prepare_population(changed)


if __name__ == '__main__':
    unittest.main()
