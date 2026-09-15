# Domain

`candidates.py` defines immutable threat, interceptor, trajectory-sample and candidate-opportunity records for the synthetic planning prototype. `evaluated_candidates.py` adds immutable supplied-profile, footprint, exposure, Pareto, category, timing and trade-space records by composing rather than mutating `CandidateOpportunity`. `__init__.py` exposes both sets. See the [candidate-opportunity contract](../../contracts/candidate-opportunities.md) and [static-scenario contract](../../contracts/static-scenario-evaluation.md).

PEC retains its calculation-specific types and validation in `backend/exposure/`; they are not duplicated or imported here. Planning coordinates are metres, interceptor heading is normalized in radians, and speed/turn-rate values are synthetic simulation inputs rather than operational performance claims. Cesium-specific types remain in the viewer.
