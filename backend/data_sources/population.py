"""Source-specific Census 2020 hierarchy and value parsing. No exposure logic."""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

POPULATION_ID = 'd_d95ae740c0f8961a0b10435836660ce0'
BOUNDARY_ID = 'd_8594ae9ff96d0c708bc2af633048edfb'
EXPECTED_POPULATION_ROWS = 388  # Official Census 2020 dataset page, inspected 2026-09-14.
EXPECTED_BOUNDARIES = 332  # Complete official MP2019 download, inspected 2026-09-14.
ALIASES = {}  # No fuzzy matching or aliases required by the inspected sources.


def normalise_name(value: str) -> str:
    """Unicode NFC, trim/collapse whitespace, uppercase; retain punctuation."""
    return ' '.join(unicodedata.normalize('NFC', value).split()).upper()


def parse_value(raw):
    if raw is None or str(raw).strip() == '':
        return None, 'missing'
    value = str(raw).strip()
    if value == '-':
        return None, 'qualified_nil_or_negligible'
    if value.lower() == 'na':
        return None, 'not_available_or_applicable'
    # Unknown qualification tokens must never become numbers, including zero.
    if value in ('..', '...', '*', 'c', 'C'):
        return None, 'qualified_uninterpreted'
    if re.fullmatch(r'\d+|\d{1,3}(?:,\d{3})+', value):
        number = int(value.replace(',', ''))
        return number, 'known_zero' if number == 0 else 'known'
    return None, 'invalid'


def load_population(path: Path):
    if path.suffix.lower() == '.csv':
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        # Official CSV download uses display headers; API uses machine headers.
        for row in rows:
            if 'Total_Total' not in row and '(Total) Total' in row:
                row['Total_Total'] = row['(Total) Total']
        return rows
    doc = json.loads(path.read_bytes())
    result = doc.get('result', {})
    if doc.get('success') is not True or not isinstance(result.get('records'), list):
        raise ValueError('Expected an unmodified successful datastore_search response or official CSV')
    rows = result['records']
    if result.get('resource_id') != POPULATION_ID or result.get('total') != len(rows):
        raise ValueError('Population response is incomplete or belongs to a different dataset')
    ids = [row.get('_id') for row in rows]
    if ids != list(range(1, len(rows) + 1)):
        raise ValueError('Population API rows must retain consecutive source _id order')
    return rows


def parse_hierarchy(rows):
    """Read the ordered Number hierarchy, including the actual 'Changi- Total'."""
    zones, aggregates = [], []
    current_area = None
    seen_areas = set()
    national_seen = False
    for index, row in enumerate(rows, 1):
        if 'Number' not in row or 'Total_Total' not in row:
            raise ValueError(f'Row {index}: missing Number or Total_Total field')
        name = str(row['Number']).strip()
        if not name:
            raise ValueError(f'Row {index}: empty geographic label')
        population, status = parse_value(row['Total_Total'])
        item = dict(source_row=index, source_id=row.get('_id'), source_label=row['Number'],
                    population_raw=row['Total_Total'], population=population, population_status=status)
        heading = re.fullmatch(r'(.+?)\s*-\s*Total', name)
        if name == 'Total':
            if national_seen or index != 1:
                raise ValueError('National total must occur once, first')
            national_seen = True
            aggregates.append(dict(item, level='national', planning_area=None))
        elif heading:
            current_area = heading.group(1).strip()
            key = normalise_name(current_area)
            if key in seen_areas:
                raise ValueError(f'Duplicate planning-area heading: {current_area}')
            seen_areas.add(key)
            aggregates.append(dict(item, level='planning_area', planning_area=current_area))
        else:
            if current_area is None:
                raise ValueError(f'Subzone before planning-area heading: {name}')
            zones.append(dict(item, planning_area=current_area, subzone=name,
                              join_key=(normalise_name(current_area), normalise_name(name))))
    if not national_seen:
        raise ValueError('National total missing')
    return zones, aggregates


def join_boundaries(zones, features):
    """Reject ambiguity in either direction; preserve every boundary for display."""
    population_index, boundary_index, ids = defaultdict(list), defaultdict(list), defaultdict(list)
    for zone in zones:
        population_index[zone['join_key']].append(zone)
    for i, feature in enumerate(features):
        p = feature['properties']
        for field in ('PLN_AREA_N', 'SUBZONE_N', 'PLN_AREA_C', 'SUBZONE_C'):
            if not isinstance(p.get(field), str) or not p[field].strip():
                raise ValueError(f'Boundary {i}: missing {field}')
        key = (normalise_name(p['PLN_AREA_N']), normalise_name(p['SUBZONE_N']))
        boundary_index[key].append(i)
        ids[p['SUBZONE_C']].append(i)
    duplicates_population = [list(k) for k, v in population_index.items() if len(v) > 1]
    duplicates_boundary = [list(k) for k, v in boundary_index.items() if len(v) > 1]
    duplicate_ids = [k for k, v in ids.items() if len(v) > 1]
    matches = []
    for feature in features:
        p = feature['properties']
        key = (normalise_name(p['PLN_AREA_N']), normalise_name(p['SUBZONE_N']))
        candidates = population_index.get(key, [])
        ambiguous = len(candidates) > 1 or len(boundary_index[key]) > 1 or p['SUBZONE_C'] in duplicate_ids
        matches.append((None if ambiguous or not candidates else candidates[0],
                        'ambiguous' if ambiguous else 'matched' if candidates else 'unmatched'))
    report = dict(duplicate_population_keys=duplicates_population, duplicate_boundary_keys=duplicates_boundary,
                  duplicate_zone_ids=duplicate_ids,
                  unmatched_population=[dict(z, join_key=list(z['join_key'])) for z in zones if z['join_key'] not in boundary_index],
                  unmatched_boundaries=[f['properties']['SUBZONE_C'] for f, (_, status) in zip(features, matches) if status == 'unmatched'],
                  ambiguous_boundaries=[f['properties']['SUBZONE_C'] for f, (_, status) in zip(features, matches) if status == 'ambiguous'])
    return matches, report
