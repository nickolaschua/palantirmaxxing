"""Bounded exhaustive oracle for small deterministic episodes."""
from copy import deepcopy
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from backend.simulation import (AssignmentStatus, ObjectiveDirection,
                                SimulationEngine, ThreatStatus)


@dataclass(frozen=True)
class OracleResult:
    raw_score: Optional[float]
    actions: Tuple[Tuple[object, ...], ...]
    enumerated_action_sequences: int
    exact: bool


def _actions(engine: SimulationEngine) -> Sequence[Tuple[object, ...]]:
    actions: List[Tuple[object, ...]] = []
    for threat_id in sorted(engine.threats):
        runtime = engine.threats[threat_id]
        if runtime.status != ThreatStatus.ACTIVE:
            continue
        for interceptor_id in sorted(engine.interceptor_resources):
            rows = runtime.candidates.get(interceptor_id, ())
            for index in range(len(rows)):
                if engine.is_assignment_valid(threat_id, interceptor_id, index):
                    actions.append(('assign', threat_id, interceptor_id, index))
        if engine.can_cancel(threat_id):
            actions.append(('cancel', threat_id))
    if engine.can_advance():
        actions.append(('advance',))
    return tuple(actions)


def _apply(engine: SimulationEngine, action: Tuple[object, ...]) -> None:
    if action[0] == 'assign':
        engine.assign(action[1], action[2], action[3])
    elif action[0] == 'cancel':
        engine.cancel(action[1])
    elif action[0] == 'advance':
        engine.advance()
    else:
        raise ValueError('unknown oracle action')


def bounded_oracle(engine: SimulationEngine,
                   max_action_sequences: int = 100_000) -> OracleResult:
    """Enumerate terminal action sequences up to the declared hard cap."""
    if type(max_action_sequences) is not int or max_action_sequences <= 0:
        raise ValueError('max_action_sequences must be a positive integer')
    if len(engine.spec.threats) > 3 or len(engine.spec.interceptors) > 3:
        raise ValueError('oracle episodes are capped at three threats and interceptors')
    if engine.spec.candidate_count > 5:
        raise ValueError('oracle episodes are capped at five candidates per pair')
    direction = engine.objective_direction
    best_score: Optional[float] = None
    best_actions: Tuple[Tuple[object, ...], ...] = ()
    terminal_count = 0
    stack = [(deepcopy(engine), ())]
    exhausted = True
    saw_truncation = False
    while stack:
        state, history = stack.pop()
        if state.truncated:
            saw_truncation = True
            continue
        if state.terminated:
            terminal_count += 1
            score = state.raw_score
            if score is not None and (best_score is None
                    or (direction == ObjectiveDirection.MINIMIZE and score < best_score)
                    or (direction == ObjectiveDirection.MAXIMIZE and score > best_score)):
                best_score = float(score)
                best_actions = history
            if terminal_count >= max_action_sequences and stack:
                exhausted = False
                break
            continue
        children = _actions(state)
        for action in reversed(children):
            child = deepcopy(state)
            _apply(child, action)
            stack.append((child, history + (action,)))
    return OracleResult(
        raw_score=best_score,
        actions=best_actions,
        enumerated_action_sequences=terminal_count,
        exact=exhausted and not saw_truncation,
    )
