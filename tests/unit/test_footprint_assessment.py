"""Contract tests for footprint assessment, using synthetic geography only."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.exposure import prepare_population, calculate_episode, CalculationSettings
from backend.orchestration import footprint_assessment as adapter

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


def request():
    return json.loads((FIXTURES / 'footprint-assessment.json').read_text())


def mapped(req, records=None):
    events = []
    for record in req['records'] if records is None else records:
        event = dict(record['footprint'], event_id=record['record_id'])
        if 'time_from_episode_start_s' in record:
            event['time_from_episode_start_s'] = record['time_from_episode_start_s']
        events.append(event)
    return dict(schema_version='pec-episode/1', episode_id=req['assessment_id'],
                population_dataset_id=req['population_dataset_id'], population_dataset_version=req['population_dataset_version'],
                coordinate_reference_system=req['coordinate_reference_system'], events=events)


def evidence(result):
    result = copy.deepcopy(result)
    result.pop('diagnostics')
    return result


class FootprintAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.population = json.loads((FIXTURES / 'pec-population.json').read_text())
        cls.prepared = prepare_population(cls.population)

    def run_case(self, req=None):
        result = adapter.assess_footprints(self.prepared, request() if req is None else req)
        json.dumps(result, allow_nan=False)
        self.assertGreaterEqual(result['diagnostics']['evaluation_latency_ms'], 0)
        return result

    def assert_invalid(self, req, code=None):
        result = self.run_case(req)
        self.assertEqual(result['status'], 'invalid_input')
        for key in ('records', 'pec_result', 'comparisons', 'summary', 'provenance'):
            self.assertNotIn(key, result)
        if code:
            self.assertIn(code, [e['code'] for e in result['errors']])
        return result

    def test_alternatives_independent_without_cross_record_aggregation(self):
        req = request()
        req['records'][1]['footprint']['center_x_m'] = -4.5
        real = calculate_episode

        def independent(dataset, episode, settings):
            self.assertLessEqual(len(episode['events']), 1)
            return real(dataset, episode, settings)

        with patch.object(adapter, 'calculate_episode', side_effect=independent):
            result = self.run_case(req)
        for record, output in zip(req['records'], result['records']):
            expected = real(self.prepared, mapped(req, [record]), CalculationSettings())
            self.assertEqual(output['exposure'], expected['events'][0])
            self.assertEqual(result['provenance'], expected['metadata'])
        for forbidden in ('unique_people_potentially_exposed', 'total_person_exposures',
                          'people_exposed_to_multiple_events', 'known_area_unique_exposure',
                          'known_area_person_exposures', 'known_area_multiple_exposure', 'pec_result'):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_episode_exact_equivalence(self):
        for scenario in ('complete', 'partial', 'overlapping', 'empty'):
            with self.subTest(scenario=scenario):
                req = request(); req['mode'] = 'episode'; del req['comparisons']
                if scenario == 'partial': req['records'][1]['footprint']['center_x_m'] = 10
                if scenario == 'overlapping': req['records'][1]['footprint']['center_x_m'] = -4.5
                if scenario == 'empty': req['records'] = []
                for i, record in enumerate(req['records']): record['time_from_episode_start_s'] = i
                result = self.run_case(req)
                expected = calculate_episode(self.prepared, mapped(req), CalculationSettings())
                self.assertEqual(result['pec_result'], expected)
                self.assertEqual(result['status'], expected['status'])
                self.assertNotIn('comparisons', result)

    def test_signed_reverse_comparisons_and_ratio(self):
        req = request()
        req['comparisons'].append(dict(reference_record_id='B', comparison_record_id='A'))
        result = self.run_case(req)
        a, b = [r['exposure']['people_potentially_exposed'] for r in result['records']]
        forward, reverse = result['comparisons']
        self.assertEqual(forward['people_exposure_delta'], b-a)
        self.assertGreater(forward['people_exposure_delta'], 0)
        self.assertEqual(reverse['people_exposure_delta'], a-b)
        self.assertEqual(forward['people_exposure_ratio'], b/a)
        self.assertEqual(reverse['people_exposure_ratio'], a/b)
        self.assertEqual(forward['footprint_area_delta_m2'], 0)
        self.assertEqual(forward['reasons'], [])

    def test_identical_footprints(self):
        req = request(); req['records'][1]['footprint'] = copy.deepcopy(req['records'][0]['footprint'])
        pair = self.run_case(req)['comparisons'][0]
        self.assertEqual(pair['people_exposure_delta'], 0)
        self.assertEqual(pair['footprint_area_delta_m2'], 0)
        self.assertEqual(pair['people_exposure_ratio'], 1)

    def test_zero_reference_and_both_zero(self):
        req = request(); req['records'][0]['footprint']['radius_m'] = 0
        for both in (False, True):
            if both: req['records'][1]['footprint']['radius_m'] = 0
            result = self.run_case(req); pair = result['comparisons'][0]
            self.assertTrue(pair['coverage_comparable'])
            self.assertIsNone(pair['people_exposure_ratio'])
            self.assertEqual(pair['reasons'][0]['code'], 'zero_reference_exposure')
            self.assertEqual(pair['people_exposure_delta'], result['records'][1]['exposure']['people_potentially_exposed'])
            self.assertIsNone(result['records'][0]['exposure']['covered_area_fraction'])

    def test_partial_coverage_pairs_and_summary(self):
        for indices in ([0], [1], [0, 1]):
            req = request()
            for i in indices: req['records'][i]['footprint']['center_x_m'] = 10
            result = self.run_case(req); pair = result['comparisons'][0]
            self.assertEqual(result['status'], 'partial_coverage')
            self.assertFalse(pair['coverage_comparable'])
            self.assertIsNone(pair['people_exposure_delta'])
            self.assertIsNone(pair['people_exposure_ratio'])
            self.assertIsNotNone(pair['footprint_area_delta_m2'])
            self.assertEqual(result['summary']['number_partial_coverage'], len(indices))
            self.assertEqual(result['summary']['complete_exposure_range']['count'], 2-len(indices))
            codes = [r['code'] for r in pair['reasons']]
            self.assertEqual(codes, [('reference' if i == 0 else 'comparison') + '_partial_coverage' for i in indices])
            for i in indices:
                self.assertTrue(result['records'][i]['warnings'])
                self.assertIsNone(result['records'][i]['exposure']['people_potentially_exposed'])
            if len(indices) == 2:
                self.assertIsNone(result['summary']['complete_exposure_range']['minimum'])
                self.assertIsNone(result['summary']['complete_exposure_range']['maximum'])

    def test_nonfinite_comparison_defense(self):
        result = self.run_case()
        result['records'][0]['exposure']['people_potentially_exposed'] = 1e-308
        result['records'][1]['exposure']['people_potentially_exposed'] = 1e308
        pair = adapter._build_comparisons(result['records'], request()['comparisons'])[0]
        self.assertIsNone(pair['people_exposure_ratio'])
        self.assertTrue(pair['coverage_comparable'])
        self.assertEqual(pair['reasons'], [dict(code='numeric_range_exceeded', field='people_exposure_ratio',
                                              message='Derived value is outside finite numeric range.')])
        json.dumps(pair, allow_nan=False)

    def test_empty_alternatives(self):
        req = request(); req['records'] = []; req['comparisons'] = []
        result = self.run_case(req)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['records'], [])
        self.assertEqual(result['comparisons'], [])
        self.assertEqual(result['summary'], dict(number_records_supplied=0, number_complete=0,
                         number_partial_coverage=0, complete_exposure_range=dict(count=0, minimum=None, maximum=None)))
        self.assertEqual(result['provenance'], calculate_episode(self.prepared, mapped(req))['metadata'])

    def test_malformed_request(self):
        for req in ({}, [], 'request', False):
            self.assert_invalid(req)
        self.assertEqual(adapter.assess_footprints(self.prepared, None)['status'], 'invalid_input')
        for key, value in [('mode', []), ('records', {}), ('records', [None]), ('geometry_settings', None),
                           ('comparisons', None), ('comparisons', [None])]:
            req = request(); req[key] = value; self.assert_invalid(req)
        req = request(); req['records'][0]['footprint'] = None; self.assert_invalid(req)

    def test_required_fields(self):
        for key in ('schema_version', 'assessment_id', 'mode', 'population_dataset_id',
                    'population_dataset_version', 'coordinate_reference_system', 'records'):
            req = request(); del req[key]; self.assert_invalid(req)
        for key in ('record_id', 'footprint'):
            req = request(); del req['records'][0][key]; self.assert_invalid(req)
        for key in ('footprint_id', 'center_x_m', 'center_y_m', 'radius_m'):
            req = request(); del req['records'][0]['footprint'][key]; self.assert_invalid(req)

    def test_unknown_properties_at_every_level(self):
        for level in ('root', 'record', 'footprint', 'comparison', 'settings'):
            req = request()
            target = {'root':req, 'record':req['records'][0], 'footprint':req['records'][0]['footprint'],
                      'comparison':req['comparisons'][0], 'settings':req['geometry_settings']}[level]
            target['metadata'] = {}
            self.assert_invalid(req, 'unknown_property')

    def test_identity_crs_and_dataset_validation(self):
        for key, values in {'schema_version':['wrong'], 'assessment_id':['', ' ', None, 1],
                            'mode':['wrong', None], 'coordinate_reference_system':['epsg:3414', 'EPSG:4326', None],
                            'population_dataset_id':['wrong', None], 'population_dataset_version':['wrong', None]}.items():
            for value in values:
                req = request(); req[key] = value; self.assert_invalid(req)
        for field in ('record_id',):
            for value in ('', ' ', None, [], True):
                req = request(); req['records'][0][field] = value; self.assert_invalid(req)
        req = request(); req['records'][1]['record_id'] = 'A'; req['comparisons'] = []; self.assert_invalid(req, 'duplicate_identifier')

    def test_footprint_numeric_validation_and_error_paths(self):
        for key, values in {'radius_m':[-1, True, None, '1', float('nan'), float('inf'), 10**400],
                            'center_x_m':[True, None, '1', float('nan'), float('inf'), 10**400],
                            'center_y_m':[False, float('-inf')], 'footprint_id':['', None, []]}.items():
            for value in values:
                req = request(); req['records'][0]['footprint'][key] = value
                result = self.assert_invalid(req)
                self.assertTrue(any(e['field'] == 'records[0].footprint.'+key for e in result['errors']))

    def test_consistent_footprint_ids_required_across_alternatives(self):
        req = request(); req['records'][1]['footprint']['footprint_id'] = 'footprint-A'
        self.assert_invalid(req, 'inconsistent_footprint')

    def test_comparison_validation(self):
        for pair, code in [({}, 'missing_property'),
                           (dict(reference_record_id='A', comparison_record_id='missing'), 'unknown_comparison_record'),
                           (dict(reference_record_id='A', comparison_record_id='A'), 'self_comparison'),
                           (dict(reference_record_id=[], comparison_record_id='B'), 'invalid_identifier')]:
            req = request(); req['comparisons'] = [pair]; self.assert_invalid(req, code)
        req = request(); req['comparisons'] *= 2; self.assert_invalid(req, 'duplicate_comparison')
        req = request(); del req['comparisons']; self.assertEqual(self.run_case(req)['comparisons'], [])

    def test_mode_prohibitions_and_episode_time(self):
        for value in (0, None):
            req = request(); req['records'][0]['time_from_episode_start_s'] = value
            self.assert_invalid(req, 'unknown_property')
        for value in ([], None):
            req = request(); req['mode'] = 'episode'; req['comparisons'] = value
            self.assert_invalid(req, 'prohibited_field')
        for value in (None, -1, True, float('inf')):
            req = request(); req['mode'] = 'episode'; del req['comparisons']
            req['records'][0]['time_from_episode_start_s'] = value
            self.assert_invalid(req, 'invalid_number')

    def test_geometry_settings(self):
        req = request(); del req['geometry_settings']
        self.assertEqual(self.run_case(req)['provenance']['circle_approximation']['edges'], 128)
        req['geometry_settings'] = {'circle_edges':256}
        result = self.run_case(req)
        self.assertEqual(result['provenance']['circle_approximation']['edges'], 256)
        self.assertEqual(result['records'][0]['exposure'], calculate_episode(self.prepared, mapped(req, [req['records'][0]]), CalculationSettings(256))['events'][0])
        for value in (True, 128.0, 64, None, '128'):
            req['geometry_settings'] = {'circle_edges':value}; self.assert_invalid(req, 'invalid_settings')

    def test_pec_numerical_failure_discards_all_records(self):
        for mode in ('alternatives', 'episode'):
            req = request(); req['mode'] = mode
            if mode == 'episode': del req['comparisons']
            req['records'][1]['footprint']['radius_m'] = 1e308
            result = self.assert_invalid(req, 'numerical_range')
            self.assertEqual(result['errors'][0]['field'], 'records[1].footprint')

    def test_validation_precedes_geometry(self):
        req = request(); req['records'][1]['footprint']['radius_m'] = -1
        with patch.object(adapter, 'calculate_episode', side_effect=AssertionError('Geometry called before validation')):
            self.assert_invalid(req)

    def test_determinism_and_provenance_roundtrip(self):
        req = request(); req['comparisons'].append(dict(reference_record_id='B', comparison_record_id='A'))
        first = self.run_case(req)
        req['records'].reverse(); req['comparisons'].reverse()
        self.assertEqual(evidence(first), evidence(self.run_case(req)))
        decoded = json.loads(json.dumps(first, allow_nan=False))
        expected = calculate_episode(self.prepared, mapped(req, [req['records'][0]]))['metadata']
        self.assertEqual(decoded['provenance'], expected)
        for field in ('population_dataset_id', 'population_dataset_version', 'dataset_checksum_sha256',
                      'coordinate_reference_system', 'calculator_version', 'libraries', 'circle_approximation',
                      'numerical_tolerances', 'assumptions'):
            self.assertIn(field, decoded['provenance'])
        self.assertEqual([r['record_id'] for r in decoded['records']], ['A', 'B'])

    def test_partial_reason_determinism_and_no_input_mutation(self):
        req = request()
        for r in req['records']: r['footprint']['center_x_m'] = 10
        before = copy.deepcopy(req)
        zones = copy.deepcopy(self.prepared.zones)
        geometries = tuple(g.wkb for g in self.prepared.geometries)
        first = self.run_case(req)
        self.assertEqual(req, before)
        req['records'].reverse()
        self.assertEqual(evidence(first), evidence(self.run_case(req)))
        self.assertEqual(self.prepared.zones, zones)
        self.assertEqual(tuple(g.wkb for g in self.prepared.geometries), geometries)
        req['records'][0]['footprint']['radius_m'] = -1
        before = copy.deepcopy(req); self.assert_invalid(req); self.assertEqual(req, before)

    def test_coverage_tolerance_is_preserved(self):
        req = request(); req['records'] = [req['records'][0]]; req['comparisons'] = []
        req['records'][0]['footprint'].update(center_x_m=100, radius_m=0.0001)
        result = self.run_case(req)
        self.assertEqual(result['status'], 'complete')
        self.assertGreater(result['records'][0]['exposure']['uncovered_area_m2'], 0)
        self.assertEqual(result['records'][0]['exposure'], calculate_episode(self.prepared, mapped(req))['events'][0])


if __name__ == '__main__':
    unittest.main()
