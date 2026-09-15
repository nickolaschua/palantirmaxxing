"""Independent footprint assessments or episode replay, using existing PEC geometry."""
import math
import re
from time import perf_counter_ns

from backend.exposure import CalculationSettings, calculate_episode
from backend.exposure.validation import identifier, validate_episode

REQUEST_VERSION = 'footprint-assessment-request/1'
RESULT_VERSION = 'footprint-assessment-result/1'


def _issue(code, field, message, record_id=None):
    result = dict(code=code, field=field, message=message)
    if identifier(record_id):
        result['record_id'] = record_id
    return result


def _to_pec_episode(request, records):
    events = []
    for record in records:
        event = dict(record['footprint'], event_id=record.get('record_id'))
        if 'time_from_episode_start_s' in record:
            event['time_from_episode_start_s'] = record['time_from_episode_start_s']
        events.append(event)
    return dict(schema_version='pec-episode/1', episode_id=request.get('assessment_id'),
                population_dataset_id=request.get('population_dataset_id'),
                population_dataset_version=request.get('population_dataset_version'),
                coordinate_reference_system=request.get('coordinate_reference_system'), events=events)


def _map_pec_errors(errors, source_records, request):
    """Translate PEC event indices back to the submitted adapter request."""
    mapped = []
    for error in errors:
        field = error['field']
        match = re.match(r'events\[(\d+)\](?:\.(.*))?$', field)
        rid = error.get('record_id') if error.get('record_type') == 'event' else None
        if match:
            index = int(match.group(1))
            record = source_records[index]
            original = next(i for i, value in enumerate(request['records']) if value is record)
            suffix = match.group(2)
            field = 'records[%d]' % original
            if suffix == 'event_id':
                field += '.record_id'
            elif suffix == 'time_from_episode_start_s':
                field += '.' + suffix
            elif suffix:
                field += '.footprint.' + suffix
        elif field == 'episode_id':
            field = 'assessment_id'
        elif field == 'events':
            field = 'records'
        elif error.get('record_type') == 'event' and rid is not None:
            original = next((i for i, r in enumerate(request['records']) if r.get('record_id') == rid), None)
            if original is not None:
                field = 'records[%d].footprint' % original
        mapped.append(_issue(error['code'], field, error['message'], rid))
    return mapped


def _validate_request(dataset, request):
    errors = []

    def shape(value, allowed, required, path):
        if not isinstance(value, dict):
            errors.append(_issue('invalid_type', path, 'Expected an object.'))
            return False
        for key in sorted(set(value) - allowed, key=str):
            errors.append(_issue('unknown_property', path + '.' + str(key), 'Property is not permitted.'))
        for key in sorted(required - set(value)):
            errors.append(_issue('missing_property', path + '.' + key, 'Required property is missing.'))
        return True

    common = {'schema_version', 'assessment_id', 'mode', 'population_dataset_id',
              'population_dataset_version', 'coordinate_reference_system', 'records'}
    if not shape(request, common | {'geometry_settings', 'comparisons'}, common, '$'):
        return errors, None
    if request.get('schema_version') != REQUEST_VERSION:
        errors.append(_issue('unsupported_schema', 'schema_version', 'Expected ' + REQUEST_VERSION))
    mode = request.get('mode')
    if mode not in ('alternatives', 'episode'):
        errors.append(_issue('invalid_mode', 'mode', 'Expected alternatives or episode.'))
    if request.get('coordinate_reference_system') != 'EPSG:3414':
        errors.append(_issue('incompatible_crs', 'coordinate_reference_system', 'Expected exactly EPSG:3414.'))
    settings = None
    raw_settings = request.get('geometry_settings', {})
    if shape(raw_settings, {'circle_edges'}, set(), 'geometry_settings'):
        try:
            settings = CalculationSettings(circle_edges=raw_settings.get('circle_edges', 128))
        except ValueError as exc:
            errors.append(_issue('invalid_settings', 'geometry_settings.circle_edges', str(exc)))
    records = request.get('records')
    if not isinstance(records, list):
        errors.append(_issue('invalid_type', 'records', 'Expected an array.'))
    else:
        record_fields = {'record_id', 'footprint'}
        if mode == 'episode':
            record_fields.add('time_from_episode_start_s')
        for i, record in enumerate(records):
            path = 'records[%d]' % i
            if shape(record, record_fields, {'record_id', 'footprint'}, path):
                fields = {'footprint_id', 'center_x_m', 'center_y_m', 'radius_m'}
                shape(record.get('footprint'), fields, fields, path + '.footprint')
    if mode != 'alternatives' and 'comparisons' in request:
        errors.append(_issue('prohibited_field', 'comparisons', 'Comparisons are allowed only in alternatives mode.'))
    pairs = request.get('comparisons', [])
    if not isinstance(pairs, list):
        errors.append(_issue('invalid_type', 'comparisons', 'Expected an array.'))
    else:
        seen = set()
        ids = {r['record_id'] for r in records or [] if isinstance(r, dict) and identifier(r.get('record_id'))} if isinstance(records, list) else set()
        for i, pair in enumerate(pairs):
            keys = {'reference_record_id', 'comparison_record_id'}
            path = 'comparisons[%d]' % i
            if not shape(pair, keys, keys, path):
                continue
            values = [pair.get(key) for key in ('reference_record_id', 'comparison_record_id')]
            if not all(identifier(v) for v in values):
                errors.append(_issue('invalid_identifier', path, 'Comparison IDs must be nonempty strings.'))
                continue
            for key in sorted(keys):
                if pair[key] not in ids:
                    errors.append(_issue('unknown_comparison_record', path + '.' + key, 'Comparison references an unknown record.', pair[key]))
            ordered = tuple(values)
            if ordered[0] == ordered[1]:
                errors.append(_issue('self_comparison', path, 'Comparison requires two distinct records.'))
            if ordered in seen:
                errors.append(_issue('duplicate_comparison', path, 'Ordered comparison pair must be unique.'))
            seen.add(ordered)
    if errors:
        return errors, settings
    # Validation only: no union or exposure calculation across alternatives.
    errors.extend(_map_pec_errors(validate_episode(_to_pec_episode(request, records), dataset), records, request))
    return errors, settings


