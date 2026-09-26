import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from backend.exposure import prepare_population
from scripts.benchmark_static_mvp import load_inputs
from scripts.run_mvp_sensitivity import (DEMO_SCENARIO, parameter_grid, evaluate_configuration,
    run_study, summarize_payload, summarize_rows, render_report, render_demo_summary, compare)

ROOT = Path(__file__).resolve().parents[2]


def payload_for_reporting(exposures=(1000, 500), times=(1, 2), shared=False):
    # Reporting-only records: no planner or PEC behavior is simulated here.
    candidates = [dict(id=name, timeFromStartS=time, suppliedSuccessProbability=.95 - index * .01,
                       exposure=dict(status='complete', peoplePotentiallyExposed=exposure))
                  for index, (name, time, exposure) in enumerate(zip(('alpha', 'omega'), times, exposures))]
    return dict(candidates=candidates, categoryAssignments=dict(earliestViable='alpha', highestSuccess='alpha',
                lowestExposure='alpha' if shared else 'omega'),
                representativeCandidateIds=['alpha'] if shared else ['alpha', 'omega'],
                diagnostics=dict(totalCandidates=2, reachableCandidates=2, eligibleCandidates=2, paretoCandidates=1 if shared else 2))


class SensitivityOutcomeTests(unittest.TestCase):
    def test_reporting_threshold_and_noncontrast_reasons(self):
        self.assertTrue(summarize_payload(payload_for_reporting())['meetsExposureContrastThreshold'])
        self.assertEqual(summarize_payload(payload_for_reporting(exposures=(1000, 850)))['outcome'],
                         'exposure_contrast_below_reporting_threshold')
        self.assertEqual(summarize_payload(payload_for_reporting(exposures=(100, 50)))['outcome'],
                         'exposure_contrast_below_reporting_threshold')
        for payload in (payload_for_reporting(exposures=(1000, 1100)), payload_for_reporting(times=(2, 1))):
            self.assertEqual(summarize_payload(payload)['outcome'], 'no_later_lower_exposure_alternative')
        single = summarize_payload(payload_for_reporting(shared=True))
        self.assertEqual(single['outcome'], 'single_representative')
        self.assertIn('no_later_lower_exposure_alternative', single['reasons'])
        self.assertEqual(single['comparison']['deltaPeoplePotentiallyExposed'], 0)
        summary = summarize_rows([single])
        self.assertEqual(summary['validComparisons'], 1)
        self.assertEqual(summary['exposureReductionPercent']['median'], 0)

    def test_zero_reference_and_empty_statistics(self):
        zero = summarize_payload(payload_for_reporting(exposures=(0, 0)))
        self.assertIsNone(zero['comparison']['relativeExposureChange'])
        summary = summarize_rows([zero])
        self.assertEqual(summary['exposureReductionPercent']['count'], 0)
        self.assertIsNone(summary['exposureReductionPercent']['median'])
        self.assertIsNone(summarize_rows([])['suppliedSuccessPenaltyPercentagePoints']['maximum'])
        self.assertIsNone(compare(None, None))


@unittest.skipUnless((ROOT / 'data/processed/population-projected.json').exists(), 'Pinned prepared population is required')
class SensitivityIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario, cls.values = load_inputs(DEMO_SCENARIO)
        cls.study = run_study(cls.scenario, cls.values)

    def test_grid_parameters_and_recorded_counts(self):
        rows = self.study['rows']
        self.assertEqual(len(rows), 45)
        self.assertEqual([r['parameters'] for r in rows], parameter_grid())
        self.assertEqual(len({tuple(r['parameters'].values()) for r in rows}), 45)
        for row in rows:
            self.assertEqual(row['counts']['totalCandidates'], 50)
            self.assertTrue(row['reasons'])
            evidence = row['representativeEvidence']['earliestViable']
            p = row['parameters']
            expected = max(.70, .97 - p['decreasePerSecond'] * evidence['timeFromStartS'])
            self.assertEqual(evidence['suppliedSuccessProbability'], expected)
        self.assertEqual(self.study['summary'], summarize_rows(rows))
        json.dumps(self.study, allow_nan=False)

    def test_deterministic_no_input_mutation_and_generated_reports(self):
        scenario_before = copy.deepcopy(self.scenario)
        states_before = self.values[:4] + self.values[5:]
        geometries_before = tuple(g.wkb for g in self.values[4].geometries)
        zones_before = copy.deepcopy(self.values[4].zones)
        repeated = run_study(self.scenario, self.values)
        self.assertEqual(repeated, self.study)
        self.assertEqual(self.scenario, scenario_before)
        self.assertEqual(self.values[:4] + self.values[5:], states_before)
        self.assertEqual(tuple(g.wkb for g in self.values[4].geometries), geometries_before)
        self.assertEqual(self.values[4].zones, zones_before)
        self.assertEqual(json.loads((ROOT / 'data/results/mvp-sensitivity.json').read_text()), self.study)
        self.assertEqual((ROOT / 'docs/specifications/mvp-sensitivity.md').read_text(), render_report(self.study))
        self.assertEqual((ROOT / 'docs/DEMO_BACKEND_SUMMARY.md').read_text(), render_demo_summary(self.study))

    def test_degenerate_unreachable_ineligible_and_failed_runs(self):
        parameters = parameter_grid()[0]
        no_reachable = list(self.values)
        no_reachable[0] = replace(self.values[0], maximum_time_to_go_s=.001)
        row = evaluate_configuration(self.scenario, tuple(no_reachable), parameters)
        self.assertEqual(row['outcome'], 'no_reachable_candidates')
        self.assertIsNone(row['comparison'])
        no_coverage = list(self.values)
        no_coverage[4] = prepare_population(dict(schema_version='pec-population/1', dataset_id='empty',
                                                version='1', coordinate_reference_system='EPSG:3414', zones=[]))
        row = evaluate_configuration(self.scenario, tuple(no_coverage), parameters)
        self.assertEqual(row['outcome'], 'no_eligible_candidates')
        self.assertIn('partial_population_coverage', row['reasons'])
        self.assertGreater(row['counts']['reachableCandidates'], 0)
        invalid = dict(parameters, footprintRadiusM=-1)
        row = evaluate_configuration(self.scenario, self.values, invalid)
        self.assertEqual(row['outcome'], 'failed_configuration')
        self.assertEqual(row['parameters']['footprintRadiusM'], -1)
        self.assertIsNone(row['counts'])
        self.assertIsNone(row['comparison'])
        self.assertEqual(row, evaluate_configuration(self.scenario, self.values, invalid))
        json.dumps(row, allow_nan=False)

    def test_coverage_reason_can_coexist_with_valid_contrast(self):
        rows = [r for r in self.study['rows'] if 'partial_population_coverage' in r['reasons']]
        self.assertTrue(rows)
        for row in rows:
            self.assertGreater(row['counts']['partialCoverageCandidates'], 0)
            for evidence in row['representativeEvidence'].values():
                if evidence:
                    self.assertEqual(evidence['exposureStatus'], 'complete')
            self.assertEqual(row['counts']['reachableCandidates'] - row['counts']['eligibleCandidates'],
                             row['counts']['partialCoverageCandidates'])


if __name__ == '__main__':
    unittest.main()
