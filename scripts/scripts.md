# Scripts

`benchmark_singapore_simulation.py` measures Singapore catalog cold start,
generation, cold/warm candidate consequence scoring, a complete immediate-
interception rollout, environment steps, memory, and (when the smoke artifact
exists) artifact reload plus masked inference. It writes
`data/results/singapore-simulation-benchmark.json`.

`export_simulation_result.py --seed N` preserves the deterministic legacy
`simulation-result/1` export. `--scenario-ref REF --policy ID` resolves one
checked immutable reference, runs the selected fixed implementation plus naive
and exact comparison replays, and writes `simulation-result/2`. A reference
identity or hash mismatch exits 42. Both versions use supplied-area and
assumption-grade language.

`audit_scenarios.py --plan canonical --check-gates` regenerates all 1,000
development audit episodes from the checked Singapore v2 distribution. It
writes deterministic JSON and derives the Markdown summary from that JSON; it
exits nonzero when a frozen Goldilocks gate fails. Timings are intentionally
excluded from these artifacts.

`build_scenario_manifest.py` creates the 544-entry `rl-scenario-suites/5`
manifest only from a passing canonical audit. `--check` performs a byte-for-byte
drift check without writing the manifest.

`generate_scenario_pool.py` materializes resumable, versioned Singapore v2
development-training pools. It writes one canonical episode JSON per record,
checkpoints after each completed record, and finalizes a checksummed manifest
containing seed, profile, retry, source, dependency, split, and coverage
provenance. The initial pilot command is
`generate_scenario_pool.py --release-id sg2-pilot-512-v1 --count 512 --workers 6 --resume`.
Use the same release ID with `--verify` to reload and checksum every artifact.

`generate_imitation_dataset.py --pool POOL --output-dir DATASET --seed 7`
replays the privileged exact fixed-rank teacher over verified development-
training records and writes deterministic, checksummed compact feature shards.
`--diagnostic-limit N` restricts generation for CLI smoke tests.

`train_imitation.py --dataset DATASET --pool POOL --output-dir ARTIFACT --seed 7`
trains the structured observation-only behavior-cloning student and runs the
mandatory overfit diagnostics (`--diagnostic-limit` defaults to 16). Add
`--validation-and-dagger` to evaluate all 64 frozen validation episodes and,
only on a failed BC gate, run up to three residual-expert DAgger rounds. The
resulting `promotion.json` records either the frozen promoted artifact identity
or the naive online deterministic fallback.

`train_rl.py` and `evaluate_rl.py` accept explicit
`--provider toy|singapore-demo-v2`, `--generator synthetic|singapore-v1|singapore-v2`,
and `--n-envs N` (default 4) select the training runtime. Use
`benchmark_rl_training.py` for the 1/2/4/6/8-worker Singapore-v2 throughput matrix.
The Singapore smoke command and evidence are documented in
`docs/singapore-simulation-integration.md`.

`train_rl.py` runs the MaskablePPO toy-provider smoke training in the separate
`.venv-rl` environment. `evaluate_rl.py` reloads the saved model and frozen
normalization statistics for deterministic comparison with the naive detected-
threat-only online policy on a fixed suite. Feasible matching and exact fixed-
rank optimization are separately labeled offline references. Generated artifacts are written below
the ignored `data/results/rl/` path.

Wall-clock training uses disposable PPO throughput calibration for a best-effort
60% training allocation, with calibration/setup overhead additional. It is not
a deadline. `--calibration-steps` sets the calibration length; environment p95
is diagnostic only. `evaluate_rl.py` emits `policy-evaluation/3` reports;
`--suite bounded-oracle` adds exactness, enumeration counts and eligible regret in
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
