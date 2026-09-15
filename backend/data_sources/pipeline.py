"""Prepare versioned display and partial PEC-candidate datasets from cached sources."""
from __future__ import annotations

import json
import platform
from collections import Counter
from pathlib import Path
import pyproj
import shapely
from shapely import to_wkt
from .acquisition import atomic_write, checksum, verify_cache
from .geography import area_density, prepare_geometry, PROJECTED_CRS
from .population import ALIASES, load_population, normalise_name, parse_hierarchy, join_boundaries

TRANSFORMATION_VERSION = 'population-preparation/1.0.0'
SETTINGS = dict(projected_crs=PROJECTED_CRS, always_xy=True, geometry_repair='none',
                display_simplification='none', overlap_tolerance_m2=0,
                name_normalisation='NFC, whitespace collapse, uppercase; punctuation preserved',
                aliases=ALIASES, population_column='Total_Total',
                qualified_values='nullable; never infer zero', area_denominator='supplied zone geometry area')


def encode(value, pretty=False):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2 if pretty else None,
                       separators=None if pretty else (',', ':'), allow_nan=False) + '\n').encode()


def prepare(raw: Path, output: Path, public: Path):
    manifest = verify_cache(raw)
    rows = load_population(raw / manifest['sources']['population']['file'])
    collection = json.loads((raw / manifest['sources']['boundaries']['file']).read_bytes())
    zones, aggregates = parse_hierarchy(rows)
    matches, joins = join_boundaries(zones, collection['features'])
    geometries, issues, overlapping, geography = prepare_geometry(collection)
    substantive = dict(transformation_version=TRANSFORMATION_VERSION, settings=SETTINGS,
                       source_checksums={k: v['sha256'] for k, v in manifest['sources'].items()},
                       libraries=dict(shapely=shapely.__version__, geos=shapely.geos_version_string,
                                      pyproj=pyproj.__version__, proj=pyproj.proj_version_str))
    version = 'sg-residents-2020-mp2019-' + checksum(encode(substantive))[:16]
    metadata = dict(dataset_version=version, population_year=2020, boundary_vintage=2019,
                    title='Singapore Resident Population — Census 2020',
                    population_source_published='2021-06-18', boundary_source_period='2021-09',
                    source_dates_note='Source release/portal dates are separate from Census 2020 and Master Plan 2019',
                    sources=manifest['sources'], retrieved_at=manifest['retrieved_at'],
                    retrieval_meaning=manifest['retrieval_meaning'], **substantive)
    display, candidates, excluded = [], [], []
    for index, (feature, (population_row, match_status), geometry) in enumerate(zip(collection['features'], matches, geometries)):
        source = feature['properties']
        population = population_row['population'] if population_row else None
        status = population_row['population_status'] if population_row else match_status
        reasons = list(issues[index])
        if match_status != 'matched':
            reasons.append('join_' + match_status)
        if population is None:
            reasons.append('population_' + status)
        if index in overlapping:
            reasons.append('positive_area_overlap')
        area, density = (None, None)
        if geometry is not None and not issues[index]:
            area, density = area_density(geometry, population)
        id = source['SUBZONE_C']
        properties = dict(zone_id=id, planning_area=source['PLN_AREA_N'], subzone=source['SUBZONE_N'],
                          planning_area_code=source['PLN_AREA_C'],
                          planning_area_normalised=normalise_name(source['PLN_AREA_N']), subzone_normalised=normalise_name(source['SUBZONE_N']),
                          population_planning_area_original=population_row['planning_area'] if population_row else None,
                          population_subzone_original=population_row['subzone'] if population_row else None,
                          population=population, population_status=status,
                          population_raw=population_row['population_raw'] if population_row else None,
                          population_source_row=population_row['source_row'] if population_row else None,
                          join_status=match_status, geometry_status='invalid' if issues[index] else 'valid',
                          zone_area_m2=area, population_density_people_per_m2=density,
                          pec_eligible=not reasons, exclusion_reasons=reasons,
                          outside_viewer_bounds=id in geography['outside_viewer_bounds'],
                          source_references=dict(population_dataset_id=manifest['sources']['population']['dataset_id'],
                                                 boundary_dataset_id=manifest['sources']['boundaries']['dataset_id'],
                                                 boundary_objectid=source.get('OBJECTID')),
                          dataset_version=version)
        # Preserve exactly the input geometry coordinates; no clipping/simplification.
        display.append(dict(type='Feature', id=id, properties=properties, geometry=feature['geometry']))
        if not reasons:
            candidates.append(dict(**properties, geometry_wkt=to_wkt(geometry, rounding_precision=-1, trim=True)))
        else:
            excluded.append(dict(zone_id=id, reasons=reasons))
    candidates.sort(key=lambda x: x['zone_id'])
    display.sort(key=lambda x: (x['properties']['zone_id'], x['properties']['source_references']['boundary_objectid'] or 0))
    known_total = sum(f['properties']['population'] or 0 for f in display)
    national = next(a for a in aggregates if a['level'] == 'national')
    reconciliations = []
    for aggregate in aggregates:
        if aggregate['level'] != 'planning_area':
            continue
        area_zones = [z for z in zones if normalise_name(z['planning_area']) == normalise_name(aggregate['planning_area'])]
        known = sum(z['population'] or 0 for z in area_zones)
        reconciliations.append(dict(planning_area=aggregate['planning_area'], published=aggregate['population'],
                                    published_raw=aggregate['population_raw'], known_subzone_sum=known,
                                    difference=None if aggregate['population'] is None else known - aggregate['population'],
                                    unknown_subzones=sum(z['population'] is None for z in area_zones)))
    statuses = Counter(f['properties']['population_status'] for f in display)
    counts = dict(raw_population_rows=len(rows), raw_boundary_features=len(collection['features']),
                  national_rows=sum(a['level'] == 'national' for a in aggregates),
                  planning_area_rows=len(aggregates)-1, population_subzone_rows=len(zones),
                  display_zones=len(display), matched=sum(s == 'matched' for _, s in matches),
                  unmatched_population=len(joins['unmatched_population']), unmatched_boundaries=len(joins['unmatched_boundaries']),
                  duplicate_population_keys=len(joins['duplicate_population_keys']), duplicate_boundary_keys=len(joins['duplicate_boundary_keys']),
                  duplicate_zone_ids=len(joins['duplicate_zone_ids']), ambiguous_boundaries=len(joins['ambiguous_boundaries']),
                  unknown_population=sum(f['properties']['population'] is None for f in display),
                  invalid_population=statuses.get('invalid', 0), invalid_geometry=len(geography['invalid']),
                  overlapping_zones=len(overlapping), overlap_pairs=len(geography['overlaps']),
                  excluded=len(excluded), eligible=len(candidates), population_statuses=dict(statuses))
    limitations = [
        'Historical resident population (citizens and permanent residents), not everyone physically present or live crowd levels.',
        'SingStat notes that rounded counts may not add to totals; no values are adjusted to reconcile.',
        "Source '-' means nil or negligible or not significant; treated as qualified unknown, not numeric zero. No suppressed numeric values are invented.",
        'Density is an average over supplied zone geometry, including any water in that geometry; no independent water mask was applied.',
        'Invalid geometry and both participants in every positive-area overlap are excluded without repair; full-resolution source geometry remains in the display artifact.',
        'The existing city/coastline tiles omit some offshore geometry. Population polygons are independent of that clipping; all boundary extents fit the current camera bounds.',
        'PEC-candidate coverage is partial, not a claim that the whole dataset is PEC-ready; downstream consumers must respect exclusions and nullable population.']
    report = dict(dataset_version=version, status='partial_coverage' if excluded or any(joins.values()) else 'validated', counts=counts,
                  source_completeness=manifest['completeness'], joins=joins, geography=geography,
                  excluded=excluded, aggregates=aggregates, planning_area_reconciliation=reconciliations,
                  totals=dict(known_display_population=known_total, eligible_population=sum(z['population'] for z in candidates),
                              published_national=national['population'], difference_from_national=known_total-national['population'] if national['population'] is not None else None,
                              known_planning_area_sum=sum(a['population'] or 0 for a in aggregates if a['level']=='planning_area'),
                              eligible_zone_area_m2=sum(z['zone_area_m2'] for z in candidates)),
                  limitations=limitations)
    metadata['coverage'] = dict(status=report['status'], counts=counts, totals=report['totals'])
    geographic = dict(type='FeatureCollection', metadata=metadata, features=display)
    projected = dict(format='population-zones-wkt/1', crs=PROJECTED_CRS, axis_order=['easting', 'northing'], units='metre',
                     metadata=metadata, coverage_status=report['status'], zones=candidates)
    # Compute everything successfully before publishing individual files atomically.
    outputs = {'population-display.geojson': encode(geographic), 'population-projected.json': encode(projected),
               'validation-report.json': encode(report, True), 'provenance.json': encode(dict(metadata, runtime_python=platform.python_version()), True)}
    for name, content in outputs.items():
        atomic_write(output / name, content)
    atomic_write(public, outputs['population-display.geojson'])
    lines = ['# Population validation summary', '', f'Dataset: `{version}`. Status: **{report["status"]}**.', '',
             f'{len(rows)} population rows: 1 national total, {len(aggregates)-1} planning-area totals, {len(zones)} subzones.',
             f'{len(display)} display zones; {counts["matched"]} matched; {counts["unknown_population"]} unknown population; {len(candidates)} eligible; {len(excluded)} excluded.',
             f'{counts["invalid_geometry"]} invalid geometries; {counts["overlap_pairs"]} overlap pairs affecting {counts["overlapping_zones"]} zones. No repairs.',
             f'Known displayed population: {known_total:,}; national published total: {national["population"]:,}; difference: {report["totals"]["difference_from_national"]:+,}.',
             f'Eligible population: {report["totals"]["eligible_population"]:,}.', '',
             'See [machine-readable report](validation-report.json) for every exclusion, join result and aggregate source row; [provenance](provenance.json) records checksums and settings.', '',
             '| Planning area | Published | Known subzone sum | Difference | Unknown zones |', '|---|---:|---:|---:|---:|']
    for r in reconciliations:
        lines.append(f'| {r["planning_area"]} | {r["published_raw"]} | {r["known_subzone_sum"]} | {r["difference"] if r["difference"] is not None else "unknown"} | {r["unknown_subzones"]} |')
    lines += ['', *['- '+note for note in limitations], '']
    atomic_write(output / 'validation-summary.md', '\n'.join(lines).encode())
    return report
