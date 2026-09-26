#!/usr/bin/env python3
"""Benchmark Singapore-v2 MaskablePPO throughput across worker counts."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning.training import train_maskable_ppo
from backend.simulation import runtime_factories


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, nargs='+', default=[1, 2, 4, 6, 8])
    parser.add_argument('--warmup-steps', type=int, default=10_000)
    parser.add_argument('--measured-steps', type=int, default=50_000)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--output', type=Path,
                        default=Path('data/results/rl/singapore-v2-worker-benchmark.json'))
    parser.add_argument('--resume', action='store_true',
                        help='reuse completed rows from a matching partial output')
    args = parser.parse_args()
    if any(type(value) is not int or value <= 0 for value in args.workers):
        parser.error('workers must be positive integers')
    provider_factory, scenario_factory = runtime_factories(
        'singapore-demo-v2', 'singapore-v2')
    rows = []
    if args.resume and args.output.is_file():
        previous = json.loads(args.output.read_text(encoding='utf-8'))
        if (previous.get('warmup_steps'), previous.get('measured_steps'),
                previous.get('seed')) != (args.warmup_steps, args.measured_steps, args.seed):
            parser.error('resume output does not match benchmark settings')
        rows = list(previous.get('results', ()))
    completed_workers = {row['n_envs'] for row in rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sdth-rl-benchmark-') as directory:
        root = Path(directory)
        for workers in args.workers:
            if workers in completed_workers:
                continue
            warm = root / ('warm-%d' % workers)
            train_maskable_ppo(warm, args.warmup_steps, args.seed,
                               provider_factory=provider_factory,
                               scenario_factory=scenario_factory, n_envs=workers)
            shutil.rmtree(warm)
            measured = root / ('measured-%d' % workers)
            started = time.perf_counter()
            artifacts = train_maskable_ppo(
                measured, args.measured_steps, args.seed,
                provider_factory=provider_factory,
                scenario_factory=scenario_factory, n_envs=workers)
            elapsed = time.perf_counter() - started
            rows.append({'n_envs': workers, 'requested_timesteps': args.measured_steps,
                         'actual_timesteps': artifacts.total_timesteps,
                         'elapsed_seconds': elapsed,
                         'timesteps_per_second': artifacts.total_timesteps / elapsed})
            partial = {'provider': 'singapore-demo-v2', 'generator': 'singapore-v2',
                       'warmup_steps': args.warmup_steps,
                       'measured_steps': args.measured_steps, 'seed': args.seed,
                       'results': rows, 'status': 'in_progress'}
            args.output.write_text(json.dumps(partial, indent=2, sort_keys=True) + '\n',
                                   encoding='utf-8')
    baseline = rows[0]['timesteps_per_second']
    for row in rows:
        row['speedup_vs_one_worker'] = row['timesteps_per_second'] / baseline
    fastest = max(rows, key=lambda row: row['timesteps_per_second'])['n_envs']
    payload = {'provider': 'singapore-demo-v2', 'generator': 'singapore-v2',
               'warmup_steps': args.warmup_steps, 'measured_steps': args.measured_steps,
               'seed': args.seed, 'results': rows,
               'fastest_stable_worker_count': fastest,
               'cli_default_worker_count': 4}
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n',
                           encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
