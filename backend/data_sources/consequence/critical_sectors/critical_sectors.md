# Critical sectors (energy, water, aviation, port)

System-level public evidence for infrastructure that is not modelled site by site. Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md). Data only: not yet routed through `score_profile`.

## Files

- `critical-sectors-profiles.csv`: 13 profiles (energy 3, water 4, aviation 3, port 3), for example `ENE-ELEC`, the national electricity system with 6,111,200 beneficiaries and 8,045 MW peak demand. Columns include beneficiaries, flow and unit, vulnerability, role, recovery baseline and what D, X and A would need.
- `critical-sectors-scenarios.csv`: 104 scenario rows (`BASE`, `PEAK`, `PARTIAL_2H`, ...) with people and service-loss inputs, effective service person-hours and H/E/D/X/R/A low/central/high, state and confidence per dimension.
- `critical-sectors-sources.csv`: source log (agency, title, date, facts, URL, confidence, limitation).
- `critical-sectors-metadata.json`: retrieval date, vector, weights (demo-v1) and the population basis.
- `singapore-critical-sectors-evidence.xlsx`: the same tables as a workbook.
- `build_critical_sectors.mjs`: the builder that produced the files above.

## Limits

- National aggregates only. Do not allocate them to specific facilities or invent component locations.
- Only E and R are populated (R is a grade D assumption). H, D, X and A are unavailable, so `policy_total_score` is null everywhere; null means unavailable, not zero.

## Rebuild

`node build_critical_sectors.mjs` needs `@oai/artifact-tool` and writes back into this folder.
