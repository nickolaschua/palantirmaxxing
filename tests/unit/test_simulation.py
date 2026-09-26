import math
import unittest

from backend.domain import InterceptorState, ThreatState
from backend.simulation import (AssignmentStatus, DeterministicToyProvider,
                                EpisodeSpec, ImmediateInterceptionPolicy,
                                InterceptorResource, ObjectiveDirection,
                                ProviderEvaluation, ScheduledThreat,
                                SeededScenarioGenerator, SimulationEngine)


def threat(threat_id='threat-1', detection=0.0, x=500.0, maximum=20.0,
           priority=1.0, preferred=0.5):
    return ScheduledThreat(
        detection,
        ThreatState(threat_id, x, 200.0, 10.0, 0.0, maximum),
        {'priority': priority, 'preferred_candidate_fraction': preferred},
    )


def interceptor(interceptor_id='interceptor-1', y=0.0):
    return InterceptorResource(InterceptorState(
        interceptor_id, 0.0, y, 0.0, 100.0, math.radians(15.0)))


def spec(threats=None, interceptors=None, candidates=20):
    return EpisodeSpec(
        'episode-test', 11,
        tuple(threats or (threat(),)),
        tuple(interceptors or (interceptor(),)),
        candidate_count=candidates,
    )


class SimulationTests(unittest.TestCase):
    def test_seeded_scenario_reproduction_and_suite_features(self):
        generator = SeededScenarioGenerator()
        self.assertEqual(generator.generate(42), generator.generate(42))
        generated = generator.generate(42)
        self.assertGreaterEqual(len(generated.threats), 2)
        self.assertTrue(any(item.detection_time_s >= 0 for item in generated.threats))
        stress = generator.generate(42, full_capacity=True)
        self.assertEqual((len(stress.threats), len(stress.interceptors)), (8, 8))

    def test_equal_timestamp_detection_order_is_stable(self):
        engine = SimulationEngine(spec(
            threats=(threat('z-threat'), threat('a-threat'))),
            DeterministicToyProvider())
        detections = [row for row in engine.event_records if row.kind == 'detection']
        self.assertEqual([row.entity_id for row in detections], ['a-threat', 'z-threat'])

    def test_future_detection_is_not_active(self):
        engine = SimulationEngine(spec(
            threats=(threat('now'), threat('later', detection=5.0))),
            DeterministicToyProvider())
        self.assertEqual(engine.visible_threat_ids(), ('now',))
        engine.advance()
        self.assertIn('later', engine.visible_threat_ids())

    def test_assignment_change_once_per_epoch_and_replacement(self):
        engine = SimulationEngine(spec(
            threats=(threat('now'), threat('later', detection=1.0)),
            interceptors=(interceptor('i-1'), interceptor('i-2', 25.0))),
            DeterministicToyProvider())
        reachable = [i for i, row in enumerate(engine.threats['now'].candidates['i-1'])
                     if row.opportunity.reachable and row.lock_time_s > 1.0]
        self.assertTrue(reachable)
        engine.assign('now', 'i-1', reachable[-1])
        self.assertFalse(engine.is_assignment_valid('now', 'i-2', reachable[-1]))
        engine.advance()  # later detection creates a new decision epoch before the lock
        other = [i for i, row in enumerate(engine.threats['now'].candidates['i-2'])
                 if row.opportunity.reachable and row.lock_time_s >= engine.current_time_s]
        self.assertTrue(other)
        engine.assign('now', 'i-2', other[-1])
        self.assertEqual(engine.assignments['now'].interceptor_id, 'i-2')
        self.assertIsNone(engine.assignment_for_interceptor('i-1'))

    def test_cancel_and_lock_consumes_resource_once(self):
        episode = spec(
            threats=(threat('now'), threat('later', detection=1.0)),
            interceptors=(interceptor('i-1'),))
        engine = SimulationEngine(episode, DeterministicToyProvider())
        candidates = engine.threats['now'].candidates['i-1']
        index = next(i for i, row in enumerate(candidates)
                     if row.opportunity.reachable and row.lock_time_s > 1.0)
        engine.assign('now', 'i-1', index)
        engine.advance()
        self.assertTrue(engine.can_cancel('now'))
        engine.cancel('now')
        self.assertNotIn('i-1', engine.consumed_interceptors)
        engine.advance()
        self.assertNotIn('now', engine.assignments)

        locked = SimulationEngine(spec(), DeterministicToyProvider())
        index = next(i for i, row in enumerate(
            locked.threats['threat-1'].candidates['interceptor-1'])
            if row.opportunity.reachable)
        locked.assign('threat-1', 'interceptor-1', index)
        locked.advance()
        self.assertEqual(locked.assignments['threat-1'].status, AssignmentStatus.LOCKED)
        self.assertIn('interceptor-1', locked.consumed_interceptors)
        self.assertFalse(locked.can_cancel('threat-1'))

    def test_toy_score_is_raw_and_direction_is_declared(self):
        provider = DeterministicToyProvider()
        engine = SimulationEngine(spec(), provider)
        run = ImmediateInterceptionPolicy().run(engine)
        self.assertTrue(run.terminated)
        self.assertFalse(run.truncated)
        self.assertIsInstance(run.raw_score, float)
        self.assertEqual(engine.objective_direction, ObjectiveDirection.MINIMIZE)
        self.assertEqual(engine.aggregate_result.raw_score, run.raw_score)

    def test_unhandled_and_provider_failure(self):
        empty = EpisodeSpec('empty-resource', 3, (threat(),), (), 20)
        engine = SimulationEngine(empty, DeterministicToyProvider())
        run = ImmediateInterceptionPolicy().run(engine)
        self.assertTrue(run.terminated)
        self.assertEqual(engine.threats['threat-1'].resolution.value, 'unhandled')

        class FailedProvider(DeterministicToyProvider):
            def evaluate_unhandled(self, threat, operational_state):
                return ProviderEvaluation(None, failure_status='deliberate')

        failed = SimulationEngine(empty, FailedProvider())
        failed.advance()
        self.assertTrue(failed.truncated)
        self.assertIn('provider_failure', failed.termination_reason)

    def test_event_limit_truncates(self):
        engine = SimulationEngine(spec(
            threats=(threat('one'), threat('two'))),
            DeterministicToyProvider(), event_limit=1)
        self.assertTrue(engine.truncated)
        self.assertEqual(engine.termination_reason, 'event_limit_exhaustion')


if __name__ == '__main__':
    unittest.main()
