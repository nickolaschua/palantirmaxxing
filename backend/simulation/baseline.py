"""Deterministic immediate-interception baseline."""
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

from .engine import SimulationEngine
from .models import Assignment, ThreatStatus


@dataclass(frozen=True)
class BaselineRun:
    actions: Tuple[Tuple[str, ...], ...]
    raw_score: Optional[float]
    terminated: bool
    truncated: bool
    termination_reason: Optional[str]


class ImmediateInterceptionPolicy:
    """Assigns each newly seen threat once to its earliest feasible option."""

    identity = 'immediate-interception/1'

    @staticmethod
    def _ordered_active_threats(engine: SimulationEngine) -> Sequence[str]:
        active = [runtime.scheduled for runtime in engine.threats.values()
                  if runtime.status == ThreatStatus.ACTIVE]
        active.sort(key=lambda row: (
            row.detection_time_s, row.expiry_time_s, row.state.threat_id))
        return tuple(item.state.threat_id for item in active)

    @staticmethod
    def _best_assignment(engine: SimulationEngine,
                         threat_id: str) -> Optional[Tuple[str, int]]:
        runtime = engine.threats[threat_id]
        options = []
        for interceptor_id in sorted(runtime.candidates):
            for index, candidate in enumerate(runtime.candidates[interceptor_id]):
                if engine.is_assignment_valid(threat_id, interceptor_id, index):
                    margin = candidate.opportunity.time_margin_s
                    options.append((
                        candidate.interception_time_s,
                        -float(margin),
                        interceptor_id,
                        candidate.opportunity.opportunity_id,
                        index,
                    ))
        if not options:
            return None
        best = min(options)
        return best[2], best[4]

    def run(self, engine: SimulationEngine) -> BaselineRun:
        considered: Set[str] = set()
        actions: List[Tuple[str, ...]] = []
        while not engine.terminated and not engine.truncated:
            for threat_id in self._ordered_active_threats(engine):
                if threat_id in considered:
                    continue
                considered.add(threat_id)
                choice = self._best_assignment(engine, threat_id)
                if choice is None:
                    actions.append(('leave-unhandled', threat_id))
                    continue
                interceptor_id, candidate_index = choice
                assignment: Assignment = engine.assign(
                    threat_id, interceptor_id, candidate_index)
                actions.append((
                    'assign', threat_id, interceptor_id,
                    assignment.candidate.opportunity.opportunity_id,
                ))
            if engine.can_advance():
                engine.advance()
                actions.append(('advance',))
            elif not engine.terminated and not engine.truncated:
                engine.truncate('malformed_state:no_event_to_advance')
        return BaselineRun(
            actions=tuple(actions),
            raw_score=engine.raw_score,
            terminated=engine.terminated,
            truncated=engine.truncated,
            termination_reason=engine.termination_reason,
        )
