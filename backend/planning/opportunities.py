"""Generate candidate opportunities without exposure or recommendation logic."""
from backend.domain import InterceptorState, ThreatState

from .reachability import evaluate_candidate_reachability
from .trajectory import DEFAULT_NUMBER_OF_SAMPLES, sample_threat_trajectory


def generate_candidate_opportunities(threat, interceptor,
                                     number_of_samples=DEFAULT_NUMBER_OF_SAMPLES):
    """Sample the threat and retain reachable and unreachable opportunities."""
    if not isinstance(threat, ThreatState):
        raise ValueError('threat must be a ThreatState')
    if not isinstance(interceptor, InterceptorState):
        raise ValueError('interceptor must be an InterceptorState')
    samples = sample_threat_trajectory(threat, number_of_samples)
    return tuple(evaluate_candidate_reachability(threat.threat_id, interceptor, sample)
                 for sample in samples)
