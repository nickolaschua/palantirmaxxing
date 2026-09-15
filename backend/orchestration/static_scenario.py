"""End-to-end orchestration for the synthetic static machine-side MVP."""
from copy import deepcopy
from dataclasses import asdict, replace
from time import perf_counter_ns

from backend.domain import (EvaluatedCandidate, InterceptorState,
                            PopulationExposureEvidence,
                            ScenarioEvaluationDiagnostics, SyntheticSuccessProfile,
                            ThreatState, TradeSpaceResult, ZoneExposureEvidence)
from backend.exposure import PreparedPopulation
from backend.planning import DEFAULT_NUMBER_OF_SAMPLES, generate_candidate_opportunities
from backend.scenario import (build_supplied_circular_footprint,
                              evaluate_synthetic_success,
                              validate_supplied_footprint_radius)
from backend.trade_space import analyze_pareto, extract_representative_categories

from .footprint_assessment import assess_footprints

RESULT_VERSION = 'static-scenario-evaluation/1'
_CATEGORY_ORDER = ('earliest_viable', 'highest_success', 'lowest_exposure')


def _milliseconds(started_ns, finished_ns):
    return (finished_ns - started_ns) / 1_000_000


def _scenario_id(threat, interceptor):
    return threat.threat_id + '__' + interceptor.interceptor_id + '__static-scenario'


def _assessment_request(prepared_population, scenario_id, enriched):
    return {
        'schema_version': 'footprint-assessment-request/1',
        'assessment_id': scenario_id + '__footprint-assessment',
        'mode': 'alternatives',
        'population_dataset_id': prepared_population.dataset_id,
        'population_dataset_version': prepared_population.version,
        'coordinate_reference_system': 'EPSG:3414',
        'records': [
            {
                'record_id': opportunity.opportunity_id,
                'footprint': asdict(footprint),
            }
            for opportunity, supplied_success_probability, footprint in enriched
        ],
        'comparisons': [],
    }


def _exposure_evidence(exposure):
    return PopulationExposureEvidence(
        event_id=exposure['event_id'],
        footprint_id=exposure['footprint_id'],
        center_x_m=exposure['center_x_m'],
        center_y_m=exposure['center_y_m'],
        radius_m=exposure['radius_m'],
        exposure_status=exposure['status'],
        footprint_area_m2=exposure['footprint_area_m2'],
        uncovered_area_m2=exposure['uncovered_area_m2'],
        covered_area_fraction=exposure['covered_area_fraction'],
        people_potentially_exposed=exposure['people_potentially_exposed'],
        known_area_exposure=exposure['known_area_exposure'],
        zone_breakdown=tuple(ZoneExposureEvidence(**row)
                             for row in exposure['zone_breakdown']),
    )


def _evaluate_exposure(prepared_population, scenario_id, supplied_success):
    enriched = tuple(
        (opportunity, probability,
         build_supplied_circular_footprint(opportunity, radius))
        for opportunity, probability, radius in supplied_success
    )
    assessment = assess_footprints(
        prepared_population,
        _assessment_request(prepared_population, scenario_id, enriched),
    )
    if assessment['status'] == 'invalid_input':
        raise ValueError('footprint assessment rejected orchestrated input: %r'
                         % assessment['errors'])
    by_id = {row['record_id']: row['exposure'] for row in assessment['records']}
    expected_ids = {opportunity.opportunity_id for opportunity, _, _ in enriched}
    if set(by_id) != expected_ids:
        raise ValueError('footprint assessment returned an inconsistent candidate set')
    candidates = []
    for opportunity, probability, footprint in enriched:
        exposure = _exposure_evidence(by_id[opportunity.opportunity_id])
        reasons = (() if exposure.exposure_status == 'complete'
                   else ('partial_population_coverage',))
        candidates.append(EvaluatedCandidate(
            opportunity=opportunity,
            supplied_success_probability=probability,
            footprint=footprint,
            exposure=exposure,
            ineligibility_reasons=reasons,
        ))
    return tuple(candidates), deepcopy(assessment['provenance'])


