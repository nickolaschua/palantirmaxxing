import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

try:
    import gymnasium
except ImportError:  # The ordinary backend environment intentionally omits RL deps.
    gymnasium = None


@unittest.skipIf(gymnasium is None, 'requires backend/learning/requirements-rl.txt')
class LearningEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.learning import CentralizedInterceptionEnv
        from backend.simulation import DeterministicToyProvider, SeededScenarioGenerator
        cls.Env = CentralizedInterceptionEnv
        cls.Provider = DeterministicToyProvider
        cls.Generator = SeededScenarioGenerator

    def test_action_index_round_trip_and_invalid_action(self):
        from backend.learning import ACTION_COUNT
        for triple in ((0, 0, 0), (7, 7, 19), (3, 4, 11)):
            action = self.Env.encode_assignment_action(*triple)
            self.assertEqual(self.Env.decode_assignment_action(action), triple)
        env = self.Env(self.Provider(), scenario_generator=self.Generator())
        env.reset(seed=4)
        self.assertEqual(len(env.action_masks()), ACTION_COUNT)
        invalid = int(np.flatnonzero(~env.action_masks().astype(bool))[0])
        with self.assertRaises(ValueError):
            env.step(invalid)

    def test_future_threat_content_is_hidden(self):
        from backend.domain import InterceptorState, ThreatState
        from backend.simulation import EpisodeSpec, InterceptorResource, ScheduledThreat
        initial = ScheduledThreat(0.0, ThreatState('a', 500, 0, 0, 0, 20),
                                  {'priority': 1, 'preferred_candidate_fraction': 0.5})
        resource = InterceptorResource(InterceptorState(
            'i', 0, 0, 0, 100, math.radians(15)))
        future_a = ScheduledThreat(5.0, ThreatState('b', 100, 0, 0, 0, 20),
                                   {'priority': 1, 'preferred_candidate_fraction': 0.1})
        future_b = ScheduledThreat(5.0, ThreatState('b', 9999, -20, 5, 7, 40),
                                   {'priority': 9, 'preferred_candidate_fraction': 0.9})
        first = EpisodeSpec('one', 1, (initial, future_a), (resource,), 20)
        second = EpisodeSpec('two', 1, (initial, future_b), (resource,), 20)
        obs_a, _ = self.Env(self.Provider(), episode_spec=first).reset()
        obs_b, _ = self.Env(self.Provider(), episode_spec=second).reset()
        np.testing.assert_array_equal(obs_a, obs_b)

    def test_gymnasium_checker_and_terminal_reward_direction(self):
        from gymnasium.utils.env_checker import check_env
        env = self.Env(self.Provider(), scenario_generator=self.Generator())
        check_env(env, skip_render_check=True)
        observation, _ = env.reset(seed=9)
        reward = 0.0
        episode_reward = 0.0
        while True:
            valid = np.flatnonzero(env.action_masks())
            observation, reward, terminated, truncated, info = env.step(int(valid[-1]))
            episode_reward += reward
            if terminated or truncated:
                break
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertEqual(episode_reward, -info['raw_score'])

    def test_jsonl_round_trip_and_replay(self):
        from backend.simulation import JsonlRolloutRecorder, replay_rollout
        with TemporaryDirectory() as directory:
            recorder = JsonlRolloutRecorder(Path(directory) / 'rollout.jsonl')
            env = self.Env(self.Provider(), scenario_generator=self.Generator(),
                           recorder=recorder)
            env.reset(seed=19)
            while True:
                action = int(np.flatnonzero(env.action_masks())[-1])
                _, _, terminated, truncated, _ = env.step(action)
                if terminated or truncated:
                    break
            records = recorder.read()
            self.assertTrue(records)
            self.assertAlmostEqual(sum(row.reward for row in records),
                                   -records[-1].raw_score)
            self.assertTrue(all(row.reward == 0 for row in records
                                if not row.step_training_costs))
            replay_env = self.Env(self.Provider(), scenario_generator=self.Generator())
            self.assertTrue(replay_rollout(records, replay_env))

    def test_assignment_and_cancel_have_zero_reward(self):
        env = self.Env(self.Provider(), scenario_generator=self.Generator())
        env.reset(seed=19)
        assignment = int(np.flatnonzero(env.action_masks()[:64 * 20])[0])
        _, reward, _, _, info = env.step(assignment)
        self.assertEqual(reward, 0.0)
        self.assertEqual(info['step_training_costs'], [])

    def test_unrecorded_step_skips_snapshots_and_duplicate_observation(self):
        env = self.Env(self.Provider(), scenario_generator=self.Generator())
        env.reset(seed=19)
        action = int(np.flatnonzero(env.action_masks())[-1])
        with patch.object(env.engine, 'snapshot', wraps=env.engine.snapshot) as snapshot, \
                patch.object(env, '_observation', wraps=env._observation) as observation:
            env.step(action)
        snapshot.assert_not_called()
        self.assertEqual(observation.call_count, 1)

    def test_action_mask_cache_is_protected_and_invalidated(self):
        env = self.Env(self.Provider(), scenario_generator=self.Generator())
        env.reset(seed=19)
        with patch.object(env.engine, 'is_assignment_valid',
                          wraps=env.engine.is_assignment_valid) as validity:
            first = env.action_masks()
            scans = validity.call_count
            second = env.action_masks()
            self.assertEqual(validity.call_count, scans)
            first[:] = 0
            np.testing.assert_array_equal(env.action_masks(), second)
            env.step(int(np.flatnonzero(second)[-1]))
            env.action_masks()
            self.assertGreater(validity.call_count, scans)

    def test_episode_seed_stride_preserves_default_and_partitions_streams(self):
        default = self.Env(self.Provider(), scenario_generator=self.Generator(), base_seed=10)
        self.assertEqual([default.reset()[1]['seed'] for _ in range(3)], [10, 11, 12])
        streams = [self.Env(self.Provider(), scenario_generator=self.Generator(),
                            base_seed=10 + rank, episode_seed_stride=2)
                   for rank in range(2)]
        self.assertEqual([[env.reset()[1]['seed'] for _ in range(3)] for env in streams],
                         [[10, 12, 14], [11, 13, 15]])

    def test_maximize_direction_returns_positive_raw_terminal_reward(self):
        from backend.simulation import ObjectiveDirection

        class MaximizingProvider(self.Provider):
            objective_direction = ObjectiveDirection.MAXIMIZE

        env = self.Env(MaximizingProvider(), scenario_generator=self.Generator())
        env.reset(seed=23)
        episode_reward = 0.0
        while True:
            action = int(np.flatnonzero(env.action_masks())[-1])
            _, reward, terminated, truncated, info = env.step(action)
            episode_reward += reward
            if terminated or truncated:
                break
        self.assertTrue(terminated)
        self.assertEqual(episode_reward, info['raw_score'])

    def test_bounded_oracle_and_fixed_suite_sizes(self):
        from backend.learning import bounded_oracle
        from backend.simulation import SimulationEngine
        from backend.simulation.suites import (HELD_OUT_TEST_SEEDS, ORACLE_SEEDS,
                                               STRESS_SEEDS, VALIDATION_SEEDS)
        self.assertEqual(
            tuple(map(len, (VALIDATION_SEEDS, HELD_OUT_TEST_SEEDS,
                            STRESS_SEEDS, ORACLE_SEEDS))),
            (64, 256, 32, 32))
        generator = self.Generator(candidate_count=5, max_threats=3,
                                   max_interceptors=3)
        episode = generator.generate(40000, threat_count=1, interceptor_count=1)
        oracle = bounded_oracle(SimulationEngine(episode, self.Provider()))
        self.assertTrue(oracle.exact)
        self.assertIsNotNone(oracle.raw_score)
        self.assertLessEqual(oracle.enumerated_action_sequences, 100000)


if __name__ == '__main__':
    unittest.main()
