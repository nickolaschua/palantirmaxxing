# Architecture

Implemented flows are independent:

1. `backend/data_sources/` acquires source snapshots, validates them and prepares versioned population artifacts and provenance. The existing frontend consumes the geographic display copy.
2. `scripts/population_exposure.py` loads an eligible projected dataset and supplied episode, calls the reusable `backend/exposure/` interface, and writes results to `data/results/` under `contracts/pec.md`.
3. `backend/planning/` samples a supplied `backend/domain/` threat state, evaluates free-terminal-heading bounded-curvature reachability from one supplied interceptor state, and returns candidate-opportunity records under `contracts/candidate-opportunities.md`.
4. `backend/scenario/` supplies explicitly synthetic time-success and fixed-circle assumptions. `backend/orchestration/static_scenario.py` joins reachable opportunities to the existing footprint-assessment adapter, then passes complete-coverage candidates to `backend/trade_space/` for Pareto and descriptive category extraction under `contracts/static-scenario-evaluation.md`.

PEC does not read the display artifact, acquire sources, infer footprint geometry, or connect to the frontend. Geometry preparation, validation, indexing and calculation use the existing pinned Python/Shapely/pyproj stack. Source geometry and population counts are preserved. Known coverage is only the eligible-zone union; exclusions and unknown counts never extend it.

The Phase A-C planning flow remains independent: it does not call PEC, infer footprints, use population data or rank candidates. Static orchestration owns the cross-flow call without moving logic into planning or PEC. Trade-space output presents alternatives and never selects a final action. API transport and frontend PEC integration remain future work. Storage is file-based with no database. PEC specifications and measured numerical limitations live in `docs/specifications/`; planning and static-evaluation semantics live in focused contracts.

The planned [explanations module](../../backend/explanations/explanations.md) will turn authoritative PEC results into deterministic explanations, independent of layout. It does not recalculate exposure or own orchestration, persistence, acquisition or transport. See the [planning specification](../specifications/pec-explanation-record.md); no adapter or final explanation contract exists yet.
