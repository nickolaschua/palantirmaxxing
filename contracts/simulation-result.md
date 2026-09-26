# `simulation-result/1` contract

`simulation-result/1` is the frontend handoff for a complete
`simulation-episode/2` rollout. It is independent from and does not replace
`planning-result/1`.

## Required top-level fields

- `schemaVersion`: exactly `simulation-result/1`.
- `episodeSchemaVersion`: exactly `simulation-episode/2` for generated Singapore
  results.
- `episodeId`, nonnegative integer `seed`, and ISO-8601 `start` / `end`.
- `coordinateReferenceSystems`: calculation, presentation, and vertical
  reference labels.
- `trajectories`: exactly eight threat trajectories.
- `assignments`: exactly eight successful assignments for an accepted generated
  episode.
- `events`: ordered detection, assignment, lock, and interception records.
- `selectedFootprints` and `terminalCounterfactualFootprints`: exactly eight of
  each for the baseline artifact.
- `consequenceSummary`, `policyVersusBaseline`, `provenance`, and `limitations`.

All JSON numbers must be finite. IDs must be unique in their relevant arrays.

## Trajectories

Every trajectory has `threatId`, `detectionTimeS`, `detectionTime`, and ordered
`samples`. A sample supplies:

- one-based `sampleIndex`;
- `timeFromDetectionS`, `timeFromEpisodeStartS`, and absolute `time`;
- `position.lon`, `position.lat`, and nonnegative `position.heightM`;
- `verticalVelocityMps`.

The final sample is the sampled WGS84 terminal position with `heightM = 0`
within the generator's numeric tolerance. Height means height above the
synthetic terminal ground plane, not surveyed elevation.

## Footprints and consequence evidence

Each footprint has a WGS84 `center`, `radiusM = 100`, stable ID, `threatId`,
`kind`, and `label`. A selected footprint also has `opportunityId` and the
snapshotted candidate consequence. Terminal footprints are counterfactual
evidence and are not rollout outcomes.

`consequenceSummary.ordinalObjectiveCost` is the sum of eight normalized dense
ordinal event costs. It is not a physical consequence unit. Raw population,
expected-casualty bounds, secondary scores, intersected sites, unavailable
fields, source versions, and assumptions stay in `physicalComponents` and
`evidence`.

The mandated labels are “supplied 100 m area,” “people potentially exposed,”
and “assumption-grade expected casualties.” A consumer must not relabel the
circle as a validated blast radius.

## Comparison and provenance

`policyVersusBaseline` records both identities and costs, measured relative
improvement, the claim text, and nullable exact-oracle evidence. The word
“optimal” is allowed only when exact bounded-oracle evidence supports it.

`provenance` includes the canonical episode hash, simulator and generator
versions, scenario/generator configuration checksums, main-island geometry and
boundary-source checksums, and provider data/config/cache identities and source
checksums.

The checked baseline example is `data/results/demo-simulation-result.json`.
Generation and frontend validation are implemented by
`backend/presentation/simulation_result.py` and
`frontend/src/demo/simulation-model.ts`.
