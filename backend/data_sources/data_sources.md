# Data sources

Implemented official Census 2020 / URA MP2019 population preparation:

- `acquisition.py`: complete downloads, explicit refresh/local import, checksums and cache verification.
- `population.py`: ordered hierarchy parsing, qualified values, conservative names and unambiguous composite joins.
- `geography.py`: full-resolution SVY21 projection, geometry/area validation and overlap detection.
- `pipeline.py`: versioned display/projected files, provenance and reconciliation reports.
- `requirements.txt`: pinned Python geometry stack.

Inputs live in `data/raw/`; derived datasets and reports live in `data/processed/`. A byte-identical geographic display copy is generated into `frontend/public/`. `scripts/population_data.py` is the thin CLI. See the [specification](../../docs/specifications/population-data.md) and [contract](../../contracts/population-dataset.md).

Additional population adapters may be added here. Exposure calculations belong in `backend/exposure/`; browser rendering belongs in `frontend/`. No events or footprints are generated.
