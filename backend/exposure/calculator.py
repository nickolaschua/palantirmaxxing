"""Deterministic population exposure under supplied circular footprints."""
from dataclasses import dataclass
import json
import math
import shapely
import pyproj
from shapely.geometry import Point, GeometryCollection
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.errors import ShapelyError
from .validation import error, identifier, validate_episode

CALCULATOR_VERSION = '0.1.0'
ASSUMPTIONS = [
    'Population is fixed throughout the episode and uniformly distributed within each eligible zone.',
    'Supplied circles are scenario inputs, not predictions; everyone within a footprint is counted equally.',
    'Episode totals describe the complete episode, not simultaneous exposure; time is descriptive only.',
    'No injury, casualty, shelter, movement, uncertainty, or hazard-validity modelling.',
    'Unknown and excluded population zones do not extend known population coverage.',
]


@dataclass(frozen=True)
class CalculationSettings:
    circle_edges: int = 128
    coverage_area_tolerance_m2: float = 1e-6

    def __post_init__(self):
        if type(self.circle_edges) is not int or self.circle_edges not in (128, 256):
            raise ValueError('circle_edges must be 128 or 256')
        if type(self.coverage_area_tolerance_m2) not in (int, float) or self.coverage_area_tolerance_m2 != 1e-6:
            raise ValueError('PEC v0.1 fixes coverage_area_tolerance_m2 at 1e-6')


def invalid_result(errors, episode=None):
    result = dict(schema_version='pec-result/1', status='invalid_input', errors=errors)
    if isinstance(episode, dict) and identifier(episode.get('episode_id')):
        result['episode_id'] = episode['episode_id']
    return result


def footprint(event, settings):
    if event['radius_m'] == 0:
        return GeometryCollection()
    radius = event['radius_m']
    if not math.isfinite(radius * radius * math.pi) or not all(
            math.isfinite(event[key] + sign * radius)
            for key in ('center_x_m', 'center_y_m') for sign in (-1, 1)):
        raise ValueError('Circle exceeds finite calculation range')
    geometry = Point(event['center_x_m'], event['center_y_m']).buffer(
        event['radius_m'], quad_segs=settings.circle_edges // 4)
    if geometry.is_empty or not geometry.is_valid or not math.isfinite(geometry.area) or geometry.area <= 0:
        raise ValueError('Circle is not representable with finite positive area at this coordinate scale')
    return geometry


def zone_exposure(dataset, geometry):
    rows = []
    for i in sorted(int(i) for i in dataset.tree.query(geometry, predicate='intersects')):
        overlap = geometry.intersection(dataset.geometries[i]).area
        if overlap > 0:
            zone = dataset.zones[i]
            rows.append(dict(zone_id=zone['zone_id'], zone_population=zone['population'],
                             zone_density_people_per_m2=zone['density'], overlap_area_m2=overlap,
                             estimated_people_exposed=zone['density'] * overlap))
    return math.fsum(row['estimated_people_exposed'] for row in rows), rows


def coverage(dataset, geometry, settings):
    area = geometry.area
    missing = geometry.difference(dataset.coverage).area
    fraction = None if area == 0 else geometry.intersection(dataset.coverage).area / area
    # Bound only floating-point ratio noise; no geometry or missing-area adjustment.
    if fraction is not None:
        if not -1e-12 <= fraction <= 1 + 1e-12:
            raise ValueError('Coverage fraction exceeds numerical bounds')
        fraction = min(1.0, max(0.0, fraction))
    return missing, fraction, 'partial_coverage' if missing > settings.coverage_area_tolerance_m2 else 'complete'


def calculate_episode(dataset, episode, settings=None):
    """Return a JSON-compatible result. Any invalid event invalidates all aggregates."""
    settings = settings or CalculationSettings()
    errors = validate_episode(episode, dataset)
    if errors:
        return invalid_result(errors, episode)
    events = sorted(episode['events'], key=lambda event: event['event_id'])
    geometries, cache = [], {}
    for event in events:
        try:
            key = tuple(event[k] for k in ('center_x_m', 'center_y_m', 'radius_m'))
            if key not in cache:
                cache[key] = footprint(event, settings)
            geometries.append(cache[key])
        except (ValueError, OverflowError, ShapelyError) as exc:
            errors.append(error('numerical_range', 'event', 'footprint', str(exc), event['event_id']))
    if errors:
        return invalid_result(errors, episode)
    try:
        results = []
        for event, geometry in zip(events, geometries):
            known, rows = zone_exposure(dataset, geometry)
            missing, fraction, status = coverage(dataset, geometry, settings)
            result = {key: event[key] for key in ('event_id', 'footprint_id', 'center_x_m', 'center_y_m', 'radius_m')}
            if 'time_from_episode_start_s' in event:
                result['time_from_episode_start_s'] = event['time_from_episode_start_s']
            result.update(status=status, footprint_area_m2=geometry.area, uncovered_area_m2=missing,
                          covered_area_fraction=fraction, people_potentially_exposed=known if status == 'complete' else None,
                          known_area_exposure=known, zone_breakdown=rows)
            results.append(result)
        union = unary_union(geometries)
        tree = STRtree(geometries)
        intersections = []
        for i, geometry in enumerate(geometries):
            for j in sorted(int(j) for j in tree.query(geometry, predicate='intersects') if int(j) > i):
                intersection = geometry.intersection(geometries[j])
                if intersection.area > 0:
                    intersections.append(intersection)
        multiple_region = unary_union(intersections)
        unique, _ = zone_exposure(dataset, union)
        multiple, _ = zone_exposure(dataset, multiple_region)
        person = math.fsum(row['known_area_exposure'] for row in results)
        missing, _, status = coverage(dataset, union, settings)
        output = dict(schema_version='pec-result/1', episode_id=episode['episode_id'], status=status,
                      events=results, unique_people_potentially_exposed=unique if status == 'complete' else None,
                      total_person_exposures=person if status == 'complete' else None,
                      people_exposed_to_multiple_events=multiple if status == 'complete' else None,
                      known_area_unique_exposure=unique, known_area_person_exposures=person,
                      known_area_multiple_exposure=multiple, uncovered_area_m2=missing,
                      metadata=dict(input_schema_versions=dict(population=dataset.input_schema, episode='pec-episode/1'),
                                    output_schema_version='pec-result/1', population_dataset_id=dataset.dataset_id,
                                    population_dataset_version=dataset.version, dataset_checksum_sha256=dataset.checksum,
                                    checksum_encoding='UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False, entire input envelope',
                                    coordinate_reference_system='EPSG:3414', calculator_version=CALCULATOR_VERSION,
                                    libraries=dict(shapely=shapely.__version__, geos=shapely.geos_version_string,
                                                   pyproj=pyproj.__version__),
                                    circle_approximation=dict(method='inscribed regular polygon; clockwise from positive x axis',
                                                              edges=settings.circle_edges, quad_segs=settings.circle_edges // 4),
                                    numerical_tolerances=dict(coverage_area_m2=settings.coverage_area_tolerance_m2,
                                                              population_overlap_area_m2=0, coverage_fraction_clamp=1e-12),
                                    assumptions=ASSUMPTIONS.copy()))
        json.dumps(output, allow_nan=False)
        return output
    except (ValueError, OverflowError, ShapelyError) as exc:
        return invalid_result([error('numerical_calculation', 'episode', 'events', str(exc), episode['episode_id'])], episode)
