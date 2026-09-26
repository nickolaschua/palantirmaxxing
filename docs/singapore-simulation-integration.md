# Singapore simulation and Emmanuel consequence integration

Status: implemented and smoke-verified on 2026-09-26.

This path is additive. The existing `planning-result/1`, synthetic scenario
generator, and `DeterministicToyProvider` remain regression fixtures. The new
end-to-end path is:

```text
singapore-scenario/1
  -> simulation-episode/2
  -> 3D threat trajectories and 2D interceptor reachability
  -> complete 8-by-8 feasible matching
  -> 100 m supplied candidate footprints
  -> Singapore population and site intersections
  -> Emmanuel demo-v2 veto/tie-band/secondary ordering
  -> normalized ordinal event costs
  -> simulation / centralized-observation/2 / MaskablePPO
  -> simulation-result/1
```

## Frozen scenario contract

`SingaporeScenarioConfig` fixes eight threats, eight one-use synthetic
interceptors, 20 samples for every threat/interceptor pair, detection times in
`[0, 10]` seconds, EPSG:3414 coordinates, a 10,000 m outer detection boundary,
a 5,000/10,000/15,000 m triangular detection-altitude distribution, 250 m/s
horizontal threat speed, gravity of 9.80665 m/s², a supplied 100 m footprint,
and the `weekday_midday` condition. Heights are relative to the synthetic
terminal ground plane.

The main-island polygon is the largest valid connected polygon obtained by
projecting and unioning `data/raw/boundaries.geojson`. Source and derived WKB
checksums are recorded in each episode. Detection positions are sampled by arc
length on a 128-segment-per-quadrant 10 km buffer exterior. Terminal positions
are sampled uniformly by area with rejection sampling. Independent deterministic
streams isolate detection, terminal, altitude, and interceptor draws. Failed
threats retry without perturbing other threats, up to 100 attempts.

An episode is accepted only if a bipartite maximum matching covers all eight
threats with distinct interceptors. An edge requires at least one physically
reachable and consequence-eligible candidate. The assignment lock remains the
one-time interceptor-consumption point.

## Consequence bridge

`SingaporeConsequenceProvider` builds an immutable indexed catalog at startup:

- prepared population zones from `population-projected.json`;
- parks and civic point sites from the checked-in consequence inputs;
- military polygons decoded from the checked-in frontend geometry;
- critical-facility polygons and locally rebuilt `weekday_midday` / `MAJOR_12H`
  profiles from checked-in inputs.

All supplied circles use the Population Exposure Calculator's 128-edge
representation and are clipped to the main-island polygon. Fully off-island
circles have zero Singapore population exposure. Point assets receive full
direct effect when intersected. Polygon occupancy and beneficiary estimates
are multiplied by `intersection area / site area`; loss fractions, outage,
alternatives, and recovery values are not changed.

PEC population is the authoritative aggregate human-exposure row, so site
profiles do not double-count casualties. The adapter calls Emmanuel's existing
`score_profile`, `veto`, and `rank_sites` functions without changing their
formulas. Missing vulnerability remains unavailable and widens the population
casualty estimate under the existing demo-v2 rule. Site casualty values remain
diagnostic; service and capability dimensions aggregate from intersected site
profiles.

Eligible candidates are ordered by the existing sequence: veto rejection,
central expected casualties, the existing 10%/0.5 casualty tie band, then the
existing secondary score. Dense ordinal position normalized to `[0, 1]` is the
only event training cost. Eight event costs are summed. Physical population,
casualty, and service evidence remains separate. Assignment-time assessments
are snapshotted and later evaluation reads that snapshot, not the mutable
provider cache. Unhandled threats return an explicit constraint failure.

Transport, healthcare/education, and richer residential-service inputs are
reported as unavailable sectors; they are never coerced to zero.

## Versioned outputs

`simulation-result/1` is separate from `planning-result/1`. It contains:

- eight WGS84 trajectories with absolute timestamps and height;
- detections, assignments, locks, and interceptions;
- selected and terminal-counterfactual supplied footprints;
- population and sector summaries, physical evidence, and ordinal cost;
- the policy/baseline comparison and complete checksum provenance;
- explicit modeling limitations and controlled wording.

The frontend parses this schema independently. The checked-in result currently
uses the immediate-interception baseline for both sides of the comparison. It
therefore reports a measured comparison, not an improvement or optimality
claim. UI text says “supplied 100 m area,” “people potentially exposed,” and
“assumption-grade expected casualties.”

## Commands

Use the combined `.venv-rl` environment, which contains the geospatial and RL
dependencies:

```bash
.venv-rl/bin/python scripts/benchmark_singapore_simulation.py
.venv-rl/bin/python scripts/train_rl.py \
  --provider singapore-demo-v2 --generator singapore-v1 \
  --output-dir data/results/rl/singapore-smoke --steps 16 --seed 7
.venv-rl/bin/python scripts/export_simulation_result.py --seed 7
.venv-rl/bin/python -m pytest -q
(cd frontend && npm test && npm run build)
```

Explicit CLI choices are `--provider toy|singapore-demo-v2` and
`--generator synthetic|singapore-v1`. Model loading checks provider, generator,
configuration, observation layout, and dependency identities. Old observation
or normalization artifacts are rejected.

## Verification evidence

The reproducible seed-7 benchmark is stored in
`data/results/singapore-simulation-benchmark.json`:

| Check | Measured result |
| --- | ---: |
| Catalog/provider cold start | 2041.70 ms |
| Complete 1,280-candidate episode generation | 510.25 ms |
| First 160-candidate consequence set, cold | 15.61 ms |
| Same set, warm cache | 1.11 ms |
| Immediate-baseline full episode | 168.76 ms |
| Environment step p95 | 28.11 ms |
| Smoke-policy masked inference p95, 30 samples | 0.19 ms |
| Peak traced benchmark memory | 70,460,713 bytes |

The baseline and deterministic environment both terminated normally with all
eight threats resolved. The 16-step smoke model trained in 0.65 seconds, then
reloaded with its normalization artifact and produced a valid masked action.
This proves plumbing only; it is not performance evidence for a learned policy.

Verification on 2026-09-26:

- backend: 308 passed;
- frontend: 18 passed;
- production frontend TypeScript/Vite build: passed (with the existing bundle
  size advisory);
- checked result, benchmark, and model metadata: strict JSON parse passed.

## Claims intentionally withheld

The 64 validation, 256 held-out, 32 stress, and bounded-oracle suites are
versioned but have not been executed for a trained Singapore policy. No learned
policy improvement, optimality, calibrated casualty prediction, validated
blast/debris radius, interceptor-altitude behavior, aircraft downtime, recovery
transition, terrain, wind, or drag claim is supported by the MVP.
