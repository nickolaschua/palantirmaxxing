# Singapore Defense Tech Hackathon

This repository combines **Singapore Canvas**, an existing CesiumJS/TypeScript/Vite 3D viewer of Singapore, with implemented Census 2020 population preparation and a standalone Population Exposure Calculator (PEC) v0.1. All existing application source, configuration, assets and frontend documentation remain in `frontend/`.

The implemented standalone Population Exposure Calculator (PEC) receives versioned population zones and externally supplied circular event footprints. PEC v0.1 is deterministic and assumes population is uniformly distributed within each zone. It reports per-event and episode-unique people potentially exposed, total person-exposures, people exposed to multiple events, population-data coverage and calculation metadata. The machine-side static MVP now composes existing deterministic trajectory/reachability, an explicitly synthetic monotonic success profile, supplied fixed circles, PEC, two-objective Pareto filtering and descriptive representative categories. It does not predict real footprints, interception performance, casualties or injuries, and it does not select a final action.

## Current status

The viewer now presents **Singapore Resident Population — Census 2020** with population/density shading, fixed legend, unknown-data styling, search, planning-area filtering, ranked chart and hover/click details. It preserves the existing camera, lighting and basemap controls, adding a plain globe for use without remote credentials. Polygon rendering and picking are reusable library capabilities; population-specific logic remains in the demo application.

The Python preparation pipeline acquires official Census 2020 and URA Master Plan 2019 files, verifies a local cache, parses the source hierarchy, joins zones, projects to SVY21 metres and generates provenance and validation reports. All 332 subzones join uniquely. There are 46 qualified unknown population values, six invalid geometries and seven overlap pairs; 275 zones containing 3,982,190 residents qualify for a **partial-coverage PEC-candidate subset**. Known display counts total 4,044,340, or 130 above the published national total; no counts are adjusted.

Read the [population preparation specification](docs/specifications/population-data.md), [file contract](contracts/population-dataset.md), [validation summary](data/processed/validation-summary.md) and [browser/check report](frontend/docs/POPULATION-VERIFICATION.md). Standalone PEC calculation, strict file execution, tests and [PEC specification](docs/specifications/pec.md) are implemented under the [PEC contracts](contracts/pec.md). The [static-scenario contract](contracts/static-scenario-evaluation.md) and [benchmark report](docs/specifications/static-mvp-benchmark.md) document machine-side Phases D-G. Frontend PEC integration, endpoints, dynamic replanning, resource allocation and databases are not implemented. Existing historical frontend scenario-design notes remain preserved.

## Repository structure

Every new folder contains its same-named Markdown guide; the existing frontend has `frontend.md`. The tree shows the assessment skeleton and key existing frontend content, omitting dependency and generated directories. The folder guides describe implementation files within each area; the following is the architectural skeleton.

```text
.
├── README.md
├── .gitignore
├── backend/
│   ├── backend.md
│   ├── api/api.md
│   ├── domain/domain.md
│   ├── exposure/exposure.md
│   ├── orchestration/orchestration.md
│   └── data_sources/data_sources.md
├── frontend/
│   ├── frontend.md
│   ├── src/                     # library, population explorer, demo and map assets
│   ├── public/public.md          # generated population.geojson served here
│   ├── docs/                    # existing API design and baseline screenshots
│   ├── CODEBASE-SUMMARY.md
│   ├── package.json
│   ├── package-lock.json
│   ├── index.html
│   ├── singapore-3d.html
│   ├── .env.example
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── vite.lib.config.ts
├── contracts/
│   ├── contracts.md
│   └── examples/examples.md
├── data/
│   ├── data.md
│   ├── raw/raw.md
│   ├── processed/processed.md
│   ├── scenarios/scenarios.md
│   └── results/results.md
├── tests/
│   ├── tests.md
│   ├── unit/unit.md
│   ├── integration/integration.md
│   └── fixtures/fixtures.md
├── docs/
│   ├── docs.md
│   ├── architecture/architecture.md
│   └── specifications/specifications.md
└── scripts/
    └── scripts.md
```

Folder guides:

