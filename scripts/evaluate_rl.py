#!/usr/bin/env python3
"""Deterministically evaluate a saved toy policy against the fixed baseline."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning import (evaluate_model, load_policy as load_normalized_policy,
                              summarize_comparison)
from backend.simulation.suites import SUITES
from backend.simulation import (GENERATOR_CHOICES, PROVIDER_CHOICES,
                                EpisodePoolFactory,
                                FeasibleImmediateMatchingPolicy,
                                NaiveLaunchOnDetectionPolicy,
                                OptimalFixedRankAssignmentPolicy,
                                SeededScenarioGenerator, SimulationEngine,
                                load_scenario_manifest, resolve_scenario_ref,
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
    parser.add_argument('--comparator', choices=('naive-online', 'feasible-offline'),
                        default='naive-online',
                        help='reference used for learned-policy comparisons')
    parser.add_argument('--pool', type=Path,
                        help='training pool identity required to reload a pool-trained model')
    parser.add_argument('--pool-profile')
    parser.add_argument('--pool-limit', type=int)
    parser.add_argument('--promotion-record', type=Path,
                        help='required for held-out evaluation of an imitation artifact')
    args = parser.parse_args()
    suite = SUITES[args.suite]
    output = args.output or Path('data/results/rl') / ('%s-report.json' % suite.name)
    provider_factory, scenario_factory = runtime_factories(
        args.provider, args.generator)
    training_scenario_factory = scenario_factory
    if args.pool is not None:
        if (args.provider, args.generator) != ('singapore-demo-v2', 'singapore-v2'):
            parser.error('--pool requires the Singapore demo-v2 provider and generator')
        training_scenario_factory = EpisodePoolFactory(
            str(args.pool.resolve()), profile=args.pool_profile,
            limit=args.pool_limit)
    elif args.pool_profile is not None or args.pool_limit is not None:
        parser.error('--pool-profile and --pool-limit require --pool')
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
        scenario_factory=training_scenario_factory)
    try:
        promotion = None
        if (suite.name == 'held-out-test'
                and getattr(policy, 'algorithm', None)
                == 'structured-behavior-cloning/1'):
            if args.promotion_record is None:
                parser.error(
                    'held-out imitation evaluation requires --promotion-record')
            try:
                promotion = json.loads(args.promotion_record.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                parser.error('cannot load the imitation promotion record: %s' % exc)
            if (promotion.get('schema_version') != 'imitation-promotion/1'
                    or promotion.get('promoted') is not True
                    or promotion.get('final_artifact_identity')
                    != getattr(policy, 'artifact_identity', None)
                    or promotion.get('held_out_suite_opened') is not False):
                parser.error('promotion record does not authorize this frozen artifact')
        episode_specs = None
        manifest_splits = {
            'validation': 'validation',
            'held-out-test': 'held-out',
            'stress': 'stress',
            'singapore-assignment-reference': 'assignment-reference',
        }
        if args.generator == 'singapore-v2' and suite.name in manifest_splits:
            manifest = load_scenario_manifest()
            split = manifest_splits[suite.name]
            episode_specs = tuple(
                resolve_scenario_ref(row['scenario_ref'], manifest, generator)
                for row in manifest.entries if row['split'] == split)
        rows = evaluate_model(
            policy, (() if episode_specs is not None else suite.seeds),
            episode_specs=episode_specs, report_path=output,
            generator=generator,
            provider_factory=provider_factory,
            baseline_policy=(
                NaiveLaunchOnDetectionPolicy()
                if args.comparator == 'naive-online'
                else FeasibleImmediateMatchingPolicy()),
            include_oracle=suite.name == 'bounded-oracle',
            full_capacity=suite.full_capacity)
        if promotion is not None:
            promotion['held_out_suite_opened'] = True
            promotion['held_out_report'] = str(output.resolve())
            args.promotion_record.write_text(
                json.dumps(promotion, indent=2, sort_keys=True,
                           allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps(asdict(summarize_comparison(rows)), indent=2, sort_keys=True))
    finally:
        policy.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
