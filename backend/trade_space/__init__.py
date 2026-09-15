"""Pure Pareto filtering and descriptive representative extraction."""
from .pareto import (EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE,
                     EXPOSURE_RELATIVE_TOLERANCE,
                     SUCCESS_ABSOLUTE_TOLERANCE,
                     analyze_pareto, compare_exposure, compare_success)
from .representatives import extract_representative_categories

__all__ = [
    'SUCCESS_ABSOLUTE_TOLERANCE',
    'EXPOSURE_ABSOLUTE_TOLERANCE_PEOPLE',
    'EXPOSURE_RELATIVE_TOLERANCE',
    'compare_success',
    'compare_exposure',
    'analyze_pareto',
    'extract_representative_categories',
]

