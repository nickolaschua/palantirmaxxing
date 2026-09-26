#!/usr/bin/env python3
"""Write the checked imperfect-condition scenario overlay matrix."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.domain import (build_imperfect_condition_matrix,
                            validate_imperfect_condition_matrix)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--output', type=Path,
        default=(ROOT / 'data/imperfect_conditions'
                 / 'imperfect-condition-scenario-matrix-v1.json'))
    args = parser.parse_args()
    document = build_imperfect_condition_matrix()
    validate_imperfect_condition_matrix(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + '\n',
        encoding='utf-8')
    print(json.dumps({
        'output': str(args.output),
        'archetype_count': document['sampling_plan']['archetype_count'],
        'weighted_slot_count': document['sampling_plan']['weighted_slot_count'],
        'condition_weighted_incidence': document['sampling_plan'][
            'condition_weighted_incidence'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
