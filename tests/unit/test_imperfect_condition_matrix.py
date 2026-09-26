import json
from pathlib import Path
import unittest

from backend.domain import (
    CONDITION_ORDER, build_imperfect_condition_matrix,
    validate_imperfect_condition_matrix)


ROOT = Path(__file__).resolve().parents[2]
MATRIX = (ROOT / 'data/imperfect_conditions'
          / 'imperfect-condition-scenario-matrix-v1.json')


class ImperfectConditionMatrixTests(unittest.TestCase):
    def test_checked_matrix_matches_the_deterministic_builder(self):
        checked = json.loads(MATRIX.read_text(encoding='utf-8'))
        self.assertEqual(checked, build_imperfect_condition_matrix())
        validate_imperfect_condition_matrix(checked)

    def test_contains_control_singles_every_pair_and_severe_cases(self):
        rows = build_imperfect_condition_matrix()['rows']
        counts = {group: sum(row['group'] == group for row in rows)
                  for group in {row['group'] for row in rows}}
        self.assertEqual(counts, {
            'control': 1,
            'single': 6,
            'pair': 15,
            'combined-severe': 6,
            'combined-stress': 1,
        })
        singles = {tuple(row['active_conditions']) for row in rows
                   if row['group'] == 'single'}
        self.assertEqual(singles, {(condition,) for condition in CONDITION_ORDER})

    def test_weighted_plan_is_balanced_and_contains_no_expert_labels(self):
        matrix = build_imperfect_condition_matrix()
        self.assertEqual(matrix['sampling_plan']['weighted_slot_count'], 34)
        self.assertEqual(
            set(matrix['sampling_plan']['condition_weighted_incidence'].values()),
            {10})
        self.assertTrue(all(row['expert_label_status'] == 'unlabelled'
                            for row in matrix['rows']))

    def test_building_condition_stays_candidate_local(self):
        rows = build_imperfect_condition_matrix()['rows']
        for row in rows:
            self.assertNotIn('building_path_intersection', row['state_flags'])
            expected = 'building_path_intersection' in row['active_conditions']
            self.assertEqual(
                row['candidate_setup']['building_path_intersection'], expected)


if __name__ == '__main__':
    unittest.main()
