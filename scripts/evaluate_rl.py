#!/usr/bin/env python3
"""Deterministically evaluate a saved toy policy against the fixed baseline."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning import (evaluate_model, load_normalized_policy,
                              summarize_comparison)
from backend.simulation.suites import SUITES
from backend.simulation import (GENERATOR_CHOICES, PROVIDER_CHOICES,
                                FeasibleImmediateMatchingPolicy,
                                OptimalFixedRankAssignmentPolicy,
                                SeededScenarioGenerator, SimulationEngine,
                                runtime_factories)


def evaluate_assignment_reference(policy_name, seeds, generator,
                                  provider_factory, output, full_capacity=False):
    policy = (FeasibleImmediateMatchingPolicy() if policy_name == 'baseline'
              else OptimalFixedRankAssignmentPolicy())
    episodes = []
    for seed in seeds:
        spec = generator.generate(seed, full_capacity=full_capacity)
        baseline_engine = SimulationEngine(spec, provider_factory())
        baseline = FeasibleImmediateMatchingPolicy().run(baseline_engine)
        selected_engine = SimulationEngine(spec, provider_factory())
        selected = policy.run(selected_engine)
        episodes.append({
            'seed': seed, 'episode_id': spec.episode_id,
            'policy_identity': policy.identity,
            'policy_raw_score': selected.raw_score,
            'baseline_identity': FeasibleImmediateMatchingPolicy.identity,
            'baseline_raw_score': baseline.raw_score,
            'predicted_cost': selected.plan.predicted_cost,
            'exact': selected.plan.exact,
            'proof_scope': selected.plan.proof_scope,
            'termination_reason': selected.termination_reason,
            'constraint_violation': False,
        })
    summary = {
        'episode_count': len(episodes),
        'constraint_violation_count': 0,
        'constraint_violation_rate': 0.0,
        'policy_no_worse_count': sum(
            row['policy_raw_score'] <= row['baseline_raw_score']
            for row in episodes),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        'schema_version': 'assignment-reference-evaluation/1',
        'summary': summary, 'episodes': episodes,
    }, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', type=Path,
                        default=Path('data/results/rl/toy-smoke'))
    parser.add_argument('--suite', choices=tuple(SUITES),
                        default='validation')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--provider', choices=PROVIDER_CHOICES, default='toy')
    parser.add_argument('--generator', choices=GENERATOR_CHOICES, default='synthetic')
    parser.add_argument('--policy', choices=('learned', 'baseline', 'optimal'),
                        default='learned')
    args = parser.parse_args()
    suite = SUITES[args.suite]
    output = args.output or Path('data/results/rl') / ('%s-report.json' % suite.name)
    provider_factory, scenario_factory = runtime_factories(
        args.provider, args.generator)
    generator = (SeededScenarioGenerator(
        max_threats=suite.threat_capacity,
        max_interceptors=suite.interceptor_capacity,
        candidate_count=suite.candidate_count)
        if args.generator == 'synthetic' else scenario_factory())
    if args.policy != 'learned':
        if args.generator != 'singapore-v1' or args.provider != 'singapore-demo-v2':
            parser.error('baseline/optimal reference evaluation requires the Singapore provider and generator')
        evaluate_assignment_reference(
            args.policy, suite.seeds, generator, provider_factory, output,
            full_capacity=suite.full_capacity)
        return 0
    policy = load_normalized_policy(
        args.model_dir, provider_factory=provider_factory,
        scenario_factory=scenario_factory)
    try:
        rows = evaluate_model(
            policy, suite.seeds, report_path=output,
            generator=generator,
            provider_factory=provider_factory,
            include_oracle=suite.name == 'bounded-oracle',
            full_capacity=suite.full_capacity)
        print(json.dumps(asdict(summarize_comparison(rows)), indent=2, sort_keys=True))
    finally:
        policy.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
