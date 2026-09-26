from collections import Counter
import unittest

from backend.simulation import (
    AUDIT_SEED_START, FROZEN_SPLIT_PROFILES, FROZEN_SPLIT_SEEDS,
    OOD_CADENCE_SEEDS, OOD_GEOGRAPHY_SEEDS, SUITE_MANIFEST_VERSION,
    VALIDATION_SEEDS, frozen_scenario_plan)
from backend.simulation.suites import TRAINING_SEED_OFFSET


class ScenarioSuiteTests(unittest.TestCase):
    def test_v5_plan_has_exact_544_quotas_and_canonical_references(self):
        plan = frozen_scenario_plan()
        self.assertEqual(SUITE_MANIFEST_VERSION, 'rl-scenario-suites/5')
        self.assertEqual(len(plan), 544)
        for split, quotas in FROZEN_SPLIT_PROFILES.items():
            selected = [row for row in plan if row['split'] == split]
            self.assertEqual(Counter(row['profile'] for row in selected),
                             Counter(dict(quotas)))
            self.assertEqual(tuple(row['seed'] for row in selected),
                             FROZEN_SPLIT_SEEDS[split])
            self.assertEqual(
                tuple(row['scenario_ref'] for row in selected),
                tuple('sg2:%s:%06d' % (split, index)
                      for index in range(len(selected))))

    def test_all_seed_partitions_are_disjoint(self):
        partitions = list(FROZEN_SPLIT_SEEDS.items())
        for index, (name, seeds) in enumerate(partitions):
            self.assertEqual(len(seeds), len(set(seeds)), name)
            self.assertTrue(all(seed < TRAINING_SEED_OFFSET for seed in seeds))
            self.assertFalse(set(seeds) & set(range(
                AUDIT_SEED_START, AUDIT_SEED_START + 1000)))
            for other_name, other in partitions[index + 1:]:
                self.assertFalse(set(seeds) & set(other),
                                 (name, other_name))
        self.assertEqual(OOD_GEOGRAPHY_SEEDS, tuple(range(60000, 60064)))
        self.assertEqual(OOD_CADENCE_SEEDS, tuple(range(70000, 70064)))
        self.assertEqual(VALIDATION_SEEDS, tuple(range(10000, 10064)))


if __name__ == '__main__':
    unittest.main()
