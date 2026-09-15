# Raw

Unmodified downloaded population sources: `population-api.json` (complete official API response), `boundaries.geojson` (official MP2019 blob) and `acquisition.json` (local manifest). Explicit imports may use `population.csv` instead. These are cached locally and ignored by Git.

`acquire` reuses verified files by default; `--refresh` downloads explicitly. All download/completeness checks precede cache replacement. Checksum failures stop preparation. Local import preserves input bytes and records import time without inventing a download date.

`backend/data_sources/` reads these sources and writes derived outputs to `data/processed/`. Do not edit sources to fix joins or totals. Future source snapshots belong here; derived geometry, event episodes and test fixtures belong elsewhere.
