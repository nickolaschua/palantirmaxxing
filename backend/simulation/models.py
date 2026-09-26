"""Versioned records for the deterministic multi-event simulation."""
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, Mapping, Optional, Tuple

from backend.domain import CandidateOpportunity, InterceptorState, ThreatState


SIMULATOR_VERSION = 'centralized-event-simulator/2'
EPISODE_SCHEMA_VERSIONS = ('simulation-episode/1', 'simulation-episode/2')
MAX_THREATS = 8
MAX_INTERCEPTORS = 8
MAX_CANDIDATES_PER_PAIR = 20


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field_name + ' must be a nonempty string')


def _finite(value: float, field_name: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(field_name + ' must be a finite number; booleans are forbidden')


class ThreatStatus(str, Enum):
    SCHEDULED = 'scheduled'
    ACTIVE = 'active'
    RESOLVED = 'resolved'


class AssignmentStatus(str, Enum):
    TENTATIVE = 'tentative'
    LOCKED = 'locked'


class ResolutionKind(str, Enum):
    INTERCEPTED = 'intercepted'
    UNHANDLED = 'unhandled'


class EventKind(str, Enum):
    DETECTION = 'detection'
    ASSIGNMENT_LOCK = 'assignment_lock'
    INTERCEPTION_OUTCOME = 'interception_outcome'
    THREAT_EXPIRY = 'threat_expiry'
    EPISODE_END = 'episode_end'


EVENT_PRIORITY = {
    EventKind.DETECTION: 0,
    EventKind.ASSIGNMENT_LOCK: 1,
    EventKind.INTERCEPTION_OUTCOME: 2,
    EventKind.THREAT_EXPIRY: 3,
    EventKind.EPISODE_END: 4,
}


@dataclass(frozen=True)
class ScheduledThreat:
    """A threat that becomes observable only at ``detection_time_s``."""

    detection_time_s: float
    state: ThreatState
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _finite(self.detection_time_s, 'detection_time_s')
        if self.detection_time_s < 0:
            raise ValueError('detection_time_s must be nonnegative')
        if not isinstance(self.state, ThreatState):
            raise ValueError('state must be a ThreatState')
        object.__setattr__(self, 'metadata', dict(self.metadata))

    @property
    def expiry_time_s(self) -> float:
        return self.detection_time_s + self.state.maximum_time_to_go_s


@dataclass(frozen=True)
class InterceptorResource:
    """A one-use interceptor available at the beginning of an episode."""

    state: InterceptorState
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.state, InterceptorState):
            raise ValueError('state must be an InterceptorState')
        object.__setattr__(self, 'metadata', dict(self.metadata))


@dataclass(frozen=True)
class EpisodeSpec:
    """Complete seeded input to one simulator episode."""

    episode_id: str
    seed: int
    threats: Tuple[ScheduledThreat, ...]
    interceptors: Tuple[InterceptorResource, ...]
    candidate_count: int = MAX_CANDIDATES_PER_PAIR
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = 'simulation-episode/1'

    def __post_init__(self) -> None:
        _identifier(self.episode_id, 'episode_id')
        if type(self.seed) is not int:
            raise ValueError('seed must be an integer')
        if self.schema_version not in EPISODE_SCHEMA_VERSIONS:
            raise ValueError('unsupported simulation episode schema')
        object.__setattr__(self, 'threats', tuple(self.threats))
        object.__setattr__(self, 'interceptors', tuple(self.interceptors))
        if len(self.threats) > MAX_THREATS:
            raise ValueError('an episode supports at most %d threats' % MAX_THREATS)
        if len(self.interceptors) > MAX_INTERCEPTORS:
            raise ValueError('an episode supports at most %d interceptors' % MAX_INTERCEPTORS)
        if type(self.candidate_count) is not int or not 1 <= self.candidate_count <= MAX_CANDIDATES_PER_PAIR:
            raise ValueError('candidate_count must be between 1 and %d' % MAX_CANDIDATES_PER_PAIR)
        threat_ids = [item.state.threat_id for item in self.threats]
        interceptor_ids = [item.state.interceptor_id for item in self.interceptors]
        if len(set(threat_ids)) != len(threat_ids):
            raise ValueError('threat IDs must be unique within an episode')
        if len(set(interceptor_ids)) != len(interceptor_ids):
            raise ValueError('interceptor IDs must be unique within an episode')
        object.__setattr__(self, 'metadata', dict(self.metadata))


@dataclass(frozen=True)
class AbsoluteCandidate:
    """Existing reachability evidence placed on the episode time line."""

    opportunity: CandidateOpportunity
    detection_time_s: float
    interception_time_s: float
    lock_time_s: float

    @classmethod
    def from_opportunity(cls, opportunity: CandidateOpportunity,
                         detection_time_s: float) -> 'AbsoluteCandidate':
        if opportunity.required_travel_time_s is None:
            lock_time = detection_time_s + opportunity.time_from_start_s
        else:
            lock_time = (detection_time_s + opportunity.time_from_start_s
                         - opportunity.required_travel_time_s)
        return cls(
            opportunity=opportunity,
            detection_time_s=detection_time_s,
            interception_time_s=detection_time_s + opportunity.time_from_start_s,
            lock_time_s=lock_time,
        )


@dataclass
class Assignment:
    threat_id: str
    interceptor_id: str
    candidate: AbsoluteCandidate
    revision: int
    status: AssignmentStatus = AssignmentStatus.TENTATIVE
    consequence_snapshot: Optional[Mapping[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        result = {
            'threat_id': self.threat_id,
            'interceptor_id': self.interceptor_id,
            'opportunity_id': self.candidate.opportunity.opportunity_id,
            'candidate_index': self.candidate.opportunity.sample_index,
            'interception_time_s': self.candidate.interception_time_s,
            'lock_time_s': self.candidate.lock_time_s,
            'revision': self.revision,
            'status': self.status.value,
        }
        if self.candidate.opportunity.position_z_m != 0 or self.consequence_snapshot is not None:
            result['position_z_m'] = self.candidate.opportunity.position_z_m
        if self.consequence_snapshot is not None:
            result['consequence_snapshot'] = dict(self.consequence_snapshot)
        return result


@dataclass
class ThreatRuntime:
    scheduled: ScheduledThreat
    status: ThreatStatus = ThreatStatus.SCHEDULED
    candidates: Dict[str, Tuple[AbsoluteCandidate, ...]] = field(default_factory=dict)
    candidate_assessments: Dict[str, Mapping[str, Any]] = field(default_factory=dict)
    resolution: Optional[ResolutionKind] = None
    resolved_time_s: Optional[float] = None


@dataclass(frozen=True)
class QueueEvent:
    time_s: float
    kind: EventKind
    entity_id: str
    revision: int = 0


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    time_s: float
    kind: str
    entity_id: str
    status: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'details', dict(self.details))

    def as_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'time_s': self.time_s,
            'kind': self.kind,
            'entity_id': self.entity_id,
            'status': self.status,
            'details': dict(self.details),
        }
