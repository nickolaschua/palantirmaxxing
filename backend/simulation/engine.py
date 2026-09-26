"""Deterministic continuous-event simulation for centralized assignments."""
import heapq
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from backend.planning import generate_candidate_opportunities

from .models import (EVENT_PRIORITY, AbsoluteCandidate, Assignment, AssignmentStatus,
                     EpisodeSpec, EventKind, EventRecord, QueueEvent, ResolutionKind,
                     SIMULATOR_VERSION, ThreatRuntime, ThreatStatus)
from .provider import (ConsequenceProvider, ObjectiveDirection, ProviderEvaluation,
                       provider_identity)


_TIME_TOLERANCE_S = 1e-9


class SimulationEngine:
    """Owns episode state and processes one deterministic event epoch at a time."""

    def __init__(self, spec: EpisodeSpec, provider: ConsequenceProvider,
                 event_limit: int = 10000):
        if not isinstance(spec, EpisodeSpec):
            raise ValueError('spec must be an EpisodeSpec')
        if type(event_limit) is not int or event_limit <= 0:
            raise ValueError('event_limit must be a positive integer')
        self.spec = spec
        self.provider = provider
        self.provider_provenance = dict(provider_identity(provider))
        self._objective_direction = ObjectiveDirection(
            self.provider_provenance['objective_direction'])
        self.event_limit = event_limit
        self._validate_scenario_provider_contract()
        self.current_time_s = 0.0
        self.threats: Dict[str, ThreatRuntime] = {
            item.state.threat_id: ThreatRuntime(item) for item in spec.threats
        }
        self.interceptor_resources = {
            item.state.interceptor_id: item for item in spec.interceptors
        }
        self.assignments: Dict[str, Assignment] = {}
        self.consumed_interceptors: Set[str] = set()
        self.modified_threats: Set[str] = set()
        self.operational_state: Dict[str, Any] = {'candidate_count': spec.candidate_count}
        self.outcomes: List[ProviderEvaluation] = []
        self.provider_failures: List[ProviderEvaluation] = []
        self.constraint_violations: List[ProviderEvaluation] = []
        self.aggregate_result: Optional[ProviderEvaluation] = None
        self.event_records: List[EventRecord] = []
        self.terminated = False
        self.truncated = False
        self.termination_reason: Optional[str] = None
        self._queue: List[Tuple[float, int, str, int, int, QueueEvent]] = []
        self._queue_sequence = 0
        self._assignment_revision = 0
        self._processed_event_count = 0
        self._assessment_contexts: Dict[str, Tuple[Any, ...]] = {}

        for threat in spec.threats:
            self._push_event(QueueEvent(
                threat.detection_time_s, EventKind.DETECTION, threat.state.threat_id))
        episode_end = max((item.expiry_time_s for item in spec.threats), default=0.0)
        self._push_event(QueueEvent(episode_end, EventKind.EPISODE_END, spec.episode_id))

        # A reset begins at t=0 with all simultaneous initial detections visible.
        if self._next_live_event_time() == 0.0:
            self.advance()
        if not spec.threats:
            self._finish_if_resolved()

    @property
    def objective_direction(self) -> ObjectiveDirection:
        return self._objective_direction

    @property
    def raw_score(self) -> Optional[float]:
        return None if self.aggregate_result is None else self.aggregate_result.raw_score

    @property
    def processed_event_count(self) -> int:
        return self._processed_event_count

    def _validate_scenario_provider_contract(self) -> None:
        if self.spec.schema_version != 'simulation-episode/2':
            return
        contract = self.spec.metadata.get('scenario_contract')
        if not isinstance(contract, Mapping):
            raise ValueError('Singapore episode requires a scenario_contract')
        radius = contract.get('supplied_footprint_radius_m')
        if radius != 100.0:
            raise ValueError('Singapore scenario radius must be exactly 100 m')
        if getattr(self.provider, 'footprint_radius_m', None) != radius:
            raise ValueError('Singapore provider radius must equal the scenario radius')
        condition = contract.get('consequence_condition')
        if getattr(self.provider, 'condition_id', None) != condition:
            raise ValueError('Singapore provider consequence condition disagrees with the scenario')
        if (getattr(getattr(self.provider, 'scenario_config', None), 'checksum', None)
                != self.spec.metadata.get('scenario_config_checksum')):
            raise ValueError('Singapore provider configuration disagrees with the scenario')
        provider_island = getattr(getattr(self.provider, 'catalog', None),
                                  'main_island', None)
        expected_checksum = self.spec.metadata.get('main_island_geometry_checksum')
        if (provider_island is None
                or provider_island.geometry_checksum != expected_checksum):
            raise ValueError('Singapore provider and scenario geometry checksums disagree')
        expected_objective = self.spec.metadata.get('objective_reference')
        if (expected_objective != 'full-candidate-universe/1'
                or getattr(self.provider, 'objective_reference_version', None)
                != expected_objective):
            raise ValueError('Singapore provider objective reference disagrees with the episode')

    def _push_event(self, event: QueueEvent) -> None:
        if not math.isfinite(event.time_s) or event.time_s < -_TIME_TOLERANCE_S:
            raise ValueError('event time must be finite and nonnegative')
        self._queue_sequence += 1
        heapq.heappush(self._queue, (
            max(0.0, event.time_s), EVENT_PRIORITY[event.kind], event.entity_id,
            event.revision, self._queue_sequence, event))

    def _event_is_live(self, event: QueueEvent) -> bool:
        if event.kind == EventKind.EPISODE_END:
            return not (self.terminated or self.truncated)
        runtime = self.threats.get(event.entity_id)
        if runtime is None:
            return False
        if event.kind == EventKind.DETECTION:
            return runtime.status == ThreatStatus.SCHEDULED
        if event.kind == EventKind.THREAT_EXPIRY:
            return runtime.status == ThreatStatus.ACTIVE
        assignment = self.assignments.get(event.entity_id)
        if assignment is None or assignment.revision != event.revision:
            return False
        if event.kind == EventKind.ASSIGNMENT_LOCK:
            return assignment.status == AssignmentStatus.TENTATIVE
        if event.kind == EventKind.INTERCEPTION_OUTCOME:
            return assignment.status == AssignmentStatus.LOCKED
        return False

    def _discard_stale_head(self) -> None:
        while self._queue and not self._event_is_live(self._queue[0][-1]):
            heapq.heappop(self._queue)

    def _next_live_event_time(self) -> Optional[float]:
        self._discard_stale_head()
        return None if not self._queue else self._queue[0][0]

    def can_advance(self) -> bool:
        return (not self.terminated and not self.truncated
                and self._next_live_event_time() is not None)

    def visible_threat_ids(self) -> Tuple[str, ...]:
        return tuple(
            threat_id for threat_id, runtime in self.threats.items()
            if runtime.status == ThreatStatus.ACTIVE
        )

    def assignment_for_interceptor(self, interceptor_id: str) -> Optional[Assignment]:
        for assignment in self.assignments.values():
            if assignment.interceptor_id == interceptor_id:
                return assignment
        return None

    def candidate(self, threat_id: str, interceptor_id: str,
                  candidate_index: int) -> AbsoluteCandidate:
        runtime = self.threats.get(threat_id)
        if runtime is None or runtime.status != ThreatStatus.ACTIVE:
            raise ValueError('threat is not active')
        candidates = runtime.candidates.get(interceptor_id)
        if candidates is None or not 0 <= candidate_index < len(candidates):
            raise ValueError('candidate index is out of range')
        return candidates[candidate_index]

    def is_assignment_valid(self, threat_id: str, interceptor_id: str,
                            candidate_index: int) -> bool:
        if self.terminated or self.truncated or threat_id in self.modified_threats:
            return False
        runtime = self.threats.get(threat_id)
        if runtime is None or runtime.status != ThreatStatus.ACTIVE:
            return False
        current = self.assignments.get(threat_id)
        if current is not None and current.status == AssignmentStatus.LOCKED:
            return False
        if interceptor_id in self.consumed_interceptors:
            return False
        reservation = self.assignment_for_interceptor(interceptor_id)
        if reservation is not None and reservation.threat_id != threat_id:
            return False
        try:
            candidate = self.candidate(threat_id, interceptor_id, candidate_index)
        except ValueError:
            return False
        if not candidate.opportunity.reachable:
            return False
        assessment = runtime.candidate_assessments.get(
            candidate.opportunity.opportunity_id)
        if assessment is not None:
            eligible = (getattr(assessment, 'eligible', None)
                        if not isinstance(assessment, Mapping)
                        else assessment.get('eligible'))
            if eligible is not True:
                return False
        if candidate.lock_time_s + _TIME_TOLERANCE_S < self.current_time_s:
            return False
        if (current is not None and current.interceptor_id == interceptor_id
                and current.candidate.opportunity.opportunity_id
                == candidate.opportunity.opportunity_id):
            return False
        return True

    def refresh_candidate_assessments(
            self, threat_ids: Optional[Sequence[str]] = None) -> None:
        """Validate frozen assessments without re-ranking the surviving actions.

        Candidate eligibility, evidence and ordinal cost are created once over a
        threat's complete candidate universe at detection. Time and reservations
        may invalidate actions, but they never change those frozen assessments.
        """
        if self.terminated or self.truncated:
            return
        selected = self.visible_threat_ids() if threat_ids is None else tuple(threat_ids)
        for threat_id in selected:
            runtime = self.threats.get(threat_id)
            if runtime is None or runtime.status != ThreatStatus.ACTIVE:
                continue
            expected = sum(len(rows) for rows in runtime.candidates.values())
            if callable(getattr(self.provider, 'assess_candidates', None)):
                if len(runtime.candidate_assessments) != expected:
                    raise ValueError('frozen candidate assessment universe is incomplete')

    def assign(self, threat_id: str, interceptor_id: str,
               candidate_index: int) -> Assignment:
        if not self.is_assignment_valid(threat_id, interceptor_id, candidate_index):
            raise ValueError('assignment is not valid in the current state')
        self.refresh_candidate_assessments((threat_id,))
        if not self.is_assignment_valid(threat_id, interceptor_id, candidate_index):
            raise ValueError('assignment became invalid during consequence ranking')
        candidate = self.candidate(threat_id, interceptor_id, candidate_index)
        assessment = self.threats[threat_id].candidate_assessments.get(
            candidate.opportunity.opportunity_id)
        if assessment is None:
            consequence_snapshot = None
        elif hasattr(assessment, 'as_dict'):
            consequence_snapshot = dict(assessment.as_dict())
        else:
            consequence_snapshot = dict(assessment)
        self._assignment_revision += 1
        assignment = Assignment(
            threat_id=threat_id,
            interceptor_id=interceptor_id,
            candidate=candidate,
            revision=self._assignment_revision,
            consequence_snapshot=consequence_snapshot,
        )
        self.assignments[threat_id] = assignment
        self.modified_threats.add(threat_id)
        self._push_event(QueueEvent(
            max(self.current_time_s, candidate.lock_time_s),
            EventKind.ASSIGNMENT_LOCK, threat_id, assignment.revision))
        self._assert_invariants()
        return assignment

    def can_cancel(self, threat_id: str) -> bool:
        assignment = self.assignments.get(threat_id)
        return bool(
            not self.terminated and not self.truncated
            and threat_id not in self.modified_threats
            and assignment is not None
            and assignment.status == AssignmentStatus.TENTATIVE
        )

    def cancel(self, threat_id: str) -> Assignment:
        if not self.can_cancel(threat_id):
            raise ValueError('assignment cannot be cancelled in the current state')
        assignment = self.assignments.pop(threat_id)
        self.modified_threats.add(threat_id)
        self._assert_invariants()
        return assignment

    def advance(self) -> Tuple[EventRecord, ...]:
        """Advance to and completely process the next timestamp."""
        if not self.can_advance():
            raise ValueError('the event queue cannot be advanced')
        target_time = self._next_live_event_time()
        if target_time is None:
            raise ValueError('the event queue is empty')
        self.current_time_s = target_time
        epoch_records: List[EventRecord] = []
        try:
            while True:
                self._discard_stale_head()
                if not self._queue or self._queue[0][0] != target_time:
                    break
                event = heapq.heappop(self._queue)[-1]
                if not self._event_is_live(event):
                    continue
                if self._processed_event_count >= self.event_limit:
                    self._truncate('event_limit_exhaustion')
                    break
                record = self._process_event(event)
                self._processed_event_count += 1
                self.event_records.append(record)
                epoch_records.append(record)
                if self.truncated or self.terminated:
                    break
            self.modified_threats.clear()
            if not self.truncated:
                self._assert_invariants()
                self._finish_if_resolved()
        except Exception as exc:  # provider/malformed-state failures truncate explicitly
            self._truncate('malformed_state:%s' % exc)
        return tuple(epoch_records)

    def _process_event(self, event: QueueEvent) -> EventRecord:
        details: Dict[str, Any] = {}
        status = 'processed'
        if event.kind == EventKind.DETECTION:
            self._detect(event.entity_id)
            details['candidate_pairs'] = len(self.interceptor_resources)
        elif event.kind == EventKind.ASSIGNMENT_LOCK:
            assignment = self.assignments[event.entity_id]
            assignment.status = AssignmentStatus.LOCKED
            self.consumed_interceptors.add(assignment.interceptor_id)
            self._push_event(QueueEvent(
                assignment.candidate.interception_time_s,
                EventKind.INTERCEPTION_OUTCOME, event.entity_id, assignment.revision))
            details.update(assignment.as_dict())
        elif event.kind == EventKind.INTERCEPTION_OUTCOME:
            assignment = self.assignments[event.entity_id]
            result = self._evaluate_assigned(assignment)
            if result is None:
                status = 'provider_failure'
            else:
                self._resolve(event.entity_id, ResolutionKind.INTERCEPTED, result)
                details['raw_score'] = result.raw_score
                details['training_cost'] = result.training_cost
                details['components'] = dict(result.components)
                details['evidence'] = dict(result.evidence)
        elif event.kind == EventKind.THREAT_EXPIRY:
            result = self._evaluate_unhandled(event.entity_id)
            if result is None:
                status = 'provider_failure'
            else:
                self._resolve(event.entity_id, ResolutionKind.UNHANDLED, result)
                details['raw_score'] = result.raw_score
                details['training_cost'] = result.training_cost
                details['components'] = dict(result.components)
                details['evidence'] = dict(result.evidence)
                if result.constraint_violation is not None:
                    details['constraint_violation'] = result.constraint_violation
                    self._terminate_constraint_violation(result)
        elif event.kind == EventKind.EPISODE_END:
            unresolved = [key for key, value in self.threats.items()
                          if value.status != ThreatStatus.RESOLVED]
            if unresolved:
                self._truncate('malformed_state:episode_end_with_unresolved_threats')
                status = 'truncated'
            else:
                status = 'complete'
        return EventRecord(
            event_id='%s:e%06d' % (self.spec.episode_id, self._processed_event_count + 1),
            time_s=self.current_time_s,
            kind=event.kind.value,
            entity_id=event.entity_id,
            status=status,
            details=details,
        )

    def _detect(self, threat_id: str) -> None:
        runtime = self.threats[threat_id]
        if runtime.status != ThreatStatus.SCHEDULED:
            raise ValueError('duplicate threat detection')
        runtime.status = ThreatStatus.ACTIVE
        for interceptor_id, resource in self.interceptor_resources.items():
            opportunities = generate_candidate_opportunities(
                runtime.scheduled.state, resource.state, self.spec.candidate_count)
            runtime.candidates[interceptor_id] = tuple(
                AbsoluteCandidate.from_opportunity(item, runtime.scheduled.detection_time_s)
                for item in opportunities
            )
        assessor = getattr(self.provider, 'assess_candidates', None)
        if callable(assessor):
            all_candidates = tuple(
                candidate
                for interceptor_id in sorted(runtime.candidates)
                for candidate in runtime.candidates[interceptor_id])
            try:
                assessments = assessor(
                    runtime.scheduled, all_candidates, dict(self.operational_state))
            except Exception as exc:
                self._truncate('provider_failure:%s' % exc)
                return
            if not isinstance(assessments, Mapping):
                raise ValueError('provider candidate assessments must be a mapping')
            for candidate in all_candidates:
                opportunity_id = candidate.opportunity.opportunity_id
                if opportunity_id not in assessments:
                    raise ValueError('provider omitted a candidate assessment')
            runtime.candidate_assessments = dict(assessments)
            if self.spec.schema_version == 'simulation-episode/2':
                expected = (len(self.interceptor_resources)
                            * self.spec.candidate_count)
                if len(all_candidates) != 160 or expected != 160:
                    raise ValueError('Singapore objective requires a 160-candidate universe per threat')
                for assessment in assessments.values():
                    context = (assessment.rank_context if hasattr(assessment, 'rank_context')
                               else assessment.get('rank_context', {}))
                    if (context.get('objective_scope') != 'full_candidate_universe'
                            or context.get('candidate_universe_count') != 160):
                        raise ValueError('Singapore candidate rank context is not full-universe')
            self._assessment_contexts.pop(threat_id, None)
        self._push_event(QueueEvent(
            runtime.scheduled.expiry_time_s, EventKind.THREAT_EXPIRY, threat_id))

    def _check_provider_identity(self) -> None:
        current = provider_identity(self.provider)
        if current['objective_direction'] != self._objective_direction.value:
            raise ValueError('provider objective direction changed during the episode')
        if (current['identity'] != self.provider_provenance['identity']
                or current['version'] != self.provider_provenance['version']):
            raise ValueError('provider identity or version changed during the episode')

    def _validate_provider_result(self, result: Any,
                                  require_training_cost: bool = False) -> ProviderEvaluation:
        if not isinstance(result, ProviderEvaluation):
            raise ValueError('provider returned a malformed result')
        if result.failure_status is not None:
            self.provider_failures.append(result)
            self._truncate('provider_failure:' + result.failure_status)
        elif require_training_cost and result.training_cost is None:
            raise ValueError('RL-compatible provider results require additive training_cost')
        return result

    def _apply_operational_update(self, result: ProviderEvaluation) -> None:
        self.operational_state.update(result.operational_state_update)

    def _evaluate_assigned(self, assignment: Assignment) -> Optional[ProviderEvaluation]:
        try:
            self._check_provider_identity()
            snapshot_evaluator = getattr(
                self.provider, 'evaluate_assigned_assessment', None)
            if callable(snapshot_evaluator) and assignment.consequence_snapshot is not None:
                evaluated = snapshot_evaluator(
                    self.threats[assignment.threat_id].scheduled,
                    assignment.candidate, assignment.consequence_snapshot,
                    dict(self.operational_state))
            else:
                evaluated = self.provider.evaluate_assigned(
                    self.threats[assignment.threat_id].scheduled,
                    assignment.candidate, dict(self.operational_state))
            result = self._validate_provider_result(
                evaluated, require_training_cost=True)
            if result.failure_status is not None:
                return None
            self._apply_operational_update(result)
            return result
        except Exception as exc:
            self._truncate('provider_failure:%s' % exc)
            return None

    def _evaluate_unhandled(self, threat_id: str) -> Optional[ProviderEvaluation]:
        try:
            self._check_provider_identity()
            result = self._validate_provider_result(self.provider.evaluate_unhandled(
                self.threats[threat_id].scheduled, dict(self.operational_state)),
                require_training_cost=True)
            if result.failure_status is not None:
                return None
            self._apply_operational_update(result)
            return result
        except Exception as exc:
            self._truncate('provider_failure:%s' % exc)
            return None

    def _resolve(self, threat_id: str, kind: ResolutionKind,
                 result: ProviderEvaluation) -> None:
        runtime = self.threats[threat_id]
        if runtime.status != ThreatStatus.ACTIVE:
            raise ValueError('only an active threat can resolve')
        runtime.status = ThreatStatus.RESOLVED
        runtime.resolution = kind
        runtime.resolved_time_s = self.current_time_s
        assignment = self.assignments.get(threat_id)
        if kind == ResolutionKind.UNHANDLED and assignment is not None:
            if assignment.status == AssignmentStatus.LOCKED:
                raise ValueError('a locked assignment cannot expire unhandled')
            self.assignments.pop(threat_id)
        self.outcomes.append(result)

    def _terminate_constraint_violation(self, violation: ProviderEvaluation) -> None:
        self.constraint_violations.append(violation)
        try:
            aggregate = self._validate_provider_result(
                self.provider.aggregate(tuple(self.outcomes), dict(self.operational_state)),
                require_training_cost=True)
            if aggregate.failure_status is not None:
                return
            self._apply_operational_update(aggregate)
            self.aggregate_result = aggregate
            self.terminated = True
            self.truncated = False
            self.termination_reason = 'constraint_violation:' + str(
                violation.constraint_violation)
        except Exception as exc:
            self._truncate('provider_failure:%s' % exc)

    def _finish_if_resolved(self) -> None:
        if self.terminated or self.truncated:
            return
        if any(item.status != ThreatStatus.RESOLVED for item in self.threats.values()):
            return
        try:
            self._check_provider_identity()
            result = self._validate_provider_result(
                self.provider.aggregate(tuple(self.outcomes), dict(self.operational_state)),
                require_training_cost=True)
            if result.failure_status is not None:
                return
            self._apply_operational_update(result)
            self.aggregate_result = result
            self.terminated = True
            self.termination_reason = 'all_threats_resolved'
        except Exception as exc:
            self._truncate('provider_failure:%s' % exc)

    def _truncate(self, reason: str) -> None:
        self.truncated = True
        self.terminated = False
        self.termination_reason = reason

    def truncate(self, reason: str) -> None:
        """Explicitly truncate for an adapter-detected malformed state."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('truncation reason must be a nonempty string')
        self._truncate(reason)

    def _assert_invariants(self) -> None:
        interceptor_ids = [item.interceptor_id for item in self.assignments.values()]
        if len(interceptor_ids) != len(set(interceptor_ids)):
            raise ValueError('one interceptor is assigned to multiple threats')
        for threat_id, assignment in self.assignments.items():
            if threat_id != assignment.threat_id:
                raise ValueError('assignment key does not match its threat')
            if self.threats[threat_id].status == ThreatStatus.SCHEDULED:
                raise ValueError('a future threat has an assignment')
            if assignment.status == AssignmentStatus.LOCKED:
                if assignment.interceptor_id not in self.consumed_interceptors:
                    raise ValueError('locked assignment did not consume its interceptor')
            elif assignment.interceptor_id in self.consumed_interceptors:
                raise ValueError('a tentative assignment uses a consumed interceptor')
        locked_ids = {
            item.interceptor_id for item in self.assignments.values()
            if item.status == AssignmentStatus.LOCKED
        }
        if not locked_ids.issubset(self.consumed_interceptors):
            raise ValueError('consumed interceptor state is inconsistent')

    def snapshot(self) -> Mapping[str, Any]:
        """Return a stable JSON-compatible state representation for audit/replay."""
        threats = []
        for threat_id in sorted(self.threats):
            runtime = self.threats[threat_id]
            threats.append({
                'threat_id': threat_id,
                'status': runtime.status.value,
                'detection_time_s': runtime.scheduled.detection_time_s,
                'expiry_time_s': runtime.scheduled.expiry_time_s,
                'resolution': None if runtime.resolution is None else runtime.resolution.value,
                'resolved_time_s': runtime.resolved_time_s,
            })
            if self.spec.schema_version == 'simulation-episode/2':
                threats[-1].update({
                    'position_z_m': runtime.scheduled.state.position_z_m,
                    'velocity_z_mps': runtime.scheduled.state.velocity_z_mps,
                    'acceleration_z_mps2': runtime.scheduled.state.acceleration_z_mps2,
                })
        return {
            'simulator_version': SIMULATOR_VERSION,
            'episode_id': self.spec.episode_id,
            'seed': self.spec.seed,
            'time_s': self.current_time_s,
            'threats': threats,
            'consumed_interceptors': sorted(self.consumed_interceptors),
            'assignments': [self.assignments[key].as_dict()
                            for key in sorted(self.assignments)],
            'operational_state': dict(sorted(self.operational_state.items())),
            'processed_event_count': self._processed_event_count,
            'terminated': self.terminated,
            'truncated': self.truncated,
            'termination_reason': self.termination_reason,
            'raw_score': self.raw_score,
            'training_cost': (None if self.aggregate_result is None
                              else self.aggregate_result.training_cost),
            'constraint_violation_count': len(self.constraint_violations),
        }

    @staticmethod
    def _provider_result_audit(result: ProviderEvaluation,
                               include_runtime: bool = True) -> Mapping[str, Any]:
        audit = {
            'raw_score': result.raw_score,
            'training_cost': result.training_cost,
            'components': dict(result.components),
            'provenance': dict(result.provenance),
            'evidence': dict(result.evidence),
            'failure_status': result.failure_status,
            'constraint_violation': result.constraint_violation,
        }
        if include_runtime:
            audit['runtime_ms'] = result.runtime_ms
        return audit

    def provider_audit(self, include_runtime: bool = True) -> Mapping[str, Any]:
        """Provider identity plus all result-level provenance retained raw."""
        return {
            **self.provider_provenance,
            'outcomes': [self._provider_result_audit(item, include_runtime)
                         for item in self.outcomes],
            'failures': [self._provider_result_audit(item, include_runtime)
                         for item in self.provider_failures],
            'constraint_violations': [
                self._provider_result_audit(item, include_runtime)
                for item in self.constraint_violations],
            'aggregate': (None if self.aggregate_result is None
                          else self._provider_result_audit(
                              self.aggregate_result, include_runtime)),
        }
