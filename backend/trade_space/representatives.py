"""Extract descriptive categories from a Pareto-efficient candidate set."""
from backend.domain import CategoryAssignments, EvaluatedCandidate

from .pareto import compare_exposure, compare_success

CATEGORY_ORDER = ('earliest_viable', 'highest_success', 'lowest_exposure')


def _canonical_key(candidate):
    opportunity = candidate.opportunity
    return (opportunity.time_from_start_s, opportunity.sample_index,
            opportunity.opportunity_id)


def extract_representative_categories(candidates, pareto_candidate_ids):
    """Return stable category assignments and unique IDs in category order."""
    if not isinstance(candidates, (tuple, list)):
        raise ValueError('candidates must be a tuple or list')
    if not isinstance(pareto_candidate_ids, (tuple, list)):
        raise ValueError('pareto_candidate_ids must be a tuple or list')
    by_id = {}
    for candidate in candidates:
        if not isinstance(candidate, EvaluatedCandidate):
            raise ValueError('candidates must contain EvaluatedCandidate records')
        candidate_id = candidate.opportunity.opportunity_id
        if candidate_id in by_id:
            raise ValueError('candidate opportunity IDs must be unique')
        by_id[candidate_id] = candidate
    if len(pareto_candidate_ids) != len(set(pareto_candidate_ids)):
        raise ValueError('pareto_candidate_ids must be unique')
    missing = [candidate_id for candidate_id in pareto_candidate_ids
               if candidate_id not in by_id]
    if missing:
        raise ValueError('Pareto IDs must reference supplied candidates')
    frontier = sorted((by_id[candidate_id] for candidate_id in pareto_candidate_ids),
                      key=_canonical_key)
    if not frontier:
        return CategoryAssignments(None, None, None), ()

    earliest = frontier[0]
    highest = frontier[0]
    lowest = frontier[0]
    for candidate in frontier[1:]:
        if compare_success(candidate.supplied_success_probability,
                           highest.supplied_success_probability) > 0:
            highest = candidate
        if compare_exposure(candidate.exposure.people_potentially_exposed,
                            lowest.exposure.people_potentially_exposed) < 0:
            lowest = candidate
    assignments = CategoryAssignments(
        earliest_viable=earliest.opportunity.opportunity_id,
        highest_success=highest.opportunity.opportunity_id,
        lowest_exposure=lowest.opportunity.opportunity_id,
    )
    unique = []
    for category in CATEGORY_ORDER:
        candidate_id = getattr(assignments, category)
        if candidate_id not in unique:
            unique.append(candidate_id)
    return assignments, tuple(unique)

