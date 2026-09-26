# Scripts

`benchmark_singapore_simulation.py` measures Singapore catalog cold start,
generation, cold/warm candidate consequence scoring, a complete immediate-
interception rollout, environment steps, memory, and (when the smoke artifact
exists) artifact reload plus masked inference. It writes
`data/results/singapore-simulation-benchmark.json`.

`export_simulation_result.py` deterministically generates a Singapore episode,
runs the feasible full-episode matching baseline, and writes the independent
`simulation-result/1` frontend artifact. The output deliberately uses supplied-
area and assumption-grade language.

`train_rl.py` and `evaluate_rl.py` accept explicit
`--provider toy|singapore-demo-v2` and `--generator synthetic|singapore-v1`
choices. The Singapore smoke command and evidence are documented in
`docs/singapore-simulation-integration.md`.

`train_rl.py` runs the MaskablePPO toy-provider smoke training in the separate
`.venv-rl` environment. `evaluate_rl.py` reloads the saved model and frozen
normalization statistics for deterministic comparison with the immediate-
interception baseline on a fixed suite. Generated artifacts are written below
the ignored `data/results/rl/` path.

Wall-clock training uses disposable PPO throughput calibration for a best-effort
60% training allocation, with calibration/setup overhead additional. It is not
a deadline. `--calibration-steps` sets the calibration length; environment p95
is diagnostic only. `evaluate_rl.py --suite bounded-oracle` emits version-2
evaluation reports with exactness, enumeration counts and eligible regret in
addition to separate inference and full decision-path latency samples.

`population_data.py` remains the thin source-acquisition/offline-preparation command. Its existing behavior is unchanged.

`population_exposure.py` loads population and episode JSON, invokes standalone PEC, writes strict structured JSON atomically and prints status/output location. Required arguments: `--population`, `--episode`, `--output`; optional `--circle-edges` is 128 (default) or 256. Valid partial coverage exits 0; invalid inputs exit 2; file errors exit 1. No network access occurs.

`benchmark_exposure.py` measures preparation and calculation separately over three runs for a deterministic 100-event real-data case at both resolutions. Defaults: `data/processed/population-projected.json` and `data/results/pec-benchmark.json`; override using `--population` and `--output`. Timing lives separately from deterministic result JSON.

Exact setup, execution and test commands are in the root README and [PEC specification](../docs/specifications/pec.md). Calculation belongs in `backend/exposure/`, acquisition in `backend/data_sources/`, and assertions in `tests/`.

`investigate_pec_coverage.py` reproduces the original benchmark from local inputs, runs diagnostic-only resolutions, audits all exclusions and generates comparison/timing JSON plus a standalone figure under `data/results/`. Optional plotting pins are in `requirements-pec-investigation.txt`; they are not PEC runtime dependencies. See the coverage investigation specification for exact commands.

`benchmark_static_mvp.py` prepares the deterministic synthetic population once,
runs one warm-up and seven timed complete Phase A-G evaluations with
`perf_counter_ns`, verifies equal non-timing evidence, and writes
`data/results/static-mvp-benchmark.json`. `--markdown` prints the timing summary
and 50-row candidate table. Seven runs are an engineering check, not rigorous
performance characterization.
