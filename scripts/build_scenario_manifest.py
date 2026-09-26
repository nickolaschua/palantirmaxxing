#!/usr/bin/env python3
"""Build or verify the immutable Singapore v2 scenario manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.simulation import (SingaporeConsequenceProvider,
                                SingaporeScenarioV2Generator,
                                load_scenario_distribution)
from backend.simulation.scenario_manifest import (
    build_frozen_scenario_manifest_parallel)


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', type=Path,
                        default=Path('data/scenarios/rl/singapore-distribution-v1.json'))
    parser.add_argument('--audit', type=Path,
                        default=Path('data/results/rl/scenario-audit-v2.json'))
    parser.add_argument('--output', type=Path,
                        default=Path('data/scenarios/rl/suites.json'))
    parser.add_argument('--check', action='store_true')
    parser.add_argument(
        '--workers', type=int, default=None,
        help='isolated worker processes (default: up to six)')
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    distribution = load_scenario_distribution(args.distribution)
    provider = SingaporeConsequenceProvider()
    generator = SingaporeScenarioV2Generator(
        distribution=distribution, config=provider.scenario_config,
        consequence_provider=provider)
    document = build_frozen_scenario_manifest_parallel(
        generator, audit, workers=args.workers)
    expected = canonical_bytes(document)
    if args.check:
        try:
            actual = args.output.read_bytes()
        except OSError:
            actual = b''
        if actual != expected:
            print('scenario manifest drift: ' + str(args.output), file=sys.stderr)
            return 1
        print('scenario manifest is current: ' + str(args.output))
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
