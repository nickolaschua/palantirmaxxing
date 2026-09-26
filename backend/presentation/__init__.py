"""Frontend presentation boundary; see frontend/docs/API-DESIGN.md."""
from .planning_result import PresentationSettings, planning_result_to_dict

from .simulation_result import (SIMULATION_RESULT_SCHEMA_VERSION,
                                SIMULATION_RESULT_V2_SCHEMA_VERSION,
                                simulation_result_to_dict,
                                simulation_result_v2_to_dict)

__all__ = [
    'PresentationSettings', 'planning_result_to_dict',
    'SIMULATION_RESULT_SCHEMA_VERSION', 'SIMULATION_RESULT_V2_SCHEMA_VERSION',
    'simulation_result_to_dict', 'simulation_result_v2_to_dict',
]
