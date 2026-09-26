"""How many of an area site's people are inside the debris footprint (Tier 1: areal density).

Some sites are areas, not buildings: merged landed lots and subzone remainders carry every resident of that
area as if they stood at one point. Scored as-is, a neighbourhood is compared with a single building. This
module scales such a site's population to the share of its geometry that a footprint covers.

ASSUMPTION-GRADE: population density is taken as uniform over the site geometry (roads, gardens and void
decks included). Tier 2 ('building_level', weighting by residential floor area) is the named follow-up and
is not implemented.

Site-level scoring has no interception candidate, so the footprint is a placeholder circle centred on the
site, with the radius the static scenario already supplies (data/scenarios/demo-singapore.json). It is not
debris physics.
"""
from __future__ import annotations

import json
import math

import shapely

from backend.data_sources.consequence.paths import SCENARIO

POPULATION_METHODS = ('direct', 'areal_density', 'building_level')
OVERLAP_TOLERANCE = 1e-9  # relative float overshoot of overlap over area that is clamped, not rejected


def _placeholder_radius_m() -> float:
    return float(json.loads(SCENARIO.read_text(encoding='utf-8'))['footprint_radius_m'])


PLACEHOLDER_FOOTPRINT_RADIUS_M = _placeholder_radius_m()  # assumption: supplied circle, not debris physics


def effective_occupancy_areal_density(population: float, site_area_km2: float, overlap_area_km2: float) -> float:
    """People inside the footprint, assuming uniform density over the site: population * overlap / area."""
    for name, value in (('population', population), ('site_area_km2', site_area_km2),
                        ('overlap_area_km2', overlap_area_km2)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f'{name} must be finite and nonnegative, got {value!r}')
    if site_area_km2 <= 0:
        raise ValueError(f'site_area_km2 must be positive, got {site_area_km2!r}')
    if overlap_area_km2 > site_area_km2 * (1 + OVERLAP_TOLERANCE):
        raise ValueError(f'overlap {overlap_area_km2!r} km2 exceeds site area {site_area_km2!r} km2')
    return population * min(overlap_area_km2, site_area_km2) / site_area_km2


def placeholder_overlap_km2(geometry, radius_m: float = PLACEHOLDER_FOOTPRINT_RADIUS_M) -> float:
    """Area (km2) of a geometry in metres (EPSG:3414) inside a circle of radius_m on its representative point."""
    circle = geometry.representative_point().buffer(radius_m)
    return shapely.intersection(geometry, circle).area / 1e6


def building_level_occupancy(*_args, **_kwargs) -> float:
    raise NotImplementedError("population_method 'building_level' (Tier 2, floor-area weighting) is not implemented")
