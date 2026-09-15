# Integration

`test_population_pipeline.py` runs the offline cache-to-output flow on official excerpts in temporary storage. It verifies exact repeat output, preserved display geometry, projected WKT/area agreement, cached acquisition without network calls, failed-refresh protection and checksum rejection. Fixture completeness counts are explicitly overridden for the four-zone excerpt, never for production preparation.

`test_candidate_exposure_integration.py` proves that candidate evidence exactly
matches a direct footprint-adapter call, preserves provenance, and excludes
partial coverage from Pareto eligibility without discarding known-area evidence.
`test_static_scenario.py` runs the 50-candidate scaled synthetic fixture through
trajectory, reachability, supplied assumptions, PEC, Pareto filtering and
representative extraction.

Isolated parsing and presentation checks belong in `tests/unit/`; production snapshots belong in `data/raw/`.

`test_exposure_files.py` verifies strict file input, calculation and JSON output, error exit codes, input overwrite protection, and repeat-run reproducibility. Its real-data case exercises the eligible WKT artifact without network and explicitly skips only when the ignored local artifacts are absent. Existing pipeline checks still run using temporary directories.
