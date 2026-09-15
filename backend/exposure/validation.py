"""Strict, transport-independent PEC input validation."""
import math
from pyproj import CRS
from pyproj.exceptions import CRSError


class PECValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('; '.join(e['message'] for e in errors))


def error(code, record_type, field, message, record_id=None):
    result = dict(code=code, record_type=record_type, field=field, message=message)
    if identifier(record_id):
        result['record_id'] = record_id
    return result


def identifier(value):
    return isinstance(value, str) and bool(value.strip())


def number(value, nonnegative=False):
    try:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and (not nonnegative or value >= 0))
    except OverflowError:
        return False


def compatible_crs(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        crs = CRS.from_user_input(value)
        return (crs.is_projected and len(crs.axis_info) == 2
                and all(a.unit_name == 'metre' for a in crs.axis_info)
                and crs.equals(CRS('EPSG:3414')))
    except (ValueError, TypeError, CRSError):
        return False


def validate_episode(episode, dataset):
    errors = []
    if not isinstance(episode, dict):
        return [error('invalid_type', 'episode', '$', 'Episode must be an object')]
    eid = episode.get('episode_id')
    for key in ('episode_id', 'population_dataset_id', 'population_dataset_version'):
        if not identifier(episode.get(key)):
            errors.append(error('invalid_identifier', 'episode', key, 'Required nonempty string', eid))
    if episode.get('schema_version') != 'pec-episode/1':
        errors.append(error('unsupported_schema', 'episode', 'schema_version', 'Expected pec-episode/1', eid))
    for key, expected in [('population_dataset_id', dataset.dataset_id), ('population_dataset_version', dataset.version)]:
        if episode.get(key) != expected:
            errors.append(error('dataset_mismatch', 'episode', key, 'Must match prepared population dataset', eid))
    if not compatible_crs(episode.get('coordinate_reference_system')):
        errors.append(error('incompatible_crs', 'episode', 'coordinate_reference_system', 'Declare EPSG:3414 in metres', eid))
    events = episode.get('events')
    if not isinstance(events, list):
        return errors + [error('invalid_type', 'episode', 'events', 'Events must be an array', eid)]
    seen, footprints = set(), {}
    for i, event in enumerate(events):
        prefix = f'events[{i}]'
        if not isinstance(event, dict):
            errors.append(error('invalid_type', 'event', prefix, 'Event must be an object'))
            continue
        event_id = event.get('event_id')
        for key in ('event_id', 'footprint_id'):
            if not identifier(event.get(key)):
                errors.append(error('invalid_identifier', 'event', prefix + '.' + key, 'Required nonempty string', event_id))
        if identifier(event_id):
            if event_id in seen:
                errors.append(error('duplicate_identifier', 'event', prefix + '.event_id', 'Event ID must be unique', event_id))
            seen.add(event_id)
        valid_geometry = True
        for key in ('center_x_m', 'center_y_m', 'radius_m', 'time_from_episode_start_s'):
            if key == 'time_from_episode_start_s' and key not in event:
                continue
            if not number(event.get(key), nonnegative=key in ('radius_m', 'time_from_episode_start_s')):
                errors.append(error('invalid_number', 'event', prefix + '.' + key, 'Expected finite number in permitted range; booleans forbidden', event_id))
                valid_geometry = False
        fid = event.get('footprint_id')
        if identifier(fid) and valid_geometry:
            geometry = tuple(event[k] for k in ('center_x_m', 'center_y_m', 'radius_m'))
            if fid in footprints and footprints[fid] != geometry:
                errors.append(error('inconsistent_footprint', 'event', prefix + '.footprint_id', 'Reused footprint ID must have identical centre and radius', event_id))
            footprints[fid] = geometry
    return errors
