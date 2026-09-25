# Parks and civic venues

Public evidence for green and civic sites, in the same H/E/D/X/R/A vocabulary as the other sectors. Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md). Data only: it is not yet routed through `score_profile`, and its composite index is a separate research baseline.

## Files

- `parks-civic-sites.csv`: 7,207 sites with id, name, category, subtype, WGS84 coordinates, postal code, area, facility count, source id and native id, source update date, derivation and confidence. Subtypes: 6,240 sport venues, 455 parks, 240 community-use sites, 125 community clubs, 77 monuments, 36 theatres, 27 libraries, 7 nature reserves. Coordinates are the mean of geometry vertices.
- `parks-civic-scenarios.csv`: 57,656 rows, 8 scenarios per site (weekday morning, day, evening, night; weekend day and evening; scheduled event; closed or severe weather). Each row has occupancy low/central/high and six component scores (occupancy, vulnerability, civic service, recovery/heritage, crowd concentration, access/egress) plus a composite index weighted 0.40/0.15/0.15/0.15/0.10/0.05.
- `parks-civic-metadata.json`: scenario definitions, weights, warning and the eight sources (NParks parks and facilities, SportSG, SLA, People's Association, NLB, NAC, NHB; all data.gov.sg).
- `singapore-parks-civic-evidence.xlsx`: the same tables as a workbook.
- `build_parks_civic.mjs`: the builder that produced the files above.

## Limits

- Occupancy is an area-density prior with a facility uplift (grade C): not observed attendance. Site geometry is grade A.
- The composite is a transparent baseline, not an interception, targeting or operational recommendation. Preserve the factors and uncertainty bands when reweighting.

## Rebuild

`node build_parks_civic.mjs` needs the `@oai/artifact-tool` package and the raw source downloads in `../cache/parks_civic/` (git-ignored; the nine `d_*.geojson` files are public data.gov.sg exports). It writes back into this folder.
