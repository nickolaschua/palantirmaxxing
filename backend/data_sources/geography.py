"""Full-resolution geometry validation and Singapore metre-based area preparation."""
from __future__ import annotations

import math
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.errors import ShapelyError
from shapely.ops import transform
from shapely.strtree import STRtree
from shapely.validation import explain_validity

PROJECTED_CRS = 'EPSG:3414'
VIEWER_BOUNDS = (103.56, 1.13, 104.14, 1.52)


def area_density(geometry, population):
    area = geometry.area
    if not math.isfinite(area) or area <= 0:
        raise ValueError('Zone area must be finite and positive in square metres')
    return area, None if population is None else population / area


def prepare_geometry(collection):
    # RFC 7946 GeoJSON uses WGS84 lon/lat. Reject alternate declared CRSs.
    declared = collection.get('crs')
    if declared and declared.get('properties', {}).get('name') not in ('urn:ogc:def:crs:OGC:1.3:CRS84', 'EPSG:4326'):
        raise ValueError('Unexpected source CRS; explicit adapter required')
    target = CRS(PROJECTED_CRS)
    if any(axis.unit_name != 'metre' for axis in target.axis_info):
        raise ValueError('Projected area CRS must have metre units')
    projector = Transformer.from_crs('EPSG:4326', target, always_xy=True, allow_ballpark=False)
    geometries, issues, outside, area_deltas = [], [], [], []
    for feature in collection['features']:
        id = feature['properties']['SUBZONE_C']
        geometry = feature.get('geometry')
        reason = []
        projected = None
        try:
            if not geometry or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
                raise ValueError('Expected Polygon or MultiPolygon')
            source = shape(geometry)
            west, south, east, north = source.bounds
            if source.is_empty or not all(math.isfinite(n) for n in source.bounds):
                raise ValueError('Empty or non-finite geometry')
            # Broad Singapore geographic range detects swapped axes/metre coordinates,
            # without restricting coverage to the existing viewer coastline.
            if not (103 < west <= east < 105 and 0 < south <= north < 2):
                raise ValueError('Coordinates are not Singapore WGS84 longitude/latitude')
            if not source.is_valid:
                reason.append('source: ' + explain_validity(source))
            projected = transform(projector.transform, source)
            if not projected.is_valid:
                reason.append('projected: ' + explain_validity(projected))
            area_density(projected, None)
            if not (VIEWER_BOUNDS[0] <= west and VIEWER_BOUNDS[1] <= south and east <= VIEWER_BOUNDS[2] and north <= VIEWER_BOUNDS[3]):
                outside.append(id)
            published = feature['properties'].get('SHAPE.AREA')
            if isinstance(published, (int, float)):
                area_deltas.append(abs(projected.area - published))
        except (ValueError, TypeError, KeyError, ShapelyError) as error:
            reason.append(str(error))
        geometries.append(projected)
        issues.append(reason)
    # Never call intersections on invalid geometries. All positive-area overlaps
    # are reported and both affected zones are excluded; there is no sliver tolerance.
    valid_indices = [i for i, g in enumerate(geometries) if g is not None and not issues[i]]
    valid = [geometries[i] for i in valid_indices]
    tree = STRtree(valid)
    overlaps, overlapping = [], set()
    for i, geometry in enumerate(valid):
        for j_ in tree.query(geometry, predicate='intersects'):
            j = int(j_)
            if j <= i:
                continue
            area = geometry.intersection(valid[j]).area
            if area > 0:
                a, b = valid_indices[i], valid_indices[j]
                overlapping.update((a, b))
                overlaps.append(dict(zone_ids=[collection['features'][k]['properties']['SUBZONE_C'] for k in (a, b)], area_m2=area))
    return geometries, issues, overlapping, dict(
        projected_crs=PROJECTED_CRS, projected_axis_order='easting, northing; metres',
        source_coordinate_convention='RFC 7946 WGS84 longitude, latitude; degrees (no crs member in inspected source)',
        transformation=projector.description, repairs=[], overlap_area_tolerance_m2=0,
        overlap_scope='Pairs of valid, positive-area source/projected zones; invalid zones excluded without repair',
        invalid=[dict(zone_id=collection['features'][i]['properties']['SUBZONE_C'], reasons=r) for i, r in enumerate(issues) if r],
        overlaps=overlaps, outside_viewer_bounds=outside,
        maximum_absolute_difference_from_source_shape_area_m2=max(area_deltas, default=None))
