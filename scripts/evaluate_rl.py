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
                                SeededScenarioGenerator, runtime_factories)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', type=Path,
                        default=Path('data/results/rl/toy-smoke'))
    parser.add_argument('--suite', choices=tuple(SUITES),
                        default='validation')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--provider', choices=PROVIDER_CHOICES, default='toy')
    parser.add_argument('--generator', choices=GENERATOR_CHOICES, default='synthetic')
    args = parser.parse_args()
    suite = SUITES[args.suite]
    output = args.output or Path('data/results/rl') / ('%s-report.json' % suite.name)
    provider_factory, scenario_factory = runtime_factories(
        args.provider, args.generator)
    policy = load_normalized_policy(
        args.model_dir, provider_factory=provider_factory,
        scenario_factory=scenario_factory)
    try:
        rows = evaluate_model(
            policy, suite.seeds, report_path=output,
            generator=(SeededScenarioGenerator(
                max_threats=suite.threat_capacity,
                max_interceptors=suite.interceptor_capacity,
                candidate_count=suite.candidate_count)
                if args.generator == 'synthetic' else scenario_factory()),
            provider_factory=provider_factory,
            include_oracle=suite.name == 'bounded-oracle',
            full_capacity=suite.full_capacity)
        print(json.dumps(asdict(summarize_comparison(rows)), indent=2, sort_keys=True))
    finally:
        policy.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
