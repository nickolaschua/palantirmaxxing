#!/usr/bin/env python3
"""Generate the frontend golden artifact from authoritative backend results."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_static_mvp import DEFAULT_SCENARIO, evaluate, load_inputs
from backend.presentation import PresentationSettings, planning_result_to_dict

DEFAULT_OUTPUT = ROOT / 'data/results/static-mvp-planning-result.json'


def present(result, scenario):
    return planning_result_to_dict(
        result, PresentationSettings(**scenario['presentation']),
        threat_id=scenario['threat']['threat_id'],
        footprint_radius_m=scenario['footprint_radius_m'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    scenario, values = load_inputs(args.scenario)
    payload = present(evaluate(values), scenario)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
