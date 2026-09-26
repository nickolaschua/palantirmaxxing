#!/usr/bin/env python3
"""Generate exact-teacher structured imitation demonstrations."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning import generate_demonstrations
from backend.simulation import runtime_factories


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--pool', type=Path, required=True,
                        help='verified development-training scenario pool')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--shard-episode-limit', type=int, default=64)
    parser.add_argument('--diagnostic-limit', type=int,
                        help='generate only this many episodes for a smoke diagnostic')
    args = parser.parse_args()
    provider_factory, _ = runtime_factories('singapore-demo-v2', 'singapore-v2')
    manifest = generate_demonstrations(
        args.pool, args.output_dir, provider_factory, seed=args.seed,
        shard_episode_limit=args.shard_episode_limit,
        episode_limit=args.diagnostic_limit)
    print(json.dumps({
        'schema_version': manifest['schema_version'],
        'dataset_checksum': manifest['dataset_checksum'],
        'episode_count': manifest['episode_count'],
        'decision_count': manifest['decision_count'],
        'shard_count': len(manifest['shards']),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
