"""Publication boundary for the two canonical v1 payloads.

Validation never repairs or enriches evidence. The original object is returned.
"""
from datetime import datetime
import math
import re


class InvalidResult(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidResult(message)


def obj(value, path):
    require(isinstance(value, dict), f'{path} must be an object')
    return value


def rows(value, path):
    require(isinstance(value, list), f'{path} must be an array')
    return value


def text(value, path):
    require(isinstance(value, str) and bool(value.strip()), f'{path} must be a nonempty string')
    return value


def number(value, path, nullable=False):
    if nullable and value is None:
        return value
    require(type(value) in (int, float) and math.isfinite(value), f'{path} must be finite')
    return value


def instant(value, path):
    require(isinstance(value, str) and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value), f'{path} must be UTC')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise InvalidResult(f'{path} is not a valid timestamp') from exc


def position(value, path, height='height'):
    value = obj(value, path)
    lon, lat = number(value.get('lon'), path + '.lon'), number(value.get('lat'), path + '.lat')
    number(value.get(height), path + '.' + height)
    require(-180 <= lon <= 180 and -90 <= lat <= 90, f'{path} outside coordinate bounds')
    if height == 'heightM':
        require(value[height] >= 0, f'{path} negative height')


def json_values(value, path='$'):
    if type(value) in (int, float):
        number(value, path)
    elif isinstance(value, dict):
        for key, item in value.items():
            require(isinstance(key, str), f'{path} key must be a string')
            json_values(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            json_values(item, f'{path}[{index}]')
    else:
        require(value is None or type(value) in (str, bool), f'{path} not a JSON value')


def unique_ids(values, key, path):
    ids = [text(obj(row, path).get(key), f'{path}.{key}') for row in values]
    require(len(ids) == len(set(ids)), f'{path} duplicate IDs')
    return set(ids)


def strings(value, path):
    for item in rows(value, path):
        text(item, path)
    return value


def figure(value, path):
    if value is None:
        return
    obj(value, path)
    central = number(value.get('central'), path + '.central')
    lo = number(value.get('low'), path + '.low', True)
    hi = number(value.get('high'), path + '.high', True)
    require((lo is None or lo <= central) and (hi is None or central <= hi), f'{path} invalid bounds')


def planning(root):
    text(root.get('scenarioId'), 'scenarioId')
    threat = obj(root.get('threat'), 'threat')
    text(threat.get('id'), 'threat.id')
    samples = rows(threat.get('samples'), 'threat.samples')
    require(len(samples) >= 2, 'The threat needs at least two ordered samples')
    previous = None
    for sample in samples:
        position(sample, 'sample')
        current = instant(sample.get('time'), 'sample.time')
        require(previous is None or current > previous, 'Threat samples must be strictly ordered')
        previous = current
    candidates = rows(root.get('candidates'), 'candidates')
    ids = unique_ids(candidates, 'id', 'candidates')
    assumptions = obj(root.get('assumptions'), 'assumptions')
    radius = number(assumptions.get('footprintRadiusM'), 'assumptions.footprintRadiusM')
    require(radius > 0, 'Planning footprint radius must be positive')
    for field in ('successModel', 'footprintModel', 'populationExposureMeaning', 'kinematicsCalibration',
                  'heightMeaning', 'scenarioTimeMeaning'):
        text(assumptions.get(field), 'assumptions.' + field)
    number(assumptions.get('visualizationHeightM'), 'assumptions.visualizationHeightM')
    for candidate in candidates:
        position(candidate.get('position'), 'candidate.position')
        instant(candidate.get('time'), 'candidate.time')
        require(type(candidate.get('sampleIndex')) is int, 'sampleIndex must be an integer')
        number(candidate.get('timeFromStartS'), 'timeFromStartS')
        for field in ('requiredTravelTimeS', 'timeMarginS'):
            require(field in candidate, f'Missing {field}')
            number(candidate[field], field, True)
        for field in ('reachable', 'paretoEfficient', 'eligibleForRecommendation'):
            require(type(candidate.get(field)) is bool, f'{field} must be boolean')
        strings(candidate.get('categories'), 'categories')
        strings(candidate.get('ineligibilityReasons'), 'ineligibilityReasons')
        if 'suppliedSuccessProbability' in candidate:
            probability = number(candidate['suppliedSuccessProbability'], 'suppliedSuccessProbability')
            require(0 <= probability <= 1, 'Success probability outside [0,1]')
        if 'footprint' in candidate:
            footprint = obj(candidate['footprint'], 'footprint')
            text(footprint.get('id'), 'footprint.id')
            require(number(footprint.get('radiusM'), 'radiusM') == radius, 'Mismatched planning radius')
        if 'exposure' in candidate:
            exposure = obj(candidate['exposure'], 'exposure')
            require(exposure.get('status') in ('complete', 'partial_coverage'), 'Unsupported exposure status')
            for field in ('peoplePotentiallyExposed', 'coveredAreaFraction'):
                require(field in exposure, f'Missing exposure.{field}')
                number(exposure[field], field, True)
            number(exposure.get('knownAreaExposure'), 'knownAreaExposure')
            fraction = exposure['coveredAreaFraction']
            require(fraction is None or 0 <= fraction <= 1, 'Coverage outside [0,1]')
            require(exposure['status'] != 'partial_coverage' or exposure['peoplePotentiallyExposed'] is None,
                    'Partial exposure must not assert a complete total')
        if 'consequence' in candidate:
            consequence = obj(candidate['consequence'], 'consequence')
            require('total' in consequence, 'Missing consequence total')
            figure(consequence['total'], 'consequence.total')
            for dimension in rows(consequence.get('dimensions'), 'dimensions'):
                require(dimension.get('id') in ('H', 'E', 'D', 'X', 'R', 'A'), 'Unknown dimension')
                number(dimension.get('weight'), 'dimension.weight')
                require('value' in dimension, 'Missing evidence must be null')
                figure(dimension['value'], 'dimension.value')
    pareto = strings(root.get('paretoCandidateIds'), 'paretoCandidateIds')
    reps = strings(root.get('representativeCandidateIds'), 'representativeCandidateIds')
    require(set(pareto) <= ids and set(reps) <= set(pareto), 'Broken Pareto/representative reference')
    require(len(set(reps)) == len(reps), 'Duplicate representatives')
    by_id = {row['id']: row for row in candidates}
    for identity in reps:
        require('footprint' in by_id[identity], 'Representative needs a supplied footprint')
    categories = obj(root.get('categoryAssignments'), 'categoryAssignments')
    for key in ('earliestViable', 'highestSuccess', 'lowestExposure'):
        require(key in categories, f'Missing categoryAssignments.{key}')
    for identity in categories.values():
        require(identity is None or isinstance(identity, str) and identity in ids, 'Broken category reference')
    for comparison in rows(root.get('comparisons'), 'comparisons'):
        require(comparison.get('referenceCandidateId') in ids and comparison.get('comparisonCandidateId') in ids,
                'Broken comparison reference')
        number(comparison.get('deltaTimeS'), 'deltaTimeS')
        for key in ('deltaSuccessProbability', 'deltaSuccessPercentagePoints',
                    'deltaPeoplePotentiallyExposed', 'relativeExposureChange'):
            require(key in comparison, 'Missing comparison.' + key)
            number(comparison[key], key, True)
    diagnostics = obj(root.get('diagnostics'), 'diagnostics')
    for key in ('totalCandidates', 'reachableCandidates', 'eligibleCandidates', 'paretoCandidates'):
        number(diagnostics.get(key), 'diagnostics.' + key)
    provenance = obj(root.get('populationProvenance'), 'populationProvenance')
    for key in ('datasetId', 'datasetVersion', 'coordinateReferenceSystem'):
        text(provenance.get(key), 'populationProvenance.' + key)


def simulation(root):
    require(root.get('episodeSchemaVersion') == 'simulation-episode/2', 'Wrong episode schema')
    text(root.get('episodeId'), 'episodeId')
    require(type(root.get('seed')) is int and 0 <= root['seed'] <= 2**31 - 1, 'Invalid seed')
    obj(root.get('coordinateReferenceSystems'), 'coordinateReferenceSystems')
    trajectories = rows(root.get('trajectories'), 'trajectories')
    threats = unique_ids(trajectories, 'threatId', 'trajectories')
    require(len(threats) == 8, 'Expected eight trajectories')
    for trajectory in trajectories:
        number(trajectory.get('detectionTimeS'), 'detectionTimeS')
        instant(trajectory.get('detectionTime'), 'detectionTime')
        samples = rows(trajectory.get('samples'), 'samples')
        require(len(samples) == 20, 'Expected 20 samples')
        previous = None
        for index, sample in enumerate(samples, 1):
            require(type(sample.get('sampleIndex')) is int and sample['sampleIndex'] == index, 'Unordered sample indices')
            current = instant(sample.get('time'), 'sample.time')
            require(previous is None or current > previous, 'Unordered sample times')
            previous = current
            position(sample.get('position'), 'sample.position', 'heightM')
            for key in ('timeFromDetectionS', 'timeFromEpisodeStartS', 'verticalVelocityMps'):
                number(sample.get(key), key)
        require(samples[-1]['position']['heightM'] == 0, 'Trajectory must terminate at zero height')
    assignments = rows(root.get('assignments'), 'assignments')
    require(len(assignments) == 8, 'Expected eight assignments')
    require(unique_ids(assignments, 'threat_id', 'assignments') == threats, 'Broken assignment threat reference')
    unique_ids(assignments, 'interceptor_id', 'assignments')
    unique_ids(assignments, 'opportunity_id', 'assignments')
    by_threat = {row['threat_id']: row for row in assignments}
    require(all(row.get('status') == 'locked' for row in assignments), 'Assignment not locked')
    for key, kind in (('selectedFootprints', 'selected'), ('terminalCounterfactualFootprints', 'terminal_counterfactual')):
        footprints = rows(root.get(key), key)
        require(len(footprints) == 8, 'Expected eight footprints')
        unique_ids(footprints, 'id', key)
        require(unique_ids(footprints, 'threatId', key) == threats, 'Broken footprint threat reference')
        for footprint in footprints:
            require(footprint.get('kind') == kind, 'Wrong footprint kind')
            require(footprint.get('label') == 'supplied 100 m area', 'Wrong supplied area label')
            require(number(footprint.get('radiusM'), 'radiusM') == 100, 'Mismatched simulation radius')
            position(footprint.get('center'), 'footprint.center', 'heightM')
            require('consequence' in footprint, 'Missing footprint consequence')
            if kind == 'selected':
                require(footprint.get('opportunityId') == by_threat[footprint['threatId']]['opportunity_id'],
                        'Broken selected footprint assignment reference')
    rows(root.get('events'), 'events')
    summary = obj(root.get('consequenceSummary'), 'consequenceSummary')
    number(summary.get('ordinalObjectiveCost'), 'ordinalObjectiveCost')
    for key, value in obj(summary.get('physicalComponents'), 'physicalComponents').items():
        number(value, 'physicalComponents.' + key)
    wording = obj(summary.get('wording'), 'wording')
    require(wording.get('area') == 'supplied 100 m area'
            and wording.get('population') == 'people potentially exposed'
            and wording.get('casualties') == 'assumption-grade expected casualties', 'Wrong consequence wording')
    comparison = obj(root.get('policyVersusBaseline'), 'policyVersusBaseline')
    baseline = 'feasible-immediate-matching/1'
    require(comparison.get('policyIdentity') in (baseline, 'optimal-fixed-rank-assignment/1')
            and comparison.get('baselineIdentity') == baseline, 'Unsupported policy identity')
    for key in ('policyOrdinalCost', 'baselineOrdinalCost'):
        number(comparison.get(key), key)
    require('measuredRelativeImprovement' in comparison, 'Missing measured improvement')
    number(comparison['measuredRelativeImprovement'], 'measuredRelativeImprovement', True)
    text(comparison.get('claim'), 'claim')
    obj(root.get('provenance'), 'provenance')
    strings(root.get('limitations'), 'limitations')


_V2_POLICIES = {
    'naive-launch-on-detection/1': 'online-detected-only',
    'feasible-immediate-matching/1': 'offline-full-episode',
    'optimal-fixed-rank-assignment/1': 'offline-full-episode',
    'structured-behavior-cloning/1': 'online-observation-only',
}
_V2_SPLITS = {
    'validation', 'held-out', 'stress', 'ood-geography', 'ood-cadence',
    'assignment-reference',
}
_V2_PROFILES = {
    'warmup', 'balanced', 'full-standard', 'burst-contention', 'low-slack',
    'consequence-contrast', 'geographic-shift', 'cadence-shift',
}
_HASH = re.compile(r'sha256:[0-9a-f]{64}', re.ASCII)
_SCENARIO_REF = re.compile(
    r'sg2:(validation|held-out|stress|ood-geography|ood-cadence|assignment-reference):[0-9]{6}',
    re.ASCII)


def _v2_trajectories(root):
    trajectories = rows(root.get('trajectories'), 'trajectories')
    threats = unique_ids(trajectories, 'threatId', 'trajectories')
    require(2 <= len(trajectories) <= 8,
            'simulation-result/2 requires two through eight trajectories')
    for trajectory in trajectories:
        number(trajectory.get('detectionTimeS'), 'detectionTimeS')
        instant(trajectory.get('detectionTime'), 'detectionTime')
        samples = rows(trajectory.get('samples'), 'samples')
        require(len(samples) == 20, 'Expected 20 samples')
        previous = None
        for index, sample in enumerate(samples, 1):
            require(type(sample.get('sampleIndex')) is int
                    and sample['sampleIndex'] == index,
                    'Unordered sample indices')
            current = instant(sample.get('time'), 'sample.time')
            require(previous is None or current > previous,
                    'Unordered sample times')
            previous = current
            position(sample.get('position'), 'sample.position', 'heightM')
            for key in ('timeFromDetectionS', 'timeFromEpisodeStartS',
                        'verticalVelocityMps'):
                number(sample.get(key), key)
        require(samples[-1]['position']['heightM'] == 0,
                'Trajectory must terminate at zero height')
    return threats


def _v2_policy_record(value, path, identity=None):
    value = obj(value, path)
    policy = text(value.get('policyIdentity'), path + '.policyIdentity')
    require(policy in _V2_POLICIES, 'Unsupported policy identity')
    if identity is not None:
        require(policy == identity, path + ' policy identity mismatch')
    require(value.get('informationScope') == _V2_POLICIES[policy],
            path + ' information scope mismatch')
    number(value.get('ordinalCost'), path + '.ordinalCost')
    require(type(value.get('completed')) is bool,
            path + '.completed must be boolean')
    text(value.get('terminationReason'), path + '.terminationReason')
    return value


def simulation_v2(root):
    require(root.get('episodeSchemaVersion') == 'simulation-episode/2',
            'Wrong episode schema')
    text(root.get('episodeId'), 'episodeId')
    require(type(root.get('seed')) is int and 0 <= root['seed'] <= 2**31 - 1,
            'Invalid seed')
    obj(root.get('coordinateReferenceSystems'), 'coordinateReferenceSystems')
    threats = _v2_trajectories(root)

    assignments = rows(root.get('assignments'), 'assignments')
    require(len(assignments) <= len(threats), 'Too many assignments')
    assignment_threats = unique_ids(assignments, 'threat_id', 'assignments')
    require(assignment_threats <= threats, 'Broken assignment threat reference')
    unique_ids(assignments, 'interceptor_id', 'assignments')
    assignment_opportunities = unique_ids(
        assignments, 'opportunity_id', 'assignments')
    require(all(row.get('status') == 'locked' for row in assignments),
            'Version 2 publishes only locked assignments')

    selected = rows(root.get('selectedFootprints'), 'selectedFootprints')
    terminal = rows(root.get('terminalCounterfactualFootprints'),
                    'terminalCounterfactualFootprints')
    require(len(selected) == len(assignments),
            'Selected footprint count must equal assignment count')
    require(len(terminal) == len(threats),
            'Terminal footprint count must equal trajectory count')
    by_assignment = {
        (row['threat_id'], row['opportunity_id']) for row in assignments}
    for footprints, kind in ((selected, 'selected'),
                             (terminal, 'terminal_counterfactual')):
        unique_ids(footprints, 'id', kind + ' footprints')
        footprint_threats = unique_ids(
            footprints, 'threatId', kind + ' footprints')
        require(footprint_threats <= threats,
                'Broken footprint threat reference')
        for footprint in footprints:
            require(footprint.get('kind') == kind, 'Wrong footprint kind')
            require(footprint.get('label') == 'supplied 100 m area',
                    'Wrong supplied area label')
            require(number(footprint.get('radiusM'), 'radiusM') == 100,
                    'Mismatched simulation radius')
            position(footprint.get('center'), 'footprint.center', 'heightM')
            require('consequence' in footprint,
                    'Missing footprint consequence')
            if kind == 'selected':
                opportunity = text(
                    footprint.get('opportunityId'), 'opportunityId')
                require((footprint['threatId'], opportunity) in by_assignment,
                        'Broken selected footprint assignment reference')
                require(opportunity in assignment_opportunities,
                        'Unknown selected opportunity')
    require({row['threatId'] for row in selected} == assignment_threats,
            'Selected footprints must cover assignments exactly')
    require({row['threatId'] for row in terminal} == threats,
            'Terminal footprints must cover every threat')

    outcomes = rows(root.get('outcomes'), 'outcomes')
    require(len(outcomes) == len(threats),
            'Outcome count must equal trajectory count')
    require(unique_ids(outcomes, 'threatId', 'outcomes') == threats,
            'Outcomes must cover every threat exactly once')
    intercepted = set()
    for outcome in outcomes:
        value = outcome.get('outcome')
        require(value in ('intercepted', 'unhandled'), 'Invalid outcome')
        resolved_s = number(
            outcome.get('resolvedTimeS'), 'resolvedTimeS', True)
        resolved_at = outcome.get('resolvedTime')
        require(resolved_at is None or resolved_s is not None,
                'resolvedTime requires resolvedTimeS')
        if resolved_at is not None:
            instant(resolved_at, 'resolvedTime')
        number(outcome.get('trainingCost'), 'trainingCost', True)
        interceptor = outcome.get('interceptorId')
        opportunity = outcome.get('opportunityId')
        if value == 'intercepted':
            intercepted.add(outcome['threatId'])
            text(interceptor, 'interceptorId')
            text(opportunity, 'opportunityId')
            require((outcome['threatId'], opportunity) in by_assignment,
                    'Intercepted outcome does not resolve to its assignment')
            require(resolved_s is not None,
                    'Intercepted outcome needs a resolution time')
        else:
            require(interceptor is None and opportunity is None,
                    'Unhandled outcome cannot claim an assignment')
    require(intercepted == assignment_threats,
            'Intercepted outcomes must equal locked assignments')

    rows(root.get('events'), 'events')
    summary = obj(root.get('consequenceSummary'), 'consequenceSummary')
    number(summary.get('ordinalObjectiveCost'), 'ordinalObjectiveCost')
    for key, value in obj(
            summary.get('physicalComponents'), 'physicalComponents').items():
        number(value, 'physicalComponents.' + key)
    wording = obj(summary.get('wording'), 'wording')
    require(wording.get('area') == 'supplied 100 m area'
            and wording.get('population') == 'people potentially exposed'
            and wording.get('casualties')
            == 'assumption-grade expected casualties',
            'Wrong consequence wording')

    policy = obj(root.get('policy'), 'policy')
    policy_identity = text(policy.get('identity'), 'policy.identity')
    require(policy_identity in _V2_POLICIES, 'Unsupported policy identity')
    require(policy.get('informationScope') == _V2_POLICIES[policy_identity],
            'Policy information scope mismatch')
    if policy_identity == 'structured-behavior-cloning/1':
        require(_HASH.fullmatch(text(
            policy.get('artifactIdentity'), 'policy.artifactIdentity'))
            is not None, 'Malformed policy artifact identity')
        require(policy.get('deploymentStatus') == 'experimental-unpromoted',
                'Structured imitation deployment status mismatch')
    comparison = obj(root.get('policyComparison'), 'policyComparison')
    active = _v2_policy_record(
        comparison.get('active'), 'policyComparison.active', policy_identity)
    naive = _v2_policy_record(
        comparison.get('naive'), 'policyComparison.naive',
        'naive-launch-on-detection/1')
    exact = _v2_policy_record(
        comparison.get('exactReference'), 'policyComparison.exactReference',
        'optimal-fixed-rank-assignment/1')
    require(exact.get('exact') is True and exact.get('completed') is True
            and exact.get('predictedCostMatchesReplay') is True,
            'Exact reference must be a completed proved replay')
    predicted = number(
        exact.get('predictedOrdinalCost'), 'predictedOrdinalCost')
    require(math.isclose(predicted, exact['ordinalCost'],
                         rel_tol=0.0, abs_tol=1e-12),
            'Exact predicted cost does not match replay')
    text(exact.get('proofScope'), 'proofScope')
    active_minus_naive = number(
        comparison.get('activeMinusNaiveCost'), 'activeMinusNaiveCost')
    require(math.isclose(
        active_minus_naive,
        active['ordinalCost'] - naive['ordinalCost'],
        rel_tol=0.0, abs_tol=1e-12),
        'Active/naive comparison is inconsistent')
    regret = comparison.get('exactRegret')
    if active['completed']:
        regret = number(regret, 'exactRegret')
        require(math.isclose(
            regret, active['ordinalCost'] - exact['ordinalCost'],
            rel_tol=0.0, abs_tol=1e-12) and regret >= -1e-12,
            'Exact regret is inconsistent')
    else:
        require(regret is None,
                'Incomplete active policies cannot claim exact regret')

    termination = obj(root.get('termination'), 'termination')
    reason = text(termination.get('reason'), 'termination.reason')
    require(type(termination.get('completed')) is bool,
            'termination.completed must be boolean')
    require(termination['completed'] == active['completed']
            and reason == active['terminationReason'],
            'Active policy and termination disagree')
    number(termination.get('terminationTimeS'), 'terminationTimeS')
    if termination['completed']:
        require(reason == 'all_threats_resolved'
                and termination.get('constraintStatus') == 'satisfied'
                and termination.get('constraintViolation') is None
                and intercepted == threats,
                'Completed result has inconsistent constraint state')
    else:
        require(reason.startswith('constraint_violation:')
                and termination.get('constraintStatus') == 'violated'
                and isinstance(termination.get('constraintViolation'), str)
                and bool(termination['constraintViolation'].strip())
                and intercepted != threats,
                'Recorded failure has inconsistent constraint state')

    provenance = obj(root.get('provenance'), 'provenance')
    scenario_ref = text(provenance.get('scenarioRef'),
                        'provenance.scenarioRef')
    require(_SCENARIO_REF.fullmatch(scenario_ref) is not None,
            'Malformed scenario reference')
    split = provenance.get('split')
    profile = provenance.get('profile')
    require(split in _V2_SPLITS, 'Unsupported scenario split')
    require(profile in _V2_PROFILES, 'Unsupported scenario profile')
    require(scenario_ref.startswith('sg2:' + split + ':'),
            'Scenario reference/split mismatch')
    require(provenance.get('seed') == root['seed'],
            'Scenario provenance seed mismatch')
    require(provenance.get('generatorVersion') == 'singapore-scenario/2'
            and provenance.get('distributionVersion')
            == 'singapore-scenario-distribution/1'
            and provenance.get('providerIdentity') == 'singapore-demo-v2',
            'Scenario provenance identity mismatch')
    for key in ('distributionChecksum', 'providerConfigChecksum',
                'providerDataChecksum', 'scenarioConfigChecksum',
                'generatorConfigurationChecksum', 'boundarySourceChecksum',
                'mainIslandGeometryChecksum', 'canonicalEpisodeHash'):
        digest = provenance.get(key)
        require(isinstance(digest, str) and _HASH.fullmatch(digest) is not None,
                'Malformed provenance hash: ' + key)
    for key in ('providerRuntimeIdentity', 'providerVersion',
                'simulatorVersion'):
        text(provenance.get(key), 'provenance.' + key)
    require(provenance.get('hashVerified') is True,
            'Scenario hash must be verified')
    require(provenance.get('policyIdentity') == policy_identity,
            'Policy provenance mismatch')
    if policy_identity == 'structured-behavior-cloning/1':
        require(provenance.get('policyArtifactIdentity')
                == policy.get('artifactIdentity'),
                'Policy artifact provenance mismatch')
        require(provenance.get('policyDeploymentStatus')
                == 'experimental-unpromoted',
                'Policy deployment provenance mismatch')
    strings(root.get('limitations'), 'limitations')


def validate_result(kind, value):
    require(kind in ('planning', 'simulation'), 'Unsupported result kind')
    root = obj(value, 'result')
    json_values(root)
    schema = root.get('schemaVersion')
    require(schema == kind + '-result/1'
            or kind == 'simulation' and schema == 'simulation-result/2',
            'Wrong result schema/kind')
    require(instant(root.get('start'), 'start') <= instant(root.get('end'), 'end'), 'Reversed result interval')
    try:
        (planning if kind == 'planning' else
         simulation_v2 if schema == 'simulation-result/2' else simulation)(root)
    except (KeyError, TypeError, AttributeError) as exc:
        raise InvalidResult(f'Malformed {kind} result: {exc}') from exc
    return value
