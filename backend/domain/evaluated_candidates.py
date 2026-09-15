"""Immutable evidence records for the synthetic static-scenario MVP."""
from dataclasses import dataclass
import math
from typing import Mapping, Optional, Tuple

from .candidates import CandidateOpportunity


def _identifier(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be a nonempty string')


def _finite_number(value, field):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(field + ' must be a finite number; booleans are forbidden')


def _probability(value, field):
    _finite_number(value, field)
    if value < 0 or value > 1:
        raise ValueError(field + ' must be between zero and one')


@dataclass(frozen=True)
class SyntheticSuccessProfile:
    """Externally assumed time-success profile for synthetic scenarios only."""
    initial_success_probability: float = 0.97
    decrease_per_second: float = 0.004
    minimum_success_probability: float = 0.70
    maximum_success_probability: float = 1.00

    def __post_init__(self):
        for field in ('initial_success_probability', 'minimum_success_probability',
                      'maximum_success_probability'):
            _probability(getattr(self, field), field)
        _finite_number(self.decrease_per_second, 'decrease_per_second')
        if self.decrease_per_second < 0:
            raise ValueError('decrease_per_second must be nonnegative')
        if self.minimum_success_probability > self.maximum_success_probability:
            raise ValueError('minimum_success_probability must not exceed maximum_success_probability')
        if not (self.minimum_success_probability <= self.initial_success_probability
                <= self.maximum_success_probability):
            raise ValueError('initial_success_probability must be within the configured bounds')


@dataclass(frozen=True)
class SuppliedCircularFootprint:
    """A caller-supplied circular scenario footprint, not a physical prediction."""
    footprint_id: str
    center_x_m: float
    center_y_m: float
    radius_m: float

    def __post_init__(self):
        _identifier(self.footprint_id, 'footprint_id')
        for field in ('center_x_m', 'center_y_m', 'radius_m'):
            _finite_number(getattr(self, field), field)
        if self.radius_m < 0:
            raise ValueError('radius_m must be nonnegative')


@dataclass(frozen=True)
class ZoneExposureEvidence:
    """One PEC zone contribution, retained without presentation rounding."""
    zone_id: str
    zone_population: float
    zone_density_people_per_m2: float
    overlap_area_m2: float
    estimated_people_exposed: float

    def __post_init__(self):
        _identifier(self.zone_id, 'zone_id')
        for field in ('zone_population', 'zone_density_people_per_m2',
                      'overlap_area_m2', 'estimated_people_exposed'):
            _finite_number(getattr(self, field), field)
            if getattr(self, field) < 0:
                raise ValueError(field + ' must be nonnegative')


@dataclass(frozen=True)
class PopulationExposureEvidence:
    """Immutable downstream view of one authoritative PEC event result."""
    event_id: str
    footprint_id: str
    center_x_m: float
    center_y_m: float
    radius_m: float
    exposure_status: str
    footprint_area_m2: float
    uncovered_area_m2: float
    covered_area_fraction: Optional[float]
    people_potentially_exposed: Optional[float]
    known_area_exposure: float
    zone_breakdown: Tuple[ZoneExposureEvidence, ...]

    def __post_init__(self):
        _identifier(self.event_id, 'event_id')
        _identifier(self.footprint_id, 'footprint_id')
        for field in ('center_x_m', 'center_y_m', 'radius_m', 'footprint_area_m2',
                      'uncovered_area_m2', 'known_area_exposure'):
            _finite_number(getattr(self, field), field)
        for field in ('radius_m', 'footprint_area_m2', 'uncovered_area_m2',
                      'known_area_exposure'):
            if getattr(self, field) < 0:
                raise ValueError(field + ' must be nonnegative')
        if self.exposure_status not in ('complete', 'partial_coverage'):
            raise ValueError('exposure_status must be complete or partial_coverage')
        if self.covered_area_fraction is not None:
            _finite_number(self.covered_area_fraction, 'covered_area_fraction')
            if self.covered_area_fraction < 0 or self.covered_area_fraction > 1:
                raise ValueError('covered_area_fraction must be between zero and one')
        if self.people_potentially_exposed is not None:
            _finite_number(self.people_potentially_exposed, 'people_potentially_exposed')
            if self.people_potentially_exposed < 0:
                raise ValueError('people_potentially_exposed must be nonnegative')
        if self.exposure_status == 'complete' and self.people_potentially_exposed is None:
            raise ValueError('complete exposure requires people_potentially_exposed')
        if self.exposure_status == 'partial_coverage' and self.people_potentially_exposed is not None:
            raise ValueError('partial coverage must not claim complete people exposure')
        if not isinstance(self.zone_breakdown, tuple):
            raise ValueError('zone_breakdown must be a tuple')
        if not all(isinstance(row, ZoneExposureEvidence) for row in self.zone_breakdown):
            raise ValueError('zone_breakdown must contain ZoneExposureEvidence records')


@dataclass(frozen=True)
class EvaluatedCandidate:
    """A reachable opportunity joined to supplied assumptions and PEC evidence."""
    opportunity: CandidateOpportunity
    supplied_success_probability: float
    footprint: SuppliedCircularFootprint
    exposure: PopulationExposureEvidence
    ineligibility_reasons: Tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.opportunity, CandidateOpportunity):
            raise ValueError('opportunity must be a CandidateOpportunity')
        if not self.opportunity.reachable:
            raise ValueError('only reachable opportunities may be evaluated')
        _probability(self.supplied_success_probability, 'supplied_success_probability')
        if not isinstance(self.footprint, SuppliedCircularFootprint):
            raise ValueError('footprint must be a SuppliedCircularFootprint')
        if not isinstance(self.exposure, PopulationExposureEvidence):
            raise ValueError('exposure must be PopulationExposureEvidence')
        if (self.footprint.center_x_m != self.opportunity.position_x_m
                or self.footprint.center_y_m != self.opportunity.position_y_m):
            raise ValueError('footprint center must equal the candidate position')
        if (self.exposure.event_id != self.opportunity.opportunity_id
                or self.exposure.footprint_id != self.footprint.footprint_id
                or self.exposure.center_x_m != self.footprint.center_x_m
                or self.exposure.center_y_m != self.footprint.center_y_m
                or self.exposure.radius_m != self.footprint.radius_m):
            raise ValueError('PEC exposure identity and geometry must match the supplied footprint')
        if not isinstance(self.ineligibility_reasons, tuple):
            raise ValueError('ineligibility_reasons must be a tuple')
        expected = () if self.exposure.exposure_status == 'complete' else ('partial_population_coverage',)
        if self.ineligibility_reasons != expected:
            raise ValueError('ineligibility reasons must reflect population coverage status')

    @property
    def eligible(self):
        return not self.ineligibility_reasons


