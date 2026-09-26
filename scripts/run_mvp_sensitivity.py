#!/usr/bin/env python3
"""Offline sensitivity within a fixed synthetic grid; no planner modifications."""
import argparse
from collections import Counter
from dataclasses import replace
from itertools import product
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_static_mvp import evaluate, load_inputs
from scripts.export_static_mvp_planning_result import present

DEMO_SCENARIO = ROOT / 'data/scenarios/demo-singapore.json'
RADII = (100, 250, 500, 750, 1000)
DECAYS = (('slow', .002), ('baseline', .004), ('fast', .008))
TURN_RATES = (10, 15, 20)
MIN_REDUCTION_PEOPLE = 100
MIN_REDUCTION_FRACTION = .20
OUTCOMES = ('distinct_representatives', 'single_representative', 'no_reachable_candidates',
            'no_eligible_candidates', 'no_later_lower_exposure_alternative',
            'exposure_contrast_below_reporting_threshold', 'failed_configuration')


def parameter_grid():
    return [dict(footprintRadiusM=radius, successDecayLabel=label,
                 decreasePerSecond=decay, turnRateDegS=turn)
            for radius, (label, decay), turn in product(RADII, DECAYS, TURN_RATES)]


def representative(candidate):
    if candidate is None:
        return None
    return {key: candidate[key] for key in ('id', 'timeFromStartS', 'suppliedSuccessProbability')} | {
        'peoplePotentiallyExposed': candidate['exposure']['peoplePotentiallyExposed'],
        'exposureStatus': candidate['exposure']['status'],
    }


def compare(reference, comparison):
    """Report factual differences, including zero differences for a shared ID."""
    if reference is None or comparison is None:
        return None
    if reference['exposureStatus'] != 'complete' or comparison['exposureStatus'] != 'complete':
        return None
    re = reference['peoplePotentiallyExposed']
    ce = comparison['peoplePotentiallyExposed']
    if re is None or ce is None or not math.isfinite(re) or not math.isfinite(ce):
        return None
    relative = (ce - re) / re if re != 0 else None
    return dict(
        referenceCandidateId=reference['id'], comparisonCandidateId=comparison['id'],
        deltaTimeS=comparison['timeFromStartS'] - reference['timeFromStartS'],
        deltaSuccessPercentagePoints=100 * (comparison['suppliedSuccessProbability'] - reference['suppliedSuccessProbability']),
        deltaPeoplePotentiallyExposed=ce - re,
        relativeExposureChange=relative if relative is None or math.isfinite(relative) else None,
    )


def summarize_payload(payload):
    by_id = {candidate['id']: candidate for candidate in payload['candidates']}
    assignments = payload['categoryAssignments']
    evidence = {key: representative(by_id.get(value)) for key, value in assignments.items()}
    delta = compare(evidence['earliestViable'], evidence['lowestExposure'])
    partial = sum(c.get('exposure', {}).get('status') == 'partial_coverage'
                  for c in payload['candidates'])
    distinct = len(payload['representativeCandidateIds']) >= 2
    later_lower = (delta is not None and delta['deltaTimeS'] > 0
                   and delta['deltaPeoplePotentiallyExposed'] < 0)
    meaningful = (distinct and later_lower and delta['relativeExposureChange'] is not None
                  and -delta['relativeExposureChange'] >= MIN_REDUCTION_FRACTION
                  and -delta['deltaPeoplePotentiallyExposed'] >= MIN_REDUCTION_PEOPLE)
    counts = dict(payload['diagnostics'], uniqueRepresentatives=len(payload['representativeCandidateIds']),
                  partialCoverageCandidates=partial)
    if counts['reachableCandidates'] == 0:
        outcome = 'no_reachable_candidates'
    elif counts['eligibleCandidates'] == 0:
        outcome = 'no_eligible_candidates'
    elif counts['uniqueRepresentatives'] == 1:
        outcome = 'single_representative'
    elif not later_lower:
        outcome = 'no_later_lower_exposure_alternative'
    elif not meaningful:
        outcome = 'exposure_contrast_below_reporting_threshold'
    else:
        outcome = 'distinct_representatives'
    reasons = [outcome]
    if partial:
        reasons.append('partial_population_coverage')
    if counts['eligibleCandidates'] > 0 and not later_lower and outcome != 'no_later_lower_exposure_alternative':
        reasons.append('no_later_lower_exposure_alternative')
    return dict(outcome=outcome, reasons=reasons, counts=counts,
                categoryAssignments=assignments,
                representativeCandidateIds=payload['representativeCandidateIds'],
                representativeEvidence=evidence, comparison=delta,
                distinctRepresentatives=distinct, laterLowerExposureAlternative=later_lower,
                meetsExposureContrastThreshold=meaningful)


