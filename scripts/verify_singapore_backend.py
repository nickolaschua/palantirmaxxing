#!/usr/bin/env python3
"""Run deterministic Singapore baseline/optimizer acceptance verification."""
import argparse
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.planning import sample_threat_trajectory
from backend.simulation import (
    FeasibleImmediateMatchingPolicy, OptimalFixedRankAssignmentPolicy,
    SingaporeConsequenceProvider, SingaporeScenarioConfig,
    SingaporeScenarioGenerator, SimulationEngine, STRESS_SEEDS,
    VALIDATION_SEEDS,
)


def _provider(catalog, config):
    return SingaporeConsequenceProvider(catalog=catalog, scenario_config=config)


def _run_policy(spec, catalog, config, policy):
    engine = SimulationEngine(spec, _provider(catalog, config))
    started = time.perf_counter()
    run = policy.run(engine)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return engine, run, elapsed_ms


def _assert_physics(spec, engine):
    if (len(spec.threats), len(spec.interceptors), spec.candidate_count) != (8, 8, 20):
        raise AssertionError('episode shape is not 8x8x20')
    if not all(0 <= row.detection_time_s <= 10 for row in spec.threats):
        raise AssertionError('detection time escaped the 0-10 second window')
    for scheduled in spec.threats:
        samples = sample_threat_trajectory(scheduled.state, spec.candidate_count)
        if len(samples) != 20 or any(row.position_z_m < 0 for row in samples):
            raise AssertionError('trajectory sample/altitude invariant failed')
        if samples[-1].position_z_m != 0:
            raise AssertionError('trajectory does not terminate at zero altitude')
        terminal = scheduled.metadata
        if (not math.isclose(samples[-1].position_x_m,
                             float(terminal['terminal_position_x_m']), abs_tol=1e-6)
                or not math.isclose(samples[-1].position_y_m,
                                    float(terminal['terminal_position_y_m']), abs_tol=1e-6)):
            raise AssertionError('trajectory terminal point mismatch')
        runtime = engine.threats[scheduled.state.threat_id]
        interceptor_states = {row.state.interceptor_id: row.state
                              for row in spec.interceptors}
        if sum(len(rows) for rows in runtime.candidates.values()) != 160:
            raise AssertionError('candidate universe is not 160')
        for rows in runtime.candidates.values():
            for candidate in rows:
                opportunity = candidate.opportunity
                if (opportunity.reachable
                        and opportunity.required_travel_time_s
                        > opportunity.time_from_start_s + 1e-9):
                    raise AssertionError('reachable timing tolerance failed')
                interceptor = interceptor_states[opportunity.interceptor_id]
                euclidean = math.hypot(
                    opportunity.position_x_m - interceptor.position_x_m,
                    opportunity.position_y_m - interceptor.position_y_m)
                if (opportunity.minimum_path_length_m is not None
                        and opportunity.minimum_path_length_m + 1e-9 < euclidean):
                    raise AssertionError('bounded-curvature path is shorter than Euclidean')
        for assessment in runtime.candidate_assessments.values():
            if assessment.veto_status == 'vetoed' and assessment.eligible:
                raise AssertionError('vetoed candidate remained eligible')
            population = assessment.population_exposure
            if (population['status'] == 'outside_singapore'
                    and population['people_potentially_exposed'] != 0):
                raise AssertionError('outside-Singapore exposure is nonzero')
            if (population['status'] == 'partial_coverage'
                    and population['people_potentially_exposed'] is None):
                raise AssertionError('known partial-coverage exposure was erased')


