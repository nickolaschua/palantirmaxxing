# Consequence

Conditional consequence data and scoring for Singapore under the model in [docs/singapore-consequence-model.md](docs/singapore-consequence-model.md). Each site or system gets a profile per time condition, expressed as the H/E/D/X/R/A vector with low/central/high bounds and provenance. A value with no defensible source is `unavailable`, never zero. Scores are a demonstration blend (`demo-v1`), not predictions or targeting advice.

Scope: this folder only. Population inputs come from `data/processed/` and `backend/exposure/` (read only); nothing here is wired into the API or frontend.

## Sectors

Each folder has its own guide named after it.

| Folder | Covers | Form | Status |
|---|---|---|---|
| [transport/](transport/transport.md) | roads and MRT/LRT stations | code (`roads.py`, `rail.py`, `datamall.py`) | scored by `pipeline.py`; rail run, roads not yet run on real data |
| [residential/](residential/residential.md) | HDB blocks and private housing | code (`residential.py`) | scored by `pipeline.py` |
| [healthcare/](healthcare/healthcare.md) | 9 public acute hospitals, 337 MOE schools | code (`hospitals.py`, `schools.py`) | scored by `pipeline.py` |
| [parks_civic/](parks_civic/parks_civic.md) | 7,207 parks, sport and civic venues | data tables and builder | published evidence; not yet scored |
| [critical_sectors/](critical_sectors/critical_sectors.md) | energy, water, aviation, port (system level) | data tables and builder | published evidence; not yet scored |
| [defence/](defence/defence.md) | abstract defence dependency archetypes | data tables and builder | published evidence; no sites by design |

## Shared files

- `profile.py`, `scoring.py`, `__init__.py`: `Estimate`/`Profile` contract and validation, H/E/D/X/R/A formulas with bounds, `demo-v1` total, all eight flags; the public API.
- `conditions.py`: the six recurring time conditions used by every scored sector.
- `sources.py`: cached downloads (data.gov.sg, MOH, census, OneMap geocoding).
- `paths.py`: cache, output and population locations.
- `pipeline.py`: shared row and CSV helpers and the one command line for the three scored sectors.
- `docs/`: the model specification.
- `tests/`: offline unit tests (scoring, sources, transport, residential, healthcare).
- `cache/`, `output/`: downloads and results, git-ignored and safe to delete. `requirements.txt`.

## Run

```bash
pip install -r backend/data_sources/consequence/requirements.txt
python -m backend.data_sources.consequence.pipeline transport [--only roads|rail] [--volume-month YYYYMM]
python -m backend.data_sources.consequence.pipeline residential
python -m backend.data_sources.consequence.pipeline healthcare [--refresh]
python -m unittest discover -s backend/data_sources/consequence/tests -p "test_*.py"
```

Each command writes to `output/<sector>/` (override with `--out-dir`). The first run downloads sources into `cache/`; runs are resumable. Requires OSMnx 1.x and pandas < 3.

`output/` and `cache/` are not in git, so a fresh clone has none until you run a sector. Each run overwrites that sector's files (`*_sites.geojson`, `*_profiles.csv`, `provenance.json`) rather than appending; `transport --only roads|rail` overwrites the same transport files with just that half. The parks_civic, critical_sectors and defence tables are committed and need no run.
