# Critical sectors (energy, water, aviation, port)

System-level public evidence for infrastructure that is not modelled site by site. Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md). The national rows are placed on URA land-use parcels and scored by `facilities.py` (`pipeline.py critical_sectors`).

## Files

- `input_profiles.csv`: 13 profiles (energy 3, water 4, aviation 3, port 3), for example `ENE-ELEC`, the national electricity system with 6,111,200 beneficiaries and 8,045 MW peak demand. Columns include beneficiaries, flow and unit, vulnerability, role, recovery baseline and what D, X and A would need.
- `../output/critical_sectors/critical_sectors_output.csv` (written by the builder, git-ignored): 104 scenario rows (`BASE`, `PEAK`, `PARTIAL_2H`, ...) with people and service-loss inputs, effective service units and H/E/D/X/R/A low/central/high, state, confidence and flags per dimension.
- `input_sources.csv`: source log (agency, title, date, facts, URL, confidence, limitation).
- `input_metadata.json`: retrieval date, vector, weights (demo-v1) and the population basis.
- `input_evidence.xlsx`: the same tables as a workbook.
- `build_critical_sectors.mjs`: the builder that produced the files above.

## Facility sites (`facilities.py`, `input_facilities.csv`, output `../output/critical_sectors/facilities_output*`)

Decided 2026-09-26 (plan: `../doc/plans/2026-09-26-rank-defence-and-critical-sectors.md`): so that they can be ranked, the national evidence is placed on official URA Master Plan 2019 land-use parcels. These come from the residential sector's cache, so no network is needed; OpenStreetMap was tried first but Overpass was unreachable.

- PORT / AIRPORT parcels near Changi (4 km) or Seletar (2 km) are merged into `facility:changi_airport` (AVI-PAX share 1.0) and `facility:seletar_airport` (share 0/0.005/0.02, assumption). Parcels mostly inside a defence air-base polygon are dropped. The other PORT / AIRPORT parcels are grouped into contiguous port areas (PORT-CONT).
- Each UTILITY parcel is one site. URA does not say whether a parcel is energy or water, so utilities carry energy and water together, with ENE-ELEC's scenario bands (identical across energy and water) and a share equal to their fraction of total utility land (0.5x-1.5x band, assumption).
- Service loss = system beneficiaries x share x the MAJOR_12H loss, duration and alternative-capacity bands. Recovery maps the builder's R back to hours. Port E is an ordinal assumption (40/60/80), because throughput has no person-hour basis.
- Occupancy is AVI-PAX passengers for airports, otherwise a generic workforce density (50/200/600 per km2) x continuous-industrial coefficients, with only the share inside the placeholder footprint scored.
- Unsited, staying national (listed in the provenance): ENE-GAS, ENE-SOLAR, WAT-POT, WAT-NEW, WAT-USED and WAT-DRAIN (utilities stand in for energy and water collectively), AVI-CARGO, AVI-ATM, PORT-VES and PORT-BUNK.
- `pipeline.py critical_sectors --rebuild` rewrites `input_facilities.csv` from the cache.

## Limits

- The builder's national aggregates are unchanged. The facility shares above are labelled assumptions (land area or equal split), not operator figures.
- E is populated only for the 8 people-based profiles (energy, water, AVI-PAX). The 5 throughput profiles (AVI-CARGO, AVI-ATM, PORT-CONT, PORT-VES, PORT-BUNK) measure tonnes, TEU or aircraft, so the person-hour bands do not apply and E is unavailable; the raw `effective_service_units` are kept. E bounds come from ranges on loss, duration and alternative capacity (`loss_*`, `hours_*`, `alt_*` columns). E is 0, not 10, only when the scenario has no service loss (BASE, PEAK).
- H is populated only for AVI-PAX (assumed 3-hour dwell, grade D); V is a category-proxy assumption, not the spec's five components. R is a grade D assumption, the same per scenario in every sector. D, X and A are unavailable, so `policy_total_score` is null everywhere; null means unavailable, not zero.
- Scenarios are disruption states, not the time conditions in `conditions.py`, so the rows are not joined to the scored sectors by condition.
- `flag_*` columns carry the eight spec section 7 flags (same thresholds as `scoring.py`); `unavailable` where the input is missing. `data_stale` is unavailable because values carry no per-value source date.

## Rebuild

`node build_critical_sectors.mjs` writes the input tables into this folder and the derived scenario vectors into `../output/critical_sectors/`, which is git-ignored, so a fresh clone must run it once. The CSV and JSON files rebuild without dependencies; the `.xlsx` also needs `@oai/artifact-tool` and is left unchanged if that is missing (it is currently stale relative to the CSVs).
