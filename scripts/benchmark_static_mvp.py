#!/usr/bin/env python3
"""Small deterministic engineering benchmark for the static machine-side MVP."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter_ns

import pyproj
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.domain import InterceptorState, SyntheticSuccessProfile, ThreatState
from backend.exposure import prepare_population
from backend.orchestration import (evaluate_static_scenario,
                                   trade_space_result_to_dict)

DEFAULT_SCENARIO = ROOT / 'data' / 'scenarios' / 'static-mvp-scenario.json'
DEFAULT_OUTPUT = ROOT / 'data' / 'results' / 'static-mvp-benchmark.json'
STAGES = ('trajectory_reachability_ms', 'success_enrichment_ms',
          'footprint_exposure_assessment_ms', 'pareto_filtering_ms',
          'representative_extraction_ms', 'total_ms')


def load_inputs(path):
    document = json.loads(path.read_text())
    population_path = ROOT / document['population_fixture']
    population = prepare_population(json.loads(population_path.read_text()))
    identity = document.get('population_identity')
    if identity is not None and (population.dataset_id, population.version, population.checksum) != (
            identity['dataset_id'], identity['version'], identity['normalized_checksum_sha256']):
        raise ValueError('Prepared population differs from pinned scenario identity')
    values = (
        ThreatState(**document['threat']),
        InterceptorState(**document['interceptor']),
        SyntheticSuccessProfile(**document['synthetic_success_profile']),
        document['footprint_radius_m'],
        population,
        document['number_of_samples'],
    )
    return document, values


def evaluate(values):
    return evaluate_static_scenario(
        values[0], values[1], values[2], values[3], values[4], values[5])


def candidate_table(result):
    evaluated = {row.opportunity.opportunity_id: row for row in result.candidates}
    pareto = set(result.pareto_candidate_ids)
    assignments = asdict(result.category_assignments)
    rows = []
    for opportunity in result.candidate_opportunities:
        candidate = evaluated.get(opportunity.opportunity_id)
        rows.append({
            'sample': opportunity.sample_index,
            'time_s': opportunity.time_from_start_s,
            'position_x_m': opportunity.position_x_m,
            'position_y_m': opportunity.position_y_m,
            'reachable': opportunity.reachable,
            'supplied_success_probability': (
                candidate.supplied_success_probability if candidate else None),
            'people_potentially_exposed': (
                candidate.exposure.people_potentially_exposed if candidate else None),
            'exposure_status': (
                candidate.exposure.exposure_status if candidate else None),
            'pareto_efficient': opportunity.opportunity_id in pareto,
            'categories': [name for name, candidate_id in assignments.items()
                           if candidate_id == opportunity.opportunity_id],
        })
    return rows


def summarize(runs):
    return {
        stage: {
            'median': statistics.median(row[stage] for row in runs),
            'minimum': min(row[stage] for row in runs),
            'maximum': max(row[stage] for row in runs),
        }
        for stage in STAGES
    }


def benchmark(scenario, values):
    # Population is already prepared. Exactly one end-to-end warm-up is excluded.
    evaluate(values)
    runs = []
    deterministic = None
    result = None
    for run_number in range(1, 8):
        started = perf_counter_ns()
        result = evaluate(values)
        external_total_ms = (perf_counter_ns() - started) / 1_000_000
        timing = asdict(result.diagnostics)
        # The caller-side measurement includes return handoff and is used for the
        # end-to-end target; internal stage timings come from the same invocation.
        timing['total_ms'] = external_total_ms
        timing['run'] = run_number
        runs.append(timing)
        evidence = trade_space_result_to_dict(result, include_diagnostics=False)
        if deterministic is None:
            deterministic = evidence
        elif evidence != deterministic:
            raise RuntimeError('deterministic evidence changed between measured runs')
    return {
        'schema_version': 'static-mvp-benchmark/1',
        'scenario_fixture': str(DEFAULT_SCENARIO.relative_to(ROOT)),
        'scenario_description': scenario['description'],
        'method': {
            'population_prepared_outside_timing': True,
            'warm_up_runs': 1,
            'measured_runs': 7,
            'clock': 'time.perf_counter_ns',
            'interpretation': 'Small engineering benchmark; not rigorous performance characterization.',
        },
        'environment': {
            'python': sys.version.split()[0],
            'platform': platform.platform(),
            'shapely': shapely.__version__,
            'geos': shapely.geos_version_string,
            'pyproj': pyproj.__version__,
        },
        'runs': runs,
        'summary': summarize(runs),
        'target_ms': 100,
        'target_met_by_median': summarize(runs)['total_ms']['median'] < 100,
        'deterministic_result': deterministic,
        'candidate_table': candidate_table(result),
    }


def markdown(payload):
    lines = [
        '# Static machine-side MVP benchmark', '',
        payload['scenario_description'], '',
        'This fixture is wholly synthetic. Its 10,000 m/s interceptor speed, '
        '1,000 m/s threat speed, 500 m footprint radius, coordinates, turn rate, '
        'population geometry and population counts are intentionally scaled test '
        'inputs. They preserve the Phase A-C reachability pattern and exercise the '
        'trade-space; they are not operational performance estimates.', '',
        'One warm-up preceded seven measured runs. Population preparation and file '
        'I/O were outside timing. `perf_counter_ns` measured each invocation. These '
        'seven runs are a small engineering benchmark, not rigorous performance '
        'characterization.', '',
        '## Timing', '',
        '| Run | Trajectory + reachability | Success enrichment | Footprint + exposure | Pareto | Representatives | Total |',
        '|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in payload['runs']:
        lines.append('| {run} | {trajectory_reachability_ms:.6f} | {success_enrichment_ms:.6f} | '
                     '{footprint_exposure_assessment_ms:.6f} | {pareto_filtering_ms:.6f} | '
                     '{representative_extraction_ms:.6f} | {total_ms:.6f} |'.format(**row))
    lines.extend(['', '| Statistic | Trajectory + reachability | Success enrichment | Footprint + exposure | Pareto | Representatives | Total |',
                  '|---|---:|---:|---:|---:|---:|---:|'])
    for name in ('median', 'minimum', 'maximum'):
        values_by_stage = [payload['summary'][stage][name] for stage in STAGES]
        lines.append('| {} | {} |'.format(name.capitalize(), ' | '.join(
            '{:.6f}'.format(value) for value in values_by_stage)))
    result = payload['deterministic_result']
    lines.extend([
        '', 'The median end-to-end runtime is `{:.6f} ms`; the `<100 ms` target is **{}**.'.format(
            payload['summary']['total_ms']['median'],
            'met' if payload['target_met_by_median'] else 'not met'),
        '', '## Deterministic result summary', '',
        '- Total candidates: `{}`'.format(result['total_candidates']),
        '- Reachable candidates: `{}`'.format(result['reachable_candidates']),
        '- Complete-coverage candidates: `{}`'.format(result['complete_coverage_candidates']),
        '- Eligible candidates: `{}`'.format(result['eligible_candidates']),
        '- Pareto-efficient candidates: `{}`'.format(len(result['pareto_candidate_ids'])),
        '- Category assignments: `{}`'.format(json.dumps(result['category_assignments'], sort_keys=True)),
        '- Unique representative IDs: `{}`'.format(json.dumps(result['representative_candidate_ids'])),
        '', 'The complete unrounded structured result is stored in the adjacent generated '
        '`data/results/static-mvp-benchmark.json` benchmark artifact.', '',
        '## Candidate table', '',
        'Values are rounded only in this presentation table.', '',
        '| Sample | Time (s) | Position (m) | Reachable | Supplied success | People potentially exposed | Pareto | Categories |',
        '|---:|---:|---|:---:|---:|---:|:---:|---|',
    ])
    for row in payload['candidate_table']:
        success = ('—' if row['supplied_success_probability'] is None else
                   '{:.4f}'.format(row['supplied_success_probability']))
        exposure = ('—' if row['people_potentially_exposed'] is None else
                    '{:.3f}'.format(row['people_potentially_exposed']))
        categories = ', '.join(row['categories']) or '—'
        lines.append('| {sample} | {time_s:.1f} | ({position_x_m:.0f}, {position_y_m:.0f}) | '
                     '{reachable_label} | {success} | {exposure} | {pareto_label} | {categories_label} |'.format(
                         success=success, exposure=exposure, categories_label=categories,
                         reachable_label='yes' if row['reachable'] else 'no',
                         pareto_label='yes' if row['pareto_efficient'] else 'no', **row))
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--markdown', action='store_true')
    args = parser.parse_args(argv)
    scenario, values = load_inputs(args.scenario.resolve())
    payload = benchmark(scenario, values)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    if args.markdown:
        print(markdown(payload), end='')
    else:
        print(json.dumps({
            'output': str(args.output),
            'measured_runs_ms': [row['total_ms'] for row in payload['runs']],
            'median_ms': payload['summary']['total_ms']['median'],
            'minimum_ms': payload['summary']['total_ms']['minimum'],
            'maximum_ms': payload['summary']['total_ms']['maximum'],
            'target_met': payload['target_met_by_median'],
        }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
