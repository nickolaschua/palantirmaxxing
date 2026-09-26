# Scenarios

`rl/singapore-distribution-v1.json` is the strict checked configuration for
`singapore-scenario/2`. Its checksum is computed from canonical compact JSON.
The generator uses independent deterministic streams and exposes the warmup,
balanced, full-standard, burst-contention, low-slack, consequence-contrast,
geographic-shift, and cadence-shift profiles. Every accepted episode has a
complete consequence-eligible matching and records its profile, distribution,
hash, active counts, spatial coverage, generation attempts, graph summary, and
existing source/provider/configuration checksums.

`rl/suites.json` is the flat `rl-scenario-suites/5` manifest. It pins 544
immutable `sg2:` references: 64 validation, 256 held-out, 32 stress, 64 OOD
geography, 64 OOD cadence, and 64 assignment-reference episodes. Each record
binds its seed and profile to generator, distribution, provider, and canonical
episode-hash identities. The bounded synthetic oracle suite remains described
at the top level. Manifest creation requires the passing canonical 1,000-episode
audit in `data/results/rl/scenario-audit-v2.json`.

Audit seeds start at 80,000. Frozen split ranges remain below that partition.
Procedural training reserves scenario seeds at or above 1,000,000,000; generated
training episodes add this offset to a nonnegative explicit reset seed or to the
base seed plus automatic episode counter. Explicit `EpisodeSpec` inputs bypass
the offset for reproducible evaluation. The partitions do not overlap.

`rl/pools/<release-id>/` contains materialized development-training releases.
Each release has a checksummed `manifest.json` and one canonical episode JSON
per record. `scripts/generate_scenario_pool.py` creates, resumes, and verifies
these releases. The initial release is `sg2-pilot-512-v1`; it uses seeds
1,000,000,000 through 1,000,000,511 and excludes all frozen evaluation, audit,
and bounded-oracle seed partitions.

These scenarios are synthetic and use assumption-grade consequences. They do
not establish operational or real-world performance. The generated audit report
at `docs/specifications/rl-scenario-audit.md` records all episodes, retries,
unavailable consequence components, online-naive and offline-exact outcomes,
and every frozen Goldilocks gate.

Supplied PEC episodes follow [pec-episode/1](../../contracts/pec.md). `pec-example.json` is a runnable two-event synthetic example using `tests/fixtures/pec-population.json`; it has complete known-population coverage. Coordinates/radii are supplied illustrative inputs, not predictions or real Singapore hazard locations.

For the prepared real dataset, use logical dataset ID `sg-residents-2020-mp2019`, copy `metadata.dataset_version` from `data/processed/population-projected.json`, and declare EPSG:3414 easting/northing metres. Small shareable inputs are versionable. This folder does not generate footprints; population data belong in `data/processed/`, outputs in `data/results/`.

`pec-coverage-benchmark.json` archives the exact original 100-event benchmark episode recovered for the [coverage investigation](../../docs/specifications/pec-coverage-investigation.md). It is tied to the documented dataset version and is a numerical workload, not a prediction.

`static-mvp-scenario.json` is the machine-side end-to-end fixture. Its 1,000 m/s
threat, 10,000 m/s interceptor, 500 m footprint and all other dimensions are
intentionally scaled synthetic test inputs chosen to preserve the Phase A-C
reachability pattern and exercise the trade-space. They are not operational
performance estimates. The fixture references
`tests/fixtures/static-mvp-population.json`.
