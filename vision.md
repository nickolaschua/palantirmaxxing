# Project vision and current reality

Updated 26 September 2026 against the current local working tree. This document
is the shared product framing for the Singapore defence tech hackathon project.
It separates the target product, the implemented demonstrator, and the claims
the current evidence can support.

## The target product

Build a Singapore-focused simulation and learning demonstrator that makes the
consequences and trade-offs of hypothetical interception choices inspectable.
The intended end product is an RL agent trained across many Singapore-specific,
multi-threat scenarios to recommend an interception choice quickly. Earlier
decisions consume finite shared resources and affect later choices in the same
episode.

The frontend is the explanation and demonstration surface. It should show the
scenario, trajectories, available choices, selected action, consequence
evidence, uncertainty, provenance, and comparison with a simple fixed baseline.
It is not the scientific or physical model itself.

The eventual demo claim is that the team trained an agent on many reproducible
Singapore-specific simulations and measured how its choices compare with an
immediate-interception baseline. “Optimal” is not part of the current claim. It
requires a frozen objective, held-out evaluation, constraint compliance,
bounded-oracle evidence, and measured end-to-end inference time.

## What is implemented now

| Area | Current implementation |
| --- | --- |
| Population data | Versioned Singapore Census 2020 resident-population geography with provenance, exclusions, and explicit partial coverage. |
| Exposure calculation | Deterministic PEC estimates people potentially within caller-supplied circular areas. It does not predict casualties or damage. |
| Static demo | The original single-scenario `planning-result/1` path remains available as a regression fixture. |
| Singapore scenario generator | `singapore-scenario/1` generates exactly eight threats and eight one-use synthetic interceptors, 3D parabolic threat trajectories, 20 samples per pair, and a complete feasible assignment in EPSG:3414. |
| Consequence bridge | Candidate-centered supplied 100 m circles are intersected with population and available site geometries, then passed through Emmanuel's existing demo-v2 scoring and ordering. |
| Event simulator | A deterministic continuous-event engine handles detection, tentative assignment, assignment lock, resource consumption, interception, and defensive failure paths. |
| Learning system | A centralized masked Gymnasium environment, MaskablePPO training/loading, normalization persistence, evaluation utilities, fixed seed suites, and bounded-oracle plumbing are implemented. |
| Result and frontend | A separate `simulation-result/1` contract, seed-7 baseline artifact, parser, and frontend view display eight trajectories, events, footprints, consequences, provenance, and limitations. |
| Live API | Not implemented. The frontend consumes checked result artifacts. |

The implemented flow is:

```text
seeded Singapore episode
  -> 3D threat paths and 2D interceptor reachability
  -> complete one-to-one resource feasibility
  -> supplied candidate and terminal footprints
  -> population and available sector intersections
  -> Emmanuel demo-v2 ordering
  -> normalized ordinal event costs
  -> baseline or masked policy rollout
  -> versioned result and frontend explanation
```

The old static demo and deterministic toy provider remain intentionally. They
are regression fixtures, not competing descriptions of the current Singapore
path.

## Current scenario and objective

The current MVP uses exactly eight threats detected over ten seconds, eight
one-use synthetic interceptors, Singapore main-island geometry, a 10 km outer
detection boundary, triangular 5/10/15 km detection altitude, 250 m/s horizontal
threat speed, and supplied 100 m circular footprints. Interceptor reachability
remains two-dimensional even though threat altitude is preserved.

Each generated episode must admit a complete matching between all eight threats
and eight distinct interceptors. The immediate-interception baseline chooses
the earliest eligible interception, with stable reachability-margin and ID
tie-breaks.

The consequence adapter preserves Emmanuel's vetoes, expected-casualty ordering,
10% / 0.5 casualty tie band, and secondary score. Valid candidates receive a
normalized ordinal rank cost from 0 to 1. Eight event costs are summed. Expected
casualties, people potentially exposed, site effects, and the ordinal learning
objective remain separate outputs.

## What has been demonstrated

The current local state has passed:

- 308 backend tests;
- 14 frontend tests; and
- the TypeScript/Vite production build, with the existing bundle-size advisory.

A 16-step Singapore MaskablePPO run trained, saved, reloaded with normalization
statistics, and produced a valid masked action. The seed-7 benchmark separately
measures scenario generation, cold and warm consequence evaluation, a complete
baseline episode, environment steps, smoke-policy inference, and memory.

This demonstrates working plumbing and reproducibility. The checked frontend
result remains the immediate-interception baseline on both sides of the
comparison.

## What has not been demonstrated

The versioned Singapore validation, held-out, stress, and bounded-oracle suites
have not been completed for a trained policy. The project therefore does not yet
have evidence of learned-policy improvement or optimality.

The current model also does not establish a validated physical blast or debris
footprint, calibrated casualties, interceptor-altitude behavior, aircraft
downtime, service recovery transitions, terrain interaction, wind, or drag.
The 100 m circle is supplied scenario geometry. Population exposure is not a
casualty count. Emmanuel's constants and weights remain demonstration
assumptions unless independently validated.

Transport, healthcare/education, and richer residential-service inputs are
explicitly unavailable in the v1 Singapore catalog. Unknowns remain unknown
rather than becoming zero. Interceptor inventory is the only persistent state
change currently modeled.

## The claim we can make today

The team has implemented a deterministic, versioned eight-threat Singapore
simulation that connects 3D synthetic trajectories, 2D interceptor
reachability, finite one-use resources, candidate-centered population and site
consequence evidence, Emmanuel's ordering, a masked RL interface, and a
frontend result. The complete path and smoke-trained policy are verified as
software plumbing.

The team has not yet shown that a trained policy outperforms the fixed baseline.
Until the evaluation gates pass, the frontend and presentation should say that
clearly.

## Next milestone

1. Review and approve the frozen scenario, typed overlap rules, ordinal
   objective, and explicit modeling limits.
2. Commit the intended local integration so the demonstrated state is
   reproducible outside the current working tree.
3. Train a non-smoke Singapore policy under a recorded budget.
4. Run validation, held-out, stress, bounded-oracle, and constraint gates.
5. Compare the learned policy with the exact same immediate-interception
   baseline and simulator configuration.
6. If the evidence supports it, update the checked result and frontend with the
   measured improvement, uncertainty, failure rate, and latency.

## Canonical references

- [Operational handoff](handoff.md)
- [Singapore integration contract](docs/singapore-simulation-integration.md)
- [Expanded integration description](nickolas/singapore-simulation-integration.md)
- [Code-review checklist](nickolas/code-review-checklist.md)
- [Simulation result contract](contracts/simulation-result.md)
- [Simulation implementation guide](backend/simulation/simulation.md)
- [Learning implementation guide](backend/learning/learning.md)
