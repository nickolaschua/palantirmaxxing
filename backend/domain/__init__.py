"""Shared application-domain records."""
from .candidates import CandidateOpportunity, InterceptorState, ThreatState, TrajectorySample
from .evaluated_candidates import (CandidateParetoEvidence, CategoryAssignments,
                                   EvaluatedCandidate, ParetoAnalysis,
                                   PopulationExposureEvidence,
                                   ScenarioEvaluationDiagnostics,
                                   SuppliedCircularFootprint,
                                   SyntheticSuccessProfile, TradeSpaceResult,
                                   ZoneExposureEvidence)
from .imperfect_conditions import (
    CONDITION_ACTION_FEATURE_ORDER, CONDITION_FEATURE_SCHEMA_VERSION,
    CONDITION_STATE_FEATURE_ORDER, IMPERFECT_CONDITION_SCHEMA_VERSION,
    CandidateCondition, ConditionedDemonstration, ExpertConditionLabel,
    ImperfectConditionObservation, condition_feature_schema,
    condition_feature_schema_checksum, explanation_lines)
from .imperfect_condition_matrix import (
    BUILDING_CONDITION, CONDITION_EFFECTS, CONDITION_ORDER,
    IMPERFECT_CONDITION_MATRIX_VERSION, SEVERE_COMBINATIONS,
    build_imperfect_condition_matrix, validate_imperfect_condition_matrix)

__all__ = [
    'ThreatState', 'InterceptorState', 'TrajectorySample', 'CandidateOpportunity',
    'SyntheticSuccessProfile', 'SuppliedCircularFootprint', 'ZoneExposureEvidence',
    'PopulationExposureEvidence', 'EvaluatedCandidate', 'CandidateParetoEvidence',
    'ParetoAnalysis', 'CategoryAssignments', 'ScenarioEvaluationDiagnostics',
    'TradeSpaceResult',
    'IMPERFECT_CONDITION_SCHEMA_VERSION', 'CONDITION_FEATURE_SCHEMA_VERSION',
    'CONDITION_STATE_FEATURE_ORDER', 'CONDITION_ACTION_FEATURE_ORDER',
    'ImperfectConditionObservation', 'CandidateCondition',
    'ExpertConditionLabel', 'ConditionedDemonstration',
    'condition_feature_schema', 'condition_feature_schema_checksum',
    'explanation_lines',
    'IMPERFECT_CONDITION_MATRIX_VERSION', 'BUILDING_CONDITION',
    'CONDITION_ORDER', 'CONDITION_EFFECTS', 'SEVERE_COMBINATIONS',
    'build_imperfect_condition_matrix', 'validate_imperfect_condition_matrix',
]
