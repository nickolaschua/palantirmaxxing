# Orchestration

Purpose: coordinate dataset loading, assessment execution and result packaging.

`footprint_assessment.py` implements the [footprint-assessment contract](../../contracts/footprint-assessment.md). It reuses prepared PEC population for independent hypothetical footprints or a single episode, preserves provenance, and emits requested factual exposure differences without ranking or selecting actions. Standalone PEC file execution is implemented by `scripts/population_exposure.py`, which directly calls the reusable PEC interface.

`static_scenario.py` implements the machine-side static MVP. It invokes the existing candidate generator, applies explicit synthetic scenario assumptions only to reachable candidates, sends their circles through `footprint_assessment.py`, excludes partial coverage from comparison, invokes pure Pareto/category modules and packages auditable evidence. `__init__.py` exposes this reusable interface. It does not call frontend code or select a final action.

Future transport coordination may load versioned inputs and package these reusable outputs for API consumers. Storage starts with files.

Calculation algorithms belong in `backend/exposure/`; source-specific acquisition and normalisation belong in `backend/data_sources/`. This folder coordinates existing modules and does not predict real success or physical footprints.