| Area | Documentation |
|---|---|
| Backend | [Overview](backend/backend.md), [API](backend/api/api.md), [domain](backend/domain/domain.md), [PEC](backend/exposure/exposure.md), [orchestration](backend/orchestration/orchestration.md), [data sources](backend/data_sources/data_sources.md) |
| Frontend | [Singapore Canvas](frontend/frontend.md), [public assets](frontend/public/public.md) |
| Contracts | [Overview](contracts/contracts.md), [examples](contracts/examples/examples.md) |
| Data | [Overview](data/data.md), [raw](data/raw/raw.md), [processed](data/processed/processed.md), [scenarios](data/scenarios/scenarios.md), [results](data/results/results.md) |
| Tests | [Overview](tests/tests.md), [unit](tests/unit/unit.md), [integration](tests/integration/integration.md), [fixtures](tests/fixtures/fixtures.md) |
| Documentation | [Overview](docs/docs.md), [architecture](docs/architecture/architecture.md), [specifications](docs/specifications/specifications.md) |
| Utilities | [Scripts](scripts/scripts.md) |

## Assessment flow

For standalone PEC: prepared eligible population and supplied footprints → PEC validation and calculation → structured JSON results.

For the static MVP: deterministic trajectory/reachability → reachable candidates → synthetic success and supplied circles → existing footprint-assessment adapter → complete-coverage eligibility → Pareto frontier → descriptive category alternatives. Frontend connection remains future work.

The implemented source adapter preserves raw population files and prepares validated, versioned zones. The thin file command loads those zones and supplied episodes, invokes standalone PEC, and writes exposure results, coverage and metadata under shared contracts. Future application orchestration and frontend integration can reuse the calculator. See [architecture](docs/architecture/architecture.md) for folder boundaries.

Storage starts with files in `data/`. Generated results are ignored by Git while Markdown documentation remains trackable; small scenarios and test fixtures can remain under version control. No database or database dependency is introduced.

## Run locally

Data preparation uses Python 3.9–3.12. Frontend commands require Node.js 22.12 or later. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/data_sources/requirements.txt

# Reuses a verified local cache; downloads only if no cache exists.
.venv/bin/python scripts/population_data.py acquire
# Offline: produces processed files and frontend/public/population.geojson.
.venv/bin/python scripts/population_data.py prepare

npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. The plain globe requires no credentials. For remote terrain/OSM buildings or Google photorealistic tiles, copy `frontend/.env.example` to `frontend/.env.local` and configure the existing provider values; do not commit credentials. Vite's `VITE_*` values are browser-visible provider configuration, so use provider restrictions.

Refresh only when explicitly desired:

```sh
.venv/bin/python scripts/population_data.py acquire --refresh
.venv/bin/python scripts/population_data.py prepare
```

If online acquisition fails, import complete official files of the same Census 2020/MP2019 datasets, then prepare offline:

```sh
.venv/bin/python scripts/population_data.py acquire \
  --population-file /path/to/official-population.csv \
  --boundary-file /path/to/official-mp2019.geojson
.venv/bin/python scripts/population_data.py prepare
```

The population file may also be a complete successful datastore-search JSON response. Local-import timestamps are labelled as such. A failed/truncated download is rejected before cache replacement; a checksum mismatch stops preparation. Optional `DATA_GOV_SG_API_KEY` can be supplied through the environment for official API rate limits.

Run offline checks and builds:

```sh
.venv/bin/python -m unittest discover -s tests/unit -p 'test_*.py'
.venv/bin/python -m unittest discover -s tests/integration -p 'test_*.py'
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run build:lib
npm --prefix frontend run preview -- --host 127.0.0.1
```

Run the deterministic machine-side MVP benchmark. It prepares population before
timing, performs one warm-up and seven measured runs, and writes an ignored full
result artifact:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/benchmark_static_mvp.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/benchmark_static_mvp.py --markdown
```

The bundled speeds, turn rate, coordinates, footprint radius, population
geometry and counts are intentionally scaled synthetic inputs. They preserve a
tested reachability pattern and produce a low-to-high-to-lower exposure path;
they are not operational performance estimates.

The production preview normally opens at `http://127.0.0.1:4173/`. Run preparation before building: Vite copies `frontend/public/population.geojson` into the demo build. Missing data produces a visible error/retry state. The reusable library build remains separate.

