#!/usr/bin/env python3
"""Thin repository-root CLI for official population acquisition and preparation."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.data_sources.acquisition import acquire
from backend.data_sources.pipeline import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['acquire', 'prepare'])
    parser.add_argument('--refresh', action='store_true', help='Explicitly replace source snapshots after successful complete downloads')
    parser.add_argument('--population-file', type=Path, help='Official complete CSV or datastore response JSON')
    parser.add_argument('--boundary-file', type=Path, help='Official MP2019 GeoJSON')
    args = parser.parse_args()
    try:
        if args.command == 'acquire':
            manifest = acquire(ROOT/'data/raw', args.refresh, args.population_file, args.boundary_file)
            print('Sources cached and verified:', manifest['retrieved_at'])
        else:
            if args.refresh or args.population_file or args.boundary_file:
                parser.error('Use acquire for refresh/import, then prepare; preparation is offline')
            report = prepare(ROOT/'data/raw', ROOT/'data/processed', ROOT/'frontend/public/population.geojson')
            print(report['status'], report['counts'])
            print(report['totals'])
    except (ValueError, OSError) as error:
        print(f'Population data error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
