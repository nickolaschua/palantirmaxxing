# Contracts

The [population dataset contract](population-dataset.md) defines existing geographic display and projected WKT preparation outputs, provenance, exclusions and versions. The [PEC contracts](pec.md) define canonical population input, the nonmutating WKT adapter, supplied episodes, result JSON and structured validation errors. The [candidate-opportunity contract](candidate-opportunities.md) defines the independent deterministic trajectory and bounded-curvature planning interface. The [static-scenario evaluation contract](static-scenario-evaluation.md) defines synthetic success/footprint enrichment, complete-coverage eligibility, Pareto evidence and descriptive representative categories. The [simulation-result contracts](simulation-result.md) define the legacy fixed eight-threat rollout and the variable-size, checked frozen-scenario result with explicit outcomes, policy scope, comparisons, constraint state, and provenance. [Examples](examples/examples.md) include a runnable PEC reference output.

These are file/reusable-calculation interfaces, not an API service. Source preparation remains in `backend/data_sources/`; PEC validation remains local to `backend/exposure/`; planning domain records remain in `backend/domain/`; frontend types remain independent.

The canonical [frontend–backend HTTP delivery contract](frontend-backend-api.md)
specifies the implemented same-origin result, run-job, and checked-manifest APIs.
The [planning-result/1 payload contract](planning-result.md) documents current
exported planning evidence and frontend compatibility. These supersede historical
frontend API-DESIGN guidance as described in each document.
