#!/usr/bin/env python3
"""Generate, resume, or verify a versioned Singapore v2 training pool."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.simulation import (SingaporeConsequenceProvider,
                                SingaporeScenarioV2Generator,
                                load_scenario_distribution)
from backend.simulation.scenario_pool import (generate_scenario_pool,
                                              verify_scenario_pool)
from backend.simulation.singapore_scenario import DEFAULT_BOUNDARIES_PATH


SOURCE_PATHS = (
    Path('backend/simulation/scenario_pool.py'),
    Path('backend/simulation/scenario_distribution.py'),
    Path('backend/simulation/singapore_scenario.py'),
    Path('backend/simulation/singapore_provider.py'),
    Path('data/scenarios/rl/singapore-distribution-v1.json'),
    DEFAULT_BOUNDARIES_PATH.relative_to(ROOT),
)


def _file_checksums():
    return {
        str(path): 'sha256:' + hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in SOURCE_PATHS}


def _git_value(*args):
    try:
        return subprocess.check_output(
            ('git',) + args, cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def _dependencies():
    result = {'python': sys.version.split()[0]}
    for package in ('numpy', 'pyproj', 'shapely'):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = 'missing'
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id', default='sg2-pilot-512-v1')
    parser.add_argument('--count', type=int, default=512)
    parser.add_argument('--seed-start', type=int, default=1_000_000_000)
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--distribution', type=Path,
                        default=Path('data/scenarios/rl/singapore-distribution-v1.json'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--reproduce-all', action='store_true',
                        help='regenerate every record during verification')
    args = parser.parse_args()
    output = args.output or Path('data/scenarios/rl/pools') / args.release_id
    distribution = load_scenario_distribution(args.distribution)
    provider = SingaporeConsequenceProvider()
    generator = SingaporeScenarioV2Generator(
        distribution=distribution, config=provider.scenario_config,
        consequence_provider=provider)
    if args.verify:
        print(json.dumps(verify_scenario_pool(
            output, generator=generator, reproduce_all=args.reproduce_all),
            indent=2, sort_keys=True))
        return 0
    revision = _git_value('rev-parse', 'HEAD')
    dirty = bool(_git_value('status', '--porcelain'))
    manifest = generate_scenario_pool(
        generator=generator, output_dir=output, release_id=args.release_id,
        count=args.count, seed_start=args.seed_start,
        source_revision=revision, source_tree_dirty=dirty,
        source_files=_file_checksums(), dependencies=_dependencies(),
        workers=args.workers, resume=args.resume)
    print(json.dumps({
        'release_id': manifest['release_id'],
        'record_count': manifest['record_count'],
        'manifest_checksum': manifest['manifest_checksum'],
        'output': str(output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
