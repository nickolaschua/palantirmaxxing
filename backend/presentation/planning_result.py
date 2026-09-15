"""Adapt authoritative static results without performing planning.

The wire contract is defined only in frontend/docs/API-DESIGN.md.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

from pyproj import Transformer

from backend.domain import TradeSpaceResult

TRANSFORMER = Transformer.from_crs('EPSG:3414', 'EPSG:4326', always_xy=True)
CATEGORIES = ('earliest_viable', 'highest_success', 'lowest_exposure')
CATEGORY_KEYS = ('earliestViable', 'highestSuccess', 'lowestExposure')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class PresentationSettings:
    scenario_start_time: str
    visualization_height_m: float

    def __post_init__(self):
        self.start_time()
        if not _finite(self.visualization_height_m):
            raise ValueError('visualization_height_m must be finite')

    def start_time(self):
        if not isinstance(self.scenario_start_time, str):
            raise ValueError('scenario_start_time must be an ISO 8601 string')
        value = datetime.fromisoformat(self.scenario_start_time.replace('Z', '+00:00'))
        if value.utcoffset() is None:
            raise ValueError('scenario_start_time must include a timezone')
        return value.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _difference(comparison, reference):
    if not (_finite(comparison) and _finite(reference)):
        return None
    delta = comparison - reference
    return delta if _finite(delta) else None


def _complete_exposure(candidate):
    exposure = candidate.get('exposure')
    if exposure and exposure['status'] == 'complete':
        return exposure['peoplePotentiallyExposed']
    return None


def _comparison(reference, comparison):
    success = _difference(comparison.get('suppliedSuccessProbability'),
                          reference.get('suppliedSuccessProbability'))
    reference_exposure = _complete_exposure(reference)
    exposure = _difference(_complete_exposure(comparison), reference_exposure)
    relative = (exposure / reference_exposure
                if exposure is not None and reference_exposure != 0 else None)
    return {
        'referenceCandidateId': reference['id'],
        'comparisonCandidateId': comparison['id'],
        'deltaTimeS': comparison['timeFromStartS'] - reference['timeFromStartS'],
        'deltaSuccessProbability': success,
        'deltaSuccessPercentagePoints': 100 * success if success is not None else None,
        'deltaPeoplePotentiallyExposed': exposure,
        'relativeExposureChange': relative if _finite(relative) else None,
    }


def planning_result_to_dict(result, settings, *, threat_id, footprint_radius_m):
    """Return JSON primitives for the supplied synthetic static-scenario result.

