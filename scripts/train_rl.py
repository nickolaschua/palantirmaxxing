#!/usr/bin/env python3
"""Train the deterministic toy-provider MaskablePPO plumbing policy."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning.training import train_maskable_ppo
from backend.simulation import (GENERATOR_CHOICES, PROVIDER_CHOICES,
                                runtime_factories)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path,
                        default=Path('data/results/rl/toy-smoke'))
    parser.add_argument('--steps', type=int, default=10_000)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--wall-clock-minutes', type=float,
                        help='best-effort PPO throughput estimate using a 60%% training allocation; not a deadline')
    parser.add_argument('--benchmark-steps', type=int, default=256)
    parser.add_argument('--calibration-steps', type=int, default=256,
                        help='disposable PPO calibration timesteps (rounded up to whole rollouts)')
    parser.add_argument('--provider', choices=PROVIDER_CHOICES, default='toy')
    parser.add_argument('--generator', choices=GENERATOR_CHOICES, default='synthetic')
    args = parser.parse_args()
    provider_factory, scenario_factory = runtime_factories(
        args.provider, args.generator)
    artifacts = train_maskable_ppo(
        output_dir=args.output_dir,
        total_timesteps=args.steps,
        seed=args.seed,
        wall_clock_seconds=(None if args.wall_clock_minutes is None
                            else args.wall_clock_minutes * 60.0),
        benchmark_steps=args.benchmark_steps,
        calibration_steps=args.calibration_steps,
        provider_factory=provider_factory,
        scenario_factory=scenario_factory,
    )
    print(json.dumps(artifacts.__dict__, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
