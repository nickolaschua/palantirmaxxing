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
                                EpisodePoolFactory, runtime_factories)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path,
                        default=Path('data/results/rl/toy-smoke'))
    parser.add_argument('--steps', type=int, default=10_000)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--n-envs', type=int, default=4,
                        help='parallel simulator workers (Python API default: 1)')
    parser.add_argument('--gamma', type=float, default=1.0,
                        help='episode-cost discount; 1.0 preserves the summed-cost objective')
    parser.add_argument('--gae-lambda', type=float, default=0.95)
    parser.add_argument('--entropy-coefficient', type=float, default=0.0)
    parser.add_argument('--wall-clock-minutes', type=float,
                        help='best-effort PPO throughput estimate using a 60%% training allocation; not a deadline')
    parser.add_argument('--benchmark-steps', type=int, default=256)
    parser.add_argument('--calibration-steps', type=int, default=256,
                        help='disposable PPO calibration timesteps (rounded up to whole rollouts)')
    parser.add_argument('--provider', choices=PROVIDER_CHOICES, default='toy')
    parser.add_argument('--generator', choices=GENERATOR_CHOICES, default='synthetic')
    parser.add_argument('--pool', type=Path,
                        help='verified scenario-pool release used for training')
    parser.add_argument('--pool-profile',
                        help='optional profile filter for a diagnostic subset')
    parser.add_argument('--pool-limit', type=int,
                        help='optional maximum records after profile filtering')
    args = parser.parse_args()
    provider_factory, scenario_factory = runtime_factories(
        args.provider, args.generator)
    if args.pool is not None:
        if (args.provider, args.generator) != ('singapore-demo-v2', 'singapore-v2'):
            parser.error('--pool requires the Singapore demo-v2 provider and generator')
        scenario_factory = EpisodePoolFactory(
            str(args.pool.resolve()), profile=args.pool_profile,
            limit=args.pool_limit)
    elif args.pool_profile is not None or args.pool_limit is not None:
        parser.error('--pool-profile and --pool-limit require --pool')
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
        n_envs=args.n_envs,
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
        entropy_coefficient=args.entropy_coefficient,
    )
    print(json.dumps(artifacts.__dict__, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
