#!/usr/bin/env python3
"""Reproducible cold/warm timing for the Singapore simulation adapter."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.learning import (ADVANCE_ACTION, CentralizedInterceptionEnv,
                              load_normalized_policy)
from backend.simulation import (ImmediateInterceptionPolicy,
                                SingaporeConsequenceProvider,
                                SingaporeScenarioGenerator, SimulationEngine)


def elapsed(call):
    started = time.perf_counter()
    value = call()
    return value, (time.perf_counter() - started) * 1000.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--output', type=Path,
                        default=Path('data/results/singapore-simulation-benchmark.json'))
    parser.add_argument('--model-dir', type=Path,
                        default=Path('data/results/rl/singapore-smoke'))
    args = parser.parse_args()
    tracemalloc.start()
    provider, provider_ms = elapsed(SingaporeConsequenceProvider)
    generator = SingaporeScenarioGenerator(consequence_provider=provider)
    spec, generator_ms = elapsed(lambda: generator.generate(args.seed))

    scoring_provider = SingaporeConsequenceProvider(catalog=provider.catalog)
    engine = SimulationEngine(spec, scoring_provider)
    _, candidate_set_ms = elapsed(engine.advance)  # first detection: 8 x 20
    threat_id = engine.visible_threat_ids()[0]
    runtime = engine.threats[threat_id]
    candidates = tuple(row for key in sorted(runtime.candidates)
                       for row in runtime.candidates[key])
    _, warm_ms = elapsed(lambda: scoring_provider.assess_candidates(
        runtime.scheduled, candidates, {}))

    rollout_provider = SingaporeConsequenceProvider(catalog=provider.catalog)
    rollout_engine = SimulationEngine(spec, rollout_provider)
    baseline, baseline_ms = elapsed(
        lambda: ImmediateInterceptionPolicy().run(rollout_engine))

    env = CentralizedInterceptionEnv(
        SingaporeConsequenceProvider(catalog=provider.catalog), episode_spec=spec)
    (initial_observation, _), reset_ms = elapsed(env.reset)
    initial_mask = env.action_masks()
    steps = []
    while env.engine is not None and not (env.engine.terminated or env.engine.truncated):
        valid = np.flatnonzero(env.action_masks())
        assignments = valid[valid < ADVANCE_ACTION]
        action = int(assignments[0] if len(assignments) else ADVANCE_ACTION)
        _, step_ms = elapsed(lambda: env.step(action))
        steps.append(step_ms)
    environment_result = {
        'steps': len(steps), 'terminated': env.engine.terminated,
        'truncated': env.engine.truncated,
        'termination_reason': env.engine.termination_reason,
    }
    env.close()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    inference = {'status': 'smoke artifact not found'}
    if (args.model_dir / 'training-metadata.json').is_file():
        provider_factory = lambda: SingaporeConsequenceProvider(catalog=provider.catalog)
        scenario_factory = lambda: SingaporeScenarioGenerator(
            consequence_provider=provider_factory())
        policy = load_normalized_policy(
            args.model_dir, seed=args.seed,
            provider_factory=provider_factory,
            scenario_factory=scenario_factory)
        try:
            inference_samples = []
            predicted_action = None
            for _ in range(30):
                started = time.perf_counter()
                predicted_action, _ = policy.predict(
                    initial_observation, deterministic=True,
                    action_masks=initial_mask)
                inference_samples.append(
                    (time.perf_counter() - started) * 1000.0)
            predicted_action = int(predicted_action)
            inference = {
                'status': 'artifact reload and masked prediction passed',
                'model_dir': str(args.model_dir),
                'samples': len(inference_samples),
                'predicted_action': predicted_action,
                'predicted_action_valid': bool(initial_mask[predicted_action]),
                'p50_ms': statistics.median(inference_samples),
                'p95_ms': float(np.percentile(inference_samples, 95)),
            }
        finally:
            policy.close()
    payload = {
        'schema_version': 'singapore-simulation-benchmark/1',
        'seed': args.seed,
        'provider_version': provider.version,
        'generator_version': generator.version,
        'candidate_count_first_detection': len(candidates),
        'episode_candidate_count': 8 * 8 * 20,
        'timings_ms': {
            'catalog_and_provider_cold_start': provider_ms,
            'complete_episode_generation': generator_ms,
            'first_complete_candidate_set_cold': candidate_set_ms,
            'same_candidate_set_warm_cache': warm_ms,
            'immediate_baseline_full_episode': baseline_ms,
            'environment_reset_fixed_episode': reset_ms,
            'environment_step_p50': statistics.median(steps),
            'environment_step_p95': float(np.percentile(steps, 95)),
        },
        'memory_peak_bytes': peak,
        'baseline': {
            'terminated': baseline.terminated, 'truncated': baseline.truncated,
            'raw_score': baseline.raw_score,
        },
        'environment': environment_result,
        'inference': inference,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        payload, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if (baseline.terminated and environment_result['terminated']
                 and inference.get('predicted_action_valid', True)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
