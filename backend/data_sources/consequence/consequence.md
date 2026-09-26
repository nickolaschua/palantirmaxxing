# Consequence

Conditional consequence data and scoring for Singapore under the model in [docs/singapore-consequence-model.md](docs/singapore-consequence-model.md). Each site or system gets a profile per time condition, expressed as the C/E/D/X/R/A vector (C = expected casualties) with low/central/high bounds and provenance. A value with no defensible source is `unavailable`, never zero. Sites are vetoed on magnitude flags, then ranked by C with a secondary E/D/X/R/A score breaking ties (`demo-v2` placeholders), not predictions or targeting advice.

Scope: this folder only. Population inputs come from `data/processed/` and `backend/exposure/` (read only); nothing here is wired into the API or frontend.

## Sectors

Each folder has its own guide named after it.

| Folder | Covers | Form | Status |
|---|---|---|---|
| [transport/](transport/transport.md) | roads and MRT/LRT stations | code (`roads.py`, `rail.py`, `datamall.py`) | scored by `pipeline.py`; rail run, roads not yet run on real data |
| [residential/](residential/residential.md) | HDB blocks and private housing | code (`residential.py`) | scored by `pipeline.py` |
| [healthcare/](healthcare/healthcare.md) | 9 public acute hospitals, 337 MOE schools | code (`hospitals.py`, `schools.py`) | scored by `pipeline.py` |
| [parks_civic/](parks_civic/parks_civic.md) | 7,207 parks, sport and civic venues | data tables, builder and `parks_civic.py` | scored by `pipeline.py` (8 parks scenarios) |
| [critical_sectors/](critical_sectors/critical_sectors.md) | energy, water, aviation, port (system level) | data tables and builder | published evidence; not yet scored |
| [defence/](defence/defence.md) | abstract defence dependency archetypes | data tables and builder | published evidence; no sites by design |

## Shared files

- `profile.py`, `scoring.py`, `__init__.py`: `Estimate`/`Profile` contract and validation, C/E/D/X/R/A formulas with bounds, `demo-v2` veto (`veto`) and lexicographic rank (`rank_sites`), all eight flags; the public API.
- `population_disaggregation.py`: people inside the footprint for area sites (areal density, placeholder circle; spec §9.1).
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
python -m backend.data_sources.consequence.pipeline parks_civic
python -m backend.data_sources.consequence.pipeline military
python -m backend.data_sources.consequence.pipeline critical_sectors [--rebuild]
python -m backend.data_sources.consequence.pipeline rank [--condition weekday_midday|all]
python -m unittest discover -s backend/data_sources/consequence/tests -p "test_*.py"
```

Each command writes to `output/<sector>/` (override with `--out-dir`). The first run downloads sources into `cache/`; runs are resumable. Requires OSMnx 1.x and pandas < 3.

`output/` and `cache/` are not in git, so a fresh clone has none until you run a sector. Each run overwrites that sector's files (`*_output_sites.geojson`, `*_output.csv`, `*_output_provenance.json`) rather than appending. Output columns per row: `C_*` (expected casualties), `O_display_*` (dashboard only), `E/D/X/R/A_*`, `secondary_*` (tie-breaker), each with `_status`; `veto_status` (`pass`, `unknown`, `vetoed`), `veto_reasons_civilian`, `veto_reasons_capability`; `population_method` (`direct`, `areal_density`; `building_level` reserved) and `overlap_area_km2` (areal rows only). `rank` joins every scored sector, including military areas and critical-sector facilities, into `output/ranking_<condition>.csv` (veto first, then lowest C); `--condition all` ranks each condition separately and stacks them in `output/ranking_all.csv` with a `condition_id` column. `transport --only roads|rail` overwrites the same transport files with just that half. The parks_civic, critical_sectors and defence evidence tables are committed; `pipeline.py parks_civic` scores parks from them without network.
