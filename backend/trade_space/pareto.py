"""Deterministic two-objective Pareto filtering for eligible candidates."""
import math

from backend.domain import CandidateParetoEvidence, EvaluatedCandidate, ParetoAnalysis

SUCCESS_ABSOLUTE_TOLERANCE = 1e-12
EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE = 1e-9
EXPOSURE_RELATIVE_TOLERANCE = 1e-12


def _finite_number(value, field):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(field + ' must be a finite number; booleans are forbidden')


def compare_success(first, second):
    """Return -1, 0 or 1; zero means numerically equivalent success."""
    _finite_number(first, 'first success probability')
    _finite_number(second, 'second success probability')
    difference = first - second
    if difference > SUCCESS_ABSOLUTE_TOLERANCE:
        return 1
    if difference < -SUCCESS_ABSOLUTE_TOLERANCE:
        return -1
    return 0


def _exposure_tolerance(first, second):
    return max(EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE,
               EXPOSURE_RELATIVE_TOLERANCE * max(abs(first), abs(second)))


def compare_exposure(first, second):
    """Return -1, 0 or 1; lower exposure is preferable."""
    _finite_number(first, 'first population exposure')
    _finite_number(second, 'second population exposure')
    if first < 0 or second < 0:
        raise ValueError('population exposure must be nonnegative')
    difference = first - second
    tolerance = _exposure_tolerance(first, second)
    if difference > tolerance:
        return 1
    if difference < -tolerance:
        return -1
    return 0


def _canonical_key(candidate):
    opportunity = candidate.opportunity
    return (opportunity.time_from_start_s, opportunity.sample_index,
            opportunity.opportunity_id)


def _dominates(first, second):
    success_comparison = compare_success(
        first.supplied_success_probability, second.supplied_success_probability)
    exposure_comparison = compare_exposure(
        first.exposure.people_potentially_exposed,
        second.exposure.people_potentially_exposed)
    return (success_comparison >= 0 and exposure_comparison <= 0
            and (success_comparison > 0 or exposure_comparison < 0))


def _equivalent(first, second):
    return (compare_success(first.supplied_success_probability,
                            second.supplied_success_probability) == 0
            and compare_exposure(first.exposure.people_potentially_exposed,
                                 second.exposure.people_potentially_exposed) == 0)


def analyze_pareto(candidates):
    """Return frontier, all dominators, and pairwise tolerance equivalence.

    Partial-coverage candidates are ignored. Equivalence evidence is pairwise
    because tolerance-based equivalence need not be mathematically transitive.
    """
    if not isinstance(candidates, (tuple, list)):
        raise ValueError('candidates must be a tuple or list')
    for candidate in candidates:
        if not isinstance(candidate, EvaluatedCandidate):
            raise ValueError('candidates must contain EvaluatedCandidate records')
    eligible = sorted((candidate for candidate in candidates if candidate.eligible),
                      key=_canonical_key)
    identifiers = [candidate.opportunity.opportunity_id for candidate in eligible]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('eligible candidate opportunity IDs must be unique')

    evidence = []
    for candidate in eligible:
        dominators = tuple(other.opportunity.opportunity_id for other in eligible
                           if other is not candidate and _dominates(other, candidate))
        equivalents = tuple(other.opportunity.opportunity_id for other in eligible
                            if other is not candidate and _equivalent(other, candidate))
        evidence.append(CandidateParetoEvidence(
            candidate_id=candidate.opportunity.opportunity_id,
            pareto_efficient=not dominators,
            dominated_by_candidate_ids=dominators,
            equivalent_candidate_ids=equivalents,
        ))
    return ParetoAnalysis(
        pareto_candidate_ids=tuple(row.candidate_id for row in evidence
                                   if row.pareto_efficient),
        candidate_evidence=tuple(evidence),
    )
