# Simulation result contracts

The simulation delivery route accepts two independent payload versions.
`simulation-result/1` remains the legacy fixed-size seed export.
`simulation-result/2` is the checked frozen-scenario export with variable
episode sizes, explicit outcomes, policy scope, and immutable provenance.

## `simulation-result/1`

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

`consequenceSummary.ordinalObjectiveCost` is the sum of eight immutable ordinal
event costs. Each cost is ranked once against that threat's complete 160-row
candidate universe and is never renormalized after reservations or time
progression. It is not a physical consequence unit. Raw population,
expected-casualty bounds, secondary scores, intersected sites, unavailable
fields, source versions, and assumptions stay in `physicalComponents` and
`evidence`.

The mandated labels are “supplied 100 m area,” “people potentially exposed,”
and “assumption-grade expected casualties.” A consumer must not relabel the
circle as a validated blast radius.

## Comparison and provenance

`policyVersusBaseline` records both identities and costs, measured relative
improvement, claim text, and the immutable assignment plan. The baseline is
`feasible-immediate-matching/1`, an offline full-episode comparator that first
chooses each pair's earliest eligible candidate and then finds a complete
one-to-one matching minimizing total interception time.

`optimal-fixed-rank-assignment/1` is exact only within its stated proof scope:
immutable additive candidate costs, one-use interceptors, complete threat
coverage, and no operational update that changes later costs. Its predicted
cost must equal a replay through the real event engine. This is not a claim of
physical or operational global optimality.

`provenance` includes the canonical episode hash, simulator and generator
versions, scenario/generator configuration checksums, main-island geometry and
boundary-source checksums, and provider data/config/cache identities and source
checksums. Canonical result JSON excludes provider wall-clock timings; benchmark
reports retain timing separately. Constraint-violating episodes are forbidden.

The checked baseline example is `data/results/demo-simulation-result.json`.
Generation and frontend validation are implemented by
`backend/presentation/simulation_result.py` and
`frontend/src/demo/simulation-model.ts`.

## `simulation-result/2`

Version 2 retains `episodeSchemaVersion: "simulation-episode/2"` and the same
trajectory, event, consequence, coordinate-reference, wording, and limitation
semantics. It changes the result cardinalities and adds these required records:

- `trajectories`: 2–8 distinct threats, each with exactly 20 ordered samples;
- `outcomes`: exactly one `intercepted` or `unhandled` row per threat;
- `assignments` and `selectedFootprints`: zero through the threat count, with
  exactly one of each for every intercepted outcome and none for unhandled
  outcomes;
- `terminalCounterfactualFootprints`: exactly one for every threat;
- `policy`: the active fixed policy identity and its information scope;
- `policyComparison`: active, naive-online, and exact-reference replay records;
- `termination`: the active replay's completion and constraint state; and
- `provenance`: the checked scenario reference and all identities required to
  reproduce and verify it.

Assignment threat, interceptor, and opportunity IDs are unique. Selected
footprints resolve to assignments exactly. Every outcome covers one trajectory;
an intercepted outcome names its locked interceptor and opportunity, while an
unhandled outcome names neither.

The supported policy identities and labels are:

| Policy | Information scope |
| --- | --- |
| `naive-launch-on-detection/1` | `online-detected-only` |
| `feasible-immediate-matching/1` | `offline-full-episode` |
| `optimal-fixed-rank-assignment/1` | `offline-full-episode` |

The exact reference must be a completed replay of
`optimal-fixed-rank-assignment/1`. Its predicted cost must equal its replayed
cost, and `exact` and `predictedCostMatchesReplay` must both be true. A completed
active replay has `all_threats_resolved`, satisfied constraints, and an exact
regret equal to active cost minus exact cost. A recorded failure has a
`constraint_violation:` reason, a nonempty violation, at least one unhandled
threat, and no exact-regret claim. Naive failures remain in the result rather
than being discarded.

`provenance` carries `scenarioRef`, split, profile, seed, generator and
distribution versions, distribution checksum, public and runtime provider
identities, provider/source/configuration/geometry checksums, simulator version,
the canonical episode hash, `hashVerified: true`, and the active policy identity.
The scenario reference must use its declared split. All digest fields use
`sha256:` followed by 64 lowercase hexadecimal digits.

Backend publication validation and the frontend parser both reject nonfinite
numbers, count or identity mismatches, unsupported policies or information
labels, false exactness, and inconsistent provenance. Generation is implemented
by `simulation_result_v2_to_dict` in
`backend/presentation/simulation_result.py`.