The caller supplies the original threat ID and fixed radius, including when no
opportunities exist. Timing and text encoding are outside this adapter.
"""
    if not isinstance(result, TradeSpaceResult):
        raise ValueError('result must be TradeSpaceResult')
    if not isinstance(settings, PresentationSettings):
        raise ValueError('settings must be PresentationSettings')
    if not isinstance(threat_id, str) or not threat_id.strip():
        raise ValueError('threat_id must be nonempty')
    if not _finite(footprint_radius_m) or footprint_radius_m < 0:
        raise ValueError('footprint_radius_m must be finite and nonnegative')
    start = settings.start_time()
    opportunities = result.candidate_opportunities
    ids = [row.opportunity_id for row in opportunities]
    evaluated = {row.opportunity.opportunity_id: row for row in result.candidates}
    if len(set(ids)) != len(ids) or len(evaluated) != len(result.candidates):
        raise ValueError('candidate IDs must be unique')
    if set(evaluated) != {row.opportunity_id for row in opportunities if row.reachable}:
        raise ValueError('enriched candidates must match reachable opportunities')
    assignments = {key: getattr(result.category_assignments, category)
                   for key, category in zip(CATEGORY_KEYS, CATEGORIES)}
    representatives = list(result.representative_candidate_ids)
    expected_representatives = list(dict.fromkeys(
        value for value in assignments.values() if value is not None))
    if representatives != expected_representatives:
        raise ValueError('representatives must agree with category assignments')
    pareto = set(result.pareto_candidate_ids)
    if not pareto.issubset(evaluated) or not set(representatives).issubset(pareto):
        raise ValueError('Pareto and category references must exist')
    candidates, samples = [], []
    for opportunity in opportunities:
        if opportunity.threat_id != threat_id:
            raise ValueError('threat_id does not match the result')
        lon, lat = TRANSFORMER.transform(opportunity.position_x_m,
                                         opportunity.position_y_m, errcheck=True)
        if not (_finite(lon) and _finite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError('coordinate conversion returned an invalid position')
        position = dict(lon=lon, lat=lat, height=settings.visualization_height_m)
        time = _iso(start + timedelta(seconds=opportunity.time_from_start_s))
        samples.append(dict(time=time, **position))
        candidate = {
            'id': opportunity.opportunity_id,
            'sampleIndex': opportunity.sample_index,
            'timeFromStartS': opportunity.time_from_start_s,
            'time': time, 'position': position,
            'reachable': opportunity.reachable,
            'requiredTravelTimeS': opportunity.required_travel_time_s,
            'timeMarginS': opportunity.time_margin_s,
            'paretoEfficient': opportunity.opportunity_id in pareto,
            'categories': [category for category in CATEGORIES
                           if getattr(result.category_assignments, category) == opportunity.opportunity_id],
            'eligibleForRecommendation': False,
            'ineligibilityReasons': ['unreachable'],
        }
        enriched = evaluated.get(opportunity.opportunity_id)
        if enriched is not None:
            if enriched.opportunity != opportunity or enriched.footprint.radius_m != footprint_radius_m:
                raise ValueError('enriched geometry must match the supplied scenario')
            exposure = enriched.exposure
            candidate.update({
                'suppliedSuccessProbability': enriched.supplied_success_probability,
                'exposure': {
                    'status': exposure.exposure_status,
                    'peoplePotentiallyExposed': exposure.people_potentially_exposed,
                    'knownAreaExposure': exposure.known_area_exposure,
                    'coveredAreaFraction': exposure.covered_area_fraction,
                },
                'footprint': {'id': enriched.footprint.footprint_id,
                              'radiusM': enriched.footprint.radius_m},
                'eligibleForRecommendation': enriched.eligible,
                'ineligibilityReasons': list(enriched.ineligibility_reasons),
            })
        candidates.append(candidate)
    by_id = {row['id']: row for row in candidates}
    provenance = result.population_exposure_provenance
    population = {target: provenance[source] for target, source in (
        ('datasetId', 'population_dataset_id'),
        ('datasetVersion', 'population_dataset_version'),
        ('coordinateReferenceSystem', 'coordinate_reference_system'))}
    if 'calculator_version' in provenance:
        population['calculatorVersion'] = provenance['calculator_version']
    payload = {
        'schemaVersion': 'planning-result/1', 'scenarioId': result.scenario_id,
        'start': _iso(start), 'end': samples[-1]['time'] if samples else _iso(start),
        'threat': {'id': threat_id, 'samples': samples}, 'candidates': candidates,
        'paretoCandidateIds': list(result.pareto_candidate_ids),
        'categoryAssignments': assignments,
        'representativeCandidateIds': representatives,
        'comparisons': [_comparison(by_id[reference], by_id[comparison])
                        for reference in representatives for comparison in representatives
                        if reference != comparison],
        'diagnostics': {
            'totalCandidates': result.total_candidates,
            'reachableCandidates': result.reachable_candidates,
            'eligibleCandidates': result.eligible_candidates,
            'paretoCandidates': len(result.pareto_candidate_ids),
        },
        'assumptions': {
            'successModel': 'synthetic_linear_decay',
            'footprintModel': 'supplied_fixed_circle',
            'footprintRadiusM': footprint_radius_m,
            'populationExposureMeaning': 'estimated_people_potentially_exposed',
            'kinematicsCalibration': 'synthetic_not_operational',
            'visualizationHeightM': settings.visualization_height_m,
            'heightMeaning': 'synthetic_visualization_only',
            'scenarioTimeMeaning': 'synthetic_presentation_clock',
        },
        'populationProvenance': population,
    }
    _validate_primitives(payload)
    return payload


def _validate_primitives(value):
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float) and _finite(value):
        return
    if type(value) is list:
        for item in value:
            _validate_primitives(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _validate_primitives(item)
        return
    raise ValueError('planning result must contain only finite JSON primitives')
