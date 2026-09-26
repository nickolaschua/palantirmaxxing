# Contracts

The [population dataset contract](population-dataset.md) defines existing geographic display and projected WKT preparation outputs, provenance, exclusions and versions. The [PEC contracts](pec.md) define canonical population input, the nonmutating WKT adapter, supplied episodes, result JSON and structured validation errors. The [candidate-opportunity contract](candidate-opportunities.md) defines the independent deterministic trajectory and bounded-curvature planning interface. The [static-scenario evaluation contract](static-scenario-evaluation.md) defines synthetic success/footprint enrichment, complete-coverage eligibility, Pareto evidence and descriptive representative categories. The [`simulation-result/1` contract](simulation-result.md) defines the separate eight-threat 3D rollout, consequence evidence, comparison, provenance and controlled frontend wording. [Examples](examples/examples.md) include a runnable PEC reference output.

These are file/reusable-calculation interfaces, not an API service. Source preparation remains in `backend/data_sources/`; PEC validation remains local to `backend/exposure/`; planning domain records remain in `backend/domain/`; frontend types remain independent.

The canonical [frontend–backend HTTP delivery contract](frontend-backend-api.md)
specifies future same-origin read-only delivery (no HTTP service exists yet).
The [planning-result/1 payload contract](planning-result.md) documents current
exported planning evidence and frontend compatibility. These supersede historical
frontend API-DESIGN guidance as described in each document.
