"""Structured imitation feature, loss, batching, and policy regression tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

try:
    import gymnasium  # noqa: F401
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, 'requires backend/learning/requirements-rl.txt')
class ImitationLearningTests(unittest.TestCase):
    def setUp(self):
        from backend.learning import CentralizedInterceptionEnv
        from backend.simulation import DeterministicToyProvider, SeededScenarioGenerator
        self.env = CentralizedInterceptionEnv(
            DeterministicToyProvider(),
            episode_spec=SeededScenarioGenerator(
                max_threats=1, max_interceptors=1,
                candidate_count=2).generate(
                    17, threat_count=1, interceptor_count=1))
        self.observation, _ = self.env.reset()

    def tearDown(self):
        self.env.close()

    def test_action_feature_types_and_widths(self):
        from backend.learning import (ACTION_FEATURE_COUNT, ADVANCE_ACTION,
                                      extract_action_features,
                                      extract_state_features)
        assignment = int(np.flatnonzero(
            self.env.action_masks()[:ADVANCE_ACTION])[0])
        assigned = extract_action_features(self.observation, assignment)
        advance = extract_action_features(self.observation, ADVANCE_ACTION)
        self.assertEqual(extract_state_features(self.observation).shape, (24,))
        self.assertEqual(assigned.shape, (ACTION_FEATURE_COUNT,))
        np.testing.assert_array_equal(assigned[-3:], (1, 0, 0))
        np.testing.assert_array_equal(advance[-3:], (0, 0, 1))
        self.env.step(assignment)
        self.env.engine.modified_threats.clear()
        cancel = self.env.cancel_action(0)
        cancelled = extract_action_features(self.env._observation(), cancel)
        np.testing.assert_array_equal(cancelled[-3:], (0, 1, 0))

    def test_set_valued_loss_counts_probability_mass(self):
        from backend.learning import set_valued_masked_cross_entropy
        logits = torch.tensor([0.0, 0.0, 2.0, 0.0, 0.0])
        offsets = torch.tensor([0, 2, 5])
        targets = torch.tensor([True, True, False, True, True])
        loss = set_valued_masked_cross_entropy(logits, offsets, targets)
        expected = (0.0 + (torch.logsumexp(logits[2:], 0)
                           - torch.logsumexp(logits[3:], 0))) / 2
        self.assertTrue(torch.allclose(loss, expected))

    def test_scorer_is_permutation_equivariant(self):
        from backend.learning import StructuredActionScorer
        torch.manual_seed(2)
        model = StructuredActionScorer()
        state = torch.randn(1, 24)
        actions = torch.randn(7, 44)
        offsets = torch.tensor([0, 7])
        permutation = torch.tensor([4, 0, 6, 2, 1, 5, 3])
        original = model(state, actions, offsets)
        permuted = model(state, actions[permutation], offsets)
        self.assertTrue(torch.allclose(
            permuted, original[permutation], atol=1e-6, rtol=1e-6))

    def test_family_split_is_grouped_and_deterministic(self):
        from backend.learning import deterministic_family_split
        families = ['a', 'b', 'a', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
        first = deterministic_family_split(families, seed=7)
        second = deterministic_family_split(tuple(reversed(families)), seed=7)
        self.assertEqual(first, second)
        self.assertEqual(set(first.values()), {'training', 'internal-validation'})

    def test_masked_policy_never_returns_an_invalid_action(self):
        from backend.learning import (ACTION_FEATURE_COUNT, STATE_FEATURE_COUNT,
                                      StructuredActionScorer,
                                      StructuredImitationPolicy)
        model = StructuredActionScorer()
        statistics = {
            'state_mean': np.zeros(STATE_FEATURE_COUNT, dtype=np.float32),
            'state_std': np.ones(STATE_FEATURE_COUNT, dtype=np.float32),
            'action_mean': np.zeros(ACTION_FEATURE_COUNT - 3, dtype=np.float32),
            'action_std': np.ones(ACTION_FEATURE_COUNT - 3, dtype=np.float32),
        }
        policy = StructuredImitationPolicy(model, statistics, 'test')
        mask = self.env.action_masks().astype(bool)
        action, state = policy.predict(self.observation, action_masks=mask)
        self.assertIsNone(state)
        self.assertTrue(mask[action])

    def test_residual_expert_cancels_an_inconsistent_tentative_assignment(self):
        from backend.learning import (ADVANCE_ACTION, ASSIGNMENT_ACTIONS,
                                      PrivilegedResidualExpert)
        from backend.simulation import (DeterministicToyProvider,
                                        SeededScenarioGenerator)
        env = self.env.__class__(
            DeterministicToyProvider(),
            episode_spec=SeededScenarioGenerator(
                max_threats=2, max_interceptors=2,
                candidate_count=3).generate(
                    29, threat_count=2, interceptor_count=2))
        try:
            env.reset()
            expert = PrivilegedResidualExpert()
            optimal = set(expert.acceptable_actions(env))
            wrong = next(action for action in np.flatnonzero(env.action_masks())
                         if action < ASSIGNMENT_ACTIONS and action not in optimal)
            env.step(int(wrong))
            # Cancellation becomes legal after an event epoch; clearing this
            # per-epoch guard isolates the residual-label behavior here.
            env.engine.modified_threats.clear()
            env._invalidate_state_cache()
            actions = expert.acceptable_actions(env)
            self.assertEqual(actions, (env.cancel_action(0),))
            self.assertLess(actions[0], ADVANCE_ACTION)
        finally:
            env.close()

    def test_residual_expert_replays_to_exact_terminal_score(self):
        from backend.learning import PrivilegedResidualExpert
        from backend.simulation import (DeterministicToyProvider,
                                        OptimalFixedRankAssignmentPolicy,
                                        SeededScenarioGenerator, SimulationEngine)
        spec = SeededScenarioGenerator(
            max_threats=2, max_interceptors=2,
            candidate_count=3).generate(
                12, threat_count=2, interceptor_count=2)
        teacher = OptimalFixedRankAssignmentPolicy().run(
            SimulationEngine(spec, DeterministicToyProvider()))
        env = self.env.__class__(DeterministicToyProvider(), episode_spec=spec)
        try:
            env.reset()
            expert = PrivilegedResidualExpert()
            while True:
                action = min(expert.acceptable_actions(env))
                _, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    break
            self.assertFalse(truncated)
            self.assertEqual(info['termination_reason'], 'all_threats_resolved')
            self.assertEqual(info['raw_score'], teacher.raw_score)
        finally:
            env.close()


if __name__ == '__main__':
    unittest.main()
