from copy import deepcopy
import json
from pathlib import Path
import unittest

from backend.simulation import (
    SingaporeConsequenceProvider, SingaporeScenarioV2Generator,
    audit_episode, evaluate_goldilocks_gates, render_audit_markdown,
    run_scenario_audit_parallel, scenario_graph_metrics)


ROOT = Path(__file__).resolve().parents[2]


def generator():
    provider = SingaporeConsequenceProvider()
    return SingaporeScenarioV2Generator(
        config=provider.scenario_config, consequence_provider=provider)


class ScenarioAuditTests(unittest.TestCase):
    def test_reported_graph_metrics_equal_independent_recomputation(self):
        created = generator()
        record = audit_episode(created, 80000, 'warmup')
        spec = created.generate(80000, 'warmup')
        metrics = scenario_graph_metrics(spec, created._provider())
        for key in (
                'feasible_edge_count', 'edge_density', 'threat_degrees',
                'interceptor_degrees', 'critical_edge_count',
                'complete_matching_count_capped_10000', 'complete_matchable',
                'pair_best_time_margin_min_s',
                'pair_best_time_margin_median_s',
                'candidate_cost_spread_by_threat',
                'candidate_cost_spread_max'):
            self.assertEqual(record[key], metrics[key])

    def test_missing_consequence_components_remain_explicitly_unavailable(self):
        record = audit_episode(generator(), 80000, 'warmup')
        self.assertEqual(record['unavailable_consequence_components'], [
            'transport', 'healthcare', 'education',
            'richer_residential_services'])
        self.assertNotIn(0, record['unavailable_consequence_components'])

    def test_custom_audit_json_and_markdown_are_byte_deterministic(self):
        plan = (
            {'seed': 80000, 'profile': 'warmup'},
            {'seed': 80100, 'profile': 'balanced'},
            {'seed': 80280, 'profile': 'full-standard'},
            {'seed': 80460, 'profile': 'burst-contention'},
            {'seed': 80640, 'profile': 'low-slack'},
            {'seed': 80820, 'profile': 'consequence-contrast'},
        )
        first = run_scenario_audit_parallel(generator(), plan)
        second = run_scenario_audit_parallel(generator(), plan)
        first_json = json.dumps(first, indent=2, sort_keys=True,
                                ensure_ascii=False, allow_nan=False) + '\n'
        second_json = json.dumps(second, indent=2, sort_keys=True,
                                 ensure_ascii=False, allow_nan=False) + '\n'
        self.assertEqual(first_json, second_json)
        first_markdown = render_audit_markdown(first)
        self.assertEqual(first_markdown, render_audit_markdown(second))
        self.assertIn('### Complete matching counts', first_markdown)
        self.assertIn(
            'Unavailable consequence-component episode counts',
            first_markdown)

    def test_each_frozen_gate_detects_its_broken_evidence(self):
        audit = json.loads((
            ROOT / 'data/results/rl/scenario-audit-v2.json').read_text())
        mutations = {
            'episode_count': lambda value: value.update(
                requested_episode_count=999),
            'zero_silent_exclusions': lambda value: value['exclusions'].append(
                {'reason': 'injected'}),
            'unique_hashes': lambda value: value['episodes'][1].update(
                canonical_episode_hash=value['episodes'][0][
                    'canonical_episode_hash']),
            'deterministic_regeneration': lambda value: value['episodes'][0].update(
                deterministic_regeneration=False),
            'matching_and_exact_completion': lambda value: value['episodes'][0].update(
                complete_matchable=False),
            'profile_predicates': lambda value: value['episodes'][0].update(
                profile_predicates_satisfied=False),
            'generation_attempts': lambda value: value['episodes'][0].update(
                generation_attempt_count=201),
            'naive_completion_warmup': lambda value: [row['naive'].update(
                completed=False) for row in value['episodes']
                if row['profile'] == 'warmup'],
            'paired_complete_full_size': lambda value: [row[
                'naive_to_exact'].update(both_completed=False)
                for row in value['episodes'] if row['active_threat_count'] == 8],
            'exact_strictly_better': lambda value: [row[
                'naive_to_exact'].update(absolute_improvement=0.0)
                for row in value['episodes']],
            'paired_median_relative_improvement': lambda value: [row[
                'naive_to_exact'].update(relative_improvement=0.0)
                for row in value['episodes']],
            'consequence_contrast': lambda value: [row[
                'naive_to_exact'].update(absolute_improvement=0.0,
                                         relative_improvement=0.0)
                for row in value['episodes']
                if row['profile'] == 'consequence-contrast'],
            'ingress_balance': lambda value: [row.update(
                ingress_sectors=[0] * row['active_threat_count'])
                for row in value['episodes']],
            'not_fully_connected': lambda value: [row.update(
                feasible_edge_count=row['active_threat_count']
                * row['active_interceptor_count'])
                for row in value['episodes'] if row['profile'] != 'warmup'],
        }
        for gate, mutate in mutations.items():
            with self.subTest(gate=gate):
                broken = deepcopy(audit)
                mutate(broken)
                evaluated = evaluate_goldilocks_gates(broken)
                self.assertFalse(evaluated['gates'][gate]['passed'])


if __name__ == '__main__':
    unittest.main()
