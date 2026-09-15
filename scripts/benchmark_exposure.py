#!/usr/bin/env python3
"""Offline PEC timing and 128/256-edge sensitivity report; no source acquisition."""
import argparse
import json
import platform
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.exposure import prepare_population, calculate_episode, CalculationSettings
from population_exposure import load_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--population', type=Path, default=ROOT/'data/processed/population-projected.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data/results/pec-benchmark.json')
    args = parser.parse_args()
    if args.output.resolve() == args.population.resolve() or (args.output.exists() and args.population.exists() and args.output.samefile(args.population)):
        parser.error('Output must not overwrite population input')
    raw = load_json(args.population)
    preparations = []
    for _ in range(3):
        start = time.perf_counter()
        dataset = prepare_population(raw)
        preparations.append(time.perf_counter() - start)
    if not dataset.zones:
        parser.error('Benchmark needs at least one eligible zone')
    # Spread deterministic centres across zone IDs. Variable radii produce a mix
    # of boundary crossings and overlap, rather than 100 isolated tiny footprints.
    events = []
    for i in range(100):
        index = i * len(dataset.zones) // 100
        point = dataset.geometries[index].representative_point()
        events.append(dict(event_id=f'event-{i:03d}', footprint_id=f'footprint-{i:03d}',
                           center_x_m=point.x, center_y_m=point.y, radius_m=[250, 750, 1500, 2500][i % 4]))
    episode = dict(schema_version='pec-episode/1', episode_id='pec-benchmark-100',
                   population_dataset_id=dataset.dataset_id, population_dataset_version=dataset.version,
                   coordinate_reference_system='EPSG:3414', events=events)
    measurements, results = {}, {}
    for edges in (128, 256):
        durations = []
        for _ in range(3):
            start = time.perf_counter()
            result = calculate_episode(dataset, episode, CalculationSettings(edges))
            durations.append(time.perf_counter() - start)
            if result['status'] == 'invalid_input':
                raise RuntimeError(result['errors'])
            if edges in results and result != results[edges]:
                raise RuntimeError('Non-reproducible benchmark calculation')
            results[edges] = result
        measurements[str(edges)] = dict(seconds=durations, median_seconds=statistics.median(durations), status=result['status'])
    fields = ['known_area_unique_exposure', 'known_area_person_exposures', 'known_area_multiple_exposure', 'uncovered_area_m2']
    sensitivity = {}
    for field in fields:
        a, b = results[128][field], results[256][field]
        sensitivity[field] = dict(edges_128=a, edges_256=b, absolute_change=b-a,
                                  relative_change=None if a == 0 else (b-a)/a)
    differences = [b['known_area_exposure'] - a['known_area_exposure'] for a,b in zip(results[128]['events'], results[256]['events'])]
    report = dict(dataset_id=dataset.dataset_id, dataset_version=dataset.version, dataset_checksum_sha256=dataset.checksum,
                  zones=len(dataset.zones), population=sum(z['population'] for z in dataset.zones), events=len(events),
                  environment=dict(python=platform.python_version(), platform=platform.platform(), processor=platform.processor(),
                                   libraries=results[128]['metadata']['libraries']),
                  scenario='100 evenly indexed eligible-zone representative points; radii cycle 250, 750, 1500, 2500 metres',
                  timing_scope='In-process wall time; preparation includes validation/index/union/checksum; calculation excludes file I/O',
                  preparation_seconds=preparations, preparation_median_seconds=statistics.median(preparations),
                  calculations=measurements, sensitivity=sensitivity,
                  maximum_event_exposure_increase=max(differences), minimum_event_exposure_increase=min(differences),
                  event_coverage_status_changes=sum(a['status'] != b['status'] for a,b in zip(results[128]['events'], results[256]['events'])),
                  changed_events=[dict(event_id=a['event_id'], status_128=a['status'], status_256=b['status'],
                                       uncovered_area_128_m2=a['uncovered_area_m2'], uncovered_area_256_m2=b['uncovered_area_m2'])
                                  for a,b in zip(results[128]['events'], results[256]['events']) if a['status'] != b['status']])
    write_json(args.output, report)
    print(json.dumps(report, indent=2, allow_nan=False))
    print('Benchmark report:', args.output)


if __name__ == '__main__':
    main()
