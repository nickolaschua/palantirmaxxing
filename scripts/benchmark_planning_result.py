#!/usr/bin/env python3
"""One warm-up and seven measured static-planning-to-presentation handoffs."""
import argparse
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

from scripts.export_static_mvp_planning_result import present
from scripts.benchmark_static_mvp import DEFAULT_SCENARIO, evaluate, load_inputs

DEFAULT_OUTPUT = ROOT / 'data/results/static-mvp-planning-result-benchmark.json'


def benchmark(scenario_path=DEFAULT_SCENARIO):
    scenario_path = Path(scenario_path).resolve()
    scenario, values = load_inputs(scenario_path)
    expected = present(evaluate(values), scenario)
    runs = []
    for number in range(1, 8):
        started = perf_counter_ns()
        result = evaluate(values)
        planned = perf_counter_ns()
        payload = present(result, scenario)
        finished = perf_counter_ns()
        if payload != expected:
            raise RuntimeError('deterministic presentation changed between runs')
        runs.append({
            'run': number,
            'planningMs': (planned - started) / 1_000_000,
            'presentationMs': (finished - planned) / 1_000_000,
            'totalMs': (finished - started) / 1_000_000,
        })
    summary = {stage: {
        'median': statistics.median(row[stage] for row in runs),
        'minimum': min(row[stage] for row in runs),
        'maximum': max(row[stage] for row in runs),
    } for stage in ('planningMs', 'presentationMs', 'totalMs')}
    return {
        'schemaVersion': 'planning-result-benchmark/1',
        'scenarioFixture': str(scenario_path.relative_to(ROOT)),
        'populationDatasetVersion': expected['populationProvenance']['datasetVersion'],
        'method': {
            'warmUpRuns': 1, 'measuredRuns': 7,
            'populationPreparedOutsideTiming': True,
            'clock': 'time.perf_counter_ns',
            'boundary': 'static evaluation through validated JSON-ready dictionary',
            'excludes': ['file IO', 'JSON text encoding', 'network', 'frontend rendering'],
            'interpretation': 'Small engineering benchmark, not rigorous performance characterization',
        },
        'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                        'pyproj': pyproj.__version__, 'shapely': shapely.__version__,
                        'geos': shapely.geos_version_string},
        'runs': runs, 'summary': summary, 'targetMs': 100,
        'targetMetByMedian': summary['totalMs']['median'] < 100,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = benchmark(args.scenario)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
