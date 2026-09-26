"""Versioned, deterministic Singapore v2 scenario distribution.

The distribution is data-backed and deliberately separate from the frozen v1
generator.  All stochastic choices use independently derived streams so adding
or retrying one component does not consume randomness owned by another.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import median
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from shapely.geometry import Point
from shapely.ops import nearest_points

from backend.domain import InterceptorState, ThreatState
from backend.planning import generate_candidate_opportunities, sample_threat_trajectory

from .assignment_planning import candidate_universes
from .baseline import NaiveLaunchOnDetectionPolicy, OptimalFixedRankAssignmentPolicy
from .engine import SimulationEngine
from .models import AbsoluteCandidate, EpisodeSpec, InterceptorResource, ScheduledThreat
from .provider import provider_identity
from .singapore_scenario import (
    DEFAULT_BOUNDARIES_PATH, SINGAPORE_EPISODE_SCHEMA_VERSION,
    SINGAPORE_OBJECTIVE_REFERENCE_VERSION, MainIslandGeometry,
    SingaporeGenerationError, SingaporeScenarioConfig, _maximum_matching,
    _sha256, canonical_episode_hash, load_main_island,
)


SINGAPORE_SCENARIO_V2_VERSION = 'singapore-scenario/2'
SINGAPORE_DISTRIBUTION_VERSION = 'singapore-scenario-distribution/1'
DEFAULT_DISTRIBUTION_PATH = (
    Path(__file__).resolve().parents[2]
    / 'data' / 'scenarios' / 'rl' / 'singapore-distribution-v1.json')
PROFILE_NAMES = (
    'warmup', 'balanced', 'full-standard', 'burst-contention', 'low-slack',
    'consequence-contrast', 'geographic-shift', 'cadence-shift')


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False).encode('utf-8')


def canonical_distribution_checksum(document: Mapping[str, Any]) -> str:
    """Hash the checked document excluding its non-recursive checksum field."""
    payload = dict(document)
    payload.pop('checksum', None)
    return _sha256(_canonical_json(payload))


def _reject_nonfinite(value: str) -> None:
    raise ValueError('distribution contains a nonfinite number: ' + value)


def _strict_keys(value: Any, expected: Sequence[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    unknown = set(value) - set(expected)
    missing = set(expected) - set(value)
    if unknown:
        raise ValueError(label + ' has unknown fields: ' + ', '.join(sorted(unknown)))
    if missing:
        raise ValueError(label + ' is missing fields: ' + ', '.join(sorted(missing)))
    return value


def _number(value: Any, label: str, *, minimum: Optional[float] = None) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' must be a finite number')
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(label + ' is below its valid range')
    return result


@dataclass(frozen=True)
class SingaporeScenarioDistribution:
    document: Mapping[str, Any]
    checksum: str
    source_path: str

    @property
    def version(self) -> str:
        return str(self.document['distribution_version'])

    @property
    def profiles(self) -> Mapping[str, Mapping[str, Any]]:
        return self.document['profiles']

    def profile(self, name: str) -> Mapping[str, Any]:
        if type(name) is not str or name not in self.profiles:
            raise ValueError('unknown Singapore v2 profile: ' + str(name))
        return self.profiles[name]


def load_scenario_distribution(
        path: Path = DEFAULT_DISTRIBUTION_PATH,
        expected_checksum: Optional[str] = None) -> SingaporeScenarioDistribution:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding='utf-8'),
                              parse_constant=_reject_nonfinite)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('cannot load Singapore scenario distribution') from exc
    _strict_keys(document, (
        'checksum', 'distribution_version', 'environment',
        'episode_schema_version', 'generator_version',
        'max_generation_attempts', 'profiles'), 'distribution')
    if document['distribution_version'] != SINGAPORE_DISTRIBUTION_VERSION:
        raise ValueError('unsupported Singapore distribution version')
    if document['generator_version'] != SINGAPORE_SCENARIO_V2_VERSION:
        raise ValueError('distribution generator identity mismatch')
    if document['episode_schema_version'] != SINGAPORE_EPISODE_SCHEMA_VERSION:
        raise ValueError('distribution episode schema mismatch')
    if document['max_generation_attempts'] != 200:
        raise ValueError('Singapore v2 fixes max_generation_attempts at 200')
    environment = _strict_keys(document['environment'], (
        'max_candidates_per_pair', 'max_interceptors', 'max_threats',
        'terminal_grid_columns', 'terminal_grid_rows'), 'environment')
    if environment != {
            'max_candidates_per_pair': 20, 'max_interceptors': 8,
            'max_threats': 8, 'terminal_grid_columns': 4,
            'terminal_grid_rows': 4}:
        raise ValueError('Singapore v2 fixes the 8x8x20 environment and 4x4 grid')
    profiles = document['profiles']
    if not isinstance(profiles, dict) or set(profiles) != set(PROFILE_NAMES):
        raise ValueError('distribution must define exactly the eight Singapore v2 profiles')
    profile_keys = (
        'detection', 'ingress_sectors', 'interceptor_layout',
        'interceptor_rule', 'predicates', 'split_use', 'threat_count_max',
        'threat_count_min', 'trajectory_duration_max_s',
        'trajectory_duration_min_s')
    detection_keys = (
        'burst_count', 'gap_max_s', 'gap_min_s', 'kind',
        'wave_separation_max_s', 'wave_separation_min_s', 'wave_width_s')
    predicate_keys = (
        'critical_edge_min', 'edge_density_max', 'edge_density_min',
        'exact_absolute_improvement_min', 'exact_relative_improvement_min',
        'interceptors_reaching_three_burst_threats_min',
        'low_degree_threat_count_min', 'min_threat_degree',
        'pair_best_margin_median_max_s', 'threat_cost_spread_min')
    for name in PROFILE_NAMES:
        profile = _strict_keys(profiles[name], profile_keys, 'profile.' + name)
        low = profile['threat_count_min']
        high = profile['threat_count_max']
        if type(low) is not int or type(high) is not int or not 1 <= low <= high <= 8:
            raise ValueError(name + ' threat-count range is invalid')
        if profile['interceptor_rule'] not in ('equal', 'one-extra'):
            raise ValueError(name + ' interceptor_rule is invalid')
        if high + (profile['interceptor_rule'] == 'one-extra') > 8:
            raise ValueError(name + ' interceptor count exceeds environment capacity')
        if profile['interceptor_layout'] not in (
                'uniform', 'two-cluster', 'two-cluster-tight',
                'clustered-outliers', 'burst-clustered-outliers'):
            raise ValueError(name + ' interceptor_layout is invalid')
        if profile['split_use'] not in ('core', 'ood-only'):
            raise ValueError(name + ' split_use is invalid')
        sectors = profile['ingress_sectors']
        if (not isinstance(sectors, list) or not sectors
                or any(type(item) is not int or not 0 <= item < 8 for item in sectors)
                or len(set(sectors)) != len(sectors)):
            raise ValueError(name + ' ingress sectors are invalid')
        duration_min = _number(
            profile['trajectory_duration_min_s'], name + '.trajectory_duration_min_s',
            minimum=0.0)
        duration_max = _number(
            profile['trajectory_duration_max_s'], name + '.trajectory_duration_max_s',
            minimum=duration_min)
        if duration_max <= duration_min:
            raise ValueError(name + ' trajectory duration range is invalid')
        detection = _strict_keys(
            profile['detection'], detection_keys, 'profile.' + name + '.detection')
        if detection['kind'] not in ('gaps', 'burst', 'two-waves'):
            raise ValueError(name + ' detection kind is invalid')
        for key, value in detection.items():
            if key == 'kind' or value is None:
                continue
            _number(value, name + '.detection.' + key, minimum=0.0)
        kind = detection['kind']
        gap_min, gap_max = detection['gap_min_s'], detection['gap_max_s']
        if kind in ('gaps', 'burst'):
            if (gap_min is None or gap_max is None
                    or gap_min > gap_max):
                raise ValueError(name + ' detection-gap range is invalid')
        if kind == 'burst':
            if (type(detection['burst_count']) is not int
                    or not 4 <= detection['burst_count'] <= low
                    or detection['wave_width_s'] is None):
                raise ValueError(name + ' burst detection configuration is invalid')
        if kind == 'two-waves':
            if (low != 8 or high != 8
                    or detection['burst_count'] != 4
                    or detection['wave_width_s'] is None
                    or detection['wave_separation_min_s'] is None
                    or detection['wave_separation_max_s'] is None
                    or detection['wave_separation_min_s']
                    > detection['wave_separation_max_s']):
                raise ValueError(name + ' two-wave detection configuration is invalid')
        predicates = _strict_keys(
            profile['predicates'], predicate_keys,
            'profile.' + name + '.predicates')
        for key, value in predicates.items():
            if value is not None:
                _number(value, name + '.predicates.' + key, minimum=0.0)
        for key in ('critical_edge_min',
                    'interceptors_reaching_three_burst_threats_min',
                    'low_degree_threat_count_min', 'min_threat_degree'):
            if type(predicates[key]) is not int:
                raise ValueError(name + '.' + key + ' must be an integer')
        if (predicates['edge_density_min'] is None
                or predicates['edge_density_max'] is None
                or not 0 <= predicates['edge_density_min']
                <= predicates['edge_density_max'] <= 1):
            raise ValueError(name + ' edge-density range is invalid')
    checksum = canonical_distribution_checksum(document)
    recorded = document['checksum']
    if (not isinstance(recorded, str) or recorded != checksum
            or expected_checksum is not None and expected_checksum != checksum):
        raise ValueError('Singapore distribution checksum mismatch')
    return SingaporeScenarioDistribution(document, checksum, str(path.resolve()))


def ingress_sector(point: Point, main_island: MainIslandGeometry) -> int:
    center = main_island.geometry.centroid
    angle = math.atan2(point.y - center.y, point.x - center.x) % math.tau
    return int(angle / (math.pi / 4.0)) % 8


def terminal_grid_cell(point: Point, main_island: MainIslandGeometry) -> int:
    min_x, min_y, max_x, max_y = main_island.geometry.bounds
    column = min(3, max(0, int(4.0 * (point.x - min_x) / (max_x - min_x))))
    row = min(3, max(0, int(4.0 * (point.y - min_y) / (max_y - min_y))))
    return row * 4 + column


def _uniform_point(polygon: Any, rng: random.Random, tries: int = 10000) -> Point:
    min_x, min_y, max_x, max_y = polygon.bounds
    for _ in range(tries):
        point = Point(rng.uniform(min_x, max_x), rng.uniform(min_y, max_y))
        if polygon.covers(point):
            return point
    raise SingaporeGenerationError('deterministic polygon sampling exhausted')


def _matching_count(edges: Mapping[str, Sequence[str]], cap: int = 10000) -> int:
    threats = tuple(sorted(edges))
    interceptors = tuple(sorted({item for values in edges.values() for item in values}))
    slot = {name: index for index, name in enumerate(interceptors)}
    states = {0: 1}
    for threat_id in threats:
        following: Dict[int, int] = {}
        for mask, count in states.items():
            for interceptor_id in sorted(edges[threat_id]):
                bit = 1 << slot[interceptor_id]
                if mask & bit:
                    continue
                next_mask = mask | bit
                following[next_mask] = min(
                    cap, following.get(next_mask, 0) + count)
        states = following
        if not states:
            return 0
    return min(cap, sum(states.values()))


def scenario_graph_metrics(
        spec: EpisodeSpec, provider: Any,
        eligibility_checker: Optional[
            Callable[[ScheduledThreat, AbsoluteCandidate], bool]] = None,
        include_universes: bool = False) -> Mapping[str, Any]:
    """Compute the declared consequence-eligible bipartite graph metrics."""
    edges: Dict[str, Tuple[str, ...]] = {}
    threat_degrees: Dict[str, int] = {}
    interceptor_degrees = {
        row.state.interceptor_id: 0 for row in spec.interceptors}
    pair_best_margins = []
    threat_spreads: Dict[str, float] = {}
    universe_result: Dict[str, Any] = {}
    for scheduled in spec.threats:
        all_candidates = []
        by_interceptor = {}
        for resource in sorted(spec.interceptors, key=lambda row: row.state.interceptor_id):
            rows = tuple(AbsoluteCandidate.from_opportunity(
                opportunity, scheduled.detection_time_s)
                for opportunity in generate_candidate_opportunities(
                    scheduled.state, resource.state, spec.candidate_count))
            by_interceptor[resource.state.interceptor_id] = rows
            all_candidates.extend(rows)
        assessments = ({ } if eligibility_checker is not None else
                       provider.assess_candidates(scheduled, tuple(all_candidates), {
                           'candidate_count': spec.candidate_count}))
        eligible_interceptors = []
        costs = []
        frozen_rows = {}
        for interceptor_id, rows in by_interceptor.items():
            eligible_rows = []
            for candidate in rows:
                if eligibility_checker is None:
                    assessment = assessments[candidate.opportunity.opportunity_id]
                    eligible = bool(candidate.opportunity.reachable and assessment.eligible)
                    cost = float(assessment.training_cost)
                else:
                    eligible = bool(candidate.opportunity.reachable
                                    and eligibility_checker(scheduled, candidate))
                    cost = 0.0
                frozen_rows[candidate.opportunity.opportunity_id] = {
                    'candidate': candidate, 'eligible': eligible,
                    'training_cost': cost}
                if eligible:
                    eligible_rows.append(candidate)
                    costs.append(cost)
            if eligible_rows:
                eligible_interceptors.append(interceptor_id)
                interceptor_degrees[interceptor_id] += 1
                earliest = min(eligible_rows, key=lambda row: (
                    row.interception_time_s,
                    -float(row.opportunity.time_margin_s),
                    row.opportunity.opportunity_id))
                pair_best_margins.append(float(earliest.opportunity.time_margin_s))
        threat_id = scheduled.state.threat_id
        edges[threat_id] = tuple(sorted(eligible_interceptors))
        threat_degrees[threat_id] = len(eligible_interceptors)
        threat_spreads[threat_id] = 0.0 if not costs else max(costs) - min(costs)
        if include_universes:
            universe_result[threat_id] = frozen_rows
    matching = _maximum_matching(edges)
    critical = []
    if len(matching) == len(spec.threats):
        for threat_id in sorted(edges):
            for interceptor_id in edges[threat_id]:
                reduced = dict(edges)
                reduced[threat_id] = tuple(
                    item for item in edges[threat_id] if item != interceptor_id)
                if len(_maximum_matching(reduced)) < len(spec.threats):
                    critical.append((threat_id, interceptor_id))
    edge_count = sum(threat_degrees.values())
    denominator = len(spec.threats) * len(spec.interceptors)
    result = {
        'feasible_edges': {key: list(value) for key, value in sorted(edges.items())},
        'feasible_edge_count': edge_count,
        'edge_density': 0.0 if denominator == 0 else edge_count / denominator,
        'threat_degrees': dict(sorted(threat_degrees.items())),
        'interceptor_degrees': dict(sorted(interceptor_degrees.items())),
        'matching': dict(sorted(matching.items())),
        'complete_matchable': len(matching) == len(spec.threats),
        'complete_matching_count_capped_10000': _matching_count(edges),
        'critical_edges': [list(row) for row in critical],
        'critical_edge_count': len(critical),
        'pair_best_time_margin_min_s': (
            None if not pair_best_margins else min(pair_best_margins)),
        'pair_best_time_margin_median_s': (
            None if not pair_best_margins else median(pair_best_margins)),
        'candidate_cost_spread_by_threat': dict(sorted(threat_spreads.items())),
        'candidate_cost_spread_max': max(threat_spreads.values(), default=0.0),
    }
    if include_universes:
        result['universes'] = universe_result
    return result


def profile_predicate_failures(
        profile_name: str, profile: Mapping[str, Any], metrics: Mapping[str, Any],
        detection_times: Sequence[float], burst_threat_ids: Sequence[str] = (),
        comparison: Optional[Mapping[str, Any]] = None) -> Tuple[str, ...]:
    predicates = profile['predicates']
    failures = []
    density = metrics['edge_density']
    if not predicates['edge_density_min'] <= density <= predicates['edge_density_max']:
        failures.append('edge_density')
    degrees = tuple(metrics['threat_degrees'].values())
    if not degrees or min(degrees) < predicates['min_threat_degree']:
        failures.append('minimum_threat_degree')
    if not metrics['complete_matchable']:
        failures.append('complete_matching')
    if metrics['critical_edge_count'] < predicates['critical_edge_min']:
        failures.append('critical_edge_count')
    if sum(value <= 2 for value in degrees) < predicates['low_degree_threat_count_min']:
        failures.append('low_degree_threat_count')
    margin_max = predicates['pair_best_margin_median_max_s']
    if (margin_max is not None and (
            metrics['pair_best_time_margin_median_s'] is None
            or metrics['pair_best_time_margin_median_s'] > margin_max)):
        failures.append('pair_best_margin')
    spread_min = predicates['threat_cost_spread_min']
    if spread_min is not None and metrics['candidate_cost_spread_max'] < spread_min:
        failures.append('candidate_cost_spread')
    required_burst_resources = predicates[
        'interceptors_reaching_three_burst_threats_min']
    if required_burst_resources:
        burst_set = set(burst_threat_ids)
        count = sum(
            sum(threat_id in burst_set and interceptor_id in neighbors
                for threat_id, neighbors in metrics['feasible_edges'].items()) >= 3
            for interceptor_id in metrics['interceptor_degrees'])
        if count < required_burst_resources:
            failures.append('burst_resource_contention')
    gaps = [later - earlier for earlier, later in zip(
        detection_times, detection_times[1:])]
    detection = profile['detection']
    if detection['kind'] == 'gaps' and gaps and any(
            gap < detection['gap_min_s'] - 1e-9
            or gap > detection['gap_max_s'] + 1e-9 for gap in gaps):
        failures.append('detection_gaps')
    if detection['kind'] == 'burst':
        count = int(detection['burst_count'])
        if (len(detection_times) < count
                or detection_times[count - 1] - detection_times[0]
                > detection['wave_width_s'] + 1e-9):
            failures.append('burst_cadence')
    if detection['kind'] == 'two-waves':
        first, second = detection_times[:4], detection_times[4:]
        separation = second[0] - first[-1] if first and second else -1.0
        if (len(first) != 4 or len(second) != 4
                or first[-1] - first[0] > detection['wave_width_s'] + 1e-9
                or second[-1] - second[0] > detection['wave_width_s'] + 1e-9
                or not detection['wave_separation_min_s'] <= separation
                <= detection['wave_separation_max_s']):
            failures.append('two_wave_cadence')
    absolute_min = predicates['exact_absolute_improvement_min']
    relative_min = predicates['exact_relative_improvement_min']
    if absolute_min is not None:
        if (not comparison or not comparison.get('both_completed')
                or comparison.get('absolute_improvement', -math.inf) < absolute_min
                or comparison.get('relative_improvement', -math.inf) < relative_min):
            failures.append('consequence_improvement')
    return tuple(failures)


class SingaporeScenarioV2Generator:
    """Generate strict profile-selected Singapore v2 episodes."""

    version = SINGAPORE_SCENARIO_V2_VERSION

    def __init__(
            self, distribution: Optional[SingaporeScenarioDistribution] = None,
            distribution_path: Path = DEFAULT_DISTRIBUTION_PATH,
            config: Optional[SingaporeScenarioConfig] = None,
            boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
            consequence_provider: Optional[Any] = None,
            eligibility_checker: Optional[
                Callable[[ScheduledThreat, AbsoluteCandidate], bool]] = None):
        self.distribution = distribution or load_scenario_distribution(distribution_path)
        if not isinstance(self.distribution, SingaporeScenarioDistribution):
            raise ValueError('distribution must be a SingaporeScenarioDistribution')
        config = (config or getattr(consequence_provider, 'scenario_config', None)
                  or SingaporeScenarioConfig())
        if not isinstance(config, SingaporeScenarioConfig):
            raise ValueError('config must be a SingaporeScenarioConfig')
        self.config = config
        self.main_island = load_main_island(boundaries_path)
        self.detection_boundary = self.main_island.geometry.buffer(
            self.config.detection_boundary_offset_m, quad_segs=128)
        if self.detection_boundary.geom_type != 'Polygon':
            self.detection_boundary = max(
                self.detection_boundary.geoms, key=lambda row: row.area)
        self.consequence_provider = consequence_provider
        self.eligibility_checker = eligibility_checker
        if consequence_provider is not None:
            self._validate_provider(consequence_provider)

    def _validate_provider(self, provider: Any) -> None:
        if getattr(provider, 'scenario_config', None) is not self.config:
            raise ValueError('Singapore v2 generator and provider must share one config object')
        geometry = getattr(getattr(provider, 'catalog', None), 'main_island', None)
        if geometry is None or geometry.geometry_checksum != self.main_island.geometry_checksum:
            raise ValueError('Singapore v2 provider geometry mismatch')

    def _provider(self) -> Any:
        if self.consequence_provider is None:
            from .singapore_provider import SingaporeConsequenceProvider
            self.consequence_provider = SingaporeConsequenceProvider(
                scenario_config=self.config, main_island=self.main_island)
        self._validate_provider(self.consequence_provider)
        return self.consequence_provider

    def _fresh_provider(self) -> Any:
        provider = self._provider()
        try:
            return type(provider)(catalog=provider.catalog, scenario_config=self.config)
        except TypeError:
            return provider

    def _seed(self, seed: int, profile: str, component: str,
              index: int = 0, attempt: int = 0) -> int:
        payload = '|'.join((
            self.version, self.distribution.checksum, str(seed), profile,
            component, str(index), str(attempt))).encode('utf-8')
        return int.from_bytes(hashlib.sha256(payload).digest()[:16], 'big')

    def _rng(self, seed: int, profile: str, component: str,
             index: int = 0, attempt: int = 0) -> random.Random:
        return random.Random(self._seed(seed, profile, component, index, attempt))

    def _counts(self, seed: int, profile_name: str,
                profile: Mapping[str, Any], attempt: int) -> Tuple[int, int]:
        rng = self._rng(seed, profile_name, 'active-counts', attempt=attempt)
        threats = rng.randint(profile['threat_count_min'], profile['threat_count_max'])
        interceptors = threats + (profile['interceptor_rule'] == 'one-extra')
        return threats, int(interceptors)

    def _detection_times(self, seed: int, profile_name: str,
                         profile: Mapping[str, Any], count: int,
                         attempt: int) -> Tuple[float, ...]:
        detection = profile['detection']
        start = self._rng(
            seed, profile_name, 'detection-start', attempt=attempt).uniform(0.0, 1.0)
        if detection['kind'] == 'two-waves':
            first = sorted(self._rng(
                seed, profile_name, 'detection-wave-one', index,
                attempt).uniform(0.0, detection['wave_width_s'])
                for index in range(4))
            separation = self._rng(
                seed, profile_name, 'detection-wave-separation',
                attempt=attempt).uniform(
                    detection['wave_separation_min_s'],
                    detection['wave_separation_max_s'])
            second_start = first[-1] + separation
            second = sorted(second_start + self._rng(
                seed, profile_name, 'detection-wave-two', index,
                attempt).uniform(0.0, detection['wave_width_s'])
                for index in range(4))
            return tuple(round(start + value, 9) for value in first + second)
        if detection['kind'] == 'burst':
            burst = int(detection['burst_count'])
            values = sorted(self._rng(
                seed, profile_name, 'detection-burst', index,
                attempt).uniform(0.0, detection['wave_width_s'])
                for index in range(burst))
            current = values[-1]
            for index in range(burst, count):
                current += self._rng(
                    seed, profile_name, 'detection-tail-gap', index,
                    attempt).uniform(detection['gap_min_s'], detection['gap_max_s'])
                values.append(current)
            return tuple(round(start + value, 9) for value in values)
        values = [start]
        for index in range(1, count):
            values.append(values[-1] + self._rng(
                seed, profile_name, 'detection-gap', index,
                attempt).uniform(detection['gap_min_s'], detection['gap_max_s']))
        return tuple(round(value, 9) for value in values)

    def _detection_point(self, seed: int, profile_name: str,
                         profile: Mapping[str, Any], index: int,
                         attempt: int) -> Tuple[Point, int]:
        sector_rng = self._rng(
            seed, profile_name, 'ingress-sector', index, attempt)
        sector = profile['ingress_sectors'][
            sector_rng.randrange(len(profile['ingress_sectors']))]
        return (self._detection_in_sector(
            seed, profile_name, index, attempt, sector), sector)

    def _detection_in_sector(self, seed: int, profile_name: str, index: int,
                             attempt: int, sector: int) -> Point:
        rng = self._rng(seed, profile_name, 'ingress-position', index, attempt)
        line = self.detection_boundary.exterior
        for _ in range(10000):
            point = line.interpolate(rng.random() * line.length)
            if ingress_sector(point, self.main_island) == sector:
                return point
        raise SingaporeGenerationError('ingress-sector sampling exhausted')

    def _terminal_point(self, seed: int, profile_name: str,
                        profile: Mapping[str, Any], index: int, attempt: int,
                        detection: Point) -> Point:
        rng = self._rng(seed, profile_name, 'terminal-position', index, attempt)
        for _ in range(20000):
            terminal = _uniform_point(self.main_island.geometry, rng)
            duration = detection.distance(terminal) / self.config.threat_horizontal_speed_mps
            if (profile['trajectory_duration_min_s'] <= duration
                    <= profile['trajectory_duration_max_s']):
                return terminal
        raise SingaporeGenerationError('terminal-duration sampling exhausted')

    def _threat(self, seed: int, profile_name: str, profile: Mapping[str, Any],
                index: int, attempt: int, detection_time_s: float,
                episode_attempt: Optional[int] = None
                ) -> ScheduledThreat:
        detection, sector = self._detection_point(
            seed, profile_name, profile, index, attempt)
        terminal = self._terminal_point(
            seed, profile_name, profile, index, attempt, detection)
        duration = detection.distance(terminal) / self.config.threat_horizontal_speed_mps
        dx, dy = terminal.x - detection.x, terminal.y - detection.y
        altitude_rng = self._rng(seed, profile_name, 'threat-altitude', index, attempt)
        z0 = altitude_rng.triangular(
            self.config.altitude_min_m, self.config.altitude_max_m,
            self.config.altitude_mode_m)
        vz = (0.5 * self.config.gravity_mps2 * duration * duration - z0) / duration
        state = ThreatState(
            'threat-%02d' % (index + 1), detection.x, detection.y,
            dx / duration, dy / duration, duration, z0, vz,
            -self.config.gravity_mps2)
        result = ScheduledThreat(round(detection_time_s, 9), state, {
            'synthetic': True, 'generator': self.version,
            'generation_attempt': (
                attempt + 1 if episode_attempt is None else episode_attempt + 1),
            'threat_retry_attempt': (
                0 if episode_attempt is None else attempt - episode_attempt),
            'ingress_sector': sector,
            'terminal_grid_cell': terminal_grid_cell(terminal, self.main_island),
            'terminal_position_x_m': terminal.x,
            'terminal_position_y_m': terminal.y,
            'terminal_position_z_m': 0.0,
            'supplied_footprint_radius_m': self.config.supplied_footprint_radius_m,
            'consequence_condition': self.config.consequence_condition,
            'vertical_reference': self.config.vertical_reference,
        })
        samples = sample_threat_trajectory(
            state, self.config.trajectory_samples_per_pair)
        if (len(samples) != 20 or samples[-1].position_z_m != 0.0
                or any(row.position_z_m < 0 for row in samples)):
            raise SingaporeGenerationError('v2 trajectory validation failed')
        return result

    @staticmethod
    def _reachable_interceptors(
            threat: ScheduledThreat,
            interceptors: Sequence[InterceptorResource]) -> Tuple[str, ...]:
        return tuple(
            resource.state.interceptor_id
            for resource in interceptors
            if any(row.reachable for row in generate_candidate_opportunities(
                threat.state, resource.state, 20)))

    def _cluster_center(self, seed: int, profile_name: str,
                        cluster: int, attempt: int) -> Point:
        return _uniform_point(
            self.main_island.geometry,
            self._rng(seed, profile_name, 'interceptor-cluster', cluster, attempt))

    def _interceptors(self, seed: int, profile_name: str,
                      profile: Mapping[str, Any], count: int,
                      attempt: int) -> Tuple[InterceptorResource, ...]:
        layout = profile['interceptor_layout']
        centers = () if layout == 'uniform' else (
            self._cluster_center(seed, profile_name, 0, attempt),
            self._cluster_center(seed, profile_name, 1, attempt))
        if layout in ('clustered-outliers', 'burst-clustered-outliers'):
            center_rng = self._rng(
                seed, profile_name, 'interceptor-edge-cluster', attempt=attempt)
            selected_sector = self._rng(
                seed, profile_name, 'interceptor-cluster-sector',
                attempt=attempt).randrange(8)
            for _ in range(10000):
                candidate = _uniform_point(self.main_island.geometry, center_rng)
                if (candidate.distance(self.main_island.geometry.exterior) <= 1000.0
                        and ingress_sector(candidate, self.main_island)
                        == selected_sector):
                    centers = (candidate, centers[1])
                    break
            else:
                raise SingaporeGenerationError('edge-cluster sampling exhausted')
        sigma = 1400.0 if layout == 'two-cluster-tight' else 3000.0
        rows = []
        for index in range(count):
            rng = self._rng(
                seed, profile_name, 'interceptor-position', index, attempt)
            if layout == 'uniform':
                point = _uniform_point(self.main_island.geometry, rng)
            elif layout in ('clustered-outliers', 'burst-clustered-outliers'):
                center = centers[0]
                central_count = (5 if layout == 'clustered-outliers'
                                 else max(4, count - 3))
                if index < central_count:
                    point = None
                    for _ in range(10000):
                        candidate = Point(
                            rng.gauss(center.x, 350.0),
                            rng.gauss(center.y, 350.0))
                        if (self.main_island.geometry.covers(candidate)
                                and candidate.distance(
                                    self.main_island.geometry.exterior) <= 1200.0):
                            point = candidate
                            break
                else:
                    point = None
                    wanted_sector = (
                        selected_sector + 2 * (index - central_count + 1)) % 8
                    for _ in range(10000):
                        candidate = _uniform_point(self.main_island.geometry, rng)
                        if (candidate.distance(center) >= 14000.0
                                and candidate.distance(
                                    self.main_island.geometry.exterior) <= 1000.0
                                and ingress_sector(candidate, self.main_island)
                                == wanted_sector):
                            point = candidate
                            break
                if point is None:
                    raise SingaporeGenerationError(
                        'clustered-outlier interceptor sampling exhausted')
            else:
                center = centers[index % 2]
                point = None
                for _ in range(10000):
                    candidate = Point(
                        rng.gauss(center.x, sigma), rng.gauss(center.y, sigma))
                    if self.main_island.geometry.covers(candidate):
                        point = candidate
                        break
                if point is None:
                    raise SingaporeGenerationError('clustered interceptor sampling exhausted')
            heading = self._rng(
                seed, profile_name, 'interceptor-heading', index, attempt).uniform(
                    0.0, math.tau)
            rows.append(InterceptorResource(InterceptorState(
                'interceptor-%02d' % (index + 1), point.x, point.y, heading,
                self.config.interceptor_speed_mps,
                math.radians(self.config.interceptor_turn_rate_deg_s)), {
                    'synthetic': True, 'generator': self.version,
                    'layout': layout, 'generation_attempt': attempt + 1,
                }))
        return tuple(rows)

    def _anchored_threat(
            self, seed: int, profile_name: str, profile: Mapping[str, Any],
            index: int, attempt: int, detection_time_s: float,
            designated: InterceptorResource) -> ScheduledThreat:
        """Aim a short trajectory through one independently sampled resource."""
        terminal_rng = self._rng(
            seed, profile_name, 'anchored-terminal', index, attempt)
        center = self.main_island.geometry.centroid
        anchor = Point(
            designated.state.position_x_m, designated.state.position_y_m)
        for local in range(1000):
            terminal = Point(
                terminal_rng.gauss(anchor.x, 200.0),
                terminal_rng.gauss(anchor.y, 200.0))
            if not self.main_island.geometry.covers(terminal):
                continue
            # The closest point on the fixed 10 km detection boundary gives a
            # short ingress while preserving the boundary-offset contract.
            detection = nearest_points(
                terminal, self.detection_boundary.exterior)[1]
            base_sector = ingress_sector(detection, self.main_island)
            duration = detection.distance(terminal) / self.config.threat_horizontal_speed_mps
            if (profile['trajectory_duration_min_s'] <= duration
                    <= profile['trajectory_duration_max_s']):
                break
        else:
            raise SingaporeGenerationError('anchored trajectory construction exhausted')
        dx, dy = terminal.x - detection.x, terminal.y - detection.y
        altitude_rng = self._rng(
            seed, profile_name, 'threat-altitude', index, attempt)
        z0 = altitude_rng.triangular(
            self.config.altitude_min_m, self.config.altitude_max_m,
            self.config.altitude_mode_m)
        vz = (0.5 * self.config.gravity_mps2 * duration * duration - z0) / duration
        state = ThreatState(
            'threat-%02d' % (index + 1), detection.x, detection.y,
            dx / duration, dy / duration, duration, z0, vz,
            -self.config.gravity_mps2)
        return ScheduledThreat(round(detection_time_s, 9), state, {
            'synthetic': True, 'generator': self.version,
            'generation_attempt': attempt + 1, 'threat_retry_attempt': 0,
            'ingress_sector': base_sector,
            'terminal_grid_cell': terminal_grid_cell(terminal, self.main_island),
            'terminal_position_x_m': terminal.x,
            'terminal_position_y_m': terminal.y,
            'terminal_position_z_m': 0.0,
            'supplied_footprint_radius_m': self.config.supplied_footprint_radius_m,
            'consequence_condition': self.config.consequence_condition,
            'vertical_reference': self.config.vertical_reference,
        })

    @property
    def configuration_checksum(self) -> str:
        return _sha256('|'.join((
            self.config.checksum, self.distribution.checksum,
            self.main_island.source_checksum,
            self.main_island.geometry_checksum)).encode('utf-8'))

    def _draft(self, seed: int, profile_name: str,
               profile: Mapping[str, Any], attempt: int) -> EpisodeSpec:
        threat_count, interceptor_count = self._counts(
            seed, profile_name, profile, attempt)
        detection_times = self._detection_times(
            seed, profile_name, profile, threat_count, attempt)
        interceptors = self._interceptors(
            seed, profile_name, profile, interceptor_count, attempt)
        if profile_name == 'low-slack':
            threats = tuple(self._anchored_threat(
                seed, profile_name, profile, index, attempt,
                detection_times[index], interceptors[index])
                for index in range(threat_count))
        elif profile_name == 'burst-contention':
            central_count = max(4, interceptor_count - 3)
            central_targets = list(range(min(3, central_count)))
            outlier_targets = list(range(central_count, interceptor_count))
            targets = central_targets + [outlier_targets.pop(0)]
            remaining_central = list(range(3, central_count))
            targets.extend(remaining_central + outlier_targets)
            if len(targets) != threat_count:
                raise SingaporeGenerationError('burst target construction mismatch')
            threats = tuple(self._anchored_threat(
                seed, profile_name, profile, index, attempt,
                detection_times[index], interceptors[targets[index]])
                for index in range(threat_count))
        else:
            threats = tuple(self._threat(
                seed, profile_name, profile, index, attempt,
                detection_times[index]) for index in range(threat_count))
        return EpisodeSpec(
            episode_id='singapore-v2-%s-%010d' % (profile_name, seed),
            seed=seed, threats=threats, interceptors=interceptors,
            candidate_count=20, schema_version=SINGAPORE_EPISODE_SCHEMA_VERSION,
            metadata={
                'generator': self.version,
                'scenario_contract': asdict(self.config),
                'scenario_config_checksum': self.config.checksum,
                'generator_configuration_checksum': self.configuration_checksum,
                'boundary_source_checksum': self.main_island.source_checksum,
                'main_island_geometry_checksum': self.main_island.geometry_checksum,
                'objective_reference': SINGAPORE_OBJECTIVE_REFERENCE_VERSION,
            })

    def _comparison(self, spec: EpisodeSpec) -> Mapping[str, Any]:
        naive_engine = SimulationEngine(spec, self._fresh_provider())
        naive = NaiveLaunchOnDetectionPolicy().run(naive_engine)
        exact_engine = SimulationEngine(spec, self._fresh_provider())
        exact = OptimalFixedRankAssignmentPolicy().run(exact_engine)
        both = naive.completed and exact.termination_reason == 'all_threats_resolved'
        absolute = (None if not both else float(naive.raw_score - exact.raw_score))
        relative = (None if not both else absolute / max(abs(float(naive.raw_score)), 1e-12))
        return {
            'both_completed': both,
            'naive_termination_reason': naive.termination_reason,
            'naive_cost': naive.raw_score,
            'exact_termination_reason': exact.termination_reason,
            'exact_cost': exact.raw_score,
            'absolute_improvement': absolute,
            'relative_improvement': relative,
        }

    def _naive_outcome(self, spec: EpisodeSpec) -> Mapping[str, Any]:
        engine = SimulationEngine(spec, self._fresh_provider())
        run = NaiveLaunchOnDetectionPolicy().run(engine)
        return {
            'completed': run.completed,
            'termination_reason': run.termination_reason,
            'cost': run.raw_score,
        }

    def generate(self, seed: int, profile: str) -> EpisodeSpec:
        if type(seed) is not int or seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        selected = self.distribution.profile(profile)
        rejected = []
        provider = self._provider()
        for attempt in range(self.distribution.document['max_generation_attempts']):
            try:
                draft = self._draft(seed, profile, selected, attempt)
                metrics = scenario_graph_metrics(
                    draft, provider, self.eligibility_checker)
                times = tuple(row.detection_time_s for row in draft.threats)
                burst_ids = tuple(row.state.threat_id for row in draft.threats[:4])
                failures = profile_predicate_failures(
                    profile, selected, metrics, times, burst_ids,
                    ({'both_completed': True,
                      'absolute_improvement': math.inf,
                      'relative_improvement': math.inf}
                     if profile == 'consequence-contrast' else None))
                comparison = None
                naive_outcome = None
                if not failures and profile == 'consequence-contrast':
                    comparison = self._comparison(draft)
                    failures = profile_predicate_failures(
                        profile, selected, metrics, times, burst_ids, comparison)
                elif not failures:
                    naive_outcome = self._naive_outcome(draft)
                    if not naive_outcome['completed']:
                        failures = ('naive_completion_constructive',)
            except (ValueError, SingaporeGenerationError, RuntimeError) as exc:
                failures = ('generation_error:' + type(exc).__name__,)
                draft = None
                metrics = None
                comparison = None
                naive_outcome = None
            if failures:
                rejected.append({'attempt': attempt + 1, 'failed_predicates': list(failures)})
                continue
            assert draft is not None and metrics is not None
            identity = provider_identity(provider)
            provider_checksums = dict(getattr(
                getattr(provider, 'catalog', None), 'source_checksums', {}))
            metadata = {
                'profile': profile,
                'distribution_identity': self.distribution.version,
                'distribution_checksum': self.distribution.checksum,
                'generator': self.version,
                'scenario_contract': asdict(self.config),
                'scenario_config_checksum': self.config.checksum,
                'generator_configuration_checksum': self.configuration_checksum,
                'boundary_source_checksum': self.main_island.source_checksum,
                'main_island_geometry_checksum': self.main_island.geometry_checksum,
                'objective_reference': SINGAPORE_OBJECTIVE_REFERENCE_VERSION,
                'provider_identity': identity['identity'],
                'provider_version': identity['version'],
                'provider_config_checksum': getattr(provider, 'config_identity', None),
                'provider_data_checksum': getattr(
                    getattr(provider, 'catalog', None), 'identity', None),
                'provider_source_checksums': provider_checksums,
                'active_threat_count': len(draft.threats),
                'active_interceptor_count': len(draft.interceptors),
                'ingress_sectors': [row.metadata['ingress_sector'] for row in draft.threats],
                'terminal_grid_cells': [
                    row.metadata['terminal_grid_cell'] for row in draft.threats],
                'generation_attempt_count': attempt + 1,
                'rejected_attempt_count': len(rejected),
                'rejected_attempts': rejected,
                'matching_summary': {
                    key: metrics[key] for key in (
                        'feasible_edges', 'feasible_edge_count', 'edge_density',
                        'threat_degrees', 'interceptor_degrees', 'matching',
                        'complete_matchable',
                        'complete_matching_count_capped_10000',
                        'critical_edges', 'critical_edge_count',
                        'pair_best_time_margin_min_s',
                        'pair_best_time_margin_median_s',
                        'candidate_cost_spread_by_threat',
                        'candidate_cost_spread_max')},
                'unavailable_consequence_components': list(getattr(
                    getattr(provider, 'catalog', None), 'unavailable_sectors', ())),
                'label': 'synthetic Singapore v2 scenario; supplied 100 m area',
            }
            if comparison is not None:
                metadata['profile_comparison'] = comparison
            if naive_outcome is not None:
                metadata['constructive_naive_outcome'] = naive_outcome
            spec = EpisodeSpec(
                draft.episode_id, draft.seed, draft.threats, draft.interceptors,
                draft.candidate_count, metadata, draft.schema_version)
            metadata = dict(spec.metadata)
            metadata['canonical_episode_hash'] = canonical_episode_hash(spec)
            return EpisodeSpec(
                spec.episode_id, spec.seed, spec.threats, spec.interceptors,
                spec.candidate_count, metadata, spec.schema_version)
        raise SingaporeGenerationError(
            '%s seed %d failed all 200 deterministic attempts' % (profile, seed))
