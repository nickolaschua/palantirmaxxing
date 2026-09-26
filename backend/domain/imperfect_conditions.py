"""Versioned, simulation-only context for imperfect-condition demonstrations.

The records in this module preserve observable condition flags separately from
expert labels. They do not encode operational thresholds or choose an action.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Optional, Sequence, Tuple


IMPERFECT_CONDITION_SCHEMA_VERSION = 'imperfect-condition-demonstration/1'
CONDITION_FEATURE_SCHEMA_VERSION = 'imperfect-condition-features/1'
CONDITION_STATE_FEATURE_ORDER = (
    'heavy_rain',
    'mist',
    'strong_wind',
    'sensor_outage',
    'communication_delay',
)
CONDITION_ACTION_FEATURE_ORDER = ('building_path_intersection',)
EXPLANATION_CODES = frozenset((
    'rain_preserved_replanning_margin',
    'mist_widened_track_uncertainty',
    'wind_widened_path_uncertainty',
    'building_path_excluded',
    'sensor_outage_reduced_coverage',
    'communication_delay_preserved_margin',
    'insufficient_confidence',
))


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(name + ' must be a nonempty string')
    return value


def _optional_nonnegative(value: Any, name: str) -> Optional[float]:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(name + ' must be null or a finite nonnegative number')
    return float(value)


def _identifiers(values: Sequence[Any], name: str) -> Tuple[str, ...]:
    result = tuple(_identifier(value, name) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(name + ' values must be unique')
    return result


def condition_feature_schema() -> Mapping[str, Any]:
    return {
        'version': CONDITION_FEATURE_SCHEMA_VERSION,
        'state_feature_order': list(CONDITION_STATE_FEATURE_ORDER),
        'action_feature_order': list(CONDITION_ACTION_FEATURE_ORDER),
        'semantics': 'binary externally supplied observations; no inferred thresholds',
    }


def condition_feature_schema_checksum() -> str:
    payload = json.dumps(condition_feature_schema(), sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    return 'sha256:' + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ImperfectConditionObservation:
    """Raw condition flags and optional source-native measurements."""

    heavy_rain: bool = False
    mist: bool = False
    strong_wind: bool = False
    sensor_outage: bool = False
    communication_delay: bool = False
    rainfall_rate_mm_h: Optional[float] = None
    visibility_m: Optional[float] = None
    wind_speed_mps: Optional[float] = None
    communication_delay_s: Optional[float] = None
    unavailable_sensor_ids: Tuple[str, ...] = ()
    source_ids: Tuple[str, ...] = ()
    synthetic: bool = True

    def __post_init__(self) -> None:
        for name in CONDITION_STATE_FEATURE_ORDER:
            if type(getattr(self, name)) is not bool:
                raise ValueError(name + ' must be boolean')
        if type(self.synthetic) is not bool:
            raise ValueError('synthetic must be boolean')
        for name in ('rainfall_rate_mm_h', 'visibility_m', 'wind_speed_mps',
                     'communication_delay_s'):
            object.__setattr__(self, name, _optional_nonnegative(
                getattr(self, name), name))
        object.__setattr__(self, 'unavailable_sensor_ids', _identifiers(
            self.unavailable_sensor_ids, 'unavailable_sensor_ids'))
        object.__setattr__(self, 'source_ids', _identifiers(
            self.source_ids, 'source_ids'))
        if self.sensor_outage != bool(self.unavailable_sensor_ids):
            raise ValueError(
                'sensor_outage must agree with unavailable_sensor_ids')
        if self.communication_delay_s is not None and not self.communication_delay:
            raise ValueError(
                'communication_delay_s requires communication_delay=true')

    def feature_vector(self) -> Tuple[float, ...]:
        return tuple(float(getattr(self, name))
                     for name in CONDITION_STATE_FEATURE_ORDER)

    def as_dict(self) -> Mapping[str, Any]:
        return {
            'heavy_rain': self.heavy_rain,
            'mist': self.mist,
            'strong_wind': self.strong_wind,
            'sensor_outage': self.sensor_outage,
            'communication_delay': self.communication_delay,
            'rainfall_rate_mm_h': self.rainfall_rate_mm_h,
            'visibility_m': self.visibility_m,
            'wind_speed_mps': self.wind_speed_mps,
            'communication_delay_s': self.communication_delay_s,
            'unavailable_sensor_ids': list(self.unavailable_sensor_ids),
            'source_ids': list(self.source_ids),
            'synthetic': self.synthetic,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> 'ImperfectConditionObservation':
        expected = {
            'heavy_rain', 'mist', 'strong_wind', 'sensor_outage',
            'communication_delay', 'rainfall_rate_mm_h', 'visibility_m',
            'wind_speed_mps', 'communication_delay_s',
            'unavailable_sensor_ids', 'source_ids', 'synthetic',
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError('condition observation fields do not match the contract')
        return cls(
            heavy_rain=value['heavy_rain'], mist=value['mist'],
            strong_wind=value['strong_wind'], sensor_outage=value['sensor_outage'],
            communication_delay=value['communication_delay'],
            rainfall_rate_mm_h=value['rainfall_rate_mm_h'],
            visibility_m=value['visibility_m'],
            wind_speed_mps=value['wind_speed_mps'],
            communication_delay_s=value['communication_delay_s'],
            unavailable_sensor_ids=tuple(value['unavailable_sensor_ids']),
            source_ids=tuple(value['source_ids']), synthetic=value['synthetic'])


@dataclass(frozen=True)
class CandidateCondition:
    """Condition feature attached to one currently valid imitation action."""

    action_index: int
    candidate_id: str
    building_path_intersection: bool
    intersected_building_ids: Tuple[str, ...] = ()
    source_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.action_index) is not int or self.action_index < 0:
            raise ValueError('action_index must be a nonnegative integer')
        _identifier(self.candidate_id, 'candidate_id')
        if type(self.building_path_intersection) is not bool:
            raise ValueError('building_path_intersection must be boolean')
        object.__setattr__(self, 'intersected_building_ids', _identifiers(
            self.intersected_building_ids, 'intersected_building_ids'))
        object.__setattr__(self, 'source_ids', _identifiers(
            self.source_ids, 'source_ids'))
        if self.building_path_intersection != bool(self.intersected_building_ids):
            raise ValueError(
                'building_path_intersection must agree with intersected_building_ids')

    def feature_vector(self) -> Tuple[float, ...]:
        return (float(self.building_path_intersection),)

    def as_dict(self) -> Mapping[str, Any]:
        return {
            'action_index': self.action_index,
            'candidate_id': self.candidate_id,
            'building_path_intersection': self.building_path_intersection,
            'intersected_building_ids': list(self.intersected_building_ids),
            'source_ids': list(self.source_ids),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> 'CandidateCondition':
        expected = {
            'action_index', 'candidate_id', 'building_path_intersection',
            'intersected_building_ids', 'source_ids',
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError('candidate condition fields do not match the contract')
        return cls(
            value['action_index'], value['candidate_id'],
            value['building_path_intersection'],
            tuple(value['intersected_building_ids']), tuple(value['source_ids']))


@dataclass(frozen=True)
class ExpertConditionLabel:
    """Expert action set and factual reason codes for one decision."""

    selected_action_index: int
    acceptable_action_indices: Tuple[int, ...]
    explanation_codes: Tuple[str, ...]
    replanning_margin_delta_s: Optional[float] = None

    def __post_init__(self) -> None:
        if type(self.selected_action_index) is not int or self.selected_action_index < 0:
            raise ValueError('selected_action_index must be a nonnegative integer')
        if (not self.acceptable_action_indices
                or any(type(value) is not int or value < 0
                       for value in self.acceptable_action_indices)):
            raise ValueError('acceptable_action_indices must contain nonnegative integers')
        if len(set(self.acceptable_action_indices)) != len(self.acceptable_action_indices):
            raise ValueError('acceptable_action_indices must be unique')
        if self.selected_action_index not in self.acceptable_action_indices:
            raise ValueError('selected action must be in the acceptable action set')
        if (not self.explanation_codes
                or any(code not in EXPLANATION_CODES for code in self.explanation_codes)):
            raise ValueError('explanation_codes contain an unsupported value')
        if len(set(self.explanation_codes)) != len(self.explanation_codes):
            raise ValueError('explanation_codes must be unique')
        object.__setattr__(self, 'replanning_margin_delta_s', _optional_nonnegative(
            self.replanning_margin_delta_s, 'replanning_margin_delta_s'))

    def as_dict(self) -> Mapping[str, Any]:
        return {
            'selected_action_index': self.selected_action_index,
            'acceptable_action_indices': list(self.acceptable_action_indices),
            'explanation_codes': list(self.explanation_codes),
            'replanning_margin_delta_s': self.replanning_margin_delta_s,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> 'ExpertConditionLabel':
        expected = {
            'selected_action_index', 'acceptable_action_indices',
            'explanation_codes', 'replanning_margin_delta_s',
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError('expert label fields do not match the contract')
        return cls(
            value['selected_action_index'], tuple(value['acceptable_action_indices']),
            tuple(value['explanation_codes']), value['replanning_margin_delta_s'])


@dataclass(frozen=True)
class ConditionedDemonstration:
    """Joinable sidecar for one decision in an imitation demonstration."""

    episode_id: str
    decision_index: int
    conditions: ImperfectConditionObservation
    candidates: Tuple[CandidateCondition, ...]
    expert_label: ExpertConditionLabel
    source_ids: Tuple[str, ...]
    schema_version: str = IMPERFECT_CONDITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != IMPERFECT_CONDITION_SCHEMA_VERSION:
            raise ValueError('unsupported imperfect-condition schema')
        _identifier(self.episode_id, 'episode_id')
        if type(self.decision_index) is not int or self.decision_index < 0:
            raise ValueError('decision_index must be a nonnegative integer')
        if not isinstance(self.conditions, ImperfectConditionObservation):
            raise ValueError('conditions must be ImperfectConditionObservation')
        object.__setattr__(self, 'candidates', tuple(self.candidates))
        if any(not isinstance(row, CandidateCondition) for row in self.candidates):
            raise ValueError('candidates must contain CandidateCondition values')
        actions = [row.action_index for row in self.candidates]
        if len(actions) != len(set(actions)):
            raise ValueError('candidate action indices must be unique')
        if not isinstance(self.expert_label, ExpertConditionLabel):
            raise ValueError('expert_label must be ExpertConditionLabel')
        object.__setattr__(self, 'source_ids', _identifiers(
            self.source_ids, 'source_ids'))
        nested_sources = set(self.conditions.source_ids)
        for row in self.candidates:
            nested_sources.update(row.source_ids)
        missing_sources = nested_sources.difference(self.source_ids)
        if missing_sources:
            raise ValueError(
                'nested source IDs are missing from top-level source_ids: '
                + ', '.join(sorted(missing_sources)))
        blocked_actions = {
            row.action_index for row in self.candidates
            if row.building_path_intersection
        }
        if blocked_actions.intersection(self.expert_label.acceptable_action_indices):
            raise ValueError(
                'building-intersecting candidates cannot be acceptable expert actions')
        self._validate_explanations()

    def _validate_explanations(self) -> None:
        codes = set(self.expert_label.explanation_codes)
        required_flags = {
            'rain_preserved_replanning_margin': self.conditions.heavy_rain,
            'mist_widened_track_uncertainty': self.conditions.mist,
            'wind_widened_path_uncertainty': self.conditions.strong_wind,
            'sensor_outage_reduced_coverage': self.conditions.sensor_outage,
            'communication_delay_preserved_margin': self.conditions.communication_delay,
        }
        for code, active in required_flags.items():
            if code in codes and not active:
                raise ValueError(code + ' requires its observed condition')
        if ('building_path_excluded' in codes
                and not any(row.building_path_intersection for row in self.candidates)):
            raise ValueError('building_path_excluded requires an intersecting candidate')
        if ({'rain_preserved_replanning_margin',
             'communication_delay_preserved_margin'} & codes
                and self.expert_label.replanning_margin_delta_s is None):
            raise ValueError('margin explanation requires replanning_margin_delta_s')

    def as_dict(self) -> Mapping[str, Any]:
        return {
            'schema_version': self.schema_version,
            'episode_id': self.episode_id,
            'decision_index': self.decision_index,
            'conditions': self.conditions.as_dict(),
            'candidates': [row.as_dict() for row in self.candidates],
            'expert_label': self.expert_label.as_dict(),
            'source_ids': list(self.source_ids),
            'feature_schema': condition_feature_schema(),
            'feature_schema_checksum': condition_feature_schema_checksum(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> 'ConditionedDemonstration':
        expected = {
            'schema_version', 'episode_id', 'decision_index', 'conditions',
            'candidates', 'expert_label', 'source_ids', 'feature_schema',
            'feature_schema_checksum',
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError('conditioned demonstration fields do not match the contract')
        if (value['feature_schema'] != condition_feature_schema()
                or value['feature_schema_checksum']
                != condition_feature_schema_checksum()):
            raise ValueError('condition feature schema identity mismatch')
        return cls(
            episode_id=value['episode_id'], decision_index=value['decision_index'],
            conditions=ImperfectConditionObservation.from_dict(value['conditions']),
            candidates=tuple(CandidateCondition.from_dict(row)
                             for row in value['candidates']),
            expert_label=ExpertConditionLabel.from_dict(value['expert_label']),
            source_ids=tuple(value['source_ids']),
            schema_version=value['schema_version'])


def explanation_lines(record: ConditionedDemonstration) -> Tuple[str, ...]:
    """Render factual demo wording from validated condition evidence."""
    codes = set(record.expert_label.explanation_codes)
    lines = []
    margin = record.expert_label.replanning_margin_delta_s
    if 'rain_preserved_replanning_margin' in codes:
        lines.append(
            'Heavy rain reduced tracking clarity; the expert demonstration '
            f'preserved {margin:.1f} seconds of additional replanning margin.')
    if 'mist_widened_track_uncertainty' in codes:
        lines.append(
            'Mist reduced visibility, so the demonstration used a wider '
            'trajectory-uncertainty range.')
    if 'wind_widened_path_uncertainty' in codes:
        lines.append(
            'Strong wind widened the simulated path range; the demonstrated '
            'action remained acceptable across the tested variations.')
    if 'building_path_excluded' in codes:
        count = sum(row.building_path_intersection for row in record.candidates)
        lines.append(
            f'{count} candidate path{" was" if count == 1 else "s were"} '
            'excluded because the modelled corridor intersected mapped buildings.')
    if 'sensor_outage_reduced_coverage' in codes:
        count = len(record.conditions.unavailable_sensor_ids)
        lines.append(
            f'{count} sensor{" was" if count == 1 else "s were"} unavailable; '
            'the demonstration relied on the remaining observations and wider uncertainty.')
    if 'communication_delay_preserved_margin' in codes:
        lines.append(
            'Communication delay was present; the expert demonstration '
            f'preserved {margin:.1f} seconds of additional decision margin.')
    if 'insufficient_confidence' in codes:
        lines.append(
            'The supplied observations did not support a sufficiently confident '
            'candidate recommendation in this synthetic case.')
    return tuple(lines)