def evaluate_configuration(scenario, values, parameters, evaluator=evaluate):
    """Replace immutable input records; retain failures without hiding programming errors."""
    row = dict(parameters=dict(parameters))
    try:
        changed = list(values)
        changed[1] = replace(values[1], max_turn_rate_rad_s=math.radians(parameters['turnRateDegS']))
        changed[2] = replace(values[2], decrease_per_second=parameters['decreasePerSecond'])
        changed[3] = parameters['footprintRadiusM']
        result = evaluator(tuple(changed))
        document = dict(scenario, footprint_radius_m=changed[3])
        row.update(summarize_payload(present(result, document)))
    except (ValueError, ArithmeticError) as exc:
        row.update(outcome='failed_configuration', reasons=['failed_configuration'],
                   counts=None, categoryAssignments=None, representativeCandidateIds=[],
                   representativeEvidence=None, comparison=None, distinctRepresentatives=False,
                   laterLowerExposureAlternative=False, meetsExposureContrastThreshold=False,
                   error={'type': type(exc).__name__, 'message': str(exc)})
    return row


def stats(values):
    values = list(values)
    return dict(count=len(values), minimum=min(values) if values else None,
                median=statistics.median(values) if values else None,
                maximum=max(values) if values else None)


def summarize_rows(rows):
    valid = [r['comparison'] for r in rows if r['comparison'] is not None]
    outcomes = Counter(r['outcome'] for r in rows)
    reasons = Counter(reason for r in rows for reason in r['reasons'])
    return dict(
        configurations=len(rows),
        distinctRepresentatives=sum(r['distinctRepresentatives'] for r in rows),
        meetsExposureContrastThreshold=sum(r['meetsExposureContrastThreshold'] for r in rows),
        validComparisons=len(valid),
        outcomeCounts={key: outcomes[key] for key in OUTCOMES},
        reasonCounts={key: reasons[key] for key in OUTCOMES + ('partial_population_coverage',)},
        exposureReductionPeople=stats(-c['deltaPeoplePotentiallyExposed'] for c in valid),
        exposureReductionPercent=stats(-100 * c['relativeExposureChange'] for c in valid
                                      if c['relativeExposureChange'] is not None),
        suppliedSuccessPenaltyPercentagePoints=stats(-c['deltaSuccessPercentagePoints'] for c in valid),
    )


def select_middle(result, payload):
    """Select a factual dominated interior peak; never supply a substitute winner."""
    by_id = {c['id']: c for c in payload['candidates']}
    early = by_id.get(payload['categoryAssignments']['earliestViable'])
    low = by_id.get(payload['categoryAssignments']['lowestExposure'])
    if early is None or low is None:
        return None
    dominance = {e.candidate_id: e.dominated_by_candidate_ids for e in result.pareto_evidence}
    eligible = [c for c in payload['candidates']
                if c['eligibleForRecommendation'] and dominance.get(c['id'])
                and early['timeFromStartS'] < c['timeFromStartS'] < low['timeFromStartS']
                and c['exposure']['peoplePotentiallyExposed'] > max(
                    early['exposure']['peoplePotentiallyExposed'], low['exposure']['peoplePotentiallyExposed'])]
    if not eligible:
        return None
    selected = min(eligible, key=lambda c: (-c['exposure']['peoplePotentiallyExposed'],
                                          c['timeFromStartS'], c['sampleIndex'], c['id']))
    return dict(evidence=representative(selected),
                dominatedByCandidateIds=list(dominance[selected['id']]),
                comparisonToEarly=compare(representative(early), representative(selected)))


