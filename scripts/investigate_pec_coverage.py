#!/usr/bin/env python3
"""Reproduce the original PEC boundary finding; diagnostic resolutions only.

Writes generated artifacts under data/results. Production settings, geometry,
coverage semantics and the original benchmark artifact are never modified.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.exposure import prepare_population, calculate_episode, CalculationSettings
from backend.exposure.calculator import footprint
from scripts.population_exposure import load_json, write_json
from shapely.geometry import shape, Point, box
from shapely.ops import transform, nearest_points, unary_union
from shapely.affinity import translate
from pyproj import Transformer


@dataclass(frozen=True)
class InvestigationSettings:
    """Private diagnostic duck type; does not expand public CalculationSettings."""
    circle_edges: int
    coverage_area_tolerance_m2: float = 1e-6

    def __post_init__(self):
        if type(self.circle_edges) is not int or self.circle_edges not in (64,128,256,512,1024,2048,4096,8192,16384):
            raise ValueError('Unsupported diagnostic resolution')
        if self.coverage_area_tolerance_m2 != 1e-6:
            raise ValueError('Do not change the production coverage tolerance')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_episode(dataset):
    # Exact recipe in benchmark_exposure.py; its unchanged file SHA is recorded.
    events = []
    for i in range(100):
        point = dataset.geometries[i * len(dataset.zones) // 100].representative_point()
        events.append(dict(event_id=f'event-{i:03d}', footprint_id=f'footprint-{i:03d}',
                           center_x_m=point.x, center_y_m=point.y, radius_m=[250,750,1500,2500][i % 4]))
    return dict(schema_version='pec-episode/1', episode_id='pec-benchmark-100',
                population_dataset_id=dataset.dataset_id, population_dataset_version=dataset.version,
                coordinate_reference_system='EPSG:3414', events=events)


def timed(dataset, episode, settings):
    times, last = [], None
    for _ in range(3):
        start = time.perf_counter()
        result = calculate_episode(dataset, episode, settings)
        times.append(time.perf_counter() - start)
        assert result['status'] != 'invalid_input', result
        assert last is None or last == result, 'Nondeterministic repeated result'
        last = result
    return last, dict(seconds=times, median_seconds=statistics.median(times))


def changes(rows, fields):
    for previous, row in zip(rows, rows[1:]):
        row['changes_from_previous_resolution'] = {
            field: dict(absolute=row[field] - previous[field],
                        relative=None if previous[field] == 0 else (row[field]-previous[field])/previous[field])
            for field in fields}


def audit_exclusions(raw, report, display):
    excluded = {x['zone_id']: x['reasons'] for x in report['excluded']}
    features = {f['properties']['zone_id']: f['properties'] for f in display['features']}
    eligible = {z['zone_id'] for z in raw['zones']}
    assert len(excluded) == len(report['excluded']) == report['counts']['excluded']
    assert len(features) == len(display['features']) == report['counts']['display_zones']
    assert len(eligible) == len(raw['zones']) == report['counts']['eligible']
    assert set(excluded).isdisjoint(eligible) and set(excluded) | eligible == set(features)
    categories, combinations, rows = Counter(), Counter(), []
    for zid, reasons in sorted(excluded.items()):
        p = features[zid]
        assert reasons and reasons == p['exclusion_reasons'] and p['pec_eligible'] is False
        kinds = set()
        for reason in reasons:
            if reason.startswith(('source:', 'projected:')):
                kinds.add('invalid_geometry')
            elif reason == 'population_qualified_nil_or_negligible':
                kinds.add('unknown_population')
            elif reason == 'positive_area_overlap':
                kinds.add('positive_area_overlap')
            else:
                raise AssertionError('Unaccounted exclusion reason: ' + reason)
        categories.update(kinds)
        combinations.update([' + '.join(sorted(kinds))])
        rows.append(dict(zone_id=zid, subzone=p['subzone'], categories=sorted(kinds), reasons=reasons))
    assert categories['unknown_population'] == report['counts']['unknown_population']
    assert categories['invalid_geometry'] == report['counts']['invalid_geometry']
    assert categories['positive_area_overlap'] == report['counts']['overlapping_zones']
    for zid in eligible:
        assert features[zid]['pec_eligible'] is True and features[zid]['exclusion_reasons'] == []
    return dict(all_exclusions_accounted_for=True, display_zones=len(features), eligible_zones=len(eligible),
                unique_excluded_zones=len(excluded), category_counts=dict(categories),
                disjoint_category_combinations=dict(combinations), zones=rows)


def draw_figure(path, dataset, excluded_geometry, circles, event, vertex):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch, Patch
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator
    from shapely.geometry.polygon import orient

    def fill(ax, geometry, color, alpha=1):
        if geometry.is_empty:
            return
        if geometry.geom_type in ('MultiPolygon', 'GeometryCollection'):
            for g in geometry.geoms: fill(ax, g, color, alpha)
        elif geometry.geom_type == 'Polygon':
            vertices, codes = [], []
            geometry = orient(geometry)
            for ring in [geometry.exterior, *geometry.interiors]:
                coords = list(ring.coords)
                vertices.extend(coords)
                codes.extend([MPath.MOVETO] + [MPath.LINETO]*(len(coords)-2) + [MPath.CLOSEPOLY])
            ax.add_patch(PathPatch(MPath(vertices,codes), facecolor=color, edgecolor='none', alpha=alpha))

    fig, axes = plt.subplots(1, 2, figsize=(12,5.9))
    colors = {128:'#135bb5',256:'#d47600',1024:'#812bb2'}
    views = [(event['center_x_m']-1700,event['center_y_m']-1700,event['center_x_m']+1700,event['center_y_m']+1700),
             (vertex.x-.32,vertex.y-.40,vertex.x+.54,vertex.y+.46)]
    for ax, bounds in zip(axes, views):
        crop = box(*bounds)
        fill(ax,dataset.coverage.intersection(crop),'#c9e3d4')
        fill(ax,excluded_geometry.intersection(crop),'#eeeeee')
        fill(ax,circles[1024].difference(dataset.coverage).intersection(crop),'#e44c4c')
        for n,color in colors.items():
            xs,ys = circles[n].exterior.xy
            ax.plot(xs,ys,color=color,lw=1.5,linestyle='--' if n==128 else '-',label=str(n))
        for geometry in (dataset.coverage.intersection(crop), excluded_geometry.intersection(crop)):
            boundary=geometry.boundary
            pieces=list(boundary.geoms) if hasattr(boundary,'geoms') else [boundary]
            for line in pieces:
                if hasattr(line,'xy'):
                    ax.plot(*line.xy,color='#476254',lw=.65)
        ax.set(xlim=(bounds[0],bounds[2]),ylim=(bounds[1],bounds[3]),xlabel='Easting (m)',ylabel='Northing (m)')
        ax.set_aspect('equal'); ax.ticklabel_format(style='plain',useOffset=False)
        ax.tick_params(labelsize=8); ax.grid(alpha=.15)
    axes[0].plot(vertex.x,vertex.y,'o',ms=7,mfc='none',mec='#ba2525')
    axes[0].annotate('Bidadari corner → close-up',xy=(vertex.x,vertex.y),xytext=(event['center_x_m']-600,event['center_y_m']+1400),
                     arrowprops=dict(arrowstyle='->',color='#ba2525'),fontsize=9)
    axes[0].plot(event['center_x_m'],event['center_y_m'],'k+',ms=7)
    axes[0].set_title('Full footprint • radius 1,500 m')
    axes[1].plot(vertex.x,vertex.y,'ko',ms=3)
    axes[1].annotate('Coverage vertex',xy=(vertex.x,vertex.y),xytext=(vertex.x-.27,vertex.y-.28),
                     arrowprops=dict(arrowstyle='->'),fontsize=8)
    axes[1].text(vertex.x+.17,vertex.y+.34,'TPSZ10: excluded\nqualified unknown population',fontsize=8,ha='center')
    axes[1].set_title('Sub-metre close-up • no geometry repair')
    axes[1].xaxis.set_major_locator(MaxNLocator(4))
    axes[1].text(vertex.x-.23,vertex.y+.31,'Woodleigh\nTPSZ08',fontsize=8)
    axes[1].text(vertex.x+.25,vertex.y-.30,'Sennett • TPSZ11',fontsize=8)
    legend=[Patch(facecolor='#c9e3d4',label='Eligible coverage'),Patch(facecolor='#eeeeee',label='Excluded Bidadari'),
            Patch(facecolor='#e44c4c',label='Uncovered at 1024 edges')]
    legend += [Line2D([0],[0],color=c,lw=1.5,linestyle='--' if n==128 else '-',label=f'{n} edges') for n,c in colors.items()]
    fig.legend(handles=legend,loc='lower center',ncol=3,fontsize=9,bbox_to_anchor=(.5,.015))
    fig.suptitle('PEC event-090 • EPSG:3414 • inscribed-circle coverage sensitivity',fontsize=13)
    fig.subplots_adjust(bottom=.23,top=.86,wspace=.34,left=.08,right=.98)
    fig.savefig(path.with_suffix('.png'),dpi=170)
    fig.savefig(path.with_suffix('.svg'))
    plt.close(fig)


def main():
    inputs = ['data/processed/population-projected.json','data/processed/validation-report.json',
              'data/processed/provenance.json','data/processed/population-display.geojson',
              'data/raw/boundaries.geojson','data/results/pec-benchmark.json',
              'scripts/benchmark_exposure.py','backend/exposure/calculator.py',
              'backend/exposure/dataset.py','backend/exposure/validation.py']
    references = {p:sha(ROOT/p) for p in inputs}
    raw, report, provenance, display, source, baseline = [load_json(ROOT/p) for p in inputs[:6]]
    assert sha(ROOT/'data/raw/boundaries.geojson') == provenance['source_checksums']['boundaries']
    dataset = prepare_population(raw)
    assert dataset.checksum == baseline['dataset_checksum_sha256']
    assert dataset.version == report['dataset_version'] == provenance['dataset_version'] == baseline['dataset_version']
    episode = original_episode(dataset)
    out = ROOT/'data/results'
    write_json(out/'pec-coverage-episode.json',episode)
    event = next(e for e in episode['events'] if e['event_id']=='event-090')
    single = dict(episode,events=[event])
    event_rows, episode_rows, geometries, complete_results, runtimes = [], [], {}, {}, {}
    for n in (64,128,256,512,1024):
        settings = InvestigationSettings(n)
        result, episode_time = timed(dataset,episode,settings)
        single_result, event_time = timed(dataset,single,settings)
        e = next(e for e in result['events'] if e['event_id']==event['event_id'])
        assert e == single_result['events'][0]
        geometries[n] = footprint(event,settings)
        if n in (128,256):
            assert result == calculate_episode(dataset,episode,CalculationSettings(n))
        complete_results[n] = result
        row = dict(edges=n, **{k:e[k] for k in ('footprint_area_m2','uncovered_area_m2','covered_area_fraction',
                                                'status','known_area_exposure','people_potentially_exposed')},
                   ideal_circle_area_m2=math.pi*event['radius_m']**2,
                   ideal_area_deficit_m2=math.pi*event['radius_m']**2-e['footprint_area_m2'],
                   ideal_area_relative_deficit=(math.pi*event['radius_m']**2-e['footprint_area_m2'])/(math.pi*event['radius_m']**2),
                   coverage_tolerance_m2=settings.coverage_area_tolerance_m2,
                   actual_edge_count=len(geometries[n].exterior.coords)-1,
                   clockwise=not geometries[n].exterior.is_ccw,
                   first_vertex=list(geometries[n].exterior.coords)[0])
        event_rows.append(row)
        episode_rows.append(dict(edges=n,**{k:result[k] for k in ('status','uncovered_area_m2','known_area_unique_exposure',
                            'known_area_person_exposures','known_area_multiple_exposure','unique_people_potentially_exposed',
                            'total_person_exposures','people_exposed_to_multiple_events')},
                            event_status_counts=dict(Counter(e['status'] for e in result['events']))))
        runtimes[str(n)]=dict(single_event_episode=event_time,full_episode=episode_time)
    for field, expected in baseline['sensitivity'].items():
        assert complete_results[128][field] == expected['edges_128']
        assert complete_results[256][field] == expected['edges_256']
    changed=[a['event_id'] for a,b in zip(complete_results[128]['events'],complete_results[256]['events']) if a['status'] != b['status']]
    assert changed == [x['event_id'] for x in baseline['changed_events']]
    changes(event_rows,['footprint_area_m2','uncovered_area_m2','known_area_exposure'])
    changes(episode_rows,['uncovered_area_m2','known_area_unique_exposure','known_area_person_exposures','known_area_multiple_exposure'])
    audit=audit_exclusions(raw,report,display)
    projector=Transformer.from_crs('EPSG:4326','EPSG:3414',always_xy=True,allow_ballpark=False)
    source_geometries={f['properties']['SUBZONE_C']:f['geometry'] for f in source['features']}
    projected={}
    properties={}
    for feature in display['features']:
        zid=feature['properties']['zone_id']
        assert feature['geometry'] == source_geometries[zid]
        projected[zid]=transform(projector.transform,shape(feature['geometry']))
        properties[zid]=feature['properties']
    for zone,g in zip(dataset.zones,dataset.geometries):
        assert g.equals_exact(projected[zone['zone_id']],0), 'Diagnostic reprojection drift'
    center=Point(event['center_x_m'],event['center_y_m'])
    vertex=nearest_points(center,dataset.coverage.boundary)[1]
    missing=geometries[1024].difference(dataset.coverage)
    nearby=[dict(zone_id=zid,subzone=properties[zid]['subzone'],pec_eligible=properties[zid]['pec_eligible'],
                 exclusion_reasons=properties[zid]['exclusion_reasons'],distance_to_missing_m=g.distance(missing),
                 missing_intersection_area_m2=g.intersection(missing).area if g.is_valid else None)
            for zid,g in projected.items() if g.distance(missing)<20]
    excluded=projected['TPSZ10']
    nesting=[]
    for a,b in zip((64,128,256,512),(128,256,512,1024)):
        nesting.append(dict(coarse=a,fine=b,coarse_outside_fine_m2=geometries[a].difference(geometries[b]).area,
                            all_coarse_vertices_in_fine_vertices=set(geometries[a].exterior.coords).issubset(set(geometries[b].exterior.coords))))
    translated_coverage=translate(dataset.coverage,xoff=-center.x,yoff=-center.y)
    shifted_event=dict(event,center_x_m=0,center_y_m=0)
    numerical=[]
    for n in (128,256,512,1024):
        f=geometries[n]
        local=footprint(shifted_event,InvestigationSettings(n)).difference(translated_coverage).area
        direct=f.difference(dataset.coverage).area
        numerical.append(dict(edges=n,direct_missing_m2=direct,translated_missing_m2=local,
                              absolute_translation_change_m2=abs(local-direct),
                              excluded_intersection_m2=f.intersection(excluded).area,
                              missing_outside_excluded_zone_m2=f.difference(dataset.coverage).difference(excluded).area))
    # Event-only extension: quantify how slowly this tiny corner area settles;
    # full-episode higher resolutions are unnecessary to attribute the cause.
    extended=[]
    for n in (2048,4096,8192,16384):
        result,timing=timed(dataset,single,InvestigationSettings(n)); e=result['events'][0]
        extended.append(dict(edges=n,**{k:e[k] for k in ('footprint_area_m2','uncovered_area_m2','covered_area_fraction','status','known_area_exposure','people_potentially_exposed')},
                             ideal_area_deficit_m2=math.pi*event['radius_m']**2-e['footprint_area_m2'],coverage_tolerance_m2=1e-6))
        runtimes[str(n)]=dict(single_event_episode=timing)
    for row in extended:
        row['ideal_circle_area_m2'] = math.pi*event['radius_m']**2
        row['ideal_area_relative_deficit'] = row['ideal_area_deficit_m2']/row['ideal_circle_area_m2']
    changes(event_rows+extended,['footprint_area_m2','uncovered_area_m2','known_area_exposure'])
    other_128 = unary_union([footprint(e,InvestigationSettings(128)) for e in episode['events'] if e['event_id'] != event['event_id']])
    affected_gap_256 = geometries[256].difference(dataset.coverage)
    original_128_gap_already_in_other_events = affected_gap_256.intersection(other_128).area
    result=dict(investigation_version='pec-coverage-investigation/1',population_dataset_id=dataset.dataset_id,
                population_dataset_version=dataset.version,population_normalized_sha256=dataset.checksum,
                episode_id=episode['episode_id'],episode_file='pec-coverage-episode.json',episode_file_sha256=sha(out/'pec-coverage-episode.json'),
                event=event,coordinate_reference_system='EPSG:3414',source_file_sha256=references,
                script_sha256=sha(Path(__file__)),source_checksums=provenance['source_checksums'],
                original_benchmark_reproduced=True,changed_events=changed,
                settings=dict(coverage_tolerance_m2=1e-6,overlap_tolerance_m2=0,coverage_ratio_clamp=1e-12,
                              quad_segs='edges / 4',orientation='clockwise from positive x',diagnostic_only_resolutions=True),
                environment=dict(python=platform.python_version(),platform=platform.platform(),libraries=complete_results[128]['metadata']['libraries']),
                event_comparison=event_rows,episode_comparison=episode_rows,event_only_extension=extended,
                nesting=nesting,numerical_cross_checks=numerical,nearby_zones=nearby,
                contributing_eligible_zones=next(e for e in complete_results[1024]['events'] if e['event_id']==event['event_id'])['zone_breakdown'],
                geometry_evidence=dict(nearest_coverage_vertex=list(vertex.coords)[0],center_to_vertex_m=center.distance(vertex),
                    ideal_circle_radial_penetration_m=event['radius_m']-center.distance(vertex),
                    vertex_distance_outside_128_polygon_m=vertex.distance(geometries[128]),
                    vertex_within_256_polygon=vertex.within(geometries[256]),
                    missing_region_1024_wkt=missing.wkt,
                    original_projected_geometry_reproduced_exactly=True,
                    affected_256_gap_already_in_other_128_events_m2=original_128_gap_already_in_other_events),exclusion_audit=audit)
    write_json(out/'pec-coverage-comparison.json',result)
    write_json(out/'pec-coverage-timing.json',dict(scope='Three in-process perf_counter measurements; prepared dataset reused; excludes file I/O and plotting. Single event time includes its one-event episode aggregation.',
                                               environment=result['environment'],measurements=runtimes))
    draw_figure(out/'pec-coverage-diagnostic',dataset,excluded,geometries,event,vertex)
    assert references == {p:sha(ROOT/p) for p in inputs}, 'An investigation input changed'
    print('Reproduced:',changed)
    print('Geometry:',result['geometry_evidence'])
    print('Exclusion combinations:',audit['disjoint_category_combinations'])
    print('Generated comparison, timings, episode, PNG and SVG in data/results')


if __name__=='__main__':
    main()
