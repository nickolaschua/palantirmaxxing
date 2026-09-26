#!/usr/bin/env python3
"""Generate the deterministic Singapore v2 scenario-diversity audit."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.simulation import (SingaporeConsequenceProvider,
                                SingaporeScenarioV2Generator,
                                load_scenario_distribution)
from backend.simulation.audit import (canonical_audit_plan,
                                      run_scenario_audit_parallel,
                                      write_canonical_audit)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', type=Path,
                        default=Path('data/scenarios/rl/singapore-distribution-v1.json'))
    parser.add_argument('--plan', choices=('canonical',), default='canonical')
    parser.add_argument('--output', type=Path,
                        default=Path('data/results/rl/scenario-audit-v2.json'))
    parser.add_argument('--summary', type=Path,
                        default=Path('docs/specifications/rl-scenario-audit.md'))
    parser.add_argument('--check-gates', action='store_true')
    parser.add_argument(
        '--workers', type=int, default=None,
        help='isolated worker processes (default: up to six)')
    args = parser.parse_args()
    distribution = load_scenario_distribution(args.distribution)
    provider = SingaporeConsequenceProvider()
    generator = SingaporeScenarioV2Generator(
        distribution=distribution, config=provider.scenario_config,
        consequence_provider=provider)
    audit = run_scenario_audit_parallel(
        generator, canonical_audit_plan(), workers=args.workers)
    write_canonical_audit(audit, args.output, args.summary)
    if args.check_gates and not audit['goldilocks']['all_passed']:
        for name, row in audit['goldilocks']['gates'].items():
            if not row['passed']:
                print('FAILED %s: %s' % (name, row['observed']), file=sys.stderr)
        return 1
    print(args.output)
    print(args.summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
