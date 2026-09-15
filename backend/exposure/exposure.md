# Exposure

Implemented standalone PEC v0.1. `dataset.py` validates/adapts prepared population and builds reusable zone geometry, coverage and spatial indexing. `validation.py` defines structured errors and episode checks. `calculator.py` constructs supplied circles and calculates event/episode exposure. `__init__.py` exposes `prepare_population`, `calculate_episode`, `CalculationSettings`, `PreparedPopulation` and `PECValidationError`.

There is no file handling, acquisition, API, frontend or application decision logic here. Use [PEC contracts](../../contracts/pec.md), [specification](../../docs/specifications/pec.md), and the thin file command under `scripts/`. The existing eligible WKT subset is reused without repairs or eligibility changes. Python and dependency pins remain shared with the population pipeline.