def run_study(scenario, values, grid=None, evaluator=evaluate):
    identity = scenario['population_identity']
    population = values[4]
    if (population.dataset_id, population.version, population.checksum) != (
            identity['dataset_id'], identity['version'], identity['normalized_checksum_sha256']):
        raise ValueError('Prepared population differs from pinned demo identity; do not silently refresh it')
    rows = [evaluate_configuration(scenario, values, p, evaluator)
            for p in (parameter_grid() if grid is None else grid)]
    baseline_result = evaluate(values)
    baseline_payload = present(baseline_result, scenario)
    groups = {parameter: [dict(value=value, **summarize_rows(
        [r for r in rows if r['parameters'][parameter] == value]))
        for value in sorted({r['parameters'][parameter] for r in rows})]
        for parameter in ('footprintRadiusM', 'decreasePerSecond', 'turnRateDegS')}
    return dict(
        schemaVersion='mvp-sensitivity/1', scenarioId=baseline_payload['scenarioId'],
        populationProvenance=dict(baseline_payload['populationProvenance'],
                                  normalizedChecksumSha256=population.checksum),
        scope='Sensitivity within the tested synthetic parameter grid on one deliberately selected corridor; not operational or real-world robustness',
        matrix=dict(footprintRadiusM=list(RADII), successDecayProfiles=[dict(label=l, decreasePerSecond=d) for l, d in DECAYS],
                    turnRateDegS=list(TURN_RATES)),
        controlledInputs=scenario,
        reportingCriteria=dict(minimumExposureReductionPeople=MIN_REDUCTION_PEOPLE,
                               minimumRelativeExposureReduction=MIN_REDUCTION_FRACTION,
                               requiresDistinctRepresentatives=True, requiresLaterLowerExposure=True,
                               affectsPlanner=False),
        comparisonSemantics='lowestExposure minus earliestViable, including zero deltas for a shared representative; complete finite exposure required; zero reference has null relative change',
        rows=rows, summary=summarize_rows(rows), byParameter=groups,
        baseline=dict(**summarize_payload(baseline_payload), middleHighExposure=select_middle(baseline_result, baseline_payload)),
    )


def number(value):
    return 'unavailable' if value is None else f'{value:,.4f}'


def evidence_table(study):
    baseline = study['baseline']
    evidence = baseline['representativeEvidence']
    early = evidence['earliestViable']
    records = [('Early / earliest viable', early)]
    if evidence['highestSuccess'] != early:
        records.append(('Highest supplied success', evidence['highestSuccess']))
    else:
        records[0] = ('Early / highest supplied success', early)
    if baseline['middleHighExposure']:
        records.append(('Middle / dominated high exposure', baseline['middleHighExposure']['evidence']))
    records.append(('Lowest exposure', evidence['lowestExposure']))
    lines = ['| Candidate/category | Time (s) | Supplied success | People potentially exposed | Exposure change vs early |',
             '|---|---:|---:|---:|---:|']
    for label, candidate in records:
        if candidate is None:
            lines.append(f'| {label}: unavailable | — | — | — | — |')
            continue
        delta = compare(early, candidate)
        relative = delta['relativeExposureChange'] if delta else None
        lines.append(f"| {label} (`{candidate['id'].rsplit('__', 1)[-1]}`) | {number(candidate['timeFromStartS'])} | "
                     f"{number(candidate['suppliedSuccessProbability'])} | {number(candidate['peoplePotentiallyExposed'])} | "
                     f"{number(100 * relative) if relative is not None else 'unavailable'}% |")
    return '\n'.join(lines)


