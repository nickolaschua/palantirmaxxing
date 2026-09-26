"""Balanced scenario overlays for imperfect-condition imitation data."""
from __future__ import annotations

from itertools import combinations
from typing import Any, Mapping, Sequence, Tuple

from .imperfect_conditions import (
    CONDITION_STATE_FEATURE_ORDER, condition_feature_schema_checksum)


IMPERFECT_CONDITION_MATRIX_VERSION = 'imperfect-condition-matrix/1'
BUILDING_CONDITION = 'building_path_intersection'
CONDITION_ORDER = CONDITION_STATE_FEATURE_ORDER[:3] + (
    BUILDING_CONDITION,) + CONDITION_STATE_FEATURE_ORDER[3:]
CONDITION_EFFECTS = {
    'heavy_rain': 'wider track-observation uncertainty',
    'mist': 'reduced visibility and wider observation uncertainty',
    'strong_wind': 'wider simulated path variation',
    BUILDING_CONDITION: 'hard exclusion for each intersecting candidate action',
    'sensor_outage': 'reduced independent sensor coverage',
    'communication_delay': 'older information at the decision point',
}
SEVERE_COMBINATIONS = (
    ('heavy_rain', 'mist', 'strong_wind'),
    ('heavy_rain', BUILDING_CONDITION, 'sensor_outage'),
    ('heavy_rain', 'mist', 'communication_delay'),
    ('strong_wind', BUILDING_CONDITION, 'sensor_outage'),
    ('strong_wind', BUILDING_CONDITION, 'communication_delay'),
    ('mist', 'sensor_outage', 'communication_delay'),
)


def _row(row_id: str, group: str, active: Sequence[str],
         sampling_weight: int = 1) -> Mapping[str, Any]:
    active_set = set(active)
    return {
        'scenario_id': row_id,
        'group': group,
        'sampling_weight': sampling_weight,
        'active_condition_count': len(active),
        'active_conditions': list(active),
        'state_flags': {
            name: name in active_set for name in CONDITION_STATE_FEATURE_ORDER
        },
        'candidate_setup': {
            BUILDING_CONDITION: BUILDING_CONDITION in active_set,
            'rule': ('at least one candidate action must be marked intersecting'
                     if BUILDING_CONDITION in active_set
                     else 'all candidate actions are marked clear'),
        },
        'expected_observation_effects': [
            CONDITION_EFFECTS[name] for name in active
        ] or ['nominal observations and no mapped building intersection'],
        'expert_label_status': 'unlabelled',
        'required_expert_fields': [
            'acceptable_action_indices',
            'selected_action_index',
            'explanation_codes',
            'replanning_margin_delta_s_when_claimed',
            'simulated_outcome',
        ],
    }


def build_imperfect_condition_matrix() -> Mapping[str, Any]:
    """Return a deterministic balanced overlay matrix for base scenarios."""
    rows = [_row('IC-CONTROL', 'control', (), sampling_weight=6)]
    for index, condition in enumerate(CONDITION_ORDER, 1):
        rows.append(_row('IC-SINGLE-%02d' % index, 'single', (condition,)))
    for index, pair in enumerate(combinations(CONDITION_ORDER, 2), 1):
        rows.append(_row('IC-PAIR-%02d' % index, 'pair', pair))
    for index, active in enumerate(SEVERE_COMBINATIONS, 1):
        rows.append(_row('IC-SEVERE-%02d' % index, 'combined-severe', active))
    rows.append(_row('IC-STRESS-ALL', 'combined-stress', CONDITION_ORDER))

    weighted_slots = sum(row['sampling_weight'] for row in rows)
    incidence = {
        condition: sum(
            row['sampling_weight']
            for row in rows if condition in row['active_conditions'])
        for condition in CONDITION_ORDER
    }
    return {
        'schema_version': IMPERFECT_CONDITION_MATRIX_VERSION,
        'feature_schema_checksum': condition_feature_schema_checksum(),
        'purpose': (
            'simulation-only condition overlays for imitation-learning '
            'demonstration generation'),
        'base_scenario_application': {
            'mode': 'overlay',
            'join_keys': ['base_episode_id', 'base_profile', 'condition_scenario_id'],
            'instruction': (
                'Apply overlays across the existing base scenario families; '
                'do not change their geometry, consequence inputs, or split identity.'),
            'split_rule': (
                'All overlays of one base family remain in the same dataset split.'),
        },
        'sampling_plan': {
            'archetype_count': len(rows),
            'weighted_slot_count': weighted_slots,
            'control_weighted_slots': rows[0]['sampling_weight'],
            'condition_weighted_incidence': incidence,
            'balance_statement': (
                'Each retained condition is active in exactly 10 of 34 weighted slots.'),
        },
        'rows': rows,
    }


def validate_imperfect_condition_matrix(document: Mapping[str, Any]) -> None:
    expected_root = {
        'schema_version', 'feature_schema_checksum', 'purpose',
        'base_scenario_application', 'sampling_plan', 'rows',
    }
    if not isinstance(document, dict) or set(document) != expected_root:
        raise ValueError('imperfect-condition matrix fields do not match the contract')
    if document['schema_version'] != IMPERFECT_CONDITION_MATRIX_VERSION:
        raise ValueError('imperfect-condition matrix schema version mismatch')
    if document['feature_schema_checksum'] != condition_feature_schema_checksum():
        raise ValueError('imperfect-condition matrix feature checksum mismatch')
    rows = document['rows']
    if not isinstance(rows, list) or len(rows) != 29:
        raise ValueError('imperfect-condition matrix must contain 29 archetypes')
    ids = [row.get('scenario_id') for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('imperfect-condition scenario IDs must be unique')
    for row in rows:
        if (set(row.get('state_flags', ())) != set(CONDITION_STATE_FEATURE_ORDER)
                or set(row.get('active_conditions', ())).difference(CONDITION_ORDER)):
            raise ValueError('scenario condition fields are invalid')
        active = set(row['active_conditions'])
        for name in CONDITION_STATE_FEATURE_ORDER:
            if row['state_flags'][name] != (name in active):
                raise ValueError('scenario state flag disagrees with active conditions')
        if (row['candidate_setup'].get(BUILDING_CONDITION)
                != (BUILDING_CONDITION in active)):
            raise ValueError('candidate building flag disagrees with active conditions')
        if row.get('expert_label_status') != 'unlabelled':
            raise ValueError('condition matrix must not contain invented expert labels')
    pairs = {
        tuple(row['active_conditions']) for row in rows if row['group'] == 'pair'
    }
    if pairs != set(combinations(CONDITION_ORDER, 2)):
        raise ValueError('condition matrix does not contain every pair')
    weighted_slots = sum(row['sampling_weight'] for row in rows)
    incidence = {
        condition: sum(row['sampling_weight'] for row in rows
                       if condition in row['active_conditions'])
        for condition in CONDITION_ORDER
    }
    if weighted_slots != 34 or set(incidence.values()) != {10}:
        raise ValueError('condition matrix is not balanced as declared')
    plan = document['sampling_plan']
    if (plan.get('archetype_count') != 29
            or plan.get('weighted_slot_count') != weighted_slots
            or plan.get('condition_weighted_incidence') != incidence):
        raise ValueError('condition matrix summary does not match its rows')
