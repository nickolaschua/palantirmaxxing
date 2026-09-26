"""Offline full-episode assignment plans for deterministic comparison policies."""
from dataclasses import dataclass
import math
from typing import Any, Dict, Mapping, Sequence, Tuple

from backend.planning import generate_candidate_opportunities

from .models import AbsoluteCandidate, EpisodeSpec


@dataclass(frozen=True)
class AssignmentDecision:
    threat_id: str
    interceptor_id: str
    opportunity_id: str
    candidate_index: int
    interception_time_s: float
    time_margin_s: float
    training_cost: float


@dataclass(frozen=True)
class AssignmentPlan:
    policy_identity: str
    decisions: Tuple[AssignmentDecision, ...]
    predicted_cost: float
    exact: bool
    proof_scope: str


def _value(assessment: Any, name: str, default: Any = None) -> Any:
    if isinstance(assessment, Mapping):
        return assessment.get(name, default)
    return getattr(assessment, name, default)


def candidate_universes(
        spec: EpisodeSpec, provider: Any
        ) -> Mapping[str, Mapping[str, Tuple[Tuple[AbsoluteCandidate, bool, float], ...]]]:
    """Recreate each threat's complete immutable candidate/cost universe."""
    result: Dict[str, Dict[str, Tuple[Tuple[AbsoluteCandidate, bool, float], ...]]] = {}
    for scheduled in spec.threats:
        by_interceptor: Dict[str, Tuple[AbsoluteCandidate, ...]] = {}
        all_candidates = []
        for resource in sorted(spec.interceptors, key=lambda row: row.state.interceptor_id):
            candidates = tuple(
                AbsoluteCandidate.from_opportunity(item, scheduled.detection_time_s)
                for item in generate_candidate_opportunities(
                    scheduled.state, resource.state, spec.candidate_count))
            by_interceptor[resource.state.interceptor_id] = candidates
            all_candidates.extend(candidates)

        assessor = getattr(provider, 'assess_candidates', None)
        assessments: Mapping[str, Any] = {}
        if callable(assessor):
            assessments = assessor(scheduled, tuple(all_candidates), {
                'candidate_count': spec.candidate_count})
            if not isinstance(assessments, Mapping):
                raise ValueError('provider candidate assessments must be a mapping')

        rows: Dict[str, Tuple[Tuple[AbsoluteCandidate, bool, float], ...]] = {}
        for interceptor_id, candidates in by_interceptor.items():
            evaluated = []
            for candidate in candidates:
                opportunity = candidate.opportunity
                if callable(assessor):
                    assessment = assessments.get(opportunity.opportunity_id)
                    if assessment is None:
                        raise ValueError('provider omitted a full-universe assessment')
                    eligible = bool(_value(assessment, 'eligible', False))
                    training_cost = _value(assessment, 'training_cost')
                else:
                    eligible = opportunity.reachable
                    provider_result = provider.evaluate_assigned(
                        scheduled, candidate, {'candidate_count': spec.candidate_count})
                    if provider_result.failure_status is not None:
                        raise ValueError('provider failed while planning: '
                                         + provider_result.failure_status)
                    training_cost = provider_result.training_cost
                if training_cost is None or type(training_cost) not in (int, float) \
                        or not math.isfinite(training_cost):
                    raise ValueError('assignment planning requires finite training_cost')
                evaluated.append((candidate, eligible and opportunity.reachable,
                                  float(training_cost)))
            rows[interceptor_id] = tuple(evaluated)
        result[scheduled.state.threat_id] = rows
    return result


def _solve_assignment(
        threat_order: Sequence[str], interceptor_order: Sequence[str],
        pair_choices: Mapping[Tuple[str, str], AssignmentDecision],
        objective: str) -> Tuple[AssignmentDecision, ...]:
    """Bitmask DP for a complete one-to-one assignment with stable ties."""
    states: Dict[int, Tuple[float, Tuple[Tuple[str, str], ...],
                            Tuple[AssignmentDecision, ...]]] = {0: (0.0, (), ())}
    slot = {interceptor_id: index for index, interceptor_id in enumerate(interceptor_order)}
    for threat_id in threat_order:
        next_states: Dict[int, Tuple[float, Tuple[Tuple[str, str], ...],
                                    Tuple[AssignmentDecision, ...]]] = {}
        for mask, (total, signature, decisions) in states.items():
            for interceptor_id in interceptor_order:
                bit = 1 << slot[interceptor_id]
                decision = pair_choices.get((threat_id, interceptor_id))
                if mask & bit or decision is None:
                    continue
                increment = (decision.interception_time_s if objective == 'time'
                             else decision.training_cost)
                candidate = (
                    total + increment,
                    signature + ((decision.interceptor_id, decision.opportunity_id),),
                    decisions + (decision,),
                )
                previous = next_states.get(mask | bit)
                if previous is None or candidate[:2] < previous[:2]:
                    next_states[mask | bit] = candidate
        states = next_states
        if not states:
            raise ValueError('no complete consequence-eligible one-to-one assignment exists')
    return min(states.values(), key=lambda row: row[:2])[2]