## Run standalone PEC

No frontend or network is required when population input is available. Reuse the existing pinned Python environment (Python 3.9–3.12):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/data_sources/requirements.txt
.venv/bin/python scripts/population_exposure.py \
  --population tests/fixtures/pec-population.json \
  --episode data/scenarios/pec-example.json \
  --output data/results/pec-example.json
```

The small synthetic example produces complete coverage with approximately 50.2453 unique people potentially exposed, 50.2453 person-exposures and zero multiple-event exposure. JSON retains unrounded values. The [reference output](contracts/examples/pec-result.json) is checked in; runtime results remain ignored. Supplied synthetic coordinates do not represent a real Singapore hazard location.

For actual eligible data, create an episode following [the contract](contracts/pec.md), using population ID `sg-residents-2020-mp2019`, the exact `metadata.dataset_version` in `data/processed/population-projected.json`, and EPSG:3414 easting/northing metres:

```sh
.venv/bin/python scripts/population_exposure.py \
  --population data/processed/population-projected.json \
  --episode data/scenarios/your-episode.json \
  --output data/results/your-result.json

# Offline 100-event runtime and 128/256-edge sensitivity measurement:
.venv/bin/python scripts/benchmark_exposure.py
```

`your-episode.json` is a caller-supplied file, not a bundled example. PEC accepts only the eligible projected artifact or canonical validated population input; it never substitutes the display dataset. Add `--circle-edges 256` for a higher-resolution calculation. Default circles have 128 edges. Areas and exposure all use that polygon geometry. Missing area above `1e-6 m²` yields `partial_coverage`: complete totals are null, known-area totals remain available. Valid complete/partial results exit 0; invalid input exits 2 with structured errors; file errors exit 1.

The reusable Python interface is `prepare_population(document)` followed by `calculate_episode(prepared, episode, CalculationSettings())` from `backend.exposure`; reuse prepared geometry across episodes. Dataset preparation failures raise `PECValidationError`; invalid episodes return `invalid_input` without aggregates.

Measured on macOS ARM64, Python 3.9.6, Shapely 2.0.7/GEOS 3.11.4: a 100-event case over 275 zones took a median 0.154 seconds at 128 edges, plus 0.093 seconds for dataset preparation. At 256 edges it took 0.204 seconds. These are local measurements, not a real-time guarantee. Known unique exposure increased 0.00848%; one event changed coverage status. See [full measurement and sensitivity findings](docs/specifications/pec-benchmark.md).

The prepared coverage still excludes 57 zones, including qualified unknown counts and problematic geometry. Historical population, uniform density, reconciliation limits and circle approximation remain material limitations; PEC does not establish real-world hazard validity. See [specification](docs/specifications/pec.md).

## Tracked and generated files

Source code, folder guides, small official test excerpts, the dataset contract, provenance and validation reports are versionable. Large raw source snapshots, raw acquisition manifest, processed display/projected geometry, the public display copy, dependencies and builds are ignored. Existing Git ignore rules are preserved; all of `data/` is **not** ignored. Preserve a copy of the checksum-identified raw snapshot when archiving a run; repeat `prepare` uses no network. No `.gitkeep` files or nested repositories are introduced.

See the historical [codebase summary](frontend/CODEBASE-SUMMARY.md) and [API design](frontend/docs/API-DESIGN.md) for original viewer architecture and planned scenario features; the current [frontend guide](frontend/frontend.md) documents this milestone.

## Open decisions

- General backend service language/runtime and transport remain undecided; Python/Shapely/pyproj is selected for offline preparation and standalone PEC.
- PEC v0.1 preserves historical counts and nulls complete totals for partial coverage; broader application integration remains future work.
- Resolving source-invalid geometries and positive-area slivers would require an explicitly documented repair policy or corrected official boundaries; none is silently applied here.
- Persistent storage starts with files. Reconsider a database if shared editing or searchable run history becomes necessary.
