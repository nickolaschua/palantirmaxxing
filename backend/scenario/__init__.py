"""Replaceable supplied assumptions for the synthetic static scenario."""
from .supplied_footprints import (build_supplied_circular_footprint,
                                  validate_supplied_footprint_radius)
from .synthetic_success import evaluate_synthetic_success

__all__ = ['evaluate_synthetic_success', 'validate_supplied_footprint_radius',
           'build_supplied_circular_footprint']
