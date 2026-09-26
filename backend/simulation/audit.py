"""Deterministic scenario-diversity audit and frozen Goldilocks gates."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

from .assignment_planning import optimal_fixed_rank_plan
from .baseline import (NaiveLaunchOnDetectionPolicy,
                       OptimalFixedRankAssignmentPolicy,
                       replay_assignment_plan)
from .engine import SimulationEngine
from .scenario_distribution import (
    SingaporeScenarioV2Generator, load_scenario_distribution,
    profile_predicate_failures)
from .singapore_provider import SingaporeConsequenceProvider
from .singapore_scenario import canonical_episode_hash, episode_to_dict


SCENARIO_AUDIT_VERSION = 'singapore-scenario-audit/2'
AUDIT_SEED_START = 80_000
CANONICAL_AUDIT_COUNTS = {
    'warmup': 100,
    'balanced': 180,
    'full-standard': 180,
    'burst-contention': 180,
    'low-slack': 180,
    'consequence-contrast': 180,
}
NAIVE_COMPLETION_THRESHOLDS = {
    'warmup': 0.98,
    'balanced': 0.95,
    'full-standard': 0.90,
    'burst-contention': 0.75,
    'low-slack': 0.70,
    'consequence-contrast': 0.90,
}
DIMENSIONS_CONSIDERED = (
    ('Active scale', '2–8 threats and 3–8 one-use interceptors'),
    ('Detection cadence', 'gapped, burst, and separated-wave event streams'),
    ('Ingress geography', 'eight centroid-bearing sectors'),
    ('Terminal geography', 'fixed 4×4 projected main-island grid'),
    ('Reachability structure', 'consequence-eligible bipartite edge density and degrees'),
    ('Matching structure', 'complete, critical-edge, and capped matching counts'),
    ('Timing slack', 'minimum and median earliest eligible pair margins'),
    ('Consequence contrast', 'online naive cost versus exact immutable-rank cost'),
    ('Distribution shift', 'held-out ingress sectors and two-wave cadence'),
)


def canonical_audit_plan() -> Tuple[Mapping[str, Any], ...]:
    rows = []
    seed = AUDIT_SEED_START
    for profile, count in CANONICAL_AUDIT_COUNTS.items():
        for _ in range(count):
            rows.append({'seed': seed, 'profile': profile})
            seed += 1
    return tuple(rows)


def _quantile(values: Iterable[float], fraction: float) -> Optional[float]:
    rows = sorted(float(value) for value in values)
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    position = fraction * (len(rows) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return rows[lower]
    weight = position - lower
    return rows[lower] * (1.0 - weight) + rows[upper] * weight


def _stats(values: Iterable[float]) -> Mapping[str, Any]:
    rows = [float(value) for value in values]
    return {
        'count': len(rows),
        'minimum': min(rows) if rows else None,
        'p05': _quantile(rows, 0.05),
        'p25': _quantile(rows, 0.25),
        'median': _quantile(rows, 0.5),
        'p75': _quantile(rows, 0.75),
        'p95': _quantile(rows, 0.95),
        'maximum': max(rows) if rows else None,
        'mean': (math.fsum(rows) / len(rows)) if rows else None,
    }


def _binned(values: Iterable[float], boundaries: Sequence[float]) -> Mapping[str, int]:
    result = {}
    rows = tuple(float(value) for value in values)
    for lower, upper in zip(boundaries, boundaries[1:]):
        label = '[%g,%g%s' % (lower, upper, ']' if upper == boundaries[-1] else ')')
        result[label] = sum(
            lower <= value <= upper if upper == boundaries[-1]
            else lower <= value < upper for value in rows)
    return result


def _policy_outcomes(spec, provider) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    naive_engine = SimulationEngine(spec, provider)
    naive = NaiveLaunchOnDetectionPolicy().run(naive_engine)
    exact_engine = SimulationEngine(spec, provider)
    plan = optimal_fixed_rank_plan(spec, provider)
    exact = replay_assignment_plan(exact_engine, plan)
    exact_cost_matches = bool(
        exact.raw_score is not None
        and math.isclose(plan.predicted_cost, exact.raw_score,
                         rel_tol=0.0, abs_tol=1e-12))
    return ({
        'policy_identity': NaiveLaunchOnDetectionPolicy.identity,
        'information_scope': NaiveLaunchOnDetectionPolicy.information_scope,
        'termination_reason': naive.termination_reason,
        'terminated': naive.terminated,
        'truncated': naive.truncated,
        'completed': naive.completed,
        'cost': naive.raw_score,
        'action_count': len(naive.actions),
    }, {
        'policy_identity': OptimalFixedRankAssignmentPolicy.identity,
        'information_scope': OptimalFixedRankAssignmentPolicy.information_scope,
        'termination_reason': exact.termination_reason,
        'terminated': exact.terminated,
        'truncated': exact.truncated,
        'completed': bool(
            exact.terminated and not exact.truncated
            and exact.termination_reason == 'all_threats_resolved'),
        'predicted_cost': plan.predicted_cost,
        'replayed_cost': exact.raw_score,
        'cost': exact.raw_score,
        'exact': plan.exact,
        'proof_scope': plan.proof_scope,
        'predicted_cost_matches_replay': exact_cost_matches,
    })


def audit_episode(generator: SingaporeScenarioV2Generator, seed: int,
                  profile: str) -> Mapping[str, Any]:
    spec = generator.generate(seed, profile)
    provider = generator._provider()
    regenerated = generator.generate(seed, profile)
    deterministic = bool(
        episode_to_dict(spec) == episode_to_dict(regenerated)
        and canonical_episode_hash(spec) == canonical_episode_hash(regenerated))
    # Generation has already computed this complete consequence-eligible graph.
    # Copy its immutable evidence here; unit tests independently recompute every
    # reported metric from the episode and provider.
    graph = dict(spec.metadata['matching_summary'])
    naive, exact = _policy_outcomes(spec, provider)
    both_completed = bool(naive['completed'] and exact['completed'])
    absolute = (None if not both_completed else
                float(naive['cost']) - float(exact['cost']))
    relative = (None if not both_completed else
                absolute / max(abs(float(naive['cost'])), 1e-12))
    detection_times = [row.detection_time_s for row in spec.threats]
    gaps = [later - earlier for earlier, later in zip(
        detection_times, detection_times[1:])]
    comparison = {
        'both_completed': both_completed,
        'absolute_improvement': absolute,
        'relative_improvement': relative,
    }
    failures = profile_predicate_failures(
        profile, generator.distribution.profile(profile), graph,
        detection_times,
        [row.state.threat_id for row in spec.threats[:4]], comparison)
    metadata = spec.metadata
    return {
        'status': 'audited',
        'seed': seed,
        'profile': profile,
        'episode_id': spec.episode_id,
        'canonical_episode_hash': canonical_episode_hash(spec),
        'deterministic_regeneration': deterministic,
        'generator_version': metadata['generator'],
        'distribution_version': metadata['distribution_identity'],
        'distribution_checksum': metadata['distribution_checksum'],
        'provider_identity': metadata['provider_identity'],
        'provider_version': metadata['provider_version'],
        'provider_config_checksum': metadata['provider_config_checksum'],
        'provider_data_checksum': metadata['provider_data_checksum'],
        'scenario_config_checksum': metadata['scenario_config_checksum'],
        'generator_configuration_checksum': metadata[
            'generator_configuration_checksum'],
        'boundary_source_checksum': metadata['boundary_source_checksum'],
        'main_island_geometry_checksum': metadata[
            'main_island_geometry_checksum'],
        'provider_source_checksums': dict(metadata['provider_source_checksums']),
        'active_threat_count': len(spec.threats),
        'active_interceptor_count': len(spec.interceptors),
        'candidate_count_per_pair': spec.candidate_count,
        'detection_times_s': detection_times,
        'detection_gap_statistics_s': _stats(gaps),
        'ingress_sectors': list(metadata['ingress_sectors']),
        'terminal_grid_cells': list(metadata['terminal_grid_cells']),
        'ingress_sector_coverage': sorted(set(metadata['ingress_sectors'])),
        'terminal_grid_coverage': sorted(set(metadata['terminal_grid_cells'])),
        'feasible_edge_count': graph['feasible_edge_count'],
        'edge_density': graph['edge_density'],
        'threat_degrees': graph['threat_degrees'],
        'interceptor_degrees': graph['interceptor_degrees'],
        'critical_edge_count': graph['critical_edge_count'],
        'complete_matching_count_capped_10000': graph[
            'complete_matching_count_capped_10000'],
        'complete_matchable': graph['complete_matchable'],
        'pair_best_time_margin_min_s': graph[
            'pair_best_time_margin_min_s'],
        'pair_best_time_margin_median_s': graph[
            'pair_best_time_margin_median_s'],
        'candidate_cost_spread_by_threat': graph[
            'candidate_cost_spread_by_threat'],
        'candidate_cost_spread_max': graph['candidate_cost_spread_max'],
        'generation_attempt_count': metadata['generation_attempt_count'],
        'rejected_attempt_count': metadata['rejected_attempt_count'],
        'rejected_attempts': list(metadata['rejected_attempts']),
        'unavailable_consequence_components': list(
            metadata['unavailable_consequence_components']),
        'profile_predicate_failures': list(failures),
        'profile_predicates_satisfied': not failures,
        'naive': naive,
        'exact_reference': exact,
        'naive_to_exact': comparison,
    }


def _gate(passed: bool, observed: Any, requirement: str) -> Mapping[str, Any]:
    return {'passed': bool(passed), 'observed': observed,
            'requirement': requirement}


def evaluate_goldilocks_gates(audit: Mapping[str, Any]) -> Mapping[str, Any]:
    records = [row for row in audit.get('episodes', ())
               if row.get('status') == 'audited']
    requested = int(audit.get('requested_episode_count', 0))
    exclusions = list(audit.get('exclusions', ()))
    failed_generations = list(audit.get('failed_generations', ()))
    gates: Dict[str, Mapping[str, Any]] = {}
    gates['episode_count'] = _gate(
        requested == 1000 and len(records) == 1000,
        {'requested': requested, 'audited': len(records)},
        'exactly 1,000 requested and 1,000 audited episodes')
    gates['zero_silent_exclusions'] = _gate(
        not exclusions and not failed_generations,
        {'exclusions': len(exclusions),
         'failed_generations': len(failed_generations)},
        'zero exclusions and zero failed generations')
    hashes = [row.get('canonical_episode_hash') for row in records]
    gates['unique_hashes'] = _gate(
        len(hashes) == len(set(hashes)) and all(hashes),
        {'unique': len(set(hashes)), 'total': len(hashes)},
        '100% unique canonical hashes')
    deterministic = sum(bool(row.get('deterministic_regeneration')) for row in records)
    gates['deterministic_regeneration'] = _gate(
        deterministic == len(records),
        {'passed': deterministic, 'total': len(records)},
        '100% deterministic regeneration')
    feasible = sum(bool(row.get('complete_matchable')) for row in records)
    exact_complete = sum(bool(row.get('exact_reference', {}).get('completed'))
                         and bool(row.get('exact_reference', {}).get('exact'))
                         and bool(row.get('exact_reference', {}).get(
                             'predicted_cost_matches_replay')) for row in records)
    gates['matching_and_exact_completion'] = _gate(
        feasible == len(records) and exact_complete == len(records),
        {'complete_matchable': feasible, 'exact_completed': exact_complete,
         'total': len(records)},
        '100% complete matchability and exact-reference completion')
    compliant = sum(bool(row.get('profile_predicates_satisfied')) for row in records)
    gates['profile_predicates'] = _gate(
        compliant == len(records),
        {'passed': compliant, 'total': len(records)},
        '100% profile-predicate compliance')
    attempts = [row.get('generation_attempt_count', math.inf) for row in records]
    attempt_p95 = _quantile(attempts, 0.95)
    gates['generation_attempts'] = _gate(
        bool(attempts) and max(attempts) <= 200
        and attempt_p95 is not None and attempt_p95 <= 25,
        {'maximum': max(attempts) if attempts else None, 'p95': attempt_p95},
        'maximum <= 200 and p95 <= 25')
    for profile, threshold in NAIVE_COMPLETION_THRESHOLDS.items():
        selected = [row for row in records if row.get('profile') == profile]
        completed = sum(bool(row.get('naive', {}).get('completed')) for row in selected)
        rate = completed / len(selected) if selected else 0.0
        gates['naive_completion_' + profile] = _gate(
            bool(selected) and rate >= threshold,
            {'completed': completed, 'total': len(selected), 'rate': rate},
            'naive completion >= %.0f%%' % (threshold * 100))
    full_size = [row for row in records
                 if row.get('active_threat_count') == 8
                 and row.get('profile') != 'warmup']
    paired = [row for row in full_size
              if row.get('naive_to_exact', {}).get('both_completed')]
    paired_rate = len(paired) / len(full_size) if full_size else 0.0
    gates['paired_complete_full_size'] = _gate(
        bool(full_size) and paired_rate >= 0.70,
        {'paired': len(paired), 'total': len(full_size), 'rate': paired_rate},
        'at least 70% of full-size core episodes paired-complete')
    better = [row for row in paired
              if row['naive_to_exact']['absolute_improvement'] > 0]
    better_rate = len(better) / len(paired) if paired else 0.0
    gates['exact_strictly_better'] = _gate(
        bool(paired) and better_rate >= 0.50,
        {'better': len(better), 'paired': len(paired), 'rate': better_rate},
        'exact strictly better in at least 50% of paired-complete full-size cases')
    median_relative = _quantile((
        row['naive_to_exact']['relative_improvement'] for row in paired), 0.5)
    gates['paired_median_relative_improvement'] = _gate(
        median_relative is not None and median_relative >= 0.10,
        median_relative, 'paired-complete median relative improvement >= 10%')
    contrast = [row for row in records
                if row.get('profile') == 'consequence-contrast']
    contrast_pass = sum(
        bool(row.get('naive_to_exact', {}).get('both_completed'))
        and row['naive_to_exact']['absolute_improvement'] >= 0.25
        and row['naive_to_exact']['relative_improvement'] >= 0.15
        for row in contrast)
    gates['consequence_contrast'] = _gate(
        bool(contrast) and contrast_pass == len(contrast),
        {'passed': contrast_pass, 'total': len(contrast)},
        'every consequence-contrast episode passes 0.25 absolute and 15% relative')
    sectors = Counter(
        sector for row in records
        if row.get('profile') not in ('geographic-shift',)
        for sector in row.get('ingress_sectors', ()))
    sector_total = sum(sectors.values())
    maximum_sector_share = max(sectors.values(), default=0) / max(1, sector_total)
    gates['ingress_balance'] = _gate(
        sector_total > 0 and maximum_sector_share <= 0.25,
        {'counts': {str(index): sectors[index] for index in range(8)},
         'maximum_share': maximum_sector_share},
        'no non-OOD ingress sector contains more than 25% of detections')
    non_warmup = [row for row in records if row.get('profile') != 'warmup']
    not_full = sum(row.get('feasible_edge_count')
                   < row.get('active_threat_count', 0)
                   * row.get('active_interceptor_count', 0)
                   for row in non_warmup)
    not_full_rate = not_full / len(non_warmup) if non_warmup else 0.0
    gates['not_fully_connected'] = _gate(
        bool(non_warmup) and not_full_rate >= 0.90,
        {'not_fully_connected': not_full, 'total': len(non_warmup),
         'rate': not_full_rate},
        'at least 90% of non-warmup graphs are not fully connected')
    return {'all_passed': all(row['passed'] for row in gates.values()),
            'gates': gates}


def summarize_audit(audit: Mapping[str, Any]) -> Mapping[str, Any]:
    records = [row for row in audit['episodes'] if row['status'] == 'audited']
    profiles = {}
    for profile in CANONICAL_AUDIT_COUNTS:
        selected = [row for row in records if row['profile'] == profile]
        profiles[profile] = {
            'episode_count': len(selected),
            'threat_count_distribution': {
                str(value): sum(row['active_threat_count'] == value for row in selected)
                for value in range(2, 9)},
            'edge_density': _stats(row['edge_density'] for row in selected),
            'generation_attempts': _stats(
                row['generation_attempt_count'] for row in selected),
            'pair_best_median_margin_s': _stats(
                row['pair_best_time_margin_median_s'] for row in selected),
            'detection_gaps_s': _stats(
                later - earlier for row in selected
                for earlier, later in zip(
                    row['detection_times_s'], row['detection_times_s'][1:])),
            'naive_completed': sum(row['naive']['completed'] for row in selected),
            'exact_completed': sum(row['exact_reference']['completed'] for row in selected),
            'paired_complete': sum(
                row['naive_to_exact']['both_completed'] for row in selected),
        }
    return {
        'profiles': profiles,
        'edge_density_bins': _binned(
            (row['edge_density'] for row in records),
            (0.0, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0)),
        'pair_best_median_margin_bins_s': _binned(
            (row['pair_best_time_margin_median_s'] for row in records),
            (-100.0, 0.0, 5.0, 10.0, 20.0, 40.0, 100.0)),
        'complete_matching_count_capped_10000': _stats(
            row['complete_matching_count_capped_10000'] for row in records),
        'complete_matching_count_bins': {
            '0': sum(row['complete_matching_count_capped_10000'] == 0
                     for row in records),
            '1': sum(row['complete_matching_count_capped_10000'] == 1
                     for row in records),
            '2-9': sum(2 <= row['complete_matching_count_capped_10000'] <= 9
                       for row in records),
            '10-99': sum(10 <= row['complete_matching_count_capped_10000'] <= 99
                         for row in records),
            '100-999': sum(100 <= row['complete_matching_count_capped_10000'] <= 999
                           for row in records),
            '1000-9999': sum(1000 <= row['complete_matching_count_capped_10000'] <= 9999
                             for row in records),
            '10000 (cap)': sum(row['complete_matching_count_capped_10000'] == 10000
                               for row in records),
        },
        'critical_edge_count': _stats(
            row['critical_edge_count'] for row in records),
        'ingress_sector_counts': {
            str(index): sum(index in row['ingress_sectors']
                            for row in records) for index in range(8)},
        'ingress_detection_counts': {
            str(index): sum(row['ingress_sectors'].count(index)
                            for row in records) for index in range(8)},
        'terminal_grid_detection_counts': {
            str(index): sum(row['terminal_grid_cells'].count(index)
                            for row in records) for index in range(16)},
        'generation_attempts': _stats(
            row['generation_attempt_count'] for row in records),
        'rejected_attempt_count': sum(
            row['rejected_attempt_count'] for row in records),
        'naive_termination_reasons': dict(sorted(Counter(
            row['naive']['termination_reason'] for row in records).items())),
        'exact_termination_reasons': dict(sorted(Counter(
            row['exact_reference']['termination_reason'] for row in records).items())),
        'unavailable_consequence_component_episode_counts': dict(sorted(Counter(
            component for row in records
            for component in row['unavailable_consequence_components']).items())),
        'paired_relative_improvement': _stats(
            row['naive_to_exact']['relative_improvement'] for row in records
            if row['naive_to_exact']['both_completed']),
    }


def _failed_episode(seed: int, profile: str, exc: Exception) -> Mapping[str, Any]:
    return {
        'status': 'generation_failed', 'seed': seed, 'profile': profile,
        'error_type': type(exc).__name__, 'error': str(exc)}


def _assemble_audit(
        generator: SingaporeScenarioV2Generator,
        plan: Sequence[Mapping[str, Any]],
        episodes: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    failures = [row for row in episodes
                if row.get('status') == 'generation_failed']
    result: MutableMapping[str, Any] = {
        'schema_version': SCENARIO_AUDIT_VERSION,
        'plan': 'canonical' if tuple(plan) == canonical_audit_plan() else 'custom',
        'development_only': True,
        'audit_seed_partition_start': AUDIT_SEED_START,
        'requested_episode_count': len(plan),
        'distribution_version': generator.distribution.version,
        'distribution_checksum': generator.distribution.checksum,
        'generator_version': generator.version,
        'dimensions_considered': [
            {'dimension': name, 'coverage': coverage}
            for name, coverage in DIMENSIONS_CONSIDERED],
        'profile_definitions': {
            name: generator.distribution.profiles[name]
            for name in CANONICAL_AUDIT_COUNTS},
        'episodes': episodes,
        'failed_generations': failures,
        'exclusions': [],
        'limitations': [
            'All episodes are operationally synthetic and are not threat or weapon-performance predictions.',
            'The supplied 100 m area is an input assumption rather than a validated physical effect.',
            'Civilian consequence estimates are assumption-grade; unavailable sectors remain explicit.',
            'The exact proof covers immutable additive fixed-rank costs and one-use interceptors only.',
            'No resource failures, sensor noise, trajectory updates, heterogeneous interceptor classes, or changed footprint physics are represented.',
            'Audit seeds are development-only and are excluded from training and frozen evaluation splits.',
        ],
    }
    result['summary'] = summarize_audit(result)
    result['goldilocks'] = evaluate_goldilocks_gates(result)
    return result


def run_scenario_audit(
        generator: SingaporeScenarioV2Generator,
        plan: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    episodes = []
    initial_provider = generator._provider()
    shared_catalog = getattr(initial_provider, 'catalog', None)
    for row in plan:
        seed, profile = row['seed'], row['profile']
        try:
            if isinstance(initial_provider, SingaporeConsequenceProvider):
                # Retain immutable source data while bounding per-candidate
                # spatial caches to one episode.
                generator.consequence_provider = SingaporeConsequenceProvider(
                    catalog=shared_catalog, scenario_config=generator.config)
            episodes.append(audit_episode(generator, seed, profile))
        except Exception as exc:
            episodes.append(_failed_episode(seed, profile, exc))
    return _assemble_audit(generator, plan, episodes)


_PARALLEL_GENERATOR: Optional[SingaporeScenarioV2Generator] = None
_PARALLEL_CATALOG: Any = None


def _initialize_audit_worker(distribution_path: str, checksum: str,
                             config: Any) -> None:
    global _PARALLEL_GENERATOR, _PARALLEL_CATALOG
    distribution = load_scenario_distribution(
        Path(distribution_path), expected_checksum=checksum)
    provider = SingaporeConsequenceProvider(scenario_config=config)
    _PARALLEL_CATALOG = provider.catalog
    _PARALLEL_GENERATOR = SingaporeScenarioV2Generator(
        distribution=distribution, config=config,
        consequence_provider=provider)


def _parallel_audit_episode(row: Mapping[str, Any]) -> Mapping[str, Any]:
    seed, profile = row['seed'], row['profile']
    try:
        if _PARALLEL_GENERATOR is None:
            raise RuntimeError('parallel audit worker was not initialized')
        _PARALLEL_GENERATOR.consequence_provider = SingaporeConsequenceProvider(
            catalog=_PARALLEL_CATALOG,
            scenario_config=_PARALLEL_GENERATOR.config)
        return audit_episode(_PARALLEL_GENERATOR, seed, profile)
    except Exception as exc:
        return _failed_episode(seed, profile, exc)


def run_scenario_audit_parallel(
        generator: SingaporeScenarioV2Generator,
        plan: Sequence[Mapping[str, Any]],
        workers: Optional[int] = None) -> Mapping[str, Any]:
    """Audit in deterministic plan order using isolated provider processes."""
    if generator.eligibility_checker is not None:
        raise ValueError('parallel audit requires the checked consequence provider')
    generator._provider()
    count = min(6, os.cpu_count() or 1) if workers is None else workers
    if type(count) is not int or count <= 0:
        raise ValueError('audit worker count must be a positive integer')
    if count == 1:
        return run_scenario_audit(generator, plan)
    rows = tuple(plan)
    with ProcessPoolExecutor(
            max_workers=count, initializer=_initialize_audit_worker,
            initargs=(generator.distribution.source_path,
                      generator.distribution.checksum,
                      generator.config)) as executor:
        episodes = tuple(executor.map(_parallel_audit_episode, rows, chunksize=1))
    return _assemble_audit(generator, rows, episodes)


def _percent(numerator: int, denominator: int) -> str:
    return '0.00%' if denominator == 0 else '%.2f%%' % (100.0 * numerator / denominator)


def render_audit_markdown(audit: Mapping[str, Any]) -> str:
    """Render the checked report from the canonical JSON object only."""
    summary = audit['summary']
    lines = [
        '# Singapore v2 scenario audit', '',
        'This report is generated from `scenario-audit-v2.json`; it contains no runtime timestamps or machine timings.', '',
        '## Dimensions considered', '',
        '| Dimension | Coverage |', '|---|---|',
    ]
    for row in audit['dimensions_considered']:
        lines.append('| %s | %s |' % (row['dimension'], row['coverage']))
    lines += ['', '## Profiles and intended split use', '',
              '| Profile | Episodes | Counts | Cadence | Intended use |',
              '|---|---:|---|---|---|']
    for name, definition in audit['profile_definitions'].items():
        count_range = '%d–%d' % (
            definition['threat_count_min'], definition['threat_count_max'])
        detection = definition['detection']
        cadence = detection['kind']
        if cadence == 'gaps':
            cadence += ' %.1f–%.1f s' % (
                detection['gap_min_s'], detection['gap_max_s'])
        elif cadence == 'burst':
            cadence += ' %d inside %.1f s' % (
                detection['burst_count'], detection['wave_width_s'])
        else:
            cadence += ' %.1f–%.1f s separation' % (
                detection['wave_separation_min_s'],
                detection['wave_separation_max_s'])
        resources = ('one extra interceptor' if definition['interceptor_rule'] == 'one-extra'
                     else 'equal interceptors')
        lines.append('| %s | %d | %s threats; %s | %s | %s |' % (
            name, summary['profiles'][name]['episode_count'], count_range,
            resources, cadence, definition['split_use']))
    lines += ['', '## Profile outcomes', '',
              '| Profile | Audited | Naive complete | Exact complete | Edge density p05 / median / p95 | Attempt p95 |',
              '|---|---:|---:|---:|---|---:|']
    for name, row in summary['profiles'].items():
        density, attempts = row['edge_density'], row['generation_attempts']
        lines.append('| %s | %d | %d (%s) | %d (%s) | %.3f / %.3f / %.3f | %.2f |' % (
            name, row['episode_count'], row['naive_completed'],
            _percent(row['naive_completed'], row['episode_count']),
            row['exact_completed'], _percent(row['exact_completed'], row['episode_count']),
            density['p05'], density['median'], density['p95'], attempts['p95']))
    lines += ['', '## Complete distributions (including empty bins)', '',
              '### Matching edge density', '', '| Bin | Episodes |', '|---|---:|']
    lines.extend('| %s | %d |' % row for row in summary['edge_density_bins'].items())
    lines += ['', '### Median pair-best time margin', '', '| Bin (seconds) | Episodes |', '|---|---:|']
    lines.extend('| %s | %d |' % row
                 for row in summary['pair_best_median_margin_bins_s'].items())
    lines += ['', '### Complete matching counts', '',
              'Counts are exact below 10,000 and capped at 10,000.', '',
              '| Bin | Episodes |', '|---|---:|']
    lines.extend('| %s | %d |' % row
                 for row in summary['complete_matching_count_bins'].items())
    lines += ['', 'Complete-matching count quantiles: `' + json.dumps(
                  summary['complete_matching_count_capped_10000'],
                  sort_keys=True) + '`', '',
              'Critical-edge count quantiles: `' + json.dumps(
                  summary['critical_edge_count'], sort_keys=True) + '`', '',
              '### Spatial and cadence coverage', '',
              'Ingress detection counts: `' + json.dumps(
                  summary['ingress_detection_counts'], sort_keys=True) + '`', '',
              'Terminal-grid detection counts: `' + json.dumps(
                  summary['terminal_grid_detection_counts'], sort_keys=True) + '`', '',
              'Threat-count and consecutive detection-gap distributions by profile:']
    for name, row in summary['profiles'].items():
        lines.append('- `%s`: threat counts `%s`; gap quantiles (seconds) `%s`' % (
            name, json.dumps(row['threat_count_distribution'], sort_keys=True),
            json.dumps(row['detection_gaps_s'], sort_keys=True)))
    lines += ['', '## Naive and exact outcomes', '',
              'Naive termination reasons: `' + json.dumps(
                  summary['naive_termination_reasons'], sort_keys=True) + '`', '',
              'Exact termination reasons: `' + json.dumps(
                  summary['exact_termination_reasons'], sort_keys=True) + '`', '',
              'Unavailable consequence-component episode counts: `' + json.dumps(
                  summary['unavailable_consequence_component_episode_counts'],
                  sort_keys=True) + '`', '',
              'Paired-complete relative-improvement quantiles: `' + json.dumps(
                  summary['paired_relative_improvement'], sort_keys=True) + '`', '',
              'Naive failures are reported as constraint outcomes and are excluded from consequence-improvement claims.', '',
              '## Generation failures and retries', '',
              'Failed generations: `%d`.' % len(audit['failed_generations']),
              'Rejected deterministic attempts: `%d`.' % summary['rejected_attempt_count'],
              'Attempt quantiles: `' + json.dumps(
                  summary['generation_attempts'], sort_keys=True) + '`', '']
    if audit['failed_generations']:
        for row in audit['failed_generations']:
            lines.append('- seed `%s`, profile `%s`: `%s: %s`' % (
                row['seed'], row['profile'], row['error_type'], row['error']))
        lines.append('')
    lines += ['## Frozen Goldilocks gates', '',
              '| Gate | Passed | Observed | Requirement |', '|---|---|---|---|']
    for name, row in audit['goldilocks']['gates'].items():
        observed = json.dumps(row['observed'], sort_keys=True, ensure_ascii=False)
        lines.append('| `%s` | %s | `%s` | %s |' % (
            name, 'yes' if row['passed'] else 'no', observed, row['requirement']))
    lines += ['', 'Overall gate result: **%s**.' % (
        'PASS' if audit['goldilocks']['all_passed'] else 'FAIL'), '',
        '## Synthetic and assumption-grade limitations', '']
    lines.extend('- ' + row for row in audit['limitations'])
    return '\n'.join(lines) + '\n'


def write_canonical_audit(audit: Mapping[str, Any], output: Path,
                          summary: Path) -> None:
    output = Path(output)
    summary = Path(summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(
        audit, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + '\n', encoding='utf-8')
    summary.write_text(render_audit_markdown(audit), encoding='utf-8')