@dataclass(frozen=True)
class CandidateParetoEvidence:
    """Deterministic dominance and tolerance-equivalence evidence."""
    candidate_id: str
    pareto_efficient: bool
    dominated_by_candidate_ids: Tuple[str, ...]
    equivalent_candidate_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ParetoAnalysis:
    pareto_candidate_ids: Tuple[str, ...]
    candidate_evidence: Tuple[CandidateParetoEvidence, ...]


@dataclass(frozen=True)
class CategoryAssignments:
    earliest_viable: Optional[str]
    highest_success: Optional[str]
    lowest_exposure: Optional[str]


@dataclass(frozen=True)
class ScenarioEvaluationDiagnostics:
    """Measured wall-clock diagnostics; excluded from deterministic evidence."""
    trajectory_reachability_ms: float
    success_enrichment_ms: float
    footprint_exposure_assessment_ms: float
    pareto_filtering_ms: float
    representative_extraction_ms: float
    total_ms: float

    def __post_init__(self):
        for field in ('trajectory_reachability_ms', 'success_enrichment_ms',
                      'footprint_exposure_assessment_ms', 'pareto_filtering_ms',
                      'representative_extraction_ms', 'total_ms'):
            _finite_number(getattr(self, field), field)
            if getattr(self, field) < 0:
                raise ValueError(field + ' must be nonnegative')


@dataclass(frozen=True)
class TradeSpaceResult:
    """Structured machine-side result; it does not choose a final action."""
    scenario_id: str
    total_candidates: int
    reachable_candidates: int
    complete_coverage_candidates: int
    eligible_candidates: int
    candidate_opportunities: Tuple[CandidateOpportunity, ...]
    candidates: Tuple[EvaluatedCandidate, ...]
    pareto_candidate_ids: Tuple[str, ...]
    pareto_evidence: Tuple[CandidateParetoEvidence, ...]
    category_assignments: CategoryAssignments
    representative_candidate_ids: Tuple[str, ...]
    population_exposure_provenance: Mapping[str, object]
    diagnostics: ScenarioEvaluationDiagnostics
