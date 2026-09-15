"""Shared application-domain records."""
from .candidates import CandidateOpportunity, InterceptorState, ThreatState, TrajectorySample
from .evaluated_candidates import (CandidateParetoEvidence, CategoryAssignments,
                                   EvaluatedCandidate, ParetoAnalysis,
                                   PopulationExposureEvidence,
                                   ScenarioEvaluationDiagnostics,
                                   SuppliedCircularFootprint,
                                   SyntheticSuccessProfile, TradeSpaceResult,
                                   ZoneExposureEvidence)

__all__ = [
    'ThreatState', 'InterceptorState', 'TrajectorySample', 'CandidateOpportunity',
    'SyntheticSuccessProfile', 'SuppliedCircularFootprint', 'ZoneExposureEvidence',
    'PopulationExposureEvidence', 'EvaluatedCandidate', 'CandidateParetoEvidence',
    'ParetoAnalysis', 'CategoryAssignments', 'ScenarioEvaluationDiagnostics',
    'TradeSpaceResult',
]
