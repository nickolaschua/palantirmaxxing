#!/usr/bin/env python3
"""Explicit local MVP prerequisites; no acquisition or fixture fallback."""
import argparse
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PREPARE = '.venv-rl/bin/python scripts/population_data.py acquire && .venv-rl/bin/python scripts/population_data.py prepare'
INPUTS = {
    'data/processed/population-projected.json': PREPARE,
    'data/processed/population-display.geojson': PREPARE,
    'frontend/public/population.geojson': PREPARE,
    'data/raw/boundaries.geojson': PREPARE,
    'data/scenarios/demo-singapore.json': 'Restore this source file from version control',
    'frontend/src/demo/military.json': 'Restore this source file from version control',
}
for folder, names in {
    'parks_civic': ('input_sites.csv', 'input_conditions.csv'),
    'critical_sectors': ('input_facilities.csv', 'input_profiles.csv'),
}.items():
    for name in names:
        INPUTS[f'backend/data_sources/consequence/{folder}/{name}'] = 'Restore this source file from version control'


def check_inputs(root=ROOT):
    errors = [f'Missing required input: {root / name}. Recovery: {recovery}'
              for name, recovery in INPUTS.items() if not (root / name).is_file()]
    if errors:
        raise RuntimeError('\n'.join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, default=ROOT)
    args = parser.parse_args()
    errors = []
    for module in ('numpy', 'shapely', 'pyproj', 'gymnasium', 'torch', 'stable_baselines3',
                   'sb3_contrib', 'osmnx', 'networkx', 'geopandas', 'pandas', 'requests',
                   'pyogrio', 'openpyxl', 'pytest'):
        try:
            importlib.import_module(module)
        except ImportError as exc:
            errors.append(f'Missing Python dependency {module}: {exc}. Recovery: '
                          '.venv-rl/bin/python -m pip install -r scripts/requirements-integration.txt')
    for command in ('node', 'npm'):
        if not shutil.which(command):
            errors.append(f'Missing {command}. Recovery: install Node.js 22.12+ and npm')
    for dependency in ('node_modules/.bin/vite', 'node_modules/@playwright/test/package.json'):
        if not (ROOT / 'frontend' / dependency).exists():
            errors.append(f'Missing frontend dependency: {ROOT / "frontend" / dependency}. Recovery: npm --prefix frontend ci')
    try:
        check_inputs(args.input_root)
    except RuntimeError as exc:
        errors.append(str(exc))
    if errors:
        raise RuntimeError('\n'.join(errors))
    from scripts.benchmark_static_mvp import load_inputs
    from backend.simulation import SingaporeConsequenceProvider, SingaporeScenarioGenerator
    load_inputs(args.input_root / 'data/scenarios/demo-singapore.json')
    provider = SingaporeConsequenceProvider()
    SingaporeScenarioGenerator(consequence_provider=provider)
    result = subprocess.run(['node', '--experimental-strip-types', 'tests/preflight.mjs'],
                            cwd=ROOT / 'frontend', text=True, capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    print(result.stdout)
    print(json.dumps({'status': 'passed', 'requiredInputs': list(INPUTS)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Prerequisite failure: {exc}', file=sys.stderr)
        sys.exit(1)