def _invalid_result(request, errors):
    result = dict(schema_version=RESULT_VERSION, status='invalid_input', errors=errors)
    if isinstance(request, dict):
        if identifier(request.get('assessment_id')):
            result['assessment_id'] = request['assessment_id']
        if request.get('mode') in ('alternatives', 'episode'):
            result['mode'] = request['mode']
    return result


def _build_comparisons(records, pairs):
    by_id = {r['record_id']: r['exposure'] for r in records}
    results = []
    for pair in sorted(pairs, key=lambda p: (p['reference_record_id'], p['comparison_record_id'])):
        reference = by_id[pair['reference_record_id']]
        comparison = by_id[pair['comparison_record_id']]
        reasons = []
        comparable = reference['status'] == comparison['status'] == 'complete'
        result = dict(pair, reference_coverage_status=reference['status'], comparison_coverage_status=comparison['status'],
                      coverage_comparable=comparable, people_exposure_delta=None, people_exposure_ratio=None,
                      footprint_area_delta_m2=None, reasons=reasons)

        def calculate(field, operation):
            try:
                value = operation()
                if math.isfinite(value):
                    result[field] = value
                    return
            except OverflowError:
                pass
            reasons.append(_issue('numeric_range_exceeded', field, 'Derived value is outside finite numeric range.'))

        calculate('footprint_area_delta_m2', lambda: comparison['footprint_area_m2'] - reference['footprint_area_m2'])
        if comparable:
            a, b = reference['people_potentially_exposed'], comparison['people_potentially_exposed']
            calculate('people_exposure_delta', lambda: b - a)
            if a == 0:
                reasons.append(_issue('zero_reference_exposure', 'people_exposure_ratio', 'Ratio is undefined for zero reference exposure.'))
            else:
                calculate('people_exposure_ratio', lambda: b / a)
        else:
            for role, exposure in (('reference', reference), ('comparison', comparison)):
                if exposure['status'] != 'complete':
                    reasons.append(_issue(role + '_partial_coverage', role + '_record_id',
                                          'Complete exposure is unavailable because population coverage is partial.', pair[role + '_record_id']))
        results.append(result)
    return results


def _build_summary(records):
    values = [r['exposure']['people_potentially_exposed'] for r in records if r['exposure']['status'] == 'complete']
    return dict(number_records_supplied=len(records), number_complete=len(values),
                number_partial_coverage=len(records) - len(values),
                complete_exposure_range=dict(count=len(values), minimum=min(values) if values else None,
                                             maximum=max(values) if values else None))


def _assess_alternatives(dataset, request, settings):
    records, metadata = [], None
    for record in sorted(request['records'], key=lambda r: r['record_id']):
        pec = calculate_episode(dataset, _to_pec_episode(request, [record]), settings)
        if pec['status'] == 'invalid_input':
            return _invalid_result(request, _map_pec_errors(pec['errors'], [record], request))
        exposure = pec['events'][0]
        metadata = pec['metadata']
        warnings = []
        if exposure['status'] == 'partial_coverage':
            warnings.append(_issue('partial_population_coverage', 'exposure.people_potentially_exposed',
                                   'Known-area exposure is a subtotal; complete exposure is unavailable.', record['record_id']))
        records.append(dict(record_id=record['record_id'], exposure=exposure, warnings=warnings))
    if metadata is None:
        pec = calculate_episode(dataset, _to_pec_episode(request, []), settings)
        if pec['status'] == 'invalid_input':
            return _invalid_result(request, _map_pec_errors(pec['errors'], [], request))
        metadata = pec['metadata']
    return dict(schema_version=RESULT_VERSION, assessment_id=request['assessment_id'], mode='alternatives',
                status='partial_coverage' if any(r['exposure']['status'] == 'partial_coverage' for r in records) else 'complete',
                records=records, comparisons=_build_comparisons(records, request.get('comparisons', [])),
                summary=_build_summary(records), provenance=metadata)


def _assess_episode(dataset, request, settings):
    pec = calculate_episode(dataset, _to_pec_episode(request, request['records']), settings)
    if pec['status'] == 'invalid_input':
        return _invalid_result(request, _map_pec_errors(pec['errors'], request['records'], request))
    return dict(schema_version=RESULT_VERSION, assessment_id=request['assessment_id'], mode='episode',
                status=pec['status'], pec_result=pec)


def assess_footprints(prepared_population, request):
    """Assess a decoded request against reusable population prepared by PEC.

    No input mutation, file I/O, population preparation, or action selection.
    Evidence is deterministic; diagnostics contain measured wall-clock latency.
    """
    started = perf_counter_ns()
    errors, settings = _validate_request(prepared_population, request)
    if errors:
        result = _invalid_result(request, errors)
    elif request['mode'] == 'alternatives':
        result = _assess_alternatives(prepared_population, request, settings)
    else:
        result = _assess_episode(prepared_population, request, settings)
    result['diagnostics'] = dict(evaluation_latency_ms=(perf_counter_ns() - started) / 1_000_000)
    return result
