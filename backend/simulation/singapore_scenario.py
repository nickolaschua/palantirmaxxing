"""Deterministic Singapore eight-threat scenario generation.

This is an operationally synthetic geometry/kinematics fixture.  It uses the
checked-in planning boundaries only to constrain coordinates; it is not a
threat, weapon-effect, or performance model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from pyproj import Transformer
import shapely
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

from backend.domain import InterceptorState, ThreatState
from backend.planning import generate_candidate_opportunities, sample_threat_trajectory

from .models import (AbsoluteCandidate, EpisodeSpec, InterceptorResource,
                     ScheduledThreat)


SINGAPORE_SCENARIO_VERSION = 'singapore-scenario/1'
SINGAPORE_EPISODE_SCHEMA_VERSION = 'simulation-episode/2'
SINGAPORE_OBJECTIVE_REFERENCE_VERSION = 'full-candidate-universe/1'
_REPO = Path(__file__).resolve().parents[2]
DEFAULT_BOUNDARIES_PATH = _REPO / 'data' / 'raw' / 'boundaries.geojson'
_TO_SVY21 = Transformer.from_crs('EPSG:4326', 'EPSG:3414', always_xy=True)


class SingaporeGenerationError(RuntimeError):
    """Raised after deterministic generation retries are exhausted."""


@dataclass(frozen=True)
class SingaporeScenarioConfig:
    schema_version: str = SINGAPORE_SCENARIO_VERSION
    threat_count: int = 8
    interceptor_count: int = 8
    trajectory_samples_per_pair: int = 20
    detection_time_min_s: float = 0.0
    detection_time_max_s: float = 10.0
    horizontal_crs: str = 'EPSG:3414'
    detection_boundary_offset_m: float = 5_000.0
    altitude_min_m: float = 5_000.0
    altitude_mode_m: float = 10_000.0
    altitude_max_m: float = 15_000.0
    threat_horizontal_speed_mps: float = 250.0
    gravity_mps2: float = 9.80665
    supplied_footprint_radius_m: float = 100.0
    consequence_condition: str = 'weekday_midday'
    interceptor_speed_mps: float = 150.0
    interceptor_turn_rate_deg_s: float = 15.0
    max_generation_attempts: int = 100
    vertical_reference: str = 'height above the synthetic terminal ground plane'

    def __post_init__(self) -> None:
        if (self.threat_count, self.interceptor_count,
                self.trajectory_samples_per_pair) != (8, 8, 20):
            raise ValueError('singapore-scenario/1 fixes 8 threats, 8 interceptors and 20 samples')
        if self.horizontal_crs != 'EPSG:3414':
            raise ValueError('singapore-scenario/1 fixes EPSG:3414')
        if self.consequence_condition != 'weekday_midday':
            raise ValueError('singapore-scenario/1 fixes weekday_midday')
        if self.supplied_footprint_radius_m != 100.0:
            raise ValueError('singapore-scenario/1 fixes the supplied footprint radius at 100 m')
        for name in (
                'detection_boundary_offset_m', 'altitude_min_m', 'altitude_mode_m',
                'altitude_max_m', 'threat_horizontal_speed_mps', 'gravity_mps2',
                'supplied_footprint_radius_m', 'interceptor_speed_mps',
                'interceptor_turn_rate_deg_s'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(name + ' must be finite and positive')
        if not (self.altitude_min_m <= self.altitude_mode_m <= self.altitude_max_m):
            raise ValueError('altitude triangular distribution must be ordered')
        if not (0 <= self.detection_time_min_s <= self.detection_time_max_s):
            raise ValueError('detection time bounds are invalid')
        if type(self.max_generation_attempts) is not int or self.max_generation_attempts <= 0:
            raise ValueError('max_generation_attempts must be a positive integer')

    @property
    def checksum(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')
        return 'sha256:' + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class MainIslandGeometry:
    geometry: Any
    source_checksum: str
    geometry_checksum: str
    source_path: str
    coordinate_reference_system: str = 'EPSG:3414'


def _sha256(data: bytes) -> str:
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def load_main_island(path: Path = DEFAULT_BOUNDARIES_PATH) -> MainIslandGeometry:
    """Project, validate and union planning boundaries; retain the largest polygon."""
    path = Path(path)
    if not path.is_file():
        raise ValueError('Singapore planning-boundary source is required: ' + str(path))
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
        geometries = []
        for feature in document['features']:
            geometry = shape(feature['geometry'])
            geometry = transform(_TO_SVY21.transform, geometry)
            if not geometry.is_valid:
                geometry = shapely.make_valid(geometry)
            if not geometry.is_empty:
                geometries.append(geometry)
        merged = unary_union(geometries)
        polygons = ([merged] if merged.geom_type == 'Polygon'
                    else [item for item in merged.geoms if item.geom_type == 'Polygon'])
        island = max(polygons, key=lambda item: item.area)
        if not island.is_valid or island.is_empty or not math.isfinite(island.area):
            raise ValueError('derived main-island polygon is invalid')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('cannot derive Singapore main-island polygon') from exc
    canonical = shapely.to_wkb(shapely.normalize(island), hex=False,
                               byte_order=1, include_srid=False)
    return MainIslandGeometry(
        island, _sha256(raw), _sha256(canonical), str(path.resolve()))


def _stream_seed(seed: int, component: str, index: int = 0, attempt: int = 0) -> int:
    payload = f'{SINGAPORE_SCENARIO_VERSION}|{seed}|{component}|{index}|{attempt}'.encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:16], 'big')


def _uniform_point_in_polygon(polygon: Any, rng: random.Random,
                              tries: int = 100_000) -> Point:
    min_x, min_y, max_x, max_y = polygon.bounds
    for _ in range(tries):
        point = Point(rng.uniform(min_x, max_x), rng.uniform(min_y, max_y))
        if polygon.covers(point):
            return point
    raise SingaporeGenerationError('uniform polygon sampling exhausted its deterministic limit')


def _maximum_matching(edges: Mapping[str, Sequence[str]]) -> Mapping[str, str]:
    """Return threat->interceptor maximum matching using stable augmenting paths."""
    owner: Dict[str, str] = {}

    def visit(threat_id: str, seen: set) -> bool:
        for interceptor_id in sorted(edges.get(threat_id, ())):
            if interceptor_id in seen:
                continue
            seen.add(interceptor_id)
            previous = owner.get(interceptor_id)
            if previous is None or visit(previous, seen):
                owner[interceptor_id] = threat_id
                return True
        return False

    for threat_id in sorted(edges):
        visit(threat_id, set())
    return {threat_id: interceptor_id for interceptor_id, threat_id in owner.items()}


def episode_to_dict(spec: EpisodeSpec) -> Mapping[str, Any]:
    """Stable JSON-compatible episode representation used by manifests and tests."""
    return {
        'schema_version': spec.schema_version,
        'episode_id': spec.episode_id,
        'seed': spec.seed,
        'candidate_count': spec.candidate_count,
        'threats': [
            {'detection_time_s': row.detection_time_s,
             'state': asdict(row.state), 'metadata': dict(row.metadata)}
            for row in spec.threats],
        'interceptors': [
            {'state': asdict(row.state), 'metadata': dict(row.metadata)}
            for row in spec.interceptors],
        'metadata': {key: value for key, value in spec.metadata.items()
                     if key != 'canonical_episode_hash'},
    }


def canonical_episode_hash(spec: EpisodeSpec) -> str:
    payload = json.dumps(episode_to_dict(spec), sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return _sha256(payload)


class SingaporeScenarioGenerator:
    """Generate valid, fully matchable Singapore episodes from independent streams."""

    version = SINGAPORE_SCENARIO_VERSION

    def __init__(self, config: Optional[SingaporeScenarioConfig] = None,
                 boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
                 consequence_provider: Optional[Any] = None,
                 eligibility_checker: Optional[Callable[[ScheduledThreat, AbsoluteCandidate], bool]] = None):
        if config is None:
            config = (getattr(consequence_provider, 'scenario_config', None)
                      or SingaporeScenarioConfig())
        if not isinstance(config, SingaporeScenarioConfig):
            raise ValueError('config must be a SingaporeScenarioConfig')
        self.config = config
        self.main_island = load_main_island(boundaries_path)
        self.consequence_provider = consequence_provider
        self.eligibility_checker = eligibility_checker
        if consequence_provider is not None:
            self._validate_provider_contract(consequence_provider)

    def _validate_provider_contract(self, provider: Any) -> None:
        if getattr(provider, 'scenario_config', None) is not self.config:
            raise ValueError('Singapore generator and provider must share the same config object')
        if float(getattr(provider, 'footprint_radius_m', math.nan)) != 100.0:
            raise ValueError('Singapore provider radius must equal the scenario 100 m radius')
        if getattr(provider, 'condition_id', None) != self.config.consequence_condition:
            raise ValueError('Singapore provider consequence condition must equal the scenario condition')
        geometry = getattr(getattr(provider, 'catalog', None), 'main_island', None)
        if (geometry is None
                or geometry.geometry_checksum != self.main_island.geometry_checksum):
            raise ValueError('Singapore provider and scenario must use the same main-island geometry')

    @property
    def configuration_checksum(self) -> str:
        payload = '|'.join((self.config.checksum, self.main_island.source_checksum,
                            self.main_island.geometry_checksum)).encode()
        return _sha256(payload)

    def _interceptors(self, seed: int) -> Tuple[InterceptorResource, ...]:
        rows = []
        for index in range(self.config.interceptor_count):
            rng = random.Random(_stream_seed(seed, 'interceptor', index))
            point = _uniform_point_in_polygon(self.main_island.geometry, rng)
            rows.append(InterceptorResource(
                InterceptorState(
                    'interceptor-%02d' % (index + 1), point.x, point.y,
                    rng.uniform(0.0, math.tau), self.config.interceptor_speed_mps,
                    math.radians(self.config.interceptor_turn_rate_deg_s)),
                {'synthetic': True, 'generator': self.version}))
        return tuple(rows)

    def _detection_times(self, seed: int) -> Tuple[float, ...]:
        values = []
        for index in range(self.config.threat_count):
            rng = random.Random(_stream_seed(seed, 'detection-time', index))
            values.append(rng.uniform(
                self.config.detection_time_min_s, self.config.detection_time_max_s))
        return tuple(sorted(values))

    def _threat(self, seed: int, index: int, attempt: int,
                detection_time_s: float) -> ScheduledThreat:
        rng = random.Random(_stream_seed(seed, 'threat', index, attempt))
        detection_boundary = self.main_island.geometry.buffer(
            self.config.detection_boundary_offset_m, quad_segs=128)
        if detection_boundary.geom_type != 'Polygon':
            detection_boundary = max(detection_boundary.geoms, key=lambda item: item.area)
        line = detection_boundary.exterior
        detection = line.interpolate(rng.random() * line.length)
        terminal = _uniform_point_in_polygon(self.main_island.geometry, rng)
        dx, dy = terminal.x - detection.x, terminal.y - detection.y
        distance = math.hypot(dx, dy)
        if not math.isfinite(distance) or distance <= 0:
            raise SingaporeGenerationError('sampled threat has invalid horizontal distance')
        duration = distance / self.config.threat_horizontal_speed_mps
        vx, vy = dx / duration, dy / duration
        z0 = rng.triangular(self.config.altitude_min_m, self.config.altitude_max_m,
                            self.config.altitude_mode_m)
        az = -self.config.gravity_mps2
        vz = (0.5 * self.config.gravity_mps2 * duration * duration - z0) / duration
        threat = ScheduledThreat(
            round(detection_time_s, 9),
            ThreatState(
                'threat-%02d' % (index + 1), detection.x, detection.y, vx, vy,
                duration, z0, vz, az),
            {
                'synthetic': True,
                'generator': self.version,
                'attempt': attempt,
                'terminal_position_x_m': terminal.x,
                'terminal_position_y_m': terminal.y,
                'terminal_position_z_m': 0.0,
                'supplied_footprint_radius_m': self.config.supplied_footprint_radius_m,
                'consequence_condition': self.config.consequence_condition,
                'vertical_reference': self.config.vertical_reference,
            })
        samples = sample_threat_trajectory(
            threat.state, self.config.trajectory_samples_per_pair)
        if len(samples) != self.config.trajectory_samples_per_pair:
            raise SingaporeGenerationError('trajectory does not contain exactly 20 samples')
        last = samples[-1]
        tolerance = 1e-6
        if (abs(last.position_x_m - terminal.x) > tolerance
                or abs(last.position_y_m - terminal.y) > tolerance
                or last.position_z_m != 0.0
                or any(row.position_z_m < 0 for row in samples)):
            raise SingaporeGenerationError('parabolic trajectory failed terminal validation')
        return threat

    def _provider(self):
        if self.eligibility_checker is not None:
            return None
        if self.consequence_provider is None:
            from .singapore_provider import SingaporeConsequenceProvider
            self.consequence_provider = SingaporeConsequenceProvider(
                scenario_config=self.config,
                main_island=self.main_island,
                footprint_radius_m=self.config.supplied_footprint_radius_m,
                condition_id=self.config.consequence_condition)
        self._validate_provider_contract(self.consequence_provider)
        return self.consequence_provider

    def _edges(self, threats: Sequence[ScheduledThreat],
               interceptors: Sequence[InterceptorResource]) -> Mapping[str, Tuple[str, ...]]:
        provider = self._provider()
        edges: Dict[str, Tuple[str, ...]] = {}
        for threat in threats:
            candidates = []
            by_interceptor: Dict[str, list] = {}
            for resource in interceptors:
                rows = tuple(AbsoluteCandidate.from_opportunity(
                    opportunity, threat.detection_time_s)
                    for opportunity in generate_candidate_opportunities(
                        threat.state, resource.state,
                        self.config.trajectory_samples_per_pair))
                by_interceptor[resource.state.interceptor_id] = list(rows)
                candidates.extend(rows)
            assessments = {}
            if provider is not None:
                assessments = provider.assess_candidates(threat, tuple(candidates), {})
            eligible = []
            for interceptor_id, rows in by_interceptor.items():
                if any(
                        row.opportunity.reachable and (
                            self.eligibility_checker(threat, row)
                            if self.eligibility_checker is not None else
                            bool(assessments[row.opportunity.opportunity_id].eligible))
                        for row in rows):
                    eligible.append(interceptor_id)
            edges[threat.state.threat_id] = tuple(eligible)
        return edges

    def generate(self, seed: int, **_ignored: Any) -> EpisodeSpec:
        if type(seed) is not int or seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        interceptors = self._interceptors(seed)
        detection_times = self._detection_times(seed)
        attempts = [0] * self.config.threat_count
        threats = []
        for index, detection_time in enumerate(detection_times):
            for attempt in range(self.config.max_generation_attempts):
                try:
                    threats.append(self._threat(seed, index, attempt, detection_time))
                    attempts[index] = attempt
                    break
                except (ValueError, SingaporeGenerationError):
                    if attempt + 1 == self.config.max_generation_attempts:
                        raise SingaporeGenerationError(
                            'threat %d failed after %d attempts' % (
                                index + 1, self.config.max_generation_attempts))

        # If consequence eligibility makes the graph incomplete, only resample
        # an unmatched threat.  Other per-threat streams remain byte-for-byte stable.
        for repair in range(self.config.max_generation_attempts):
            edges = self._edges(threats, interceptors)
            matching = _maximum_matching(edges)
            if len(matching) == self.config.threat_count:
                break
            unmatched = next(index for index, row in enumerate(threats)
                             if row.state.threat_id not in matching)
            attempts[unmatched] += 1
            threats[unmatched] = self._threat(
                seed, unmatched, attempts[unmatched], detection_times[unmatched])
        else:
            raise SingaporeGenerationError(
                'complete consequence-eligible matching not found after %d attempts'
                % self.config.max_generation_attempts)

        spec = EpisodeSpec(
            episode_id='singapore-%010d' % seed,
            seed=seed,
            threats=tuple(threats),
            interceptors=interceptors,
            candidate_count=self.config.trajectory_samples_per_pair,
            schema_version=SINGAPORE_EPISODE_SCHEMA_VERSION,
            metadata={
                'generator': self.version,
                'scenario_contract': asdict(self.config),
                'scenario_config_checksum': self.config.checksum,
                'generator_configuration_checksum': self.configuration_checksum,
                'boundary_source_checksum': self.main_island.source_checksum,
                'main_island_geometry_checksum': self.main_island.geometry_checksum,
                'objective_reference': SINGAPORE_OBJECTIVE_REFERENCE_VERSION,
                'matching': dict(sorted(matching.items())),
                'generation_attempts_by_threat': dict(
                    (row.state.threat_id, attempts[index])
                    for index, row in enumerate(threats)),
                'label': 'synthetic Singapore scenario; supplied 100 m area',
            })
        # Hash excludes itself, avoiding a recursive identity.
        metadata = dict(spec.metadata)
        metadata['canonical_episode_hash'] = canonical_episode_hash(spec)
        return EpisodeSpec(
            spec.episode_id, spec.seed, spec.threats, spec.interceptors,
            spec.candidate_count, metadata, spec.schema_version)