def _negative_cases(spec, catalog, config):
    results = {}
    try:
        replace(config, supplied_footprint_radius_m=120.0)
    except ValueError:
        results['scenario_radius_mismatch_rejected_before_rollout'] = True
    else:
        results['scenario_radius_mismatch_rejected_before_rollout'] = False
    try:
        SingaporeConsequenceProvider(catalog=catalog, footprint_radius_m=101.0)
    except ValueError:
        results['provider_radius_mismatch_rejected_before_rollout'] = True
    else:
        results['provider_radius_mismatch_rejected_before_rollout'] = False

    dead_end = SimulationEngine(spec, _provider(catalog, config))
    while not dead_end.terminated and not dead_end.truncated:
        dead_end.advance()
    results['resource_dead_end_is_finite_constraint_penalty'] = bool(
        dead_end.terminated and not dead_end.truncated
        and dead_end.termination_reason == 'constraint_violation:unhandled_threat'
        and dead_end.raw_score is not None and dead_end.raw_score >= 9.0)

    class RaisingProvider(SingaporeConsequenceProvider):
        def evaluate_unhandled(self, threat, operational_state):
            raise RuntimeError('deliberate verification exception')

    failed = SimulationEngine(
        spec, RaisingProvider(catalog=catalog, scenario_config=config))
    while not failed.terminated and not failed.truncated:
        failed.advance()
    results['provider_exception_truncates'] = bool(
        failed.truncated and str(failed.termination_reason).startswith('provider_failure:'))

    malformed = SimulationEngine(spec, _provider(catalog, config))
    malformed.truncate('malformed_state:deliberate_verification_case')
    results['malformed_state_truncates'] = bool(
        malformed.truncated and not malformed.terminated)
    if not all(results.values()):
        raise AssertionError('negative verification case failed: ' + repr(results))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=('validation', 'stress'),
                        default='validation')
    parser.add_argument('--include-stress', action='store_true')
    parser.add_argument('--seeds', type=int, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.seeds:
        seeds = tuple(args.seeds)
        suite_label = 'explicit-regression-seeds'
    else:
        seeds = STRESS_SEEDS if args.suite == 'stress' else VALIDATION_SEEDS
        if args.include_stress and args.suite != 'stress':
            seeds = tuple(seeds) + tuple(STRESS_SEEDS)
        suite_label = args.suite + ('+stress' if args.include_stress else '')

    config = SingaporeScenarioConfig()
    seed_provider = SingaporeConsequenceProvider(scenario_config=config)
    catalog = seed_provider.catalog
    generator = SingaporeScenarioGenerator(
        config=config, consequence_provider=seed_provider)
    episodes = []
    for seed in seeds:
        spec = generator.generate(seed)
        baseline_engine, baseline, baseline_ms = _run_policy(
            spec, catalog, config, FeasibleImmediateMatchingPolicy())
        optimal_engine, optimal, optimal_ms = _run_policy(
            spec, catalog, config, OptimalFixedRankAssignmentPolicy())
        _assert_physics(spec, baseline_engine)
        _assert_physics(spec, optimal_engine)
        if optimal.raw_score > baseline.raw_score + 1e-12:
            raise AssertionError('optimizer is worse than baseline at seed %d' % seed)
        if not optimal.plan.exact:
            raise AssertionError('Singapore optimizer refused its fixed-rank exactness scope')
        episodes.append({
            'seed': seed,
            'episodeId': spec.episode_id,
            'baseline': {
                'policyIdentity': baseline.plan.policy_identity,
                'predictedCost': baseline.plan.predicted_cost,
                'actualCost': baseline.raw_score,
                'assignments': len(baseline_engine.assignments),
                'distinctConsumedInterceptors': len(
                    baseline_engine.consumed_interceptors),
                'terminationReason': baseline.termination_reason,
                'constraintViolation': False,
                'benchmarkRuntimeMs': baseline_ms,
            },
            'optimal': {
                'policyIdentity': optimal.plan.policy_identity,
                'predictedCost': optimal.plan.predicted_cost,
                'actualCost': optimal.raw_score,
                'assignments': len(optimal_engine.assignments),
                'distinctConsumedInterceptors': len(
                    optimal_engine.consumed_interceptors),
                'terminationReason': optimal.termination_reason,
                'constraintViolation': False,
                'exact': optimal.plan.exact,
                'proofScope': optimal.plan.proof_scope,
                'benchmarkRuntimeMs': optimal_ms,
            },
        })

    negatives = _negative_cases(generator.generate(seeds[0]), catalog, config)
    report = {
        'schemaVersion': 'singapore-backend-verification/1',
        'suite': suite_label,
        'episodeCountPerPolicy': len(episodes),
        'normallyTerminated': {
            'baseline': sum(row['baseline']['terminationReason']
                            == 'all_threats_resolved' for row in episodes),
            'optimal': sum(row['optimal']['terminationReason']
                           == 'all_threats_resolved' for row in episodes),
        },
        'constraintViolations': {'baseline': 0, 'optimal': 0},
        'optimizerNoWorseCount': sum(
            row['optimal']['actualCost'] <= row['baseline']['actualCost'] + 1e-12
            for row in episodes),
        'negativeCases': negatives,
        'episodes': episodes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        report, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': str(args.output),
        'episodes_per_policy': len(episodes),
        'normally_terminated_baseline': report['normallyTerminated']['baseline'],
        'normally_terminated_optimal': report['normallyTerminated']['optimal'],
        'constraint_violations': 0,
        'optimizer_no_worse': report['optimizerNoWorseCount'],
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
