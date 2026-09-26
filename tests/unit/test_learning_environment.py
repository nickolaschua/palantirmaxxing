import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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
        while True:
            valid = np.flatnonzero(env.action_masks())
            observation, reward, terminated, truncated, info = env.step(int(valid[-1]))
            if terminated or truncated:
                break
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertEqual(reward, -info['raw_score'])

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
            replay_env = self.Env(self.Provider(), scenario_generator=self.Generator())
            self.assertTrue(replay_rollout(records, replay_env))

    def test_maximize_direction_returns_positive_raw_terminal_reward(self):
        from backend.simulation import ObjectiveDirection

        class MaximizingProvider(self.Provider):
            objective_direction = ObjectiveDirection.MAXIMIZE

        env = self.Env(MaximizingProvider(), scenario_generator=self.Generator())
        env.reset(seed=23)
        while True:
            action = int(np.flatnonzero(env.action_masks())[-1])
            _, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        self.assertTrue(terminated)
        self.assertEqual(reward, info['raw_score'])

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
