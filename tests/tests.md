# Tests

The population milestone adds offline Python unit/integration tests plus Node's built-in test runner for TypeScript presentation selectors. See [unit](unit/unit.md), [integration](integration/integration.md) and [fixtures](fixtures/fixtures.md).

Checks cover hierarchy and special values, conservative names, ambiguous joins, area/density units, invalid/overlapping geometry, cache protection and deterministic output. Frontend checks cover metric/filter/ranking consistency, colors and payload guards. Commands are in the root README; routine tests use only local fixtures.

Production data preparation belongs in `backend/data_sources/`; full source snapshots belong in `data/raw/`.

PEC adds synthetic known-answer unit coverage and subprocess file integration, plus an offline real-data test when the prepared artifacts are present. No network is needed. Use the existing unittest discovery commands in the README. See `test_exposure.py` and `test_exposure_files.py` in their respective subfolders.

Phases D-G add unit coverage for scenario assumptions and trade-space semantics,
focused candidate/PEC integration, and a deterministic 50-sample end-to-end
scenario. Timing is reported by a separate engineering benchmark rather than a
flaky wall-clock unit-test assertion.
