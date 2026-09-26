#!/usr/bin/env python3
"""Train the observation-only structured behavior-cloning policy."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning import (load_demonstrations,
                              train_structured_behavior_cloning,
                              train_with_conditional_dagger)
from backend.simulation import (load_scenario_manifest, resolve_scenario_ref,
                                runtime_factories)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--pool', type=Path, required=True,
                        help='verified source training pool (identity checked)')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--learning-rate', type=float, default=1e-3)
    parser.add_argument('--decision-batch-size', type=int, default=128)
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--patience', type=int, default=10)
    parser.add_argument('--diagnostic-limit', type=int, default=16,
                        help='reserved fixed training-scenario diagnostic size')
    parser.add_argument('--initial-artifact-dir', type=Path,
                        help='preceding checkpoint for DAgger fine-tuning')
    parser.add_argument('--validation-and-dagger', action='store_true',
                        help='run frozen validation and conditional DAgger (up to three rounds)')
    args = parser.parse_args()
    provider_factory, generator_factory = runtime_factories(
        'singapore-demo-v2', 'singapore-v2')
    dataset = load_demonstrations(args.dataset)
    pool_manifest = json.loads((args.pool / 'manifest.json').read_text(encoding='utf-8'))
    if (dataset.manifest['source_pool']['manifest_checksum']
            != pool_manifest.get('manifest_checksum')):
        parser.error('--pool does not match the demonstration training pool')
    if args.validation_and_dagger:
        if args.initial_artifact_dir is not None:
            parser.error('--initial-artifact-dir is managed by conditional DAgger')
        manifest = load_scenario_manifest()
        generator = generator_factory()
        validation = tuple(
            resolve_scenario_ref(row['scenario_ref'], manifest, generator)
            for row in manifest.entries if row['split'] == 'validation')
        result = train_with_conditional_dagger(
            args.dataset, args.pool, args.output_dir, validation,
            provider_factory, seed=args.seed,
            batch_size=args.decision_batch_size, max_epochs=args.epochs,
            patience=args.patience, diagnostic_limit=args.diagnostic_limit)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    artifacts = train_structured_behavior_cloning(
        args.dataset, args.output_dir, seed=args.seed,
        learning_rate=args.learning_rate, batch_size=args.decision_batch_size,
        max_epochs=args.epochs, patience=args.patience,
        initial_artifact_dir=args.initial_artifact_dir,
        provider_factory=provider_factory,
        diagnostic_limit=args.diagnostic_limit)
    print(json.dumps(asdict(artifacts), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
