import json
from pathlib import Path
import unittest

from backend.domain import (
    CONDITION_ACTION_FEATURE_ORDER, CONDITION_STATE_FEATURE_ORDER,
    CandidateCondition, ConditionedDemonstration, ExpertConditionLabel,
    ImperfectConditionObservation, explanation_lines)


def fixture():
    conditions = ImperfectConditionObservation(
        heavy_rain=True,
        mist=True,
        strong_wind=True,
        sensor_outage=True,
        communication_delay=True,
        rainfall_rate_mm_h=42.0,
        visibility_m=900.0,
        wind_speed_mps=14.0,
        communication_delay_s=1.2,
        unavailable_sensor_ids=('sensor-b',),
        source_ids=('synthetic-weather-v1',),
    )
    candidates = (
        CandidateCondition(10, 'candidate-clear', False, (), ('building-map-v1',)),
        CandidateCondition(11, 'candidate-blocked', True, ('building-17',),
                           ('building-map-v1',)),
    )
    label = ExpertConditionLabel(
        selected_action_index=10,
        acceptable_action_indices=(10,),
        explanation_codes=(
            'rain_preserved_replanning_margin',
            'mist_widened_track_uncertainty',
            'wind_widened_path_uncertainty',
            'building_path_excluded',
            'sensor_outage_reduced_coverage',
            'communication_delay_preserved_margin',
        ),
        replanning_margin_delta_s=3.5,
    )
    return ConditionedDemonstration(
        'synthetic-episode-1', 0, conditions, candidates, label,
        ('synthetic-weather-v1', 'building-map-v1'))


class ImperfectConditionTests(unittest.TestCase):
    def test_feature_order_is_small_explicit_and_stable(self):
        record = fixture()
        self.assertEqual(CONDITION_STATE_FEATURE_ORDER, (
            'heavy_rain', 'mist', 'strong_wind', 'sensor_outage',
            'communication_delay'))
        self.assertEqual(CONDITION_ACTION_FEATURE_ORDER,
                         ('building_path_intersection',))
        self.assertEqual(record.conditions.feature_vector(), (1, 1, 1, 1, 1))
        self.assertEqual(record.candidates[0].feature_vector(), (0,))
        self.assertEqual(record.candidates[1].feature_vector(), (1,))

    def test_json_round_trip_preserves_contract_and_feature_identity(self):
        record = fixture()
        encoded = json.loads(json.dumps(record.as_dict(), allow_nan=False))
        self.assertEqual(ConditionedDemonstration.from_dict(encoded), record)
        encoded['feature_schema_checksum'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(ValueError, 'schema identity'):
            ConditionedDemonstration.from_dict(encoded)

    def test_checked_example_satisfies_the_runtime_contract(self):
        root = Path(__file__).resolve().parents[2]
        value = json.loads((
            root / 'data/imperfect_conditions'
            / 'imperfect-condition-demonstration-example.json'
        ).read_text(encoding='utf-8'))
        parsed = ConditionedDemonstration.from_dict(value)
        self.assertTrue(parsed.conditions.heavy_rain)
        self.assertEqual(parsed.expert_label.selected_action_index, 10)

    def test_explanations_are_derived_from_validated_observations(self):
        lines = explanation_lines(fixture())
        self.assertEqual(len(lines), 6)
        self.assertIn('Heavy rain', lines[0])
        self.assertTrue(any('mapped buildings' in line for line in lines))
        self.assertTrue(any('1 sensor was unavailable' in line for line in lines))

    def test_reason_cannot_claim_a_condition_that_is_not_present(self):
        record = fixture()
        clear = ImperfectConditionObservation(
            source_ids=('synthetic-weather-v1',))
        with self.assertRaisesRegex(ValueError, 'requires its observed condition'):
            ConditionedDemonstration(
                record.episode_id, record.decision_index, clear,
                record.candidates, record.expert_label, record.source_ids)

    def test_nested_sources_must_be_declared_at_the_top_level(self):
        record = fixture()
        with self.assertRaisesRegex(ValueError, 'nested source IDs'):
            ConditionedDemonstration(
                record.episode_id, record.decision_index, record.conditions,
                record.candidates, record.expert_label,
                ('synthetic-weather-v1',))

    def test_building_reason_requires_an_intersecting_candidate(self):
        record = fixture()
        candidates = (CandidateCondition(
            10, 'candidate-clear', False, (), ('building-map-v1',)),)
        with self.assertRaisesRegex(ValueError, 'intersecting candidate'):
            ConditionedDemonstration(
                record.episode_id, record.decision_index, record.conditions,
                candidates, record.expert_label, record.source_ids)

    def test_building_intersection_is_a_hard_expert_exclusion(self):
        record = fixture()
        label = ExpertConditionLabel(
            11, (11,), ('building_path_excluded',), None)
        with self.assertRaisesRegex(ValueError, 'cannot be acceptable'):
            ConditionedDemonstration(
                record.episode_id, record.decision_index, record.conditions,
                record.candidates, label, record.source_ids)

    def test_margin_wording_requires_measured_expert_label_delta(self):
        record = fixture()
        label = ExpertConditionLabel(
            10, (10,), ('rain_preserved_replanning_margin',), None)
        with self.assertRaisesRegex(ValueError, 'margin explanation'):
            ConditionedDemonstration(
                record.episode_id, record.decision_index, record.conditions,
                record.candidates, label, record.source_ids)


if __name__ == '__main__':
    unittest.main()
