"""Gymnasium adapter for the centralized continuous-event simulator."""
from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

import gymnasium as gym
from gymnasium import spaces
import numpy as np

from backend.simulation import (MAX_CANDIDATES_PER_PAIR, MAX_INTERCEPTORS,
                                MAX_THREATS, AssignmentStatus,
                                ConsequenceProvider, EpisodeSpec,
                                JsonlRolloutRecorder, ObjectiveDirection,
                                RolloutRecord, SeededScenarioGenerator,
                                SimulationEngine, ThreatStatus,
                                observation_reference)


ASSIGNMENT_ACTIONS = MAX_THREATS * MAX_INTERCEPTORS * MAX_CANDIDATES_PER_PAIR
CANCEL_ACTION_START = ASSIGNMENT_ACTIONS
ADVANCE_ACTION = CANCEL_ACTION_START + MAX_THREATS
ACTION_COUNT = ADVANCE_ACTION + 1
PROVIDER_FEATURE_COUNT = 16
OBSERVATION_LAYOUT_VERSION = 'centralized-observation/2'
CANDIDATE_FEATURE_COUNT = 17
THREAT_FEATURE_COUNT = 11
INTERCEPTOR_FEATURE_COUNT = 7
ASSIGNMENT_FEATURE_COUNT = 6
GLOBAL_FEATURE_COUNT = 8


