"""Export a completed version-2 simulation as ``simulation-result/1``."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping, Optional

from pyproj import Transformer

from backend.planning import sample_threat_trajectory
from backend.simulation import (AssignmentPlan, FeasibleImmediateMatchingPolicy,
                                NaiveLaunchOnDetectionPolicy,
                                OptimalFixedRankAssignmentPolicy,
                                SimulationEngine, canonical_episode_hash)


SIMULATION_RESULT_SCHEMA_VERSION = 'simulation-result/1'
SIMULATION_RESULT_V2_SCHEMA_VERSION = 'simulation-result/2'
_TO_WGS84 = Transformer.from_crs('EPSG:3414', 'EPSG:4326', always_xy=True)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec='microseconds').replace('+00:00', 'Z')


def _position(x: float, y: float, z: float) -> Mapping[str, float]:
    lon, lat = _TO_WGS84.transform(x, y, errcheck=True)
    values = (lon, lat, z)
    if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
        raise ValueError('coordinate conversion returned a nonfinite position')
    return {'lon': lon, 'lat': lat, 'heightM': z}


def simulation_result_to_dict(
        engine: SimulationEngine,
        start_time: str = '2026-09-26T04:00:00Z',
        policy_identity: str = FeasibleImmediateMatchingPolicy.identity,
        baseline_raw_score: Optional[float] = None,
        assignment_plan: Optional[AssignmentPlan] = None) -> Mapping[str, Any]:
    if not isinstance(engine, SimulationEngine):
        raise ValueError('engine must be a SimulationEngine')
    if engine.spec.schema_version != 'simulation-episode/2':
        raise ValueError('simulation-result/1 requires simulation-episode/2')
    if not engine.terminated or engine.truncated or engine.aggregate_result is None:
        raise ValueError('simulation must terminate successfully before export')
    if engine.termination_reason != 'all_threats_resolved':
        raise ValueError('constraint-violating episodes cannot be exported')
    if (len(engine.spec.threats) != 8 or len(engine.spec.interceptors) != 8
            or engine.spec.candidate_count != 20):
        raise ValueError('simulation-result/1 requires the fixed 8x8x20 scenario')
    if (len(engine.assignments) != 8 or len(engine.consumed_interceptors) != 8
            or len({row.interceptor_id for row in engine.assignments.values()}) != 8
            or any(runtime.resolution is None
                   or runtime.resolution.value != 'intercepted'
                   for runtime in engine.threats.values())):
        raise ValueError('export requires eight intercepted threats and distinct assignments')
    try:
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError('start_time must be timezone-aware ISO 8601') from exc
    if start.utcoffset() is None:
        raise ValueError('start_time must include a timezone')
    start = start.astimezone(timezone.utc)
    radius = float(engine.spec.metadata['scenario_contract'][
        'supplied_footprint_radius_m'])
    if (radius != 100.0 or getattr(engine.provider, 'footprint_radius_m', None) != radius
            or engine.spec.metadata.get('objective_reference')
            != 'full-candidate-universe/1'):
        raise ValueError('export radius/objective contract disagrees with the episode')
    if any(float(row.metadata.get('supplied_footprint_radius_m', math.nan)) != radius
           for row in engine.spec.threats):
        raise ValueError('threat footprint radius disagrees with the scenario')
    for runtime in engine.threats.values():
        for assessment in runtime.candidate_assessments.values():
            assessment_radius = (assessment.footprint_radius_m
                                 if hasattr(assessment, 'footprint_radius_m')
                                 else assessment.get('footprint_radius_m'))
            if assessment_radius != radius:
                raise ValueError('candidate footprint radius disagrees with the scenario')
    provider_island = getattr(getattr(engine.provider, 'catalog', None),
                              'main_island', None)
    if (provider_island is None or provider_island.geometry_checksum
            != engine.spec.metadata.get('main_island_geometry_checksum')):
        raise ValueError('export provider/scenario geometry checksum mismatch')

    trajectories = []
    terminal_footprints = []
    selected_footprints = []
    assignments = []
    for scheduled in engine.spec.threats:
        state = scheduled.state
        samples = sample_threat_trajectory(state, engine.spec.candidate_count)
        trajectories.append({
            'threatId': state.threat_id,
            'detectionTimeS': scheduled.detection_time_s,
            'detectionTime': _iso(start + timedelta(seconds=scheduled.detection_time_s)),
            'samples': [{
                'sampleIndex': row.sample_index,
                'timeFromDetectionS': row.time_from_start_s,
                'timeFromEpisodeStartS': scheduled.detection_time_s + row.time_from_start_s,
                'time': _iso(start + timedelta(
                    seconds=scheduled.detection_time_s + row.time_from_start_s)),
                'position': _position(row.position_x_m, row.position_y_m,
                                      row.position_z_m),
                'verticalVelocityMps': row.velocity_z_mps,
            } for row in samples],
        })
        runtime = engine.threats[state.threat_id]
        terminal_candidate = next(
            row for interceptor_id in sorted(runtime.candidates)
            for row in runtime.candidates[interceptor_id]
            if row.opportunity.sample_index == engine.spec.candidate_count)
        terminal_assessment = runtime.candidate_assessments.get(
            terminal_candidate.opportunity.opportunity_id)
        terminal_footprints.append({
            'id': state.threat_id + ':terminal-counterfactual',
            'threatId': state.threat_id,
            'kind': 'terminal_counterfactual',
            'label': 'supplied 100 m area',
            'center': _position(
                float(scheduled.metadata['terminal_position_x_m']),
                float(scheduled.metadata['terminal_position_y_m']), 0.0),
            'radiusM': radius,
            'consequence': (None if terminal_assessment is None else
                            terminal_assessment.as_dict()),
        })
        assignment = engine.assignments.get(state.threat_id)
        if assignment is not None:
            opportunity = assignment.candidate.opportunity
            snapshot = assignment.consequence_snapshot
            footprint_row = {
                'id': opportunity.opportunity_id + ':supplied-area',
                'threatId': state.threat_id,
                'opportunityId': opportunity.opportunity_id,
                'kind': 'selected',
                'label': 'supplied 100 m area',
                'center': _position(opportunity.position_x_m,
                                    opportunity.position_y_m,
                                    opportunity.position_z_m),
                'radiusM': radius,
                'consequence': snapshot,
            }
            selected_footprints.append(footprint_row)
            assignments.append({
                **assignment.as_dict(),
                'interceptionTime': _iso(start + timedelta(
                    seconds=assignment.candidate.interception_time_s)),
                'lockTime': _iso(start + timedelta(
                    seconds=assignment.candidate.lock_time_s)),
                'position': footprint_row['center'],
            })

    event_rows = []
    for event in engine.event_records:
        event_rows.append({
            **event.as_dict(),
            'absoluteTime': _iso(start + timedelta(seconds=event.time_s)),
        })
    baseline = engine.raw_score if baseline_raw_score is None else baseline_raw_score
    improvement = None if baseline == 0 else (baseline - engine.raw_score) / abs(baseline)
    comparison = {
        'policyIdentity': policy_identity,
        'policyOrdinalCost': engine.raw_score,
        'baselineIdentity': FeasibleImmediateMatchingPolicy.identity,
        'baselineOrdinalCost': baseline,
        'measuredRelativeImprovement': improvement,
        'claim': (
            'exact within the immutable additive fixed-rank assignment-model scope'
            if assignment_plan is not None and assignment_plan.exact
            and assignment_plan.predicted_cost == engine.raw_score
            else 'measured comparison with the feasible full-episode baseline'),
        'assignmentPlan': (None if assignment_plan is None else {
            'policyIdentity': assignment_plan.policy_identity,
            'predictedOrdinalCost': assignment_plan.predicted_cost,
            'exact': assignment_plan.exact,
            'proofScope': assignment_plan.proof_scope,
            'orderedDecisions': [{
                'threatId': row.threat_id,
                'interceptorId': row.interceptor_id,
                'opportunityId': row.opportunity_id,
                'candidateIndex': row.candidate_index,
                'trainingCost': row.training_cost,
            } for row in assignment_plan.decisions],
        }),
    }
    aggregate = engine.aggregate_result
    result = {
        'schemaVersion': SIMULATION_RESULT_SCHEMA_VERSION,
        'episodeSchemaVersion': engine.spec.schema_version,
        'episodeId': engine.spec.episode_id,
        'seed': engine.spec.seed,
        'start': _iso(start),
        'end': _iso(start + timedelta(seconds=max(
            row.expiry_time_s for row in engine.spec.threats))),
        'coordinateReferenceSystems': {
            'calculation': 'EPSG:3414', 'presentation': 'EPSG:4326',
            'verticalReference': engine.spec.metadata['scenario_contract'][
                'vertical_reference'],
        },
        'trajectories': trajectories,
        'events': event_rows,
        'assignments': assignments,
        'selectedFootprints': selected_footprints,
        'terminalCounterfactualFootprints': terminal_footprints,
        'consequenceSummary': {
            'ordinalObjectiveCost': aggregate.training_cost,
            'physicalComponents': dict(aggregate.components),
            'evidence': dict(aggregate.evidence),
            'wording': {
                'area': 'supplied 100 m area',
                'population': 'people potentially exposed',
                'casualties': 'assumption-grade expected casualties',
            },
        },
        'policyVersusBaseline': comparison,
        'provenance': {
            'simulatorVersion': engine.snapshot()['simulator_version'],
            'provider': engine.provider_audit(include_runtime=False),
            'generatorVersion': engine.spec.metadata['generator'],
            'scenarioConfigChecksum': engine.spec.metadata[
                'scenario_config_checksum'],
            'generatorConfigurationChecksum': engine.spec.metadata[
                'generator_configuration_checksum'],
            'boundarySourceChecksum': engine.spec.metadata[
                'boundary_source_checksum'],
            'mainIslandGeometryChecksum': engine.spec.metadata[
                'main_island_geometry_checksum'],
            'canonicalEpisodeHash': canonical_episode_hash(engine.spec),
            'objectiveReference': engine.spec.metadata['objective_reference'],
            'policyIdentity': policy_identity,
        },
        'limitations': [
            'The supplied 100 m area is a scenario input, not a validated blast radius.',
            'No physical debris model, validated casualty model, terrain, drag, wind, aircraft downtime, or recovery transition is simulated.',
            'Interceptor motion is evaluated in two dimensions; no interceptor altitude model is present.',
            'Expected-casualty constants are uncalibrated demonstration assumptions.',
            'weekday_midday is fixed for the ten-second detection window; no calendar progression is simulated.',
            'Transport, healthcare, education, and richer residential-service consequence sectors are unavailable in v1.',
        ],
    }
    _validate_primitives(result)
    return result


def _json_native(value: Any) -> Any:
    """Convert immutable evidence sequences without changing their values."""
    if isinstance(value, tuple):
        return [_json_native(item) for item in value]
    if isinstance(value, list):
        return [_json_native(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_native(item) for key, item in value.items()}
    return value


_POLICY_INFORMATION_SCOPES = {
    NaiveLaunchOnDetectionPolicy.identity:
        NaiveLaunchOnDetectionPolicy.information_scope,
    FeasibleImmediateMatchingPolicy.identity:
        FeasibleImmediateMatchingPolicy.information_scope,
    OptimalFixedRankAssignmentPolicy.identity:
        OptimalFixedRankAssignmentPolicy.information_scope,
    'structured-behavior-cloning/1': 'online-observation-only',
}


def _v2_policy_record(engine: SimulationEngine, identity: str) -> Mapping[str, Any]:
    completed = bool(
        engine.terminated and not engine.truncated
        and engine.termination_reason == 'all_threats_resolved')
    return {
        'policyIdentity': identity,
        'informationScope': _POLICY_INFORMATION_SCOPES[identity],
        'ordinalCost': engine.raw_score,
        'completed': completed,
        'terminationReason': engine.termination_reason,
    }


def simulation_result_v2_to_dict(
        engine: SimulationEngine,
        *,
        scenario_entry: Mapping[str, Any],
        policy_identity: str,
        naive_engine: SimulationEngine,
        exact_engine: SimulationEngine,
        exact_plan: AssignmentPlan,
        policy_artifact_identity: Optional[str] = None,
        policy_deployment_status: Optional[str] = None,
        start_time: str = '2026-09-26T04:00:00Z') -> Mapping[str, Any]:
    """Export a checked frozen-scenario replay as ``simulation-result/2``.

    The active, naive, and exact engines must all be completed replays of the
    same immutable episode.  A constraint-terminated active or naive replay is
    a valid recorded outcome; provider failures and simulator truncations are
    not publication results.
    """
    engines = (engine, naive_engine, exact_engine)
    if any(not isinstance(item, SimulationEngine) for item in engines):
        raise ValueError('all replay inputs must be SimulationEngine instances')
    if policy_identity not in _POLICY_INFORMATION_SCOPES:
        raise ValueError('unsupported simulation-result/2 policy identity')
    is_imitation = policy_identity == 'structured-behavior-cloning/1'
    if is_imitation != (policy_artifact_identity is not None):
        raise ValueError(
            'structured imitation results require an artifact identity')
    if is_imitation and policy_deployment_status != 'experimental-unpromoted':
        raise ValueError(
            'structured imitation results must retain their deployment status')
    if any(item.spec.schema_version != 'simulation-episode/2'
           for item in engines):
        raise ValueError('simulation-result/2 requires simulation-episode/2')
    episode_hash = canonical_episode_hash(engine.spec)
    if any(canonical_episode_hash(item.spec) != episode_hash
           for item in engines[1:]):
        raise ValueError('comparison engines do not replay the active episode')
    if any(item.truncated or not item.terminated
           or item.aggregate_result is None for item in engines):
        raise ValueError('all result replays must terminate without truncation')
    if naive_engine.termination_reason not in (
            'all_threats_resolved',) and not str(
                naive_engine.termination_reason).startswith(
                    'constraint_violation:'):
        raise ValueError('naive replay ended for an unsupported reason')
    if (exact_engine.termination_reason != 'all_threats_resolved'
            or not exact_plan.exact
            or exact_plan.policy_identity
            != OptimalFixedRankAssignmentPolicy.identity
            or exact_engine.raw_score is None
            or not math.isclose(exact_plan.predicted_cost,
                                exact_engine.raw_score,
                                rel_tol=0.0, abs_tol=1e-12)):
        raise ValueError('exact reference replay does not prove its stated cost')
    if not 2 <= len(engine.spec.threats) <= 8:
        raise ValueError('simulation-result/2 requires two through eight threats')
    if engine.spec.candidate_count != 20:
        raise ValueError('simulation-result/2 requires 20 trajectory samples')
    required_entry = {
        'scenario_ref', 'split', 'seed', 'profile', 'generator_version',
        'distribution_version', 'distribution_checksum', 'provider_identity',
        'canonical_episode_hash', 'expected_feasible',
    }
    if not isinstance(scenario_entry, Mapping) \
            or not required_entry.issubset(scenario_entry):
        raise ValueError('scenario_entry is missing immutable provenance')
    metadata = engine.spec.metadata
    if (scenario_entry['seed'] != engine.spec.seed
            or scenario_entry['profile'] != metadata.get('profile')
            or scenario_entry['generator_version'] != metadata.get('generator')
            or scenario_entry['distribution_version']
            != metadata.get('distribution_identity')
            or scenario_entry['distribution_checksum']
            != metadata.get('distribution_checksum')
            or scenario_entry['canonical_episode_hash'] != episode_hash
            or scenario_entry['expected_feasible'] is not True):
        raise ValueError('scenario entry does not match the replayed episode')
    try:
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError('start_time must be timezone-aware ISO 8601') from exc
    if start.utcoffset() is None:
        raise ValueError('start_time must include a timezone')
    start = start.astimezone(timezone.utc)
    radius = float(metadata['scenario_contract'][
        'supplied_footprint_radius_m'])
    if radius != 100.0:
        raise ValueError('simulation-result/2 requires the supplied 100 m area')

    trajectories = []
    terminal_footprints = []
    assignments = []
    selected_footprints = []
    resolved_evaluations = {}
    resolution_events = [
        row for row in engine.event_records
        if row.kind in ('interception_outcome', 'threat_expiry')
        and row.entity_id in engine.threats
        and 'training_cost' in row.details]
    for event, evaluation in zip(resolution_events, engine.outcomes):
        resolved_evaluations[event.entity_id] = evaluation

    for scheduled in engine.spec.threats:
        state = scheduled.state
        samples = sample_threat_trajectory(state, engine.spec.candidate_count)
        trajectories.append({
            'threatId': state.threat_id,
            'detectionTimeS': scheduled.detection_time_s,
            'detectionTime': _iso(
                start + timedelta(seconds=scheduled.detection_time_s)),
            'samples': [{
                'sampleIndex': row.sample_index,
                'timeFromDetectionS': row.time_from_start_s,
                'timeFromEpisodeStartS': (
                    scheduled.detection_time_s + row.time_from_start_s),
                'time': _iso(start + timedelta(seconds=(
                    scheduled.detection_time_s + row.time_from_start_s))),
                'position': _position(
                    row.position_x_m, row.position_y_m, row.position_z_m),
                'verticalVelocityMps': row.velocity_z_mps,
            } for row in samples],
        })
        runtime = engine.threats[state.threat_id]
        terminal_candidate = next((
            row for interceptor_id in sorted(runtime.candidates)
            for row in runtime.candidates[interceptor_id]
            if row.opportunity.sample_index == engine.spec.candidate_count), None)
        terminal_assessment = (None if terminal_candidate is None else
                               runtime.candidate_assessments.get(
                                   terminal_candidate.opportunity.opportunity_id))
        terminal_footprints.append({
            'id': state.threat_id + ':terminal-counterfactual',
            'threatId': state.threat_id,
            'kind': 'terminal_counterfactual',
            'label': 'supplied 100 m area',
            'center': _position(
                float(scheduled.metadata['terminal_position_x_m']),
                float(scheduled.metadata['terminal_position_y_m']), 0.0),
            'radiusM': radius,
            'consequence': (None if terminal_assessment is None else
                            terminal_assessment.as_dict()),
        })
        assignment = engine.assignments.get(state.threat_id)
        if (assignment is not None and assignment.status.value == 'locked'
                and runtime.resolution is not None
                and runtime.resolution.value == 'intercepted'):
            opportunity = assignment.candidate.opportunity
            center = _position(opportunity.position_x_m,
                               opportunity.position_y_m,
                               opportunity.position_z_m)
            assignments.append({
                **assignment.as_dict(),
                'interceptionTime': _iso(start + timedelta(
                    seconds=assignment.candidate.interception_time_s)),
                'lockTime': _iso(start + timedelta(
                    seconds=assignment.candidate.lock_time_s)),
                'position': center,
            })
            selected_footprints.append({
                'id': opportunity.opportunity_id + ':supplied-area',
                'threatId': state.threat_id,
                'opportunityId': opportunity.opportunity_id,
                'kind': 'selected',
                'label': 'supplied 100 m area',
                'center': center,
                'radiusM': radius,
                'consequence': assignment.consequence_snapshot,
            })

    outcomes = []
    for scheduled in engine.spec.threats:
        threat_id = scheduled.state.threat_id
        runtime = engine.threats[threat_id]
        intercepted = (runtime.resolution is not None
                       and runtime.resolution.value == 'intercepted')
        assignment = engine.assignments.get(threat_id) if intercepted else None
        evaluation = resolved_evaluations.get(threat_id)
        outcomes.append({
            'threatId': threat_id,
            'outcome': 'intercepted' if intercepted else 'unhandled',
            'resolvedTimeS': runtime.resolved_time_s,
            'resolvedTime': (None if runtime.resolved_time_s is None else
                             _iso(start + timedelta(
                                 seconds=runtime.resolved_time_s))),
            'interceptorId': (None if assignment is None else
                              assignment.interceptor_id),
            'opportunityId': (None if assignment is None else
                              assignment.candidate.opportunity.opportunity_id),
            'trainingCost': (None if evaluation is None else
                             evaluation.training_cost),
        })

    event_rows = [{
        **event.as_dict(),
        'absoluteTime': _iso(start + timedelta(seconds=event.time_s)),
    } for event in engine.event_records]
    active = _v2_policy_record(engine, policy_identity)
    naive = _v2_policy_record(
        naive_engine, NaiveLaunchOnDetectionPolicy.identity)
    exact = {
        **_v2_policy_record(
            exact_engine, OptimalFixedRankAssignmentPolicy.identity),
        'predictedOrdinalCost': exact_plan.predicted_cost,
        'exact': exact_plan.exact,
        'proofScope': exact_plan.proof_scope,
        'predictedCostMatchesReplay': True,
    }
    active_minus_naive = (
        None if active['ordinalCost'] is None or naive['ordinalCost'] is None
        else active['ordinalCost'] - naive['ordinalCost'])
    exact_regret = (
        None if not active['completed'] or active['ordinalCost'] is None
        else active['ordinalCost'] - exact['ordinalCost'])
    aggregate = engine.aggregate_result
    violation = (None if not engine.constraint_violations else
                 engine.constraint_violations[-1].constraint_violation)
    result = {
        'schemaVersion': SIMULATION_RESULT_V2_SCHEMA_VERSION,
        'episodeSchemaVersion': engine.spec.schema_version,
        'episodeId': engine.spec.episode_id,
        'seed': engine.spec.seed,
        'start': _iso(start),
        'end': _iso(start + timedelta(seconds=max(
            row.expiry_time_s for row in engine.spec.threats))),
        'coordinateReferenceSystems': {
            'calculation': 'EPSG:3414', 'presentation': 'EPSG:4326',
            'verticalReference': metadata['scenario_contract'][
                'vertical_reference'],
        },
        'trajectories': trajectories,
        'events': event_rows,
        'outcomes': outcomes,
        'assignments': assignments,
        'selectedFootprints': selected_footprints,
        'terminalCounterfactualFootprints': terminal_footprints,
        'consequenceSummary': {
            'ordinalObjectiveCost': aggregate.training_cost,
            'physicalComponents': dict(aggregate.components),
            'evidence': dict(aggregate.evidence),
            'wording': {
                'area': 'supplied 100 m area',
                'population': 'people potentially exposed',
                'casualties': 'assumption-grade expected casualties',
            },
        },
        'policy': {
            'identity': policy_identity,
            'informationScope': _POLICY_INFORMATION_SCOPES[policy_identity],
            **({'artifactIdentity': policy_artifact_identity,
                'deploymentStatus': policy_deployment_status}
               if is_imitation else {}),
        },
        'policyComparison': {
            'active': active,
            'naive': naive,
            'exactReference': exact,
            'activeMinusNaiveCost': active_minus_naive,
            'exactRegret': exact_regret,
        },
        'termination': {
            'reason': engine.termination_reason,
            'completed': active['completed'],
            'constraintStatus': ('violated' if violation is not None
                                 else 'satisfied'),
            'constraintViolation': violation,
            'terminationTimeS': engine.current_time_s,
        },
        'provenance': {
            'scenarioRef': scenario_entry['scenario_ref'],
            'split': scenario_entry['split'],
            'profile': scenario_entry['profile'],
            'seed': scenario_entry['seed'],
            'generatorVersion': scenario_entry['generator_version'],
            'distributionVersion': scenario_entry['distribution_version'],
            'distributionChecksum': scenario_entry['distribution_checksum'],
            'providerIdentity': scenario_entry['provider_identity'],
            'providerRuntimeIdentity': metadata['provider_identity'],
            'providerVersion': metadata['provider_version'],
            'providerConfigChecksum': metadata['provider_config_checksum'],
            'providerDataChecksum': metadata['provider_data_checksum'],
            'scenarioConfigChecksum': metadata['scenario_config_checksum'],
            'generatorConfigurationChecksum': metadata[
                'generator_configuration_checksum'],
            'boundarySourceChecksum': metadata['boundary_source_checksum'],
            'mainIslandGeometryChecksum': metadata[
                'main_island_geometry_checksum'],
            'simulatorVersion': engine.snapshot()['simulator_version'],
            'canonicalEpisodeHash': episode_hash,
            'hashVerified': True,
            'policyIdentity': policy_identity,
            **({'policyArtifactIdentity': policy_artifact_identity,
                'policyDeploymentStatus': policy_deployment_status}
               if is_imitation else {}),
        },
        'limitations': [
            'The supplied 100 m area is a scenario input, not a validated blast radius.',
            'No physical debris model, validated casualty model, terrain, drag, wind, aircraft downtime, or recovery transition is simulated.',
            'Interceptor motion is evaluated in two dimensions; no interceptor altitude model is present.',
            'Expected-casualty constants are uncalibrated demonstration assumptions.',
            'Transport, healthcare, education, and richer residential-service consequence sectors are unavailable.',
            *(['The structured imitation checkpoint is experimental and unpromoted; validation included constraint violations.']
              if is_imitation else []),
        ],
    }
    result = _json_native(result)
    _validate_primitives(result)
    return result


def _validate_primitives(value: Any) -> None:
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float) and math.isfinite(value):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_primitives(item)
        return
    if isinstance(value, dict) and all(type(key) is str for key in value):
        for item in value.values():
            _validate_primitives(item)
        return
    raise ValueError('simulation result must contain only finite JSON primitives')
