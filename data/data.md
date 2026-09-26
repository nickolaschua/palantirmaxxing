# Data

File-based assessment storage. Official population snapshots are cached in [raw](raw/raw.md); generated zone datasets and validation/provenance reports live in [processed](processed/processed.md). The first milestone prepares Census 2020 residents against MP2019 boundaries. [Scenarios](scenarios/scenarios.md) contains a runnable synthetic PEC episode; [results](results/results.md) holds ignored exposure outputs and separate benchmark measurements.

Raw snapshots and large regenerated geographic/projected datasets are ignored by Git. Small official test excerpts, provenance and readable/machine validation reports are versionable. See the root README for reproduction and local-import commands. Existing Canvas map assets remain in `frontend/src/lib/`.

[`imperfect_conditions`](imperfect_conditions/README.md) is a self-contained,
simulation-only handoff for generating balanced imperfect-condition imitation
demonstrations. It includes the scenario overlays, data dictionary, source
registry, and one contract-valid example.

PEC run outputs belong in `data/results/`, not population preparation outputs. Test-specific inputs belong in `tests/fixtures/`. Storage starts with files; reconsider a database only if shared editing or searchable run history becomes necessary.
