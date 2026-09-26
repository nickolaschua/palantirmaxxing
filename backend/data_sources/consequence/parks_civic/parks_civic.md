# Parks and civic venues

Public evidence for green and civic sites, in the same H/E/D/X/R/A vocabulary as the other sectors. Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md). `parks_civic.py` routes these tables through `score_profile` (`pipeline.py parks_civic`). The builder's composite index remains a separate research baseline and is not comparable with sector totals.

## Files

- `input_sites.csv`: 7,207 sites with id, name, category, subtype, WGS84 coordinates, postal code, area, facility count, source id and native id, source update date, derivation and confidence. Subtypes: 6,240 sport venues, 455 parks, 240 community-use sites, 125 community clubs, 77 monuments, 36 theatres, 27 libraries, 7 nature reserves. Coordinates are the mean of geometry vertices.
- `input_conditions.csv`: 57,656 rows, 8 scenarios per site (weekday morning, day, evening, night; weekend day and evening; scheduled event; closed or severe weather). Each row has occupancy low/central/high and six component scores (occupancy, vulnerability, civic service, recovery/heritage, crowd concentration, access/egress) plus a composite index weighted 0.40/0.15/0.15/0.15/0.10/0.05.
- `input_metadata.json`: scenario definitions, weights, warning and the eight sources (NParks parks and facilities, SportSG, SLA, People's Association, NLB, NAC, NHB; all data.gov.sg).
- `input_evidence.xlsx`: the same tables as a workbook.
- `build_parks_civic.mjs`: the builder that produced the files above.
- `parks_civic.py`: turns each site and scenario into a `Profile`. Its outputs are the model's H/E/D/X/R/A vector, the demo-v1 total and all eight flags.

## Scored profiles

`python -m backend.data_sources.consequence.pipeline parks_civic` writes to `output/parks_civic/`. It needs no network and takes about 30 seconds.
- `parks_civic_output.csv` has 57,656 rows (8 scenarios per site) in the 35-column transport layout.
- The run also writes `parks_civic_output_sites.geojson` and `parks_civic_output_provenance.json`.

Inputs:
- Occupancy is the scenario band from the scenarios table.
- Beneficiaries are the weekend-day band, used as a regular-user proxy.
- Loss, hours of use lost, alternative share, recovery, outdoor share and hazard are per-subtype assumptions (grade D). They are calibrated so that:
  - open space keeps E at or below 25 and R at or below 30, which is road level;
  - civic buildings and monuments keep R at or below 75, which is housing and school level.
- D is unavailable and X is not computed.

On the 2026-09-25 run:
- Totals by sector (median / max): parks 20 / 44, roads and rail 44 / 47, schools 36 / 52. No parks row exceeds the transport maximum.
- `data_stale` is raised on 53,616 rows, because sport venues date from 2024 and libraries from 2017–2019.
- `uncertainty_high` is raised on 768 rows.

## Limits

- Occupancy is an area-density prior with a facility uplift (grade C): not observed attendance. Site geometry is grade A.
- The composite is a transparent baseline, not an interception, targeting or operational recommendation. Preserve the factors and uncertainty bands when reweighting.

## Rebuild

`node build_parks_civic.mjs` needs the `@oai/artifact-tool` package and the raw source downloads in `../cache/parks_civic/` (git-ignored; the nine `d_*.geojson` files are public data.gov.sg exports). It writes back into this folder.
