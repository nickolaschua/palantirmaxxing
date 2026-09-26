from dataclasses import replace
import unittest

from backend.simulation import (
    EpisodeSpec, InterceptorResource, NaiveLaunchOnDetectionPolicy,
    OptimalFixedRankAssignmentPolicy, SingaporeConsequenceProvider,
    SingaporeScenarioV2Generator, SimulationEngine)


class _TraceEngine(SimulationEngine):
    def __init__(self, *args, **kwargs):
        self.assignment_trace = []
        super().__init__(*args, **kwargs)

    def assign(self, threat_id, interceptor_id, candidate_index):
        assignment = super().assign(threat_id, interceptor_id, candidate_index)
        self.assignment_trace.append((
            self.current_time_s, threat_id, interceptor_id,
            assignment.candidate.opportunity.opportunity_id))
        return assignment


class _DetectionSpy(SingaporeConsequenceProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clock = None
        self.assessed = []

    def assess_candidates(self, threat, candidates, operational_state):
        if self.clock is None or threat.detection_time_s > self.clock() + 1e-9:
            raise AssertionError('policy/provider inspected a scheduled future threat')
        self.assessed.append(threat.state.threat_id)
        return super().assess_candidates(threat, candidates, operational_state)


class NaiveOnlinePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_provider = SingaporeConsequenceProvider()
        cls.generator = SingaporeScenarioV2Generator(
            config=cls.base_provider.scenario_config,
            consequence_provider=cls.base_provider)
        cls.spec = cls.generator.generate(80000, 'warmup')

    def provider(self, cls=SingaporeConsequenceProvider):
        return cls(catalog=self.base_provider.catalog,
                   scenario_config=self.base_provider.scenario_config)

    def test_future_threat_mutation_cannot_change_pre_detection_actions(self):
        future = self.spec.threats[-1]
        changed_state = replace(
            future.state, position_x_m=future.state.position_x_m + 500.0)
        changed_future = replace(future, state=changed_state)
        changed = EpisodeSpec(
            self.spec.episode_id, self.spec.seed,
            self.spec.threats[:-1] + (changed_future,), self.spec.interceptors,
            self.spec.candidate_count, self.spec.metadata,
            self.spec.schema_version)
        engines = []
        for spec in (self.spec, changed):
            engine = _TraceEngine(spec, self.provider())
            NaiveLaunchOnDetectionPolicy().run(engine)
            engines.append(engine)
        cutoff = future.detection_time_s
        prefixes = [tuple(row for row in engine.assignment_trace
                          if row[0] < cutoff) for engine in engines]
        self.assertTrue(prefixes[0])
        self.assertEqual(prefixes[0], prefixes[1])

    def test_provider_spy_only_sees_detected_threats(self):
        provider = self.provider(_DetectionSpy)
        engine = SimulationEngine(self.spec, provider)
        provider.clock = lambda: engine.current_time_s
        run = NaiveLaunchOnDetectionPolicy().run(engine)
        self.assertTrue(run.completed)
        self.assertEqual(set(provider.assessed),
                         {row.state.threat_id for row in self.spec.threats})

    def test_selection_uses_documented_order_and_tie_break_key(self):
        engine = SimulationEngine(self.spec, self.provider())
        while not engine.visible_threat_ids():
            engine.advance()
        scheduled = min(
            (engine.threats[key].scheduled
             for key in engine.visible_threat_ids()),
            key=lambda row: (row.detection_time_s, row.expiry_time_s,
                             row.state.threat_id))
        choices = []
        for interceptor_id in sorted(engine.interceptor_resources):
            for index, candidate in enumerate(
                    engine.threats[scheduled.state.threat_id].candidates[
                        interceptor_id]):
                if engine.is_assignment_valid(
                        scheduled.state.threat_id, interceptor_id, index):
                    choices.append((
                        candidate.interception_time_s,
                        -float(candidate.opportunity.time_margin_s),
                        interceptor_id, candidate.opportunity.opportunity_id,
                        index))
        expected = min(choices)
        run = NaiveLaunchOnDetectionPolicy().run(engine)
        first = next(row for row in run.actions if row[0] == 'assign')
        self.assertEqual(first[1:], (
            scheduled.state.threat_id, expected[2], expected[3]))

    def test_naive_is_deliberately_not_consequence_aware(self):
        engine = SimulationEngine(self.spec, self.provider())
        while not engine.visible_threat_ids():
            engine.advance()
        threat_id = min(engine.visible_threat_ids())
        choices = []
        for interceptor_id in sorted(engine.interceptor_resources):
            for index, candidate in enumerate(engine.threats[threat_id].candidates[interceptor_id]):
                if engine.is_assignment_valid(threat_id, interceptor_id, index):
                    assessment = engine.threats[threat_id].candidate_assessments[
                        candidate.opportunity.opportunity_id]
                    choices.append((candidate.interception_time_s,
                                    -float(candidate.opportunity.time_margin_s),
                                    interceptor_id,
                                    candidate.opportunity.opportunity_id,
                                    index, assessment.training_cost))
        earliest = min(choices)
        least_cost = min(row[5] for row in choices)
        self.assertGreater(earliest[5], least_cost)
        run = NaiveLaunchOnDetectionPolicy().run(engine)
        first = next(row for row in run.actions if row[0] == 'assign')
        self.assertEqual(first[3], earliest[3])

    def test_greedy_constraint_failure_is_a_recorded_policy_outcome(self):
        resources = tuple(InterceptorResource(
            replace(row.state,
                    position_x_m=row.state.position_x_m + 1_000_000.0,
                    position_y_m=row.state.position_y_m + 1_000_000.0),
            row.metadata)
            for row in self.spec.interceptors)
        impossible = EpisodeSpec(
            self.spec.episode_id, self.spec.seed, self.spec.threats, resources,
            self.spec.candidate_count, self.spec.metadata,
            self.spec.schema_version)
        engine = SimulationEngine(impossible, self.provider())
        run = NaiveLaunchOnDetectionPolicy().run(engine)
        self.assertTrue(run.terminated)
        self.assertFalse(run.truncated)
        self.assertFalse(run.completed)
        self.assertTrue(run.termination_reason.startswith(
            'constraint_violation:'))
        self.assertGreater(engine.raw_score, 0)
        self.assertEqual(len(engine.constraint_violations), 1)

    def test_exact_predicted_cost_equals_authoritative_replay(self):
        engine = SimulationEngine(self.spec, self.provider())
        run = OptimalFixedRankAssignmentPolicy().run(engine)
        self.assertTrue(run.plan.exact)
        self.assertEqual(run.plan.predicted_cost, run.raw_score)


if __name__ == '__main__':
    unittest.main()
