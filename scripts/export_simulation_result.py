#!/usr/bin/env python3
"""Write a deterministic feasible-baseline or exact Singapore result."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.presentation import simulation_result_to_dict
from backend.simulation import (FeasibleImmediateMatchingPolicy,
                                OptimalFixedRankAssignmentPolicy,
                                SingaporeConsequenceProvider,
                                SingaporeScenarioConfig,
                                SingaporeScenarioGenerator, SimulationEngine)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--output', type=Path,
                        default=Path('data/results/demo-simulation-result.json'))
    parser.add_argument('--policy', choices=('baseline', 'optimal'),
                        default='baseline')
    args = parser.parse_args()
    config = SingaporeScenarioConfig()
    seed_provider = SingaporeConsequenceProvider(scenario_config=config)
    generator = SingaporeScenarioGenerator(
        config=config, consequence_provider=seed_provider)
    episode = generator.generate(args.seed)

    baseline_provider = SingaporeConsequenceProvider(
        catalog=seed_provider.catalog, scenario_config=config)
    baseline_engine = SimulationEngine(episode, baseline_provider)
    baseline = FeasibleImmediateMatchingPolicy().run(baseline_engine)

    selected_provider = SingaporeConsequenceProvider(
        catalog=seed_provider.catalog, scenario_config=config)
    selected_engine = SimulationEngine(episode, selected_provider)
    policy = (FeasibleImmediateMatchingPolicy() if args.policy == 'baseline'
              else OptimalFixedRankAssignmentPolicy())
    selected = policy.run(selected_engine)
    payload = simulation_result_to_dict(
        selected_engine, policy_identity=policy.identity,
        baseline_raw_score=baseline.raw_score, assignment_plan=selected.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        payload, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + '\n', encoding='utf-8')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
