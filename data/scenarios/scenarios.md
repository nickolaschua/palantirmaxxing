# Scenarios

Supplied PEC episodes follow [pec-episode/1](../../contracts/pec.md). `pec-example.json` is a runnable two-event synthetic example using `tests/fixtures/pec-population.json`; it has complete known-population coverage. Coordinates/radii are supplied illustrative inputs, not predictions or real Singapore hazard locations.

For the prepared real dataset, use logical dataset ID `sg-residents-2020-mp2019`, copy `metadata.dataset_version` from `data/processed/population-projected.json`, and declare EPSG:3414 easting/northing metres. Small shareable inputs are versionable. This folder does not generate footprints; population data belong in `data/processed/`, outputs in `data/results/`.

`pec-coverage-benchmark.json` archives the exact original 100-event benchmark episode recovered for the [coverage investigation](../../docs/specifications/pec-coverage-investigation.md). It is tied to the documented dataset version and is a numerical workload, not a prediction.

`static-mvp-scenario.json` is the machine-side end-to-end fixture. Its 1,000 m/s
threat, 10,000 m/s interceptor, 500 m footprint and all other dimensions are
intentionally scaled synthetic test inputs chosen to preserve the Phase A-C
reachability pattern and exercise the trade-space. They are not operational
performance estimates. The fixture references
`tests/fixtures/static-mvp-population.json`.
