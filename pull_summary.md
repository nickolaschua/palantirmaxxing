# Recent pull from `main`

**Pull:** PR #3, `Add military, facility and parks scoring plus all-condition cross-sector ranking`
**Range:** `93ebb72` → `e12bb11` (pulled 26 September 2026)
**Scope:** 52 changed files, primarily under `backend/data_sources/consequence/`.

## What changed

- Replaced the demonstration's blended `H` total with a `demo-v2` consequence model. Human harm is expressed as expected casualties (`C`); sites receive a veto status from consequence flags and are then ordered by `C`, with a weighted `E/D/X/R/A` score breaking close ties. Scores retain low, central and high estimates.
- Added area-based population disaggregation for large residential areas, military areas and critical facilities. It estimates people within a placeholder footprint from site area and overlap, and records the method in the output.
- Added scored profiles for parks and civic venues, military land polygons, and critical-sector facilities. The facility profiles place parts of national aviation, port and utility evidence on land-use parcels. Missing capability and dependency inputs remain unavailable.
- Added `pipeline.py rank`, which combines sector CSVs for one time condition or produces separately ranked results for all six shared conditions. Sector outputs were renamed to `*_output.csv` with matching site and provenance files.
- Renamed several committed evidence files to the `input_*` convention and expanded the model documentation and unit tests.

## Verification and review findings

- `python -m unittest discover -s backend/data_sources/consequence/tests -p 'test_*.py'` passed: **123 tests**.
- The new `military` command fails on this checkout because its required, git-ignored `output/defence/defence_output.csv` has not been generated. `critical_sectors` likewise fails because `output/critical_sectors/critical_sectors_output.csv` is absent. The documented commands need their input-generation steps or should generate these inputs themselves.
- `rank --condition all` does not include parks in `weekend_night`: the parks condition map has no entry for the ordinary `WE_PM` weekend-evening scenario. Its time window differs from the shared condition, so the mapping needs an explicit decision.

## Relevant files

- `backend/data_sources/consequence/scoring.py` — `demo-v2` scoring, veto and ranking.
- `backend/data_sources/consequence/pipeline.py` — sector commands, output writing and cross-sector ranking.
- `backend/data_sources/consequence/population_disaggregation.py` — area-based occupancy estimate.
- `backend/data_sources/consequence/parks_civic/parks_civic.py`, `defence/military.py`, and `critical_sectors/facilities.py` — new sector profiles.
- `backend/data_sources/consequence/docs/singapore-consequence-model.md` — updated model specification.