def render_report(study):
    summary = study['summary']
    radii = '/'.join(str(value) for value in study['matrix']['footprintRadiusM'])
    configurations = summary['configurations']
    lines = [
        '# MVP synthetic-parameter sensitivity', '',
        'Generated by `scripts/run_mvp_sensitivity.py`; machine-readable evidence: '
        '[mvp-sensitivity.json](../../data/results/mvp-sensitivity.json).', '',
        '## Scope and method', '', study['scope'] + '.', '',
        'The fixed demo corridor uses the unchanged prepared Census 2020 resident population dataset '
        f"`{study['populationProvenance']['datasetVersion']}`. Source CRS is EPSG:3414. "
        'Dataset identity and normalized checksum are pinned in the scenario and checked by the runner.', '',
        f'Full factorial grid: radii {radii} m × success decays 0.002/0.004/0.008 per second '
        f'× turn rates 10/15/20 deg/s: {configurations} configurations. Initial success 0.97, minimum 0.70, maximum 1.00, '
        'trajectory, speeds, origins, 20-second horizon and 50 samples stay fixed. '
        f'The {configurations} rows include the baseline; baseline evidence is also evaluated separately for the pitch table.', '',
        'Meaningful contrast is a reporting criterion: distinct representatives, a later lower-exposure alternative, '
        'at least 20% and 100 fewer people potentially exposed relative to the earliest representative. '
        'It does not change planner eligibility, categories or human controls.', '',
        '## Stable findings within the tested grid', '',
        f"The qualitative trade-off persisted in {summary['distinctRepresentatives']}/{summary['configurations']} tested synthetic configurations "
        '(at least two distinct representatives). '
        f"{summary['meetsExposureContrastThreshold']}/{summary['configurations']} met the stated exposure-contrast reporting threshold.", '',
        f"Complete early-to-low comparisons were available in {summary['validComparisons']}/{summary['configurations']} configurations. "
        'Statistics include zero differences when the same candidate holds both categories; they do not silently exclude collapsed trade-spaces. '
        'Relative reductions exclude zero reference exposure and report their own denominator.', '',
        '| Metric | Valid count | Minimum | Median | Maximum |', '|---|---:|---:|---:|---:|',
    ]
    for key, label in [('exposureReductionPeople', 'Exposure reduction (people)'),
                       ('exposureReductionPercent', 'Exposure reduction (%)'),
                       ('suppliedSuccessPenaltyPercentagePoints', 'Supplied-success penalty (percentage points)')]:
        s = summary[key]
        lines.append(f"| {label} | {s['count']} | {number(s['minimum'])} | {number(s['median'])} | {number(s['maximum'])} |")
    lines += ['', '## Outcome and coverage reasons', '',
              'Primary outcomes are mutually exclusive. Reason flags can overlap: partial population coverage can '
              'coexist with complete representatives and a meaningful trade-off. A coverage flag is not itself a failed configuration.', '',
              '| Primary outcome | Count |', '|---|---:|']
    lines += [f'| {key} | {value} |' for key, value in summary['outcomeCounts'].items()]
    lines += ['', '| Reason flag | Count |', '|---|---:|']
    lines += [f'| {key} | {value} |' for key, value in summary['reasonCounts'].items()]
    lines += ['', '## Parameter-sensitive findings', '',
              'Each group below varies the other two parameters over their tested values. These are descriptive '
              'grid summaries, not uncertainty intervals or evidence of real-world robustness.', '',
              '| Parameter | Value | Distinct / runs | Contrast / runs | Configurations with partial coverage | Median exposure reduction (%) | Median success penalty (pp) |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for parameter, groups in study['byParameter'].items():
        for group in groups:
            lines.append(f"| {parameter} | {group['value']} | {group['distinctRepresentatives']}/{group['configurations']} | "
                         f"{group['meetsExposureContrastThreshold']}/{group['configurations']} | "
                         f"{group['reasonCounts'].get('partial_population_coverage', 0)} | "
                         f"{number(group['exposureReductionPercent']['median'])} | "
                         f"{number(group['suppliedSuccessPenaltyPercentagePoints']['median'])} |")
    lines += ['', 'Radius changes both the geographic exposure integral and whether footprints cross coverage gaps. '
              'Success decay changes the supplied-success price of delay; it does not change exposure or reachability. '
              'Turn rate changes bounded-curvature reachability, potentially changing which early opportunities are available. '
              'The per-configuration rows retain these separate counts and outcomes.', '',
              '## Main demo evidence', '', evidence_table(study), '']
    middle = study['baseline']['middleHighExposure']
    if middle:
        lines += ['The middle example is an eligible, complete-coverage candidate strictly between the early and low-exposure '
                  'representatives. It has higher exposure than both and '
                  f"{len(middle['dominatedByCandidateIds'])} recorded backend dominators, including "
                  f"`{middle['dominatedByCandidateIds'][0]}` (full list in JSON). "
                  'The highest qualifying exposure is selected deterministically. This demonstrates that exposure does not '
                  'simply decrease with time; geography changes the comparison.', '']
    else:
        lines += ['No qualifying dominated middle high-exposure candidate exists in this baseline.', '']
    lines += ['## Known limitations', '',
              '- This corridor was deliberately selected for demonstration; no claim generalizes to other routes or Singapore as a whole.',
              '- Threat path, launch origin, speeds, turn rate, success parameters, footprint radius, clock and height are synthetic/supplied and not operationally calibrated.',
              '- Exposure is calculated from resident counts distributed uniformly within supplied zones. It is not live occupancy, casualties, expected loss, or a count of identified people saved.',
              '- Low resident exposure near industrial geography does not mean few workers or visitors; this dataset does not measure daytime occupancy.',
              '- Excluded/unknown population areas remain uncovered; partial exposure is never substituted for a complete estimate.',
              '- The existing PEC circle approximation and tolerances are unchanged. This study does not investigate their convergence.',
              '- Three decay settings and three turn rates are a small controlled grid, not probability distributions or operational validation.',
              '- No universal best action or automatic go/no-go decision is selected.', '',
              '## Regeneration', '', '```sh', '.venv/bin/python -B scripts/run_mvp_sensitivity.py', '```', '',
              'Requires the pinned local `data/processed/population-projected.json`. No download or population repair is performed.', '']
    return '\n'.join(lines)


def render_demo_summary(study):
    s = study['summary']
    footprint_radius_m = study['controlledInputs']['footprint_radius_m']
    return '\n'.join([
        '# Backend demo summary', '',
        'Use `planning-result/1` and load [demo-planning-result.json](../data/results/demo-planning-result.json). '
        'The sole frontend contract definition remains [API-DESIGN.md](../frontend/docs/API-DESIGN.md). '
        'This document explains the demo, not a second API definition.', '',
        '## Machine-side flow', '',
        'Supplied threat state → 50 future trajectory samples → bounded-curvature reachability → '
        'synthetic success enrichment → supplied circular consequence footprints → population exposure → '
        'Pareto filtering → representative alternatives → planning-result/1 → frontend / human review.', '',
        'Calculated by the backend: trajectory samples from supplied motion, reachability, geographic population exposure, '
        'Pareto membership, representative categories and factual comparison deltas. '
        'All 50 opportunities remain in the handoff; unreachable and dominated candidates are excluded from the decision frontier, not erased.', '',
        'Synthetic/supplied: fictional threat path and launch origin, 225 m/s threat speed, 500 m/s interceptor speed, '
        f'15 deg/s turn limit, {footprint_radius_m:g} m consequence radius and linear success profile (0.97 initial, 0.004/s decay, 0.70 floor). '
        'The UTC start 2026-09-15T00:00:00Z and 1000 m visualization height have no model significance. '
        'No physical debris trajectory or operational calibration is claimed.', '',
        '## Separate Singapore demo', '',
        'The fictional eastbound Ang Mo Kio–Serangoon path runs from EPSG:3414 (27300,39500) to (31800,39500) '
        'over 20 seconds. The launch origin is (26600,38500). Both are comfortably inside Canvas bounds. '
        'Real prepared Census 2020 resident population and MP2019 boundaries supply the geographic evidence. '
        'Population data are not altered to produce the story. The engineering fixture remains separate and unchanged.', '',
        evidence_table(study), '',
        'A middle candidate is shown only when computed exposure exceeds both endpoint representatives and backend dominance '
        'evidence exists. Exposure means estimated people potentially within the supplied area, not casualties or identified people saved. '
        'The human retains go/no-go authority.', '',
        '## Sensitivity evidence', '',
        f"The qualitative trade-off persisted in {s['distinctRepresentatives']}/{s['configurations']} tested synthetic configurations; "
        f"{s['meetsExposureContrastThreshold']}/{s['configurations']} met the reporting criterion of at least 20% and 100 fewer people potentially exposed. "
        'This is sensitivity within a small synthetic parameter grid on one selected corridor, not operational or real-world robustness. '
        'See [the generated study](specifications/mvp-sensitivity.md) for coverage effects, outcome reasons and limitations.', '',
        '## Reproduce the handoff', '', '```sh',
        '.venv/bin/python -B scripts/export_static_mvp_planning_result.py --scenario data/scenarios/demo-singapore.json --output data/results/demo-planning-result.json',
        '.venv/bin/python -B scripts/run_mvp_sensitivity.py',
        '.venv/bin/python -B scripts/benchmark_planning_result.py --scenario data/scenarios/demo-singapore.json --output data/results/demo-planning-result-benchmark.json',
        '```', '',
        'Prepared population must already exist locally at the pinned identity in `demo-singapore.json`. '
        'The [benchmark artifact](../data/results/demo-planning-result-benchmark.json) records planning, presentation and total '
        'over one warm-up and seven measured runs; population preparation, text encoding, file IO, network and frontend rendering are excluded.', '',
        'Frontend rendering, camera, animation, cards and controls belong to the frontend teammate. '
        'No model expansion accompanies this work; [the post-MVP backlog](MVP_SCOPE_AND_BACKLOG.md) remains deferred.', '',
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, default=DEMO_SCENARIO)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/results/mvp-sensitivity.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'docs/specifications/mvp-sensitivity.md')
    parser.add_argument('--summary', type=Path, default=ROOT / 'docs/DEMO_BACKEND_SUMMARY.md')
    args = parser.parse_args()
    scenario, values = load_inputs(args.scenario)
    study = run_study(scenario, values)
    args.output.write_text(json.dumps(study, indent=2, allow_nan=False) + '\n')
    args.report.write_text(render_report(study))
    args.summary.write_text(render_demo_summary(study))
    print(json.dumps(study['summary'], indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
