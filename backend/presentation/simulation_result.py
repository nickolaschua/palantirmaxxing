"""Export a completed version-2 simulation as ``simulation-result/1``."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping, Optional

from pyproj import Transformer

from backend.planning import sample_threat_trajectory
from backend.simulation import (ImmediateInterceptionPolicy, SimulationEngine,
                                canonical_episode_hash)


SIMULATION_RESULT_SCHEMA_VERSION = 'simulation-result/1'
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
        policy_identity: str = ImmediateInterceptionPolicy.identity,
        baseline_raw_score: Optional[float] = None,
        exact_oracle: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
    if not isinstance(engine, SimulationEngine):
        raise ValueError('engine must be a SimulationEngine')
    if engine.spec.schema_version != 'simulation-episode/2':
        raise ValueError('simulation-result/1 requires simulation-episode/2')
    if not engine.terminated or engine.truncated or engine.aggregate_result is None:
        raise ValueError('simulation must terminate successfully before export')
    try:
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError('start_time must be timezone-aware ISO 8601') from exc
    if start.utcoffset() is None:
        raise ValueError('start_time must include a timezone')
    start = start.astimezone(timezone.utc)
    radius = float(engine.spec.metadata['scenario_contract'][
        'supplied_footprint_radius_m'])

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
        'baselineIdentity': ImmediateInterceptionPolicy.identity,
        'baselineOrdinalCost': baseline,
        'measuredRelativeImprovement': improvement,
        'claim': ('optimal with exact bounded-oracle evidence'
                  if exact_oracle and exact_oracle.get('exact') is True
                  and exact_oracle.get('raw_score') == engine.raw_score
                  else 'measured comparison with the immediate-interception baseline'),
        'exactOracleEvidence': exact_oracle,
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
            'provider': engine.provider_audit(),
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
