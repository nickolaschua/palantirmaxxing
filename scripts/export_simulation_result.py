#!/usr/bin/env python3
"""Write the checked-in Singapore immediate-interception baseline result."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.presentation import simulation_result_to_dict
from backend.simulation import (ImmediateInterceptionPolicy,
                                SingaporeConsequenceProvider,
                                SingaporeScenarioGenerator, SimulationEngine)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--output', type=Path,
                        default=Path('data/results/demo-simulation-result.json'))
    args = parser.parse_args()
    provider = SingaporeConsequenceProvider()
    generator = SingaporeScenarioGenerator(consequence_provider=provider)
    engine = SimulationEngine(generator.generate(args.seed), provider)
    baseline = ImmediateInterceptionPolicy().run(engine)
    if baseline.truncated or not baseline.terminated:
        raise RuntimeError('baseline did not terminate: ' + str(baseline.termination_reason))
    payload = simulation_result_to_dict(engine, baseline_raw_score=baseline.raw_score)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        payload, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + '\n', encoding='utf-8')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