def _decision(candidate: AbsoluteCandidate, candidate_index: int,
              training_cost: float) -> AssignmentDecision:
    opportunity = candidate.opportunity
    return AssignmentDecision(
        threat_id=opportunity.threat_id,
        interceptor_id=opportunity.interceptor_id,
        opportunity_id=opportunity.opportunity_id,
        candidate_index=candidate_index,
        interception_time_s=candidate.interception_time_s,
        time_margin_s=float(opportunity.time_margin_s),
        training_cost=training_cost,
    )


def feasible_immediate_plan(spec: EpisodeSpec, provider: Any) -> AssignmentPlan:
    """Full-episode comparator minimizing summed earliest interception times."""
    universes = candidate_universes(spec, provider)
    threat_order = tuple(row.state.threat_id for row in sorted(
        spec.threats, key=lambda row: (
            row.detection_time_s, row.expiry_time_s, row.state.threat_id)))
    interceptor_order = tuple(sorted(
        row.state.interceptor_id for row in spec.interceptors))
    choices: Dict[Tuple[str, str], AssignmentDecision] = {}
    for threat_id in threat_order:
        for interceptor_id in interceptor_order:
            options = []
            for index, (candidate, eligible, cost) in enumerate(
                    universes[threat_id][interceptor_id]):
                if eligible:
                    options.append((
                        candidate.interception_time_s,
                        -float(candidate.opportunity.time_margin_s),
                        candidate.opportunity.opportunity_id,
                        index, candidate, cost))
            if options:
                best = min(options)
                choices[(threat_id, interceptor_id)] = _decision(
                    best[4], best[3], best[5])
    decisions = _solve_assignment(
        threat_order, interceptor_order, choices, objective='time')
    return AssignmentPlan(
        policy_identity='feasible-immediate-matching/1',
        decisions=decisions,
        predicted_cost=math.fsum(row.training_cost for row in decisions),
        exact=False,
        proof_scope=(
            'offline full-episode comparator: earliest eligible candidate per pair; '
            'complete matching minimizes summed interception time'),
    )


def optimal_fixed_rank_plan(spec: EpisodeSpec, provider: Any) -> AssignmentPlan:
    """Minimize additive immutable ordinal cost by eight-resource bitmask DP."""
    universes = candidate_universes(spec, provider)
    threat_order = tuple(sorted(row.state.threat_id for row in spec.threats))
    interceptor_order = tuple(sorted(
        row.state.interceptor_id for row in spec.interceptors))
    choices: Dict[Tuple[str, str], AssignmentDecision] = {}
    for threat_id in threat_order:
        for interceptor_id in interceptor_order:
            options = []
            for index, (candidate, eligible, cost) in enumerate(
                    universes[threat_id][interceptor_id]):
                if eligible:
                    options.append((
                        cost, candidate.interception_time_s,
                        -float(candidate.opportunity.time_margin_s),
                        candidate.opportunity.opportunity_id,
                        index, candidate))
            if options:
                best = min(options)
                choices[(threat_id, interceptor_id)] = _decision(
                    best[5], best[4], best[0])
    decisions = _solve_assignment(
        threat_order, interceptor_order, choices, objective='cost')
    exact = all((
        getattr(provider, 'fixed_candidate_costs', False),
        getattr(provider, 'additive_training_costs', False),
        not getattr(provider, 'operational_updates_affect_costs', True),
    ))
    scope = (
        'exact for immutable additive fixed-rank costs with one-use interceptors, '
        'complete threat coverage, and no cost-changing operational updates'
        if exact else
        'inexact: provider does not certify immutable additive costs without '
        'cost-changing operational updates')
    return AssignmentPlan(
        policy_identity='optimal-fixed-rank-assignment/1',
        decisions=decisions,
        predicted_cost=math.fsum(row.training_cost for row in decisions),
        exact=exact,
        proof_scope=scope,
    )