def evaluate_static_scenario(threat, interceptor, synthetic_success_profile,
                             footprint_radius_m, prepared_population,
                             number_of_samples=DEFAULT_NUMBER_OF_SAMPLES):
    """Evaluate one static synthetic threat/interceptor scenario end to end.

    Measured durations are diagnostic only. All other returned evidence is
    deterministic for equal inputs and an equal software environment.
    """
    total_started = perf_counter_ns()
    if not isinstance(threat, ThreatState):
        raise ValueError('threat must be a ThreatState')
    if not isinstance(interceptor, InterceptorState):
        raise ValueError('interceptor must be an InterceptorState')
    if not isinstance(synthetic_success_profile, SyntheticSuccessProfile):
        raise ValueError('synthetic_success_profile must be a SyntheticSuccessProfile')
    if not isinstance(prepared_population, PreparedPopulation):
        raise ValueError('prepared_population must be PreparedPopulation')
    validate_supplied_footprint_radius(footprint_radius_m)
    scenario_id = _scenario_id(threat, interceptor)

    stage_started = perf_counter_ns()
    opportunities = generate_candidate_opportunities(
        threat, interceptor, number_of_samples=number_of_samples)
    trajectory_finished = perf_counter_ns()

    reachable = tuple(opportunity for opportunity in opportunities
                      if opportunity.reachable)
    supplied_success = tuple(
        (opportunity,
         evaluate_synthetic_success(synthetic_success_profile,
                                    opportunity.time_from_start_s),
         footprint_radius_m)
        for opportunity in reachable
    )
    success_finished = perf_counter_ns()

    candidates, provenance = _evaluate_exposure(
        prepared_population, scenario_id, supplied_success)
    exposure_finished = perf_counter_ns()

    pareto = analyze_pareto(candidates)
    pareto_finished = perf_counter_ns()

    assignments, representatives = extract_representative_categories(
        candidates, pareto.pareto_candidate_ids)
    representatives_finished = perf_counter_ns()

    diagnostics = ScenarioEvaluationDiagnostics(
        trajectory_reachability_ms=_milliseconds(stage_started, trajectory_finished),
        success_enrichment_ms=_milliseconds(trajectory_finished, success_finished),
        footprint_exposure_assessment_ms=_milliseconds(success_finished, exposure_finished),
        pareto_filtering_ms=_milliseconds(exposure_finished, pareto_finished),
        representative_extraction_ms=_milliseconds(pareto_finished,
                                                   representatives_finished),
        total_ms=0,
    )
    complete = sum(candidate.exposure.exposure_status == 'complete'
                   for candidate in candidates)
    eligible = sum(candidate.eligible for candidate in candidates)
    result = TradeSpaceResult(
        scenario_id=scenario_id,
        total_candidates=len(opportunities),
        reachable_candidates=len(reachable),
        complete_coverage_candidates=complete,
        eligible_candidates=eligible,
        candidate_opportunities=tuple(opportunities),
        candidates=candidates,
        pareto_candidate_ids=pareto.pareto_candidate_ids,
        pareto_evidence=pareto.candidate_evidence,
        category_assignments=assignments,
        representative_candidate_ids=representatives,
        population_exposure_provenance=provenance,
        diagnostics=diagnostics,
    )
    total_finished = perf_counter_ns()
    return replace(result, diagnostics=replace(
        diagnostics, total_ms=_milliseconds(total_started, total_finished)))


def _candidate_record(candidate, pareto_evidence, assignments):
    opportunity = candidate.opportunity
    record = asdict(opportunity)
    record.update({
        'supplied_success_probability': candidate.supplied_success_probability,
        'footprint_id': candidate.footprint.footprint_id,
        'footprint_radius_m': candidate.footprint.radius_m,
        'exposure_status': candidate.exposure.exposure_status,
        'people_potentially_exposed': candidate.exposure.people_potentially_exposed,
        'known_area_exposure': candidate.exposure.known_area_exposure,
        'covered_area_fraction': candidate.exposure.covered_area_fraction,
        'footprint_area_m2': candidate.exposure.footprint_area_m2,
        'uncovered_area_m2': candidate.exposure.uncovered_area_m2,
        'zone_breakdown': [asdict(row) for row in candidate.exposure.zone_breakdown],
        'eligible': candidate.eligible,
        'ineligibility_reasons': list(candidate.ineligibility_reasons),
    })
    evidence = pareto_evidence.get(opportunity.opportunity_id)
    record['pareto_efficient'] = evidence.pareto_efficient if evidence else False
    record['dominated_by_candidate_ids'] = (
        list(evidence.dominated_by_candidate_ids) if evidence else [])
    record['equivalent_candidate_ids'] = (
        list(evidence.equivalent_candidate_ids) if evidence else [])
    record['categories'] = [category for category in _CATEGORY_ORDER
                            if getattr(assignments, category)
                            == opportunity.opportunity_id]
    return record


def trade_space_result_to_dict(result, include_diagnostics=True):
    """Return the stable structured contract view of a TradeSpaceResult."""
    if not isinstance(result, TradeSpaceResult):
        raise ValueError('result must be a TradeSpaceResult')
    evidence = {row.candidate_id: row for row in result.pareto_evidence}
    payload = {
        'schema_version': RESULT_VERSION,
        'scenario_id': result.scenario_id,
        'total_candidates': result.total_candidates,
        'reachable_candidates': result.reachable_candidates,
        'complete_coverage_candidates': result.complete_coverage_candidates,
        'eligible_candidates': result.eligible_candidates,
        'pareto_candidate_ids': list(result.pareto_candidate_ids),
        'category_assignments': asdict(result.category_assignments),
        'representative_candidate_ids': list(result.representative_candidate_ids),
        'candidate_opportunities': [asdict(row)
                                    for row in result.candidate_opportunities],
        'candidates': [_candidate_record(row, evidence, result.category_assignments)
                       for row in result.candidates],
        'population_exposure_provenance': deepcopy(
            result.population_exposure_provenance),
    }
    if include_diagnostics:
        payload['diagnostics'] = asdict(result.diagnostics)
    return payload
