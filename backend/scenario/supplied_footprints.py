"""Fixed-radius supplied footprints for the synthetic MVP scenario."""
import math

from backend.domain import CandidateOpportunity
from backend.domain.evaluated_candidates import SuppliedCircularFootprint


def validate_supplied_footprint_radius(footprint_radius_m):
    """Validate and return the nonnegative finite scenario radius."""
    try:
        valid_radius = (type(footprint_radius_m) in (int, float)
                        and math.isfinite(footprint_radius_m))
    except OverflowError:
        valid_radius = False
    if not valid_radius:
        raise ValueError('footprint_radius_m must be a finite number; booleans are forbidden')
    if footprint_radius_m < 0:
        raise ValueError('footprint_radius_m must be nonnegative')
    return footprint_radius_m


def build_supplied_circular_footprint(opportunity, footprint_radius_m):
    """Create a deterministic supplied circle centered exactly on a candidate."""
    if not isinstance(opportunity, CandidateOpportunity):
        raise ValueError('opportunity must be a CandidateOpportunity')
    validate_supplied_footprint_radius(footprint_radius_m)
    return SuppliedCircularFootprint(
        footprint_id=opportunity.opportunity_id + '__footprint',
        center_x_m=opportunity.position_x_m,
        center_y_m=opportunity.position_y_m,
        radius_m=footprint_radius_m,
    )
