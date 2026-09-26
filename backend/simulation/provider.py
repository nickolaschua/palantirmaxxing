"""Replaceable consequence-provider contract and deterministic toy provider."""
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, Tuple

from .models import AbsoluteCandidate, ScheduledThreat


class ObjectiveDirection(str, Enum):
    MINIMIZE = 'minimize'
    MAXIMIZE = 'maximize'


@dataclass(frozen=True)
class ProviderEvaluation:
    """One consequence result or aggregate result from a provider."""

    raw_score: Optional[float]
    components: Mapping[str, float] = field(default_factory=dict)
    operational_state_update: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    runtime_ms: float = 0.0
    failure_status: Optional[str] = None
    training_cost: Optional[float] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    constraint_violation: Optional[str] = None

    def __post_init__(self) -> None:
        if self.raw_score is not None and (
                type(self.raw_score) not in (int, float) or not math.isfinite(self.raw_score)):
            raise ValueError('provider raw_score must be finite when present')
        if self.failure_status is None and self.raw_score is None:
            raise ValueError('a successful provider result must include raw_score')
        if self.training_cost is not None and (
                type(self.training_cost) not in (int, float)
                or not math.isfinite(self.training_cost)):
            raise ValueError('provider training_cost must be finite when present')
        if self.failure_status is not None and (
                not isinstance(self.failure_status, str) or not self.failure_status.strip()):
            raise ValueError('failure_status must be a nonempty string when present')
        if self.constraint_violation is not None and (
                not isinstance(self.constraint_violation, str)
                or not self.constraint_violation.strip()):
            raise ValueError('constraint_violation must be a nonempty string when present')
        if self.failure_status is not None and self.constraint_violation is not None:
            raise ValueError('provider failure and constraint violation are distinct states')
        if self.constraint_violation is not None and self.training_cost is None:
            raise ValueError('constraint violations require a finite training_cost')
        for name, value in self.components.items():
            if not isinstance(name, str) or type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('provider components must have string keys and finite values')
        if type(self.runtime_ms) not in (int, float) or not math.isfinite(self.runtime_ms) or self.runtime_ms < 0:
            raise ValueError('provider runtime_ms must be a finite nonnegative number')
        object.__setattr__(self, 'components', dict(self.components))
        object.__setattr__(self, 'operational_state_update', dict(self.operational_state_update))
        object.__setattr__(self, 'provenance', dict(self.provenance))
        object.__setattr__(self, 'evidence', dict(self.evidence))


class ConsequenceProvider(Protocol):
    """Boundary that Emmanuel's aggregate scorer can implement unchanged."""

    @property
    def identity(self) -> str:
        ...

    @property
    def version(self) -> str:
        ...

    @property
    def objective_direction(self) -> ObjectiveDirection:
        ...

    def decision_features(self, state: Any,
                          visible_threat_ids: Sequence[str]) -> Sequence[float]:
        ...

    def evaluate_assigned(self, threat: ScheduledThreat,
                          candidate: AbsoluteCandidate,
                          operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        ...

    def evaluate_unhandled(self, threat: ScheduledThreat,
                           operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        ...

    def aggregate(self, outcomes: Iterable[ProviderEvaluation],
                  operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        ...


def provider_identity(provider: ConsequenceProvider) -> Mapping[str, str]:
    direction = provider.objective_direction
    if not isinstance(direction, ObjectiveDirection):
        try:
            direction = ObjectiveDirection(direction)
        except (TypeError, ValueError) as exc:
            raise ValueError('provider objective_direction must be minimize or maximize') from exc
    if not isinstance(provider.identity, str) or not provider.identity.strip():
        raise ValueError('provider identity must be a nonempty string')
    if not isinstance(provider.version, str) or not provider.version.strip():
        raise ValueError('provider version must be a nonempty string')
    return {
        'identity': provider.identity,
        'version': provider.version,
        'objective_direction': direction.value,
    }


class DeterministicToyProvider:
    """A plumbing-only scorer; it is not project outcome evidence."""

    identity = 'deterministic-toy-provider'
    version = 'toy-plumbing-validation/1'
    objective_direction = ObjectiveDirection.MINIMIZE
    fixed_candidate_costs = True
    additive_training_costs = True
    operational_updates_affect_costs = False

    @staticmethod
    def _priority(threat: ScheduledThreat) -> float:
        value = threat.metadata.get('priority', 1.0)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('toy threat priority must be finite and positive')
        return float(value)

    @staticmethod
    def _preferred_fraction(threat: ScheduledThreat) -> float:
        value = threat.metadata.get('preferred_candidate_fraction', 0.5)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('toy preferred_candidate_fraction must be within [0, 1]')
        return float(value)

    def decision_features(self, state: Any,
                          visible_threat_ids: Sequence[str]) -> Sequence[float]:
        features = []
        for threat_id in visible_threat_ids:
            threat = state.threats[threat_id].scheduled
            features.extend((self._priority(threat), self._preferred_fraction(threat)))
        return tuple(features)

    def evaluate_assigned(self, threat: ScheduledThreat,
                          candidate: AbsoluteCandidate,
                          operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        count = max(1, int(operational_state.get('candidate_count', 1)))
        denominator = max(1, count - 1)
        fraction = (candidate.opportunity.sample_index - 1) / denominator
        distance = abs(fraction - self._preferred_fraction(threat))
        score = self._priority(threat) * distance
        return ProviderEvaluation(
            raw_score=score,
            training_cost=score,
            components={'preference_distance_cost': score},
            operational_state_update={
                'handled_count': int(operational_state.get('handled_count', 0)) + 1,
            },
            provenance={
                'provider': self.identity,
                'version': self.version,
                'label': 'plumbing validation only',
            },
        )

    def evaluate_unhandled(self, threat: ScheduledThreat,
                           operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        score = self._priority(threat) * 1.25
        return ProviderEvaluation(
            raw_score=score,
            training_cost=score,
            components={'unhandled_cost': score},
            operational_state_update={
                'unhandled_count': int(operational_state.get('unhandled_count', 0)) + 1,
            },
            provenance={
                'provider': self.identity,
                'version': self.version,
                'label': 'plumbing validation only',
            },
        )

    def aggregate(self, outcomes: Iterable[ProviderEvaluation],
                  operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        rows: Tuple[ProviderEvaluation, ...] = tuple(outcomes)
        score = sum(float(item.raw_score) for item in rows if item.raw_score is not None)
        return ProviderEvaluation(
            raw_score=score,
            training_cost=score,
            components={
                'toy_total_cost': score,
                'resolved_outcomes': float(len(rows)),
            },
            provenance={
                'provider': self.identity,
                'version': self.version,
                'label': 'plumbing validation only',
            },
        )
