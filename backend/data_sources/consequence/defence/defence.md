# Defence and sensitive dependencies

Abstract, non-geographic evidence about how civil infrastructure failures could degrade defence-relevant functions. Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md). Data only.

## Files

- `defence-dependency-archetypes.csv`: 8 archetypes (`AR-01`..`AR-08`, for example continuity of government, civil-military communications, air mobility) with civil dependencies, consequences and the fields an operator would supply.
- `defence-global-evidence.csv`: 8 documented international cases (event, system, consequences, metrics, source, confidence).
- `defence-resilience-scenarios.csv`: scenarios such as external power loss and communications degradation, with what to observe and which dimensions they touch.
- `defence-dependency-input-template.csv`: empty template for authorised operator input.
- `defence-authorised-D-contract.csv`: the allowed fields for supplying the capability dimension (opaque id, capability share band, loss fraction band).
- `defence-dependencies-metadata.json`: scope, vector, weights and the warning.
- `singapore-defence-dependencies-evidence.xlsx`: the same tables as a workbook.
- `build_defence_dependencies.mjs`: the builder that produced the files above.

## Limits

Do not use this folder to identify, map, rank or infer specific defence sites, readiness, vulnerabilities or single points of failure. D stays unavailable until supplied through an authorised interface.

## Rebuild

`node build_defence_dependencies.mjs` needs `@oai/artifact-tool` and writes back into this folder.
