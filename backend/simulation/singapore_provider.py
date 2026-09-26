"""Singapore population/site consequence adapter for simulation candidates.

The adapter reuses Emmanuel's ``demo-v2`` formulas verbatim.  Its only scalar
learning objective is the normalized ordinal induced by that existing veto,
casualty tie-band and secondary-score ordering.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from pyproj import Transformer
import shapely
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

from backend.data_sources.consequence import (Estimate, POLICY_DEMO_V2, Profile,
                                                Score, flag_table, rank_sites,
                                                score_profile, veto)
from backend.data_sources.consequence.critical_sectors import facilities
from backend.data_sources.consequence.defence import military
from backend.data_sources.consequence.parks_civic import parks_civic
from backend.exposure import CalculationSettings, prepare_population
from backend.exposure.calculator import coverage, footprint, zone_exposure

from .models import AbsoluteCandidate, ScheduledThreat
from .provider import ObjectiveDirection, ProviderEvaluation
from .singapore_scenario import (MainIslandGeometry, SingaporeScenarioConfig,
                                 SINGAPORE_OBJECTIVE_REFERENCE_VERSION,
                                 load_main_island)


SINGAPORE_PROVIDER_VERSION = 'singapore-demo-v2-fixed-rank/2'
CONSEQUENCE_CATALOG_VERSION = 'singapore-consequence-catalog/1'
_REPO = Path(__file__).resolve().parents[2]
_POPULATION = _REPO / 'data' / 'processed' / 'population-projected.json'
_MILITARY = _REPO / 'frontend' / 'src' / 'demo' / 'military.json'
_PARKS = _REPO / 'backend' / 'data_sources' / 'consequence' / 'parks_civic'
_CRITICAL = _REPO / 'backend' / 'data_sources' / 'consequence' / 'critical_sectors'
_TO_SVY21 = Transformer.from_crs('EPSG:4326', 'EPSG:3414', always_xy=True)


class FrozenDict(dict):
    """JSON-compatible mapping that cannot be changed after construction."""

    def _immutable(self, *_args, **_kwargs):
        raise TypeError('candidate assessment evidence is immutable')

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _immutable

    def __deepcopy__(self, _memo):
        return self

    def __reduce__(self):
        # Multiprocessing reconstructs dict subclasses by mutation unless an
        # explicit constructor is provided, which conflicts with immutability.
        return (_frozen_dict_from_items, (tuple(self.items()),))


def _frozen_dict_from_items(items) -> FrozenDict:
    return FrozenDict(items)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenDict((key, _freeze(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _sha256_bytes(value: bytes) -> str:
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError('required consequence artifact is missing: ' + str(path))
    return _sha256_bytes(path.read_bytes())


def _json_identity(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return _sha256_bytes(encoded)


def _estimate_scaled(estimate: Estimate, fraction: float, method: str) -> Estimate:
    if not estimate.available:
        return estimate
    return replace(
        estimate,
        low=estimate.low * fraction,
        central=estimate.central * fraction,
        high=estimate.high * fraction,
        method=(estimate.method + '; ' + method).strip('; '))


def _estimate(triple: Sequence[float], unit: str, method: str,
              state: str = 'assumption', grade: str = 'D',
              source: str = '') -> Estimate:
    return Estimate(float(triple[0]), float(triple[1]), float(triple[2]),
                    unit, state, grade, source=source, method=method)


def _estimate_evidence(estimate: Estimate) -> Mapping[str, Any]:
    return {
        'low': estimate.low, 'central': estimate.central, 'high': estimate.high,
        'unit': estimate.unit, 'state': estimate.state, 'grade': estimate.grade,
        'source': estimate.source, 'source_date': estimate.source_date,
        'method': estimate.method, 'resolution': estimate.resolution,
    }


def _score_evidence(score: Optional[Score]) -> Optional[Mapping[str, float]]:
    if score is None:
        return None
    return {'low': score.low, 'central': score.central, 'high': score.high}


@dataclass(frozen=True)
class CatalogSite:
    site_id: str
    source_kind: str
    geometry: Any
    profile: Profile
    geometry_rule: str


@dataclass(frozen=True)
class ConsequenceCatalog:
    population: Any
    main_island: MainIslandGeometry
    sites: Tuple[CatalogSite, ...]
    site_geometries: Tuple[Any, ...]
    site_tree: Any
    source_checksums: Mapping[str, str]
    identity: str
    unavailable_sectors: Tuple[str, ...]


@dataclass(frozen=True)
class CandidateAssessment:
    opportunity_id: str
    eligible: bool
    veto_status: str
    veto_reasons: Tuple[str, ...]
    training_cost: float
    footprint_radius_m: float
    C: Tuple[float, float, float]
    secondary: Optional[Tuple[float, float, float]]
    population_exposure: Mapping[str, Any]
    intersected_sites: Tuple[Mapping[str, Any], ...]
    decision_features: Tuple[float, ...]
    provider_identity: str
    provider_version: str
    data_identity: str
    config_identity: str
    cache_identity: str
    rank_context: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not math.isfinite(self.training_cost):
            raise ValueError('candidate training_cost must be finite')
        if self.footprint_radius_m != 100.0:
            raise ValueError('candidate assessment radius must be 100 m')
        object.__setattr__(self, 'population_exposure',
                           _freeze(self.population_exposure))
        object.__setattr__(self, 'intersected_sites',
                           _freeze(self.intersected_sites))
        object.__setattr__(self, 'rank_context', _freeze(self.rank_context))

    def as_dict(self) -> Mapping[str, Any]:
        value = asdict(self)
        value['C'] = {'low': self.C[0], 'central': self.C[1], 'high': self.C[2]}
        value['secondary'] = (None if self.secondary is None else {
            'low': self.secondary[0], 'central': self.secondary[1],
            'high': self.secondary[2]})
        return value


def _decode_military_ring(encoded: Sequence[int]) -> Polygon:
    if len(encoded) < 6 or len(encoded) % 2:
        raise ValueError('invalid checked-in military ring')
    longitude, latitude = encoded[0], encoded[1]
    points = [(longitude / 1e5, latitude / 1e5)]
    for index in range(2, len(encoded), 2):
        longitude += encoded[index]
        latitude += encoded[index + 1]
        points.append((longitude / 1e5, latitude / 1e5))
    projected = [_TO_SVY21.transform(lon, lat) for lon, lat in points]
    geometry = Polygon(projected)
    if not geometry.is_valid:
        geometry = shapely.make_valid(geometry)
    if geometry.geom_type == 'MultiPolygon':
        geometry = max(geometry.geoms, key=lambda row: row.area)
    if geometry.is_empty or geometry.area <= 0:
        raise ValueError('invalid projected military geometry')
    return geometry


def _military_profile(site_id: str, name: str, geometry: Any,
                      condition_id: str) -> Profile:
    area_km2 = geometry.area / 1e6
    coefficient = military.TIME_COEFFICIENT[condition_id]
    occupancy = tuple(value * area_km2 * coefficient
                      for value in military.DENSITY_PER_KM2)
    air_base = 'air base' in name.lower()
    zero = Estimate.exact(0.0, 'people', 'assumption', 'D',
                          method='no publicly attributable civilian service')
    return Profile(
        site_id, condition_id,
        'military_air_base' if air_base else 'military_area', geometry.wkt,
        _estimate(occupancy, 'people',
                  'generic military-land density over the full site'),
        zero, _estimate((1, 1, 1), 'fraction', 'beneficiaries are zero'),
        _estimate((24, 24, 24), 'hours', 'beneficiaries are zero'),
        _estimate((0, 0, 0), 'fraction', 'beneficiaries are zero'),
        _estimate(military.RECOVERY_T90_HOURS, 'hours',
                  'time to 90% of site function'),
        priority_asset=air_base,
        categories=(('defence_security', 'aviation') if air_base
                    else ('defence_security',)),
        raw={'name': name, 'source': 'checked-in frontend military geometry'},
        population_method='areal_density')


def _critical_profiles(condition_id: str) -> Sequence[Tuple[facilities.Facility, Profile]]:
    """Rebuild the MAJOR_12H rows needed by the provider from committed inputs."""
    with (_CRITICAL / 'input_profiles.csv').open(encoding='utf-8') as stream:
        evidence = {row['id']: row for row in csv.DictReader(stream)}
    rows = []
    for facility in facilities.load_facilities(_CRITICAL / 'input_facilities.csv'):
        key = facilities.EVIDENCE_OF.get(facility.profile_id, facility.profile_id)
        system = evidence[key]
        geometry = shapely.from_wkt(facility.geometry_wkt)
        area_km2 = geometry.area / 1e6
        source = 'critical-sector committed inputs; MAJOR_12H deterministic rebuild'
        if facility.profile_id in facilities.THROUGHPUT:
            beneficiaries = _estimate(facilities.THROUGHPUT_E_PERSON_HOURS,
                                      'person-hours equivalent',
                                      'ordinal throughput assumption')
            loss = _estimate((1, 1, 1), 'fraction', 'ordinal throughput assumption')
            outage = _estimate((1, 1, 1), 'hours', 'ordinal throughput assumption')
            alternative = _estimate((0, 0, 0), 'fraction', 'ordinal throughput assumption')
        else:
            count = float(system['beneficiaries'])
            beneficiaries = _estimate((count, count, count), 'people',
                                      'system beneficiaries', 'derived', 'C', source)
            share = facility.share
            loss = _estimate(tuple(value * scale for value, scale in zip(
                (0.42, 0.60, 0.78), share)), 'fraction',
                'facility share x MAJOR_12H system loss', source=source)
            outage = _estimate((6, 12, 24), 'hours', 'MAJOR_12H duration', source=source)
            alternative = _estimate((0.05, 0.20, 0.35), 'fraction',
                                    'MAJOR_12H alternative capacity', source=source)
        recovery = _estimate((48, 48, 200), 'hours',
                             'MAJOR_12H recovery band rebuilt locally', source=source)
        if facility.profile_id == 'AVI-PAX' and system['h']:
            base = float(system['h'])
            occupancy = tuple(base * share for share in facility.share)
            occupancy_method = 'AVI-PAX people present x facility share'
        else:
            occupancy = tuple(value * area_km2 * facilities.INDUSTRIAL_COEFFICIENT[condition_id]
                              for value in facilities.WORKFORCE_PER_KM2)
            occupancy_method = 'generic workforce density over the full site'
        profile = Profile(
            facility.site_id, condition_id, facilities.ROLE[facility.profile_id],
            facility.geometry_wkt,
            _estimate(occupancy, 'people', occupancy_method),
            beneficiaries, loss, outage, alternative, recovery,
            categories=facilities.CATEGORIES.get(
                facility.profile_id, (system['sector'],)), raw=facility.raw,
            population_method='areal_density')
        rows.append((facility, profile))
    return rows


def build_consequence_catalog(main_island: Optional[MainIslandGeometry] = None,
                              condition_id: str = 'weekday_midday') -> ConsequenceCatalog:
    if condition_id != 'weekday_midday':
        raise ValueError('Singapore provider v1 fixes weekday_midday')
    main_island = main_island or load_main_island()
    population_raw = json.loads(_POPULATION.read_text(encoding='utf-8'))
    population = prepare_population(population_raw)
    sites = []

    # Point assets receive their full direct profile when the supplied circle intersects.
    for site in parks_civic.load_sites(_PARKS):
        profile = next(row for row in parks_civic.parks_profiles(site)
                       if row.condition_id == 'WD_DAY')
        sites.append(CatalogSite(site.site_id, 'parks_civic',
                                 shapely.from_wkt(site.geometry_wkt), profile,
                                 'point_full_direct_effect'))

    military_document = json.loads(_MILITARY.read_text(encoding='utf-8'))
    for index, row in enumerate(military_document['military']):
        geometry = _decode_military_ring(row['ring'])
        name = row.get('name') or 'Unnamed military area %d' % (index + 1)
        site_id = 'military:%03d' % (index + 1)
        sites.append(CatalogSite(
            site_id, 'military', geometry,
            _military_profile(site_id, name, geometry, condition_id),
            'polygon_area_fraction'))

    for _, profile in _critical_profiles(condition_id):
        sites.append(CatalogSite(
            profile.site_id, 'critical_facility',
            shapely.from_wkt(profile.geometry_wkt), profile,
            'polygon_area_fraction'))

    geometries = tuple(row.geometry for row in sites)
    checksums = {
        'population': _sha256_file(_POPULATION),
        'parks_sites': _sha256_file(_PARKS / 'input_sites.csv'),
        'parks_conditions': _sha256_file(_PARKS / 'input_conditions.csv'),
        'military_geometry': _sha256_file(_MILITARY),
        'critical_facilities': _sha256_file(_CRITICAL / 'input_facilities.csv'),
        'critical_profiles': _sha256_file(_CRITICAL / 'input_profiles.csv'),
        'boundary_source': main_island.source_checksum,
        'main_island_geometry': main_island.geometry_checksum,
    }
    identity = _json_identity({
        'version': CONSEQUENCE_CATALOG_VERSION,
        'condition_id': condition_id,
        'checksums': checksums,
        'site_ids': [row.site_id for row in sites],
    })
    return ConsequenceCatalog(
        population, main_island, tuple(sites), geometries, STRtree(geometries),
        checksums, identity,
        ('transport', 'healthcare', 'education', 'richer_residential_services'))


def _population_profile(people: float, condition_id: str) -> Profile:
    unavailable = Estimate.unavailable('not applicable to population exposure row')
    return Profile(
        'population:pec', condition_id, 'population_exposure', 'main-island clipped circle',
        Estimate.exact(people, 'people', 'derived', 'C',
                       source='Population Exposure Calculator',
                       method='area-density overlap of prepared Census 2020 zones'),
        unavailable, unavailable, unavailable, unavailable, unavailable,
        categories=('population',),
        raw={'authoritative_human_exposure': True})


class SingaporeConsequenceProvider:
    identity = 'singapore-consequence-provider'
    version = SINGAPORE_PROVIDER_VERSION
    objective_direction = ObjectiveDirection.MINIMIZE
    fixed_candidate_costs = True
    additive_training_costs = True
    operational_updates_affect_costs = False
    objective_reference_version = SINGAPORE_OBJECTIVE_REFERENCE_VERSION

    def __init__(self, catalog: Optional[ConsequenceCatalog] = None,
                 main_island: Optional[MainIslandGeometry] = None,
                 footprint_radius_m: float = 100.0,
                 condition_id: str = 'weekday_midday',
                 scenario_config: Optional[SingaporeScenarioConfig] = None):
        if scenario_config is not None:
            if not isinstance(scenario_config, SingaporeScenarioConfig):
                raise ValueError('scenario_config must be a SingaporeScenarioConfig')
            footprint_radius_m = scenario_config.supplied_footprint_radius_m
            condition_id = scenario_config.consequence_condition
        if type(footprint_radius_m) not in (int, float) or not math.isfinite(
                footprint_radius_m) or footprint_radius_m != 100.0:
            raise ValueError('Singapore provider fixes footprint_radius_m at 100 m')
        if condition_id != 'weekday_midday':
            raise ValueError('Singapore provider fixes weekday_midday')
        if scenario_config is None:
            scenario_config = SingaporeScenarioConfig()
        self.scenario_config = scenario_config
        self.catalog = catalog or build_consequence_catalog(main_island, condition_id)
        self.footprint_radius_m = float(footprint_radius_m)
        self.condition_id = condition_id
        self.settings = CalculationSettings(circle_edges=128)
        self.config_identity = _json_identity({
            'provider_version': self.version,
            'catalog_identity': self.catalog.identity,
            'footprint_radius_m': self.footprint_radius_m,
            'condition_id': self.condition_id,
            'policy': POLICY_DEMO_V2,
            'circle_edges': self.settings.circle_edges,
            'objective_reference': self.objective_reference_version,
            'scenario_config_checksum': self.scenario_config.checksum,
        })
        self.cache_identity = _json_identity({
            'schema': 'candidate-assessment-cache/2',
            'config_identity': self.config_identity})
        self._spatial_cache: Dict[Tuple[float, float, float], Mapping[str, Any]] = {}
        self._assessments: Dict[str, CandidateAssessment] = {}
        self._by_threat: Dict[str, Tuple[CandidateAssessment, ...]] = {}

    def _footprint(self, candidate: AbsoluteCandidate) -> Tuple[Any, Any]:
        event = {
            'center_x_m': candidate.opportunity.position_x_m,
            'center_y_m': candidate.opportunity.position_y_m,
            'radius_m': self.footprint_radius_m,
        }
        supplied = footprint(event, self.settings)
        return supplied, supplied.intersection(self.catalog.main_island.geometry)

    def _scaled_profile(self, site: CatalogSite, overlap_fraction: float) -> Profile:
        if site.geometry_rule == 'point_full_direct_effect':
            return site.profile
        method = 'scaled by candidate footprint intersection area / site area'
        return replace(
            site.profile,
            occupancy=_estimate_scaled(site.profile.occupancy, overlap_fraction, method),
            beneficiaries_per_hour=_estimate_scaled(
                site.profile.beneficiaries_per_hour, overlap_fraction, method),
            overlap_area_km2=site.geometry.area * overlap_fraction / 1e6)

    def _spatial_assessment(self, candidate: AbsoluteCandidate) -> Mapping[str, Any]:
        key = (candidate.opportunity.position_x_m,
               candidate.opportunity.position_y_m, self.footprint_radius_m)
        if key in self._spatial_cache:
            return self._spatial_cache[key]
        supplied, clipped = self._footprint(candidate)
        supplied_area = supplied.area
        if clipped.is_empty or clipped.area == 0:
            population = {
                'status': 'outside_singapore',
                'people_potentially_exposed': 0.0,
                'known_area_exposure': 0.0,
                'covered_area_fraction': 1.0,
                'supplied_area_m2': supplied_area,
                'singapore_clipped_area_m2': 0.0,
                'zone_breakdown': [],
            }
            known = 0.0
        else:
            known, zones = zone_exposure(self.catalog.population, clipped)
            missing, fraction, status = coverage(
                self.catalog.population, clipped, self.settings)
            population = {
                'status': status,
                'people_potentially_exposed': known,
                'known_area_exposure': known,
                'covered_area_fraction': fraction,
                'uncovered_area_m2': missing,
                'supplied_area_m2': supplied_area,
                'singapore_clipped_area_m2': clipped.area,
                'zone_breakdown': zones,
            }

        population_profile = _population_profile(known, self.condition_id)
        population_scored = score_profile(population_profile)
        population_flags = flag_table(population_profile, population_scored)
        population_veto_reasons = tuple(
            name for name in ('high_human_exposure', 'essential_service_floor_breach')
            if population_flags.get(name) is True)

        site_rows = []
        secondary_scores = []
        site_veto_reasons = []
        any_unknown = False
        if not clipped.is_empty:
            indexes = sorted(int(index) for index in self.catalog.site_tree.query(
                clipped, predicate='intersects'))
            for index in indexes:
                site = self.catalog.sites[index]
                if site.geometry.geom_type == 'Point':
                    overlap_fraction = 1.0
                else:
                    overlap_fraction = clipped.intersection(site.geometry).area / site.geometry.area
                if overlap_fraction <= 0:
                    continue
                profile = self._scaled_profile(site, overlap_fraction)
                scored = score_profile(profile)
                table = flag_table(profile, scored)
                status, civilian, capability = veto(
                    table, profile.priority_asset, profile.capability.available)
                if status == 'vetoed':
                    site_veto_reasons.extend(
                        '%s:%s' % (site.site_id, reason)
                        for reason in civilian + capability)
                elif status == 'unknown':
                    any_unknown = True
                if scored.secondary is not None:
                    secondary_scores.append(scored.secondary)
                site_rows.append({
                    'site_id': site.site_id,
                    'source_kind': site.source_kind,
                    'role': profile.role,
                    'categories': list(profile.categories),
                    'geometry_rule': site.geometry_rule,
                    'overlap_fraction': overlap_fraction,
                    'scores': {
                        name: _score_evidence(getattr(scored, name))
                        for name in ('C', 'E', 'D', 'X', 'R', 'A', 'secondary')},
                    'site_casualties_diagnostic_only': _score_evidence(scored.C),
                    'veto_status': status,
                    'veto_reasons_civilian': list(civilian),
                    'veto_reasons_capability': list(capability),
                    'dimensions_missing': list(scored.dimensions_missing),
                    'inputs': {
                        name: _estimate_evidence(getattr(profile, name))
                        for name in ('occupancy', 'beneficiaries_per_hour',
                                     'loss_fraction', 'outage_hours',
                                     'alternative_capacity_fraction',
                                     'recovery_t90_hours')},
                    'raw': dict(profile.raw),
                })

        if secondary_scores:
            secondary = Score(*(math.fsum(row[index] for row in secondary_scores)
                                for index in range(3)))
        elif site_rows:
            secondary = None
            any_unknown = True
        else:
            secondary = Score(0.0, 0.0, 0.0)
        reasons = tuple(population_veto_reasons) + tuple(site_veto_reasons)
        veto_status = 'vetoed' if reasons else ('unknown' if any_unknown else 'pass')
        result = {
            'population': population,
            'C': population_scored.C,
            'secondary': secondary,
            'veto_status': veto_status,
            'veto_reasons': reasons,
            'sites': tuple(site_rows),
        }
        self._spatial_cache[key] = result
        return result

    def assess_candidates(self, threat: ScheduledThreat,
                          candidates: Sequence[AbsoluteCandidate],
                          operational_state: Mapping[str, Any]) -> Mapping[str, CandidateAssessment]:
        del operational_state
        raw = []
        for candidate in sorted(candidates, key=lambda row: row.opportunity.opportunity_id):
            spatial = self._spatial_assessment(candidate)
            C = spatial['C']
            secondary = spatial['secondary']
            raw.append({
                'candidate': candidate,
                'spatial': spatial,
                'C_central': C.central,
                'secondary_central': None if secondary is None else secondary.central,
                'veto_status': spatial['veto_status'],
            })
        rankable = [row for row in raw
                    if row['candidate'].opportunity.reachable
                    and row['veto_status'] != 'vetoed']
        ordered = rank_sites(rankable, POLICY_DEMO_V2) if rankable else []
        costs = {}
        denominator = max(1, len(ordered) - 1)
        for position, row in enumerate(ordered):
            costs[row['candidate'].opportunity.opportunity_id] = position / denominator
        rank_context = {
            'threat_id': threat.state.threat_id,
            'eligible_candidate_count': len(ordered),
            'candidate_universe_count': len(raw),
            'objective_reference': self.objective_reference_version,
            'objective_scope': 'full_candidate_universe',
            'ordered_opportunity_ids': [
                row['candidate'].opportunity.opportunity_id for row in ordered],
            'policy_version': POLICY_DEMO_V2['version'],
            'tie_band': POLICY_DEMO_V2['tie_band'],
            'tie_floor': POLICY_DEMO_V2['tie_floor'],
        }
        assessments = []
        for row in raw:
            candidate, spatial = row['candidate'], row['spatial']
            opportunity_id = candidate.opportunity.opportunity_id
            eligible = candidate.opportunity.reachable and row['veto_status'] != 'vetoed'
            training_cost = costs.get(opportunity_id, 1.0)
            C, secondary = spatial['C'], spatial['secondary']
            coverage_code = {
                'outside_singapore': 0.0, 'complete': 1.0,
                'partial_coverage': 0.5}.get(spatial['population']['status'], -1.0)
            features = (
                float(eligible), training_cost, C.low, C.central, C.high,
                -1.0 if secondary is None else secondary.central,
                float(row['veto_status'] == 'vetoed'),
                float(row['veto_status'] == 'unknown'), coverage_code,
            )
            assessment = CandidateAssessment(
                opportunity_id, eligible, row['veto_status'],
                tuple(spatial['veto_reasons']), training_cost,
                self.footprint_radius_m,
                (C.low, C.central, C.high),
                None if secondary is None else tuple(secondary),
                dict(spatial['population']), tuple(spatial['sites']), features,
                self.identity, self.version, self.catalog.identity,
                self.config_identity, self.cache_identity, rank_context)
            self._assessments[opportunity_id] = assessment
            assessments.append(assessment)
        self._by_threat[threat.state.threat_id] = tuple(assessments)
        return {row.opportunity_id: row for row in assessments}

    def assessment_for(self, opportunity_id: str) -> Optional[CandidateAssessment]:
        return self._assessments.get(opportunity_id)

    def decision_features(self, state: Any,
                          visible_threat_ids: Sequence[str]) -> Sequence[float]:
        features = []
        for threat_id in visible_threat_ids:
            rows = [row for row in self._by_threat.get(threat_id, ()) if row.eligible]
            features.extend((float(len(rows)), min(
                (row.training_cost for row in rows), default=1.0)))
        return tuple(features)

    def _evaluation(self, assessment: CandidateAssessment,
                    runtime_ms: float = 0.0) -> ProviderEvaluation:
        components = {
            'ordinal_training_cost': assessment.training_cost,
            'expected_casualties_low': assessment.C[0],
            'expected_casualties_central': assessment.C[1],
            'expected_casualties_high': assessment.C[2],
            'people_potentially_exposed': float(
                assessment.population_exposure['people_potentially_exposed']),
        }
        if assessment.secondary is not None:
            components['secondary_score_central'] = assessment.secondary[1]
        return ProviderEvaluation(
            raw_score=assessment.training_cost,
            training_cost=assessment.training_cost,
            components=components,
            operational_state_update={},
            provenance={
                'provider': self.identity, 'version': self.version,
                'catalog_version': CONSEQUENCE_CATALOG_VERSION,
                'catalog_identity': self.catalog.identity,
                'config_identity': self.config_identity,
                'cache_identity': self.cache_identity,
                'source_checksums': dict(self.catalog.source_checksums),
            },
            evidence=assessment.as_dict(), runtime_ms=runtime_ms)

    def evaluate_assigned_assessment(self, threat: ScheduledThreat,
                                     candidate: AbsoluteCandidate,
                                     assessment: Mapping[str, Any],
                                     operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        del threat, operational_state
        started = time.perf_counter()
        if assessment.get('opportunity_id') != candidate.opportunity.opportunity_id:
            return ProviderEvaluation(
                None, failure_status='candidate_assessment_mismatch',
                evidence={'opportunity_id': candidate.opportunity.opportunity_id})
        try:
            training_cost = float(assessment['training_cost'])
            casualties = assessment['C']
            population = assessment['population_exposure']
            components = {
                'ordinal_training_cost': training_cost,
                'expected_casualties_low': float(casualties['low']),
                'expected_casualties_central': float(casualties['central']),
                'expected_casualties_high': float(casualties['high']),
                'people_potentially_exposed': float(
                    population['people_potentially_exposed']),
            }
            secondary = assessment.get('secondary')
            if secondary is not None:
                components['secondary_score_central'] = float(secondary['central'])
        except (KeyError, TypeError, ValueError) as exc:
            return ProviderEvaluation(
                None, failure_status='malformed_candidate_assessment_snapshot',
                evidence={'opportunity_id': candidate.opportunity.opportunity_id,
                          'error': str(exc)})
        # The assignment snapshot, rather than the provider's mutable cache, is
        # authoritative after the resource is locked.
        return ProviderEvaluation(
            raw_score=training_cost,
            training_cost=training_cost,
            components=components,
            operational_state_update={},
            provenance={
                'provider': assessment.get('provider_identity', self.identity),
                'version': assessment.get('provider_version', self.version),
                'catalog_version': CONSEQUENCE_CATALOG_VERSION,
                'catalog_identity': assessment.get('data_identity'),
                'config_identity': assessment.get('config_identity'),
                'cache_identity': assessment.get('cache_identity'),
                'source_checksums': dict(self.catalog.source_checksums),
                'assessment_source': 'assignment_snapshot',
            },
            evidence=dict(assessment),
            runtime_ms=(time.perf_counter() - started) * 1000.0)

    def evaluate_assigned(self, threat: ScheduledThreat,
                          candidate: AbsoluteCandidate,
                          operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        del threat, operational_state
        assessment = self._assessments.get(candidate.opportunity.opportunity_id)
        if assessment is None:
            return ProviderEvaluation(None, failure_status='missing_candidate_assessment')
        return self._evaluation(assessment)

    def evaluate_unhandled(self, threat: ScheduledThreat,
                           operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        del operational_state
        return ProviderEvaluation(
            9.0,
            training_cost=9.0,
            components={'constraint_violation_penalty': 9.0},
            constraint_violation='unhandled_threat',
            provenance={
                'provider': self.identity, 'version': self.version,
                'objective_reference': self.objective_reference_version,
            },
            evidence={'threat_id': threat.state.threat_id,
                      'constraint': 'all-threats-intercepted'})

    def aggregate(self, outcomes: Iterable[ProviderEvaluation],
                  operational_state: Mapping[str, Any]) -> ProviderEvaluation:
        del operational_state
        rows = tuple(outcomes)
        total = math.fsum(float(row.training_cost) for row in rows
                          if row.training_cost is not None)
        components = {
            'ordinal_training_cost_total': total,
            'resolved_outcomes': float(len(rows)),
            'expected_casualties_central_total': math.fsum(
                row.components.get('expected_casualties_central', 0.0) for row in rows),
            'people_potentially_exposed_total': math.fsum(
                row.components.get('people_potentially_exposed', 0.0) for row in rows),
        }
        return ProviderEvaluation(
            total, components=components, training_cost=total,
            provenance={
                'provider': self.identity, 'version': self.version,
                'catalog_identity': self.catalog.identity,
                'config_identity': self.config_identity,
                'aggregation': 'sum of eight normalized ordinal event costs',
                'objective_reference': self.objective_reference_version,
            },
            evidence={
                'outcome_count': len(rows),
                'unavailable_sectors': list(self.catalog.unavailable_sectors),
                'persistent_operational_updates': {},
            })
