"""Feasible offline comparator and exact fixed-rank assignment policy."""
from dataclasses import dataclass
import math
from typing import Callable, List, Optional, Tuple

from .assignment_planning import (AssignmentPlan, feasible_immediate_plan,
                                  optimal_fixed_rank_plan)
from .engine import SimulationEngine
from .models import AssignmentStatus, ResolutionKind


@dataclass(frozen=True)
class BaselineRun:
    actions: Tuple[Tuple[str, ...], ...]
    raw_score: Optional[float]
    terminated: bool
    truncated: bool
    termination_reason: Optional[str]
    plan: AssignmentPlan


def replay_assignment_plan(engine: SimulationEngine,
                           plan: AssignmentPlan) -> BaselineRun:
    """Replay a complete offline plan through the authoritative event engine."""
    if len(plan.decisions) != len(engine.spec.threats):
        raise ValueError('assignment plan must cover every generated threat')
    if len({row.interceptor_id for row in plan.decisions}) != len(plan.decisions):
        raise ValueError('assignment plan must use every interceptor at most once')
    decision_by_threat = {row.threat_id: row for row in plan.decisions}
    if len(decision_by_threat) != len(plan.decisions):
        raise ValueError('assignment plan contains duplicate threats')

    actions: List[Tuple[str, ...]] = []
    while not engine.terminated and not engine.truncated:
        for threat_id in sorted(engine.visible_threat_ids()):
            if threat_id in engine.assignments:
                continue
            decision = decision_by_threat.get(threat_id)
            if decision is None:
                raise ValueError('assignment plan omitted active threat ' + threat_id)
            rows = engine.threats[threat_id].candidates.get(decision.interceptor_id, ())
            index = next((index for index, candidate in enumerate(rows)
                          if candidate.opportunity.opportunity_id
                          == decision.opportunity_id), None)
            if index is None:
                raise ValueError('planned opportunity is absent from replay engine')
            assignment = engine.assign(threat_id, decision.interceptor_id, index)
            actions.append(('assign', threat_id, decision.interceptor_id,
                            assignment.candidate.opportunity.opportunity_id))
        if engine.can_advance():
            engine.advance()
            actions.append(('advance',))
        elif not engine.terminated and not engine.truncated:
            engine.truncate('malformed_state:no_event_to_advance')

    run = BaselineRun(
        actions=tuple(actions), raw_score=engine.raw_score,
        terminated=engine.terminated, truncated=engine.truncated,
        termination_reason=engine.termination_reason, plan=plan)
    if run.truncated or not run.terminated:
        raise RuntimeError('%s rollout did not terminate normally: %s'
                           % (plan.policy_identity, run.termination_reason))
    if run.termination_reason != 'all_threats_resolved':
        raise RuntimeError('%s produced a constraint violation' % plan.policy_identity)
    if (len(engine.assignments) != len(engine.spec.threats)
            or len(engine.consumed_interceptors) != len(engine.spec.threats)
            or any(row.status != AssignmentStatus.LOCKED
                   for row in engine.assignments.values())
            or any(row.resolution != ResolutionKind.INTERCEPTED
                   for row in engine.threats.values())):
        raise RuntimeError('%s did not lock and intercept every threat with distinct resources'
                           % plan.policy_identity)
    if run.raw_score is None or not math.isclose(
            run.raw_score, plan.predicted_cost, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError('%s predicted cost does not match replayed aggregate cost'
                           % plan.policy_identity)
    return run


class _AssignmentPolicy:
    identity = ''
    planner: Callable[..., AssignmentPlan]

    def plan(self, engine: SimulationEngine) -> AssignmentPlan:
        plan = self.planner(engine.spec, engine.provider)
        if plan.policy_identity != self.identity:
            raise ValueError('planner identity does not match policy identity')
        return plan

    def run(self, engine: SimulationEngine) -> BaselineRun:
        # Planning completes before replay mutates assignment/resource state.
        return replay_assignment_plan(engine, self.plan(engine))


class FeasibleImmediateMatchingPolicy(_AssignmentPolicy):
    """Offline full-episode feasible comparator with stable matching ties."""

    identity = 'feasible-immediate-matching/1'
    planner = staticmethod(feasible_immediate_plan)


class OptimalFixedRankAssignmentPolicy(_AssignmentPolicy):
    """Exact Singapore assignment optimizer within the declared fixed-rank scope."""

    identity = 'optimal-fixed-rank-assignment/1'
    planner = staticmethod(optimal_fixed_rank_plan)


# Compatibility import for callers compiled against the previous class name.
# Its behavior and public identity are the new feasible comparator.
ImmediateInterceptionPolicy = FeasibleImmediateMatchingPolicy
