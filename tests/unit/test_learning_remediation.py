"""Regression coverage for seed isolation, exhaustive replay and RL evidence."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

try:
    import gymnasium
except ImportError:
    gymnasium = None


class AdvancePolicy:
    def predict(self, observation, deterministic=True, action_masks=None):
        return int(np.flatnonzero(action_masks)[-1]), None


@unittest.skipIf(gymnasium is None, 'requires backend/learning/requirements-rl.txt')
class RemediationTests(unittest.TestCase):
    def test_fixed_rank_optimizer_matches_small_bounded_oracle(self):
        from backend.learning import bounded_oracle
        from backend.simulation import (DeterministicToyProvider,
                                        OptimalFixedRankAssignmentPolicy,
                                        SeededScenarioGenerator,
                                        SimulationEngine)
        generator = SeededScenarioGenerator(
            max_threats=1, max_interceptors=1, candidate_count=3)
        spec = generator.generate(40003, full_capacity=True)
        oracle = bounded_oracle(
            SimulationEngine(spec, DeterministicToyProvider()))
        engine = SimulationEngine(spec, DeterministicToyProvider())
        run = OptimalFixedRankAssignmentPolicy().run(engine)
        self.assertTrue(oracle.exact)
        self.assertEqual(run.raw_score, oracle.raw_score)
        self.assertTrue(run.plan.exact)

    def test_optimizer_refuses_exactness_for_cost_changing_provider(self):
        from backend.simulation import (DeterministicToyProvider,
                                        SeededScenarioGenerator,
                                        optimal_fixed_rank_plan)
        class CostChangingProvider(DeterministicToyProvider):
            operational_updates_affect_costs = True
        spec = SeededScenarioGenerator(
            max_threats=1, max_interceptors=1,
            candidate_count=3).generate(40004, full_capacity=True)
        plan = optimal_fixed_rank_plan(spec, CostChangingProvider())
        self.assertFalse(plan.exact)
        self.assertIn('inexact', plan.proof_scope)

    def setUp(self):
        from backend.learning import CentralizedInterceptionEnv
        from backend.simulation import DeterministicToyProvider, SeededScenarioGenerator
        self.Env = CentralizedInterceptionEnv
        self.Provider = DeterministicToyProvider
        self.Generator = SeededScenarioGenerator

    def test_seed_partition_at_boundaries_and_over_long_reset_sequence(self):
        from backend.simulation.suites import SUITES, TRAINING_SEED_OFFSET
        evaluation_seeds = {seed for suite in SUITES.values() for seed in suite.seeds}
        env = self.Env(self.Provider(), base_seed=9999,
                       scenario_seed_offset=TRAINING_SEED_OFFSET)
        for seed in (0, 9999, 10000, 10063, 10064, 19999, 20000, 20255,
                     20256, 29999, 30000, 30031, 30032, 39999, 40000, 40031, 40032):
            _, info = env.reset(seed=seed)
            self.assertEqual(info['seed'], TRAINING_SEED_OFFSET + seed)
            self.assertNotIn(info['seed'], evaluation_seeds)
        # Exercise the actual automatic-reset selection through all suite ranges
        # without spending the test's time generating geometry 40,000 times.
        with patch.object(env.scenario_generator, 'generate', side_effect=lambda seed: seed):
            seeds = {env._select_episode(None) for _ in range(41000)}
        self.assertTrue(seeds.isdisjoint(evaluation_seeds))
        self.assertGreaterEqual(min(seeds), TRAINING_SEED_OFFSET)
        _, info = env.reset()
        self.assertGreaterEqual(info['seed'], TRAINING_SEED_OFFSET)
        evaluation = self.Env(self.Provider())
        self.assertEqual(evaluation.reset(seed=10000)[1]['seed'], 10000)

    def test_fixed_and_explicit_specs_bypass_offset(self):
        from backend.simulation.suites import TRAINING_SEED_OFFSET
        spec = self.Generator().generate(10000)
        for fixed in (False, True):
            env = self.Env(self.Provider(), episode_spec=spec if fixed else None,
                           scenario_seed_offset=TRAINING_SEED_OFFSET)
            options = None if fixed else {'episode_spec': spec}
            self.assertEqual(env.reset(seed=23, options=options)[1]['seed'], 10000)

    def test_negative_training_seeds_and_offsets_rejected(self):
        from backend.learning import train_maskable_ppo, load_normalized_policy
        for seed in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                train_maskable_ppo(Path('unused'), seed=seed)
            with self.assertRaises(ValueError):
                load_normalized_policy(Path('unused'), seed=seed)
        with self.assertRaises(ValueError):
            self.Env(self.Provider(), base_seed=-1, scenario_seed_offset=100)
        with self.assertRaises(ValueError):
            self.Env(self.Provider(), scenario_seed_offset=-1)

    def recorded_episodes(self, offset=0, event_limit=10000):
        from backend.simulation import JsonlRolloutRecorder
        with TemporaryDirectory() as directory:
            recorder = JsonlRolloutRecorder(Path(directory) / 'episodes.jsonl')
            env = self.Env(self.Provider(), recorder=recorder,
                           scenario_seed_offset=offset, event_limit=event_limit)
            groups = []
            for seed in (19, 20):
                env.reset(seed=seed)
                start = len(recorder.read())
                while True:
                    _, _, terminated, truncated, _ = env.step(
                        int(np.flatnonzero(env.action_masks())[-1]))
                    if terminated or truncated:
                        break
                groups.append(recorder.read()[start:])
            return groups

    def test_replay_consumes_multiple_episodes_and_offset_seeds(self):
        from backend.simulation import replay_rollout
        from backend.simulation.suites import TRAINING_SEED_OFFSET
        for offset in (0, TRAINING_SEED_OFFSET):
            first, second = self.recorded_episodes(offset)
            records = first + second
            env = self.Env(self.Provider(), scenario_seed_offset=offset)
            with patch.object(env, 'step', wraps=env.step) as step:
                self.assertTrue(replay_rollout(iter(records), env))
                self.assertEqual(step.call_count, len(records))
            self.assertEqual(env.engine.snapshot(), second[-1].state_after)

    def test_replay_partial_only_allowed_for_final_episode(self):
        from backend.simulation import replay_rollout
        first, second = self.recorded_episodes()
        env = self.Env(self.Provider())
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            replay_rollout(first[:-1], env)
        self.assertTrue(replay_rollout(first + second[:-1], env, require_complete=False))
        with self.assertRaisesRegex(ValueError, 'before termination'):
            replay_rollout(first[:-1] + second, env, require_complete=False)
        with self.assertRaisesRegex(ValueError, 'at least one'):
            replay_rollout(iter(()), env)

    def test_replay_rejects_reordering_reuse_and_trailing_records(self):
        from backend.simulation import replay_rollout
        first, second = self.recorded_episodes()
        env = self.Env(self.Provider())
        for records in (first + second + first, first + (first[-1],),
                        (first[1], first[0]) + first[2:],
                        first + second[:-1] + (replace(second[-1], raw_score=-123),)):
            with self.subTest(records=len(records)), self.assertRaises(ValueError):
                replay_rollout(records, env)

    def test_replay_checks_each_recorded_field(self):
        from backend.simulation import replay_rollout
        first, _ = self.recorded_episodes()
        changes = {
            'seed': 999, 'event_id': first[0].episode_id + ':d000002',
            'observation_ref': 'wrong', 'action_mask': (), 'action': -1,
            'state_before': {}, 'state_after': {},
            'assignments_before': ({'wrong': 1},),
            'assignments_after': ({'wrong': 1},), 'raw_score': -123,
            'termination_reason': 'wrong', 'schema_version': 'unknown',
            'reward': 123.0, 'step_training_costs': (123.0,),
        }
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay_rollout((replace(first[0], **{field: value}),) + first[1:],
                               self.Env(self.Provider()))
        with self.assertRaisesRegex(ValueError, 'inconsistent seed'):
            replay_rollout((first[0], replace(first[1], seed=777)) + first[2:],
                           self.Env(self.Provider()))

    def test_replay_accepts_verified_truncation(self):
        from backend.simulation import replay_rollout
        first, _ = self.recorded_episodes(event_limit=3)
        self.assertTrue(first[-1].state_after['truncated'])
        self.assertTrue(replay_rollout(first, self.Env(self.Provider(), event_limit=3)))

    def test_budget_uses_ppo_throughput_and_whole_rollouts(self):
        from backend.learning import budget_from_wall_clock
        budget = budget_from_wall_clock(100, 20, 256, 0.1, rollout_steps=256)
        self.assertEqual(budget.planned_training_steps, 2816)
        self.assertEqual(budget.training_seconds, 60)
        self.assertEqual(budget.estimated_training_seconds, 56.32)
        other = budget_from_wall_clock(100, 20, 256, 999, rollout_steps=256)
        self.assertEqual(other.planned_training_steps, budget.planned_training_steps)
        tiny = budget_from_wall_clock(0.01, 20, 256, 0.1, rollout_steps=256)
        self.assertEqual(tiny.planned_training_steps, 256)
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                budget_from_wall_clock(100, value, 256, 1)

    def test_vectorized_rollout_and_minibatch_divisibility(self):
        from backend.learning.training import (_ppo_rollout_configuration,
                                               _scenario_seed_offset)
        for total, workers in ((10_000, 1), (50_000, 2), (50_000, 4),
                               (50_003, 6), (1, 8)):
            n_steps, batch_size = _ppo_rollout_configuration(total, workers)
            buffer_size = n_steps * workers
            self.assertLessEqual(n_steps, 256)
            self.assertLessEqual(batch_size, 64)
            self.assertEqual(buffer_size % batch_size, 0)
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                _ppo_rollout_configuration(100, invalid)
        self.assertEqual(_scenario_seed_offset(object()), 1_000_000_000)
        self.assertEqual(_scenario_seed_offset(type(
            'PoolSelector', (), {'selects_pool_records': True})()), 0)

    def test_training_rejects_invalid_discount_configuration(self):
        from backend.learning import train_maskable_ppo
        for kwargs in ({'gamma': -0.1}, {'gamma': 1.1},
                       {'gae_lambda': -0.1}, {'gae_lambda': 1.1},
                       {'entropy_coefficient': -0.1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                train_maskable_ppo(Path('unused'), **kwargs)

    def small_generator(self, candidate_count=2):
        generator = self.Generator(candidate_count=candidate_count, max_threats=3,
                                   max_interceptors=3)
        original = generator.generate
        generator.generate = lambda seed, **kwargs: original(
            seed, threat_count=1, interceptor_count=1)
        return generator

    def test_oracle_exact_capped_and_equal_baseline_evidence(self):
        from backend.learning import evaluate_model, summarize_comparison
        from backend.learning import acceptance_evidence
        generator = self.small_generator(5)
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'evaluation.json'
            rows = evaluate_model(AdvancePolicy(), [40002], generator=generator,
                                  include_oracle=True, report_path=report)
            oracle = rows[0].oracle
            self.assertTrue(oracle.exact)
            self.assertIsNotNone(oracle.normalized_regret)
            self.assertIsNone(oracle.regret_ineligibility_reason)
            summary = summarize_comparison(rows)
            self.assertEqual(summary.oracle_eligible_regret_count, 1)
            self.assertEqual(summary.median_normalized_regret, oracle.normalized_regret)
            payload = json.loads(report.read_text())
            self.assertEqual(payload['schema_version'], 'policy-evaluation/3')
            self.assertEqual(payload['primary_comparator']['identity'],
                             'naive-launch-on-detection/1')
            self.assertEqual(
                {row['identity'] for row in payload['offline_references']},
                {'feasible-immediate-matching/1',
                 'optimal-fixed-rank-assignment/1'})
            self.assertEqual(payload['episodes'][0]['oracle']['raw_score'], oracle.raw_score)
            self.assertEqual(payload['acceptance_gates'], acceptance_evidence(
                summary, summary.median_normalized_regret))
        capped = evaluate_model(AdvancePolicy(), [40000], generator=generator,
                                include_oracle=True, oracle_max_action_sequences=1)
        self.assertFalse(capped[0].oracle.exact)
        self.assertEqual(capped[0].oracle.enumerated_action_sequences, 1)
        self.assertEqual(capped[0].oracle.regret_ineligibility_reason, 'oracle_inexact')
        summary = summarize_comparison(capped)
        self.assertIsNone(summary.median_normalized_regret)
        self.assertFalse(acceptance_evidence(summary, summary.median_normalized_regret)[
            'median_normalized_regret_at_most_10_percent'])
        equal = evaluate_model(AdvancePolicy(), [40000], generator=self.small_generator(1),
                               include_oracle=True)
        self.assertTrue(equal[0].oracle.exact)
        self.assertEqual(equal[0].oracle.raw_score, equal[0].baseline_raw_score)
        self.assertEqual(equal[0].oracle.regret_ineligibility_reason,
                         'oracle_not_strictly_better_than_baseline')
        self.assertIsNone(equal[0].oracle.normalized_regret)

    def test_evaluation_accepts_frozen_explicit_episode_specs(self):
        from backend.learning import evaluate_model
        generator = self.small_generator()
        specs = (generator.generate(19), generator.generate(20))
        rows = evaluate_model(AdvancePolicy(), episode_specs=specs)
        self.assertEqual([row.seed for row in rows], [19, 20])
        self.assertEqual([row.episode_id for row in rows],
                         [spec.episode_id for spec in specs])
        with self.assertRaises(ValueError):
            evaluate_model(AdvancePolicy(), [19], episode_specs=specs)

    def test_evaluation_records_online_comparator_scope(self):
        from backend.learning import evaluate_model
        from backend.simulation import NaiveLaunchOnDetectionPolicy
        rows = evaluate_model(
            AdvancePolicy(), [19], generator=self.small_generator(),
            baseline_policy=NaiveLaunchOnDetectionPolicy())
        self.assertEqual(
            rows[0].baseline_version,
            NaiveLaunchOnDetectionPolicy.identity)
        self.assertEqual(
            rows[0].baseline_information_scope,
            NaiveLaunchOnDetectionPolicy.information_scope)

    def test_exact_oracle_policy_passes_report_regret_gate(self):
        from backend.learning import bounded_oracle, evaluate_model, ADVANCE_ACTION
        from backend.simulation import SimulationEngine
        generator = self.small_generator(5)
        spec = generator.generate(40002)
        solution = bounded_oracle(SimulationEngine(spec, self.Provider()))
        env_class = self.Env

        class OraclePolicy:
            actions = iter(solution.actions)

            def predict(self, *args, **kwargs):
                action = next(self.actions)
                if action[0] == 'assign':
                    return env_class.encode_assignment_action(0, 0, action[3]), None
                if action[0] == 'cancel':
                    return env_class.cancel_action(0), None
                return ADVANCE_ACTION, None

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'oracle-report.json'
            row = evaluate_model(OraclePolicy(), [40002], generator=generator,
                                 include_oracle=True, report_path=path)[0]
            self.assertEqual(row.oracle.normalized_regret, 0)
            report = json.loads(path.read_text())
            self.assertTrue(report['acceptance_gates'][
                'median_normalized_regret_at_most_10_percent'])
            self.assertEqual(report['summary']['oracle_exact_episode_count'], 1)
            self.assertEqual(report['summary']['oracle_eligible_regret_count'], 1)

    def test_cli_bounded_oracle_uses_suite_limits(self):
        from scripts import evaluate_rl
        from backend.learning import evaluate_model
        from backend.simulation.suites import ORACLE_SUITE
        rows = evaluate_model(AdvancePolicy(), [19], generator=self.small_generator())
        with TemporaryDirectory() as directory, \
                patch('sys.argv', ['evaluate_rl.py', '--suite', 'bounded-oracle',
                                   '--output', str(Path(directory) / 'report.json')]), \
                patch.object(evaluate_rl, 'load_normalized_policy') as load, \
                patch.object(evaluate_rl, 'evaluate_model', return_value=rows) as evaluate, \
                patch('builtins.print'):
            self.assertEqual(evaluate_rl.main(), 0)
            args, kwargs = evaluate.call_args
            self.assertEqual(args[1], ORACLE_SUITE.seeds)
            self.assertTrue(kwargs['include_oracle'])
            generator = kwargs['generator']
            self.assertEqual((generator.max_threats, generator.max_interceptors,
                              generator.candidate_count), (3, 3, 5))
            load.return_value.close.assert_called_once()

    def test_oracle_at_exact_cap_and_truncated_search(self):
        from backend.learning import bounded_oracle
        from backend.simulation import SimulationEngine
        spec = self.small_generator(1).generate(40000)
        result = bounded_oracle(SimulationEngine(spec, self.Provider()))
        at_cap = bounded_oracle(SimulationEngine(spec, self.Provider()),
                                result.enumerated_action_sequences)
        self.assertTrue(at_cap.exact)
        truncated = bounded_oracle(SimulationEngine(spec, self.Provider(), event_limit=1))
        self.assertFalse(truncated.exact)

    def test_regret_directions_and_gate(self):
        from backend.learning import (evaluate_model, summarize_comparison,
                                      normalized_regret, acceptance_evidence)
        from backend.simulation import ObjectiveDirection
        self.assertAlmostEqual(normalized_regret(1, 10, 0, ObjectiveDirection.MINIMIZE), 0.1)
        self.assertAlmostEqual(normalized_regret(9, 0, 10, ObjectiveDirection.MAXIMIZE), 0.1)
        rows = evaluate_model(AdvancePolicy(), [19], generator=self.small_generator())
        summary = summarize_comparison(rows)
        self.assertFalse(acceptance_evidence(summary, 0.0)[
            'median_normalized_regret_at_most_10_percent'])
        summary = replace(summary, oracle_eligible_regret_count=1, oracle_exact_episode_count=1)
        self.assertTrue(acceptance_evidence(summary, 0.1)[
            'median_normalized_regret_at_most_10_percent'])
        self.assertFalse(acceptance_evidence(summary, 0.11)[
            'median_normalized_regret_at_most_10_percent'])

    def test_latency_separates_prediction_from_provider_and_mask_work(self):
        from backend.learning import evaluate_model
        clock = [0.0]

        class DelayedPolicy(AdvancePolicy):
            def predict(self, *args, **kwargs):
                clock[0] += 0.007
                return super().predict(*args, **kwargs)

        class DelayedProvider(self.Provider):
            def decision_features(self, *args, **kwargs):
                clock[0] += 0.025
                return super().decision_features(*args, **kwargs)

        mask = self.Env.action_masks

        def delayed_mask(env):
            clock[0] += 0.003
            return mask(env)

        # Virtual delays make the timing assertion deterministic on slow CI.
        with patch('time.perf_counter', side_effect=lambda: clock[0]), \
                patch.object(self.Env, 'action_masks', delayed_mask):
            row = evaluate_model(DelayedPolicy(), [19], generator=self.small_generator(),
                                 provider_factory=DelayedProvider)[0]
        np.testing.assert_allclose(row.policy_inference_samples_ms, 7.0)
        self.assertEqual(len(row.decision_path_samples_ms), row.policy_actions)
        # The revision cache removes repeated provider/mask work on decisions
        # that do not need a fresh assessment; inference plus mask retrieval
        # must still be represented in the end-to-end sample.
        self.assertTrue(all(value >= 10 - 1e-8 for value in row.decision_path_samples_ms))
        self.assertAlmostEqual(row.policy_inference_p95_ms, 7)
        self.assertAlmostEqual(row.decision_path_p95_ms,
                               np.percentile(row.decision_path_samples_ms, 95))

    def test_summary_latency_flattens_unequal_episode_samples(self):
        from backend.learning import evaluate_model, summarize_comparison
        template = evaluate_model(AdvancePolicy(), [19], generator=self.small_generator())[0]
        rows = (
            replace(template, policy_actions=100, policy_inference_samples_ms=(1.0,) * 100,
                    decision_path_samples_ms=(2.0,) * 100,
                    policy_inference_p95_ms=1, decision_path_p95_ms=2),
            replace(template, policy_actions=1, policy_inference_samples_ms=(1000.0,),
                    decision_path_samples_ms=(2000.0,),
                    policy_inference_p95_ms=1000, decision_path_p95_ms=2000),
        )
        summary = summarize_comparison(rows)
        self.assertEqual(summary.inference_p95_ms, 1)
        self.assertEqual(summary.decision_path_p95_ms, 2)

    def test_calibration_train_save_load_evaluate_smoke(self):
        from backend.learning import train_maskable_ppo, load_normalized_policy, evaluate_model
        from backend.simulation.suites import TRAINING_SEED_OFFSET
        try:
            import sb3_contrib
        except ImportError:
            self.skipTest('requires PPO dependencies')
        with TemporaryDirectory() as directory:
            output = Path(directory)
            artifacts = train_maskable_ppo(output, total_timesteps=1, seed=10000,
                                           wall_clock_seconds=0.001,
                                           benchmark_steps=2, calibration_steps=3)
            metadata = json.loads(Path(artifacts.metadata_path).read_text())
            self.assertEqual(metadata['requested_timesteps'], 1)
            self.assertEqual(metadata['effective_timesteps'], 2)
            self.assertEqual(metadata['effective_timesteps'], metadata['total_timesteps'])
            self.assertEqual(metadata['calibration_steps'], 4)
            self.assertEqual(metadata['algorithm_seed'], 10000)
            self.assertEqual(metadata['first_scenario_seed'], TRAINING_SEED_OFFSET + 10000)
            self.assertGreater(metadata['ppo_ms_per_timestep'], 0)
            self.assertAlmostEqual(metadata['ppo_ms_per_timestep'],
                                   metadata['calibration_seconds'] * 1000 / 4)
            budget = metadata['budget']
            self.assertAlmostEqual(budget['estimated_training_seconds'],
                                   budget['planned_training_steps'] * budget['ppo_ms_per_timestep'] / 1000)
            self.assertAlmostEqual(budget['training_overrun_seconds'] - budget['training_underrun_seconds'],
                                   artifacts.elapsed_seconds - budget['training_seconds'])
            policy = load_normalized_policy(output)
            try:
                self.assertFalse(policy.normalization_env.training)
                self.assertEqual(policy.normalization_env.venv.envs[0].scenario_seed_offset,
                                 TRAINING_SEED_OFFSET)
                rows = evaluate_model(policy, [10000], generator=self.small_generator(),
                                      report_path=output / 'report.json')
                self.assertEqual(rows[0].seed, 10000)
                self.assertGreater(rows[0].policy_actions, 0)
            finally:
                policy.close()


if __name__ == '__main__':
    unittest.main()
