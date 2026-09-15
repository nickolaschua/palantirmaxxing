"""Prepare eligible population geometry once, without acquisition or repair."""
from dataclasses import dataclass
import hashlib
import json
import math
import numpy as np
from shapely import from_wkt, get_coordinates
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.errors import ShapelyError
from shapely.validation import explain_validity
from .validation import PECValidationError, error, identifier, number, compatible_crs


@dataclass(frozen=True)
class PreparedPopulation:
    dataset_id: str
    version: str
    checksum: str
    input_schema: str
    zones: tuple
    geometries: tuple
    coverage: object
    tree: object


def prepare_population(dataset):
    """Validate a canonical or existing projected envelope; raise PECValidationError."""
    errors = []
    def issue(code, field, message, zid=None):
        errors.append(error(code, 'zone' if zid is not None or field.startswith('zones[') else 'population', field, message, zid))
    if not isinstance(dataset, dict):
        raise PECValidationError([error('invalid_type', 'population', '$', 'Dataset must be an object')])
    legacy = dataset.get('format') == 'population-zones-wkt/1'
    metadata = dataset.get('metadata', {})
    if not isinstance(metadata, dict):
        metadata = {}
        issue('invalid_type', 'metadata', 'Metadata must be an object')
    dataset_id = 'sg-residents-2020-mp2019' if legacy else dataset.get('dataset_id')
    version = metadata.get('dataset_version') if legacy else dataset.get('version')
    schema = dataset.get('format') if legacy else dataset.get('schema_version')
    if schema not in ('population-zones-wkt/1', 'pec-population/1'):
        issue('unsupported_schema', 'schema_version', 'Expected pec-population/1 or population-zones-wkt/1')
    for key, value in [('dataset_id', dataset_id), ('version', version)]:
        if not identifier(value):
            issue('invalid_identifier', key, 'Required nonempty string')
    if not compatible_crs(dataset.get('crs' if legacy else 'coordinate_reference_system')):
        issue('incompatible_crs', 'crs' if legacy else 'coordinate_reference_system', 'Declare EPSG:3414 in metres')
    if legacy and (dataset.get('units') != 'metre' or dataset.get('axis_order') != ['easting', 'northing']):
        issue('incompatible_coordinates', 'axis_order', 'Prepared WKT requires metre units and easting, northing axes')
    raw = dataset.get('zones')
    if not isinstance(raw, list):
        raise PECValidationError(errors + [error('invalid_type', 'population', 'zones', 'Zones must be an array')])
    zones, geometries, seen = [], [], set()
    for i, zone in enumerate(raw):
        path = f'zones[{i}]'
        if not isinstance(zone, dict):
            issue('invalid_type', path, 'Zone must be an object')
            continue
        zid = zone.get('zone_id')
        before = len(errors)
        if not identifier(zid):
            issue('invalid_identifier', path + '.zone_id', 'Required nonempty string', zid)
        elif zid in seen:
            issue('duplicate_identifier', path + '.zone_id', 'Zone ID must be unique', zid)
        else:
            seen.add(zid)
        if not number(zone.get('population'), True):
            issue('invalid_number', path + '.population', 'Population must be finite and nonnegative; booleans forbidden', zid)
        if legacy:
            if (zone.get('pec_eligible') is not True or zone.get('exclusion_reasons') != []
                    or zone.get('population_status') not in ('known', 'known_zero')
                    or zone.get('geometry_status') != 'valid' or zone.get('join_status') != 'matched'):
                issue('ineligible_zone', path, 'Prepared dataset must contain only eligible zones', zid)
            if zone.get('dataset_version') != version:
                issue('dataset_mismatch', path + '.dataset_version', 'Zone version must match envelope', zid)
        elif ('pec_eligible' in zone and zone['pec_eligible'] is not True) or zone.get('exclusion_reasons'):
            issue('ineligible_zone', path, 'Excluded zones cannot extend population coverage', zid)
        try:
            source = zone.get('geometry_wkt') if legacy else zone.get('geometry')
            if legacy:
                if not isinstance(source, str):
                    raise ValueError('Expected WKT string')
                geometry = from_wkt(source)
            else:
                if not isinstance(source, dict) or source.get('type') not in ('Polygon', 'MultiPolygon'):
                    raise ValueError('Expected Polygon or MultiPolygon geometry object')
                # Reject boolean and nonnumeric coordinates before Shapely coercion.
                def coordinates(value):
                    if not isinstance(value, (list, tuple)) or not value:
                        raise ValueError('Expected nonempty coordinate arrays')
                    if isinstance(value[0], (list, tuple)):
                        for item in value: coordinates(item)
                    elif len(value) != 2 or not all(number(x) for x in value):
                        raise ValueError('Coordinates must be finite two-dimensional numbers')
                coordinates(source.get('coordinates'))
                polygons = [source['coordinates']] if source['type'] == 'Polygon' else source['coordinates']
                for polygon in polygons:
                    for ring in polygon:
                        if len(ring) < 4 or ring[0] != ring[-1]:
                            raise ValueError('Polygon rings require at least four positions and explicit closure')
                geometry = shape(source)
            if not geometry.is_valid:
                raise ValueError('Invalid geometry: ' + explain_validity(geometry))
            if (geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty
                    or geometry.has_z or not np.isfinite(get_coordinates(geometry)).all()
                    or not geometry.is_valid or not math.isfinite(geometry.area) or geometry.area <= 0):
                raise ValueError('Expected valid finite 2D Polygon/MultiPolygon with positive area')
            if number(zone.get('population'), True) and not math.isfinite(zone['population'] / geometry.area):
                raise ValueError('Derived density is not finite')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, ShapelyError) as exc:
            issue('invalid_geometry', path + ('.geometry_wkt' if legacy else '.geometry'), str(exc), zid)
        if len(errors) == before:
            zones.append(dict(zone_id=zid, population=zone['population'], area=geometry.area,
                              density=zone['population'] / geometry.area))
            geometries.append(geometry)
    if errors:
        raise PECValidationError(errors)
    order = sorted(range(len(zones)), key=lambda i: zones[i]['zone_id'])
    zones = tuple(zones[i] for i in order)
    geometries = tuple(geometries[i] for i in order)
    tree = STRtree(geometries)
    try:
        for i, geometry in enumerate(geometries):
            for j in sorted(int(j) for j in tree.query(geometry, predicate='intersects') if int(j) > i):
                if geometry.intersection(geometries[j]).area > 0:
                    issue('overlapping_zones', 'zones', 'Positive-area overlap with zone ' + zones[j]['zone_id'], zones[i]['zone_id'])
        coverage = unary_union(geometries)
        if not math.isfinite(coverage.area):
            issue('numerical_range', 'zones', 'Coverage area is not finite')
        encoded = json.dumps(dataset, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, OverflowError, ShapelyError) as exc:
        issue('invalid_population', 'zones', str(exc))
    if errors:
        raise PECValidationError(errors)
    return PreparedPopulation(dataset_id, version, hashlib.sha256(encoded).hexdigest(), schema,
                              zones, geometries, coverage, tree)
