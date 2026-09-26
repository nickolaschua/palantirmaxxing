"""Versioned JSONL rollout recording and deterministic replay helpers."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


ROLLOUT_SCHEMA_VERSION = 'rl-rollout/1'


def observation_reference(observation: Any) -> str:
    """Return a stable content address for a contiguous numeric observation."""
    try:
        payload = observation.tobytes(order='C')
    except (AttributeError, TypeError):
        payload = json.dumps(observation, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')
    return 'sha256:' + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RolloutRecord:
    episode_id: str
    event_id: str
    seed: int
    observation_ref: str
    action_mask: Tuple[bool, ...]
    action: int
    assignments_before: Tuple[Mapping[str, Any], ...]
    assignments_after: Tuple[Mapping[str, Any], ...]
    raw_score: Optional[float]
    state_before: Mapping[str, Any]
    state_after: Mapping[str, Any]
    provider_provenance: Mapping[str, Any]
    model_version: str
    termination_reason: Optional[str]
    timing_ms: float
    schema_version: str = ROLLOUT_SCHEMA_VERSION

    def as_dict(self) -> Mapping[str, Any]:
        value = asdict(self)
        value['action_mask'] = list(self.action_mask)
        value['assignments_before'] = list(self.assignments_before)
        value['assignments_after'] = list(self.assignments_after)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> 'RolloutRecord':
        if value.get('schema_version') != ROLLOUT_SCHEMA_VERSION:
            raise ValueError('unsupported rollout record schema')
        return cls(
            episode_id=value['episode_id'],
            event_id=value['event_id'],
            seed=value['seed'],
            observation_ref=value['observation_ref'],
            action_mask=tuple(value['action_mask']),
            action=value['action'],
            assignments_before=tuple(value['assignments_before']),
            assignments_after=tuple(value['assignments_after']),
            raw_score=value.get('raw_score'),
            state_before=value['state_before'],
            state_after=value['state_after'],
            provider_provenance=value['provider_provenance'],
            model_version=value['model_version'],
            termination_reason=value.get('termination_reason'),
            timing_ms=value['timing_ms'],
            schema_version=value['schema_version'],
        )


class JsonlRolloutRecorder:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: RolloutRecord) -> None:
        if not isinstance(record, RolloutRecord):
            raise ValueError('record must be a RolloutRecord')
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record.as_dict(), sort_keys=True,
                                    separators=(',', ':'), allow_nan=False) + '\n')

    def read(self) -> Tuple[RolloutRecord, ...]:
        if not self.path.exists():
            return ()
        records = []
        with self.path.open('r', encoding='utf-8') as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    records.append(RolloutRecord.from_dict(json.loads(line)))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError('invalid rollout record on line %d' % line_number) from exc
        return tuple(records)


def replay_rollout(records: Iterable[RolloutRecord], env: Any,
                   require_complete: bool = True) -> bool:
    """Verify every transition in contiguous episodes, including the final row.

    Recorded seeds are actual scenario seeds; undo a replay environment's seed
    offset before resetting it. Only the final episode may be partial, and only
    when explicitly requested.
    """
    seen = set()
    episode_id = None
    episode_seed = None
    decision = 0
    complete = False
    for expected in records:
        if expected.schema_version != ROLLOUT_SCHEMA_VERSION:
            raise ValueError('unsupported rollout record schema')
        if not isinstance(expected.episode_id, str) or not expected.episode_id:
            raise ValueError('episode_id must be a nonempty string')
        if type(expected.seed) is not int:
            raise ValueError('recorded seed must be an integer')
        if expected.episode_id != episode_id:
            if episode_id is not None and not complete:
                raise ValueError('episode changed before termination')
            if expected.episode_id in seen:
                raise ValueError('noncontiguous reuse of episode ID')
            seen.add(expected.episode_id)
            episode_id, episode_seed = expected.episode_id, expected.seed
            reset_seed = episode_seed
            if getattr(env, 'scenario_generator', None) is not None:
                reset_seed -= getattr(env, 'scenario_seed_offset', 0)
            observation, info = env.reset(seed=reset_seed)
            if info['episode_id'] != episode_id or info['seed'] != episode_seed:
                raise ValueError('replay reset does not match recorded episode')
            decision, complete = 0, False
        elif complete:
            raise ValueError('record follows episode termination')
        if expected.seed != episode_seed:
            raise ValueError('inconsistent seed within episode')
        decision += 1
        if expected.event_id != '%s:d%06d' % (episode_id, decision):
            raise ValueError('malformed decision numbering')

        def verify(actual, recorded, field):
            if actual != recorded:
                raise ValueError('rollout %s diverged at %s' % (field, expected.event_id))

        verify(observation_reference(observation), expected.observation_ref, 'observation')
        mask = tuple(bool(item) for item in env.action_masks())
        verify(mask, expected.action_mask, 'action mask')
        before = env.engine.snapshot()
        verify(before, expected.state_before, 'pre-state')
        verify(tuple(before['assignments']), expected.assignments_before, 'assignments before')
        if (type(expected.action) is not int or not 0 <= expected.action < len(mask)
                or not mask[expected.action]):
            raise ValueError('invalid recorded action at ' + expected.event_id)
        observation, _, terminated, truncated, info = env.step(expected.action)
        after = env.engine.snapshot()
        verify(after, expected.state_after, 'post-state')
        verify(tuple(after['assignments']), expected.assignments_after, 'assignments after')
        verify(info['raw_score'], expected.raw_score, 'raw score')
        verify(info['termination_reason'], expected.termination_reason, 'termination reason')
        complete = terminated or truncated
    if not seen:
        raise ValueError('at least one rollout record is required')
    if require_complete and not complete:
        raise ValueError('final episode is incomplete')
    return True


def write_records(path: Path, records: Iterable[RolloutRecord]) -> None:
    recorder = JsonlRolloutRecorder(path)
    for record in records:
        recorder.record(record)