@dataclass(frozen=True)
class ObservationLayout:
    global_state: slice
    threats: slice
    interceptors: slice
    assignments: slice
    candidates: slice
    provider_features: slice
    threat_presence: slice
    interceptor_presence: slice
    candidate_presence: slice
    size: int

    @classmethod
    def build(cls) -> 'ObservationLayout':
        offset = 0

        def take(count: int) -> slice:
            nonlocal offset
            result = slice(offset, offset + count)
            offset += count
            return result

        global_state = take(GLOBAL_FEATURE_COUNT)
        threats = take(MAX_THREATS * THREAT_FEATURE_COUNT)
        interceptors = take(MAX_INTERCEPTORS * INTERCEPTOR_FEATURE_COUNT)
        assignments = take(MAX_THREATS * ASSIGNMENT_FEATURE_COUNT)
        candidates = take(
            MAX_THREATS * MAX_INTERCEPTORS * MAX_CANDIDATES_PER_PAIR
            * CANDIDATE_FEATURE_COUNT)
        provider_features = take(PROVIDER_FEATURE_COUNT)
        threat_presence = take(MAX_THREATS)
        interceptor_presence = take(MAX_INTERCEPTORS)
        candidate_presence = take(
            MAX_THREATS * MAX_INTERCEPTORS * MAX_CANDIDATES_PER_PAIR)
        return cls(global_state, threats, interceptors, assignments, candidates,
                   provider_features, threat_presence, interceptor_presence,
                   candidate_presence, offset)

    @property
    def checksum(self) -> str:
        payload = {
            'version': OBSERVATION_LAYOUT_VERSION,
            'counts': {
                'global': GLOBAL_FEATURE_COUNT, 'threat': THREAT_FEATURE_COUNT,
                'interceptor': INTERCEPTOR_FEATURE_COUNT,
                'assignment': ASSIGNMENT_FEATURE_COUNT,
                'candidate': CANDIDATE_FEATURE_COUNT,
                'provider': PROVIDER_FEATURE_COUNT,
            },
            'size': self.size,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        return 'sha256:' + hashlib.sha256(encoded).hexdigest()


class MaskAwareDiscrete(spaces.Discrete):
    """Lets generic environment checkers sample a currently valid action."""

    def __init__(self, n: int, mask_provider: Callable[[], np.ndarray]):
        super().__init__(n)
        self._mask_provider = mask_provider

    def sample(self, mask=None, probability=None):
        if mask is None:
            mask = np.asarray(self._mask_provider(), dtype=np.int8)
            if not np.any(mask):
                return super().sample(mask=None, probability=probability)
            # Advance is valid in every nonterminal reset state, including when
            # the checker samples before resetting to a different seed.
            if len(mask) > ADVANCE_ACTION and mask[ADVANCE_ACTION]:
                return np.int64(ADVANCE_ACTION)
        return super().sample(mask=mask, probability=probability)


class CentralizedInterceptionEnv(gym.Env):
    """Fixed-shape, invalid-action-masked Gymnasium environment."""

    metadata = {'render_modes': []}

    def __init__(self, provider: ConsequenceProvider,
                 episode_spec: Optional[EpisodeSpec] = None,
                 scenario_generator: Optional[SeededScenarioGenerator] = None,
                 base_seed: int = 0,
                 event_limit: int = 10000,
                 recorder: Optional[JsonlRolloutRecorder] = None,
                 policy_version: str = 'policy-not-specified',
                 scenario_seed_offset: int = 0):
        super().__init__()
        if episode_spec is None and scenario_generator is None:
            scenario_generator = SeededScenarioGenerator()
        if episode_spec is not None and scenario_generator is not None:
            raise ValueError('supply either episode_spec or scenario_generator, not both')
        if type(base_seed) is not int:
            raise ValueError('base_seed must be an integer')
        if type(scenario_seed_offset) is not int or scenario_seed_offset < 0:
            raise ValueError('scenario_seed_offset must be a nonnegative integer')
        if scenario_seed_offset and base_seed < 0:
            raise ValueError('base_seed must be nonnegative when using a seed offset')
        self.provider = provider
        self._fixed_episode_spec = episode_spec
        self.scenario_generator = scenario_generator
        self.base_seed = base_seed
        self.scenario_seed_offset = scenario_seed_offset
        self.event_limit = event_limit
        self.recorder = recorder
        if not isinstance(policy_version, str) or not policy_version.strip():
            raise ValueError('policy_version must be a nonempty string')
        self.policy_version = policy_version
        self.layout = ObservationLayout.build()
        float_limit = np.finfo(np.float32).max
        self.observation_space = spaces.Box(
            low=-float_limit, high=float_limit,
            shape=(self.layout.size,), dtype=np.float32)
        self.action_space = MaskAwareDiscrete(ACTION_COUNT, self.action_masks)
        self.engine: Optional[SimulationEngine] = None
        self.episode_spec: Optional[EpisodeSpec] = None
        self.threat_slots: Tuple[Optional[str], ...] = (None,) * MAX_THREATS
        self.interceptor_slots: Tuple[Optional[str], ...] = (None,) * MAX_INTERCEPTORS
        self._episode_counter = 0
        self._decision_counter = 0
        self._episode_reward = 0.0

    @staticmethod
    def encode_assignment_action(threat_slot: int, interceptor_slot: int,
                                 candidate_slot: int) -> int:
        for value, upper, name in (
                (threat_slot, MAX_THREATS, 'threat_slot'),
                (interceptor_slot, MAX_INTERCEPTORS, 'interceptor_slot'),
                (candidate_slot, MAX_CANDIDATES_PER_PAIR, 'candidate_slot')):
            if type(value) is not int or not 0 <= value < upper:
                raise ValueError(name + ' is out of range')
        return ((threat_slot * MAX_INTERCEPTORS + interceptor_slot)
                * MAX_CANDIDATES_PER_PAIR + candidate_slot)

    @staticmethod
    def decode_assignment_action(action: int) -> Tuple[int, int, int]:
        if type(action) is not int or not 0 <= action < ASSIGNMENT_ACTIONS:
            raise ValueError('action is not an assignment action')
        pair, candidate_slot = divmod(action, MAX_CANDIDATES_PER_PAIR)
        threat_slot, interceptor_slot = divmod(pair, MAX_INTERCEPTORS)
        return threat_slot, interceptor_slot, candidate_slot

    @staticmethod
    def cancel_action(threat_slot: int) -> int:
        if type(threat_slot) is not int or not 0 <= threat_slot < MAX_THREATS:
            raise ValueError('threat_slot is out of range')
        return CANCEL_ACTION_START + threat_slot

    def _select_episode(self, seed: Optional[int]) -> EpisodeSpec:
        if self._fixed_episode_spec is not None:
            return self._fixed_episode_spec
        if seed is None:
            selected_seed = self.base_seed + self._episode_counter
        else:
            selected_seed = seed
        if type(selected_seed) is not int or (self.scenario_seed_offset and selected_seed < 0):
            raise ValueError('scenario seed must be a nonnegative integer with an offset')
        self._episode_counter += 1
        return self.scenario_generator.generate(selected_seed + self.scenario_seed_offset)

    def reset(self, *, seed: Optional[int] = None,
              options: Optional[Mapping[str, Any]] = None):
        super().reset(seed=seed)
        selected = None if options is None else options.get('episode_spec')
        if selected is not None:
            if not isinstance(selected, EpisodeSpec):
                raise ValueError('options[episode_spec] must be an EpisodeSpec')
            self.episode_spec = selected
        else:
            self.episode_spec = self._select_episode(seed)
        self.engine = SimulationEngine(
            self.episode_spec, self.provider, event_limit=self.event_limit)
        ordered_threats = sorted(self.episode_spec.threats, key=lambda item: (
            item.detection_time_s, item.expiry_time_s, item.state.threat_id))
        ordered_interceptors = sorted(
            self.episode_spec.interceptors, key=lambda item: item.state.interceptor_id)
        self.threat_slots = tuple(
            [item.state.threat_id for item in ordered_threats]
            + [None] * (MAX_THREATS - len(ordered_threats)))
        self.interceptor_slots = tuple(
            [item.state.interceptor_id for item in ordered_interceptors]
            + [None] * (MAX_INTERCEPTORS - len(ordered_interceptors)))
        self._decision_counter = 0
        self._episode_reward = 0.0
        observation = self._observation()
        return observation, self._info(())

    def action_masks(self) -> np.ndarray:
        mask = np.zeros(ACTION_COUNT, dtype=np.int8)
        if self.engine is None or self.engine.terminated or self.engine.truncated:
            return mask
        try:
            self.engine.refresh_candidate_assessments()
        except Exception as exc:
            self.engine.truncate('provider_failure:%s' % exc)
            return mask
        for threat_slot, threat_id in enumerate(self.threat_slots):
            if threat_id is None:
                continue
            for interceptor_slot, interceptor_id in enumerate(self.interceptor_slots):
                if interceptor_id is None:
                    continue
                for candidate_slot in range(MAX_CANDIDATES_PER_PAIR):
                    action = self.encode_assignment_action(
                        threat_slot, interceptor_slot, candidate_slot)
                    if self.engine.is_assignment_valid(
                            threat_id, interceptor_id, candidate_slot):
                        mask[action] = 1
            if self.engine.can_cancel(threat_id):
                mask[self.cancel_action(threat_slot)] = 1
        if self.engine.can_advance():
            mask[ADVANCE_ACTION] = 1
        return mask

    def step(self, action):
        if self.engine is None:
            raise ValueError('reset must be called before step')
        if isinstance(action, np.integer):
            action = int(action)
        if type(action) is not int or not self.action_space.contains(action):
            raise ValueError('action must be an integer within the discrete action space')
        mask = self.action_masks()
        if not bool(mask[action]):
            raise ValueError('action is invalid in the current state')
        before = self.engine.snapshot()
        before_observation = self._observation()
        started = time.perf_counter()
        processed_events = ()
        if action < ASSIGNMENT_ACTIONS:
            threat_slot, interceptor_slot, candidate_slot = self.decode_assignment_action(action)
            self.engine.assign(
                self.threat_slots[threat_slot],
                self.interceptor_slots[interceptor_slot],
                candidate_slot,
            )
        elif action < ADVANCE_ACTION:
            self.engine.cancel(self.threat_slots[action - CANCEL_ACTION_START])
        else:
            processed_events = self.engine.advance()
        timing_ms = (time.perf_counter() - started) * 1000.0
        observation = self._observation()
        after = self.engine.snapshot()
        step_training_costs = tuple(
            float(record.details['training_cost'])
            for record in processed_events
            if record.kind in ('interception_outcome', 'threat_expiry')
            and record.details.get('training_cost') is not None)
        reward = math.fsum(step_training_costs)
        if self.engine.objective_direction == ObjectiveDirection.MINIMIZE:
            reward = -reward
        self._episode_reward = math.fsum((self._episode_reward, reward))
        if (self.engine.terminated and self.engine.aggregate_result is not None
                and self.engine.aggregate_result.training_cost is not None):
            expected = float(self.engine.aggregate_result.training_cost)
            if self.engine.objective_direction == ObjectiveDirection.MINIMIZE:
                expected = -expected
            if not math.isclose(self._episode_reward, expected,
                                rel_tol=0.0, abs_tol=1e-12):
                self.engine.truncate('malformed_state:reward_cost_mismatch')
        self._decision_counter += 1
        info = self._info(processed_events, step_training_costs)
        if self.recorder is not None:
            event_id = '%s:d%06d' % (
                self.episode_spec.episode_id, self._decision_counter)
            self.recorder.record(RolloutRecord(
                episode_id=self.episode_spec.episode_id,
                event_id=event_id,
                seed=self.episode_spec.seed,
                observation_ref=observation_reference(before_observation),
                action_mask=tuple(bool(item) for item in mask),
                action=action,
                assignments_before=tuple(before['assignments']),
                assignments_after=tuple(after['assignments']),
                raw_score=self.engine.raw_score,
                state_before=before,
                state_after=after,
                provider_provenance=self.engine.provider_audit(),
                model_version=self.policy_version,
                termination_reason=self.engine.termination_reason,
                reward=reward,
                step_training_costs=step_training_costs,
                timing_ms=timing_ms,
            ))
        return (observation, reward, self.engine.terminated,
                self.engine.truncated, info)

    def _info(self, processed_events: Sequence[Any],
              step_training_costs: Sequence[float] = ()) -> Dict[str, Any]:
        return {
            'episode_id': self.episode_spec.episode_id,
            'seed': self.episode_spec.seed,
            'raw_score': self.engine.raw_score,
            'score_direction': self.engine.objective_direction.value,
            'provider': dict(self.engine.provider_provenance),
            'simulator_version': self.engine.snapshot()['simulator_version'],
            'termination_reason': self.engine.termination_reason,
            'processed_events': [item.as_dict() for item in processed_events],
            'step_training_costs': list(step_training_costs),
            'episode_reward': self._episode_reward,
        }

    @staticmethod
    def _write_row(target: np.ndarray, row: int, width: int,
                   values: Sequence[float]) -> None:
        start = row * width
        target[start:start + width] = np.asarray(values, dtype=np.float32)

    def _observation(self) -> np.ndarray:
        engine = self.engine
        result = np.zeros(self.layout.size, dtype=np.float32)
        if not engine.terminated and not engine.truncated:
            try:
                engine.refresh_candidate_assessments()
            except Exception as exc:
                engine.truncate('provider_failure:%s' % exc)
        active_ids = [key for key in self.threat_slots if key is not None
                      and engine.threats[key].status == ThreatStatus.ACTIVE]
        assignments = [item for key, item in engine.assignments.items()
                       if engine.threats[key].status == ThreatStatus.ACTIVE]
        global_values = (
            engine.current_time_s,
            len(active_ids),
            len(engine.interceptor_resources),
            sum(interceptor_id not in engine.consumed_interceptors
                and engine.assignment_for_interceptor(interceptor_id) is None
                for interceptor_id in engine.interceptor_resources),
            sum(item.status == AssignmentStatus.TENTATIVE for item in assignments),
            sum(item.status == AssignmentStatus.LOCKED for item in assignments),
            sum(item.status == ThreatStatus.RESOLVED for item in engine.threats.values()),
            engine.processed_event_count,
        )
        result[self.layout.global_state] = global_values
        threat_values = result[self.layout.threats]
        interceptor_values = result[self.layout.interceptors]
        assignment_values = result[self.layout.assignments]
        candidate_values = result[self.layout.candidates]
        threat_presence = result[self.layout.threat_presence]
        interceptor_presence = result[self.layout.interceptor_presence]
        candidate_presence = result[self.layout.candidate_presence]

        for threat_slot, threat_id in enumerate(self.threat_slots):
            if threat_id is None:
                continue
            runtime = engine.threats[threat_id]
            if runtime.status != ThreatStatus.ACTIVE:
                continue
            threat_presence[threat_slot] = 1.0
            threat = runtime.scheduled
            state = threat.state
            assignment = engine.assignments.get(threat_id)
            status_code = 0.0 if assignment is None else (
                1.0 if assignment.status == AssignmentStatus.TENTATIVE else 2.0)
            self._write_row(threat_values, threat_slot, THREAT_FEATURE_COUNT, (
                engine.current_time_s - threat.detection_time_s,
                threat.expiry_time_s - engine.current_time_s,
                state.position_x_m,
                state.position_y_m,
                state.position_z_m,
                state.velocity_x_mps,
                state.velocity_y_mps,
                state.velocity_z_mps,
                state.acceleration_z_mps2,
                state.maximum_time_to_go_s,
                status_code,
            ))
            if assignment is not None:
                interceptor_slot = self.interceptor_slots.index(assignment.interceptor_id)
                candidate_slot = assignment.candidate.opportunity.sample_index - 1
                self._write_row(assignment_values, threat_slot,
                                ASSIGNMENT_FEATURE_COUNT, (
                                    1.0,
                                    interceptor_slot,
                                    candidate_slot,
                                    float(assignment.status == AssignmentStatus.LOCKED),
                                    assignment.candidate.lock_time_s - engine.current_time_s,
                                    assignment.candidate.interception_time_s - engine.current_time_s,
                                ))
            for interceptor_slot, interceptor_id in enumerate(self.interceptor_slots):
                if interceptor_id is None:
                    continue
                rows = runtime.candidates.get(interceptor_id, ())
                for candidate_slot, candidate in enumerate(rows):
                    flat_row = ((threat_slot * MAX_INTERCEPTORS + interceptor_slot)
                                * MAX_CANDIDATES_PER_PAIR + candidate_slot)
                    candidate_presence[flat_row] = 1.0
                    opportunity = candidate.opportunity
                    assessment = runtime.candidate_assessments.get(
                        opportunity.opportunity_id)
                    if assessment is None:
                        consequence = (-1.0, -1.0, -1.0, -1.0, -1.0,
                                       0.0, 1.0, -1.0)
                    else:
                        values = getattr(assessment, 'decision_features', None)
                        if values is None and isinstance(assessment, Mapping):
                            values = assessment.get('decision_features')
                        if values is None or len(values) != 9:
                            raise ValueError('candidate assessment must provide nine decision features')
                        # Eligibility is already represented by the action mask;
                        # retain the remaining rank/consequence/status fields.
                        consequence = tuple(values[1:])
                    self._write_row(candidate_values, flat_row,
                                    CANDIDATE_FEATURE_COUNT, (
                                        float(opportunity.reachable),
                                        candidate.interception_time_s - engine.current_time_s,
                                        candidate.lock_time_s - engine.current_time_s,
                                        opportunity.position_x_m,
                                        opportunity.position_y_m,
                                        opportunity.position_z_m,
                                        opportunity.required_travel_time_s,
                                        opportunity.time_margin_s,
                                        opportunity.minimum_path_length_m,
                                        *consequence,
                                    ))

        for interceptor_slot, interceptor_id in enumerate(self.interceptor_slots):
            if interceptor_id is None:
                continue
            interceptor_presence[interceptor_slot] = 1.0
            state = engine.interceptor_resources[interceptor_id].state
            reservation = engine.assignment_for_interceptor(interceptor_id)
            self._write_row(interceptor_values, interceptor_slot,
                            INTERCEPTOR_FEATURE_COUNT, (
                                state.position_x_m,
                                state.position_y_m,
                                state.heading_rad,
                                state.speed_mps,
                                state.max_turn_rate_rad_s,
                                float(interceptor_id in engine.consumed_interceptors),
                                float(reservation is not None),
                            ))

        if engine.terminated or engine.truncated:
            return result
        try:
            features = tuple(self.provider.decision_features(engine, active_ids))
            if len(features) > PROVIDER_FEATURE_COUNT:
                raise ValueError('provider returned more than 16 decision features')
            if any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in features):
                raise ValueError('provider decision features must be finite numbers')
            result[self.layout.provider_features.start:
                   self.layout.provider_features.start + len(features)] = features
        except Exception as exc:
            engine.truncate('provider_failure:%s' % exc)
        if not np.all(np.isfinite(result)):
            engine.truncate('malformed_state:nonfinite_observation')
            result = np.nan_to_num(
                result, nan=0.0,
                posinf=np.finfo(np.float32).max,
                neginf=np.finfo(np.float32).min)
        return result
