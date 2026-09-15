# Candidate-opportunity planning — Phases A-C

`backend.domain` defines immutable Python records and `backend.planning` generates deterministic future candidate opportunities. This is an internal reusable Python contract, not an API or file envelope.

## Scope and boundaries

The model produces synthetic candidate locations along a deterministic 2D threat trajectory and tests whether a simplified, constant-speed, bounded-turn-rate interceptor can reach each location before its candidate time.

It does not model real interceptor performance, guidance, acceleration, altitude, seeker performance, target maneuvering, uncertainty, success probability, footprints, population exposure, costs, allocation, recommendations or optimization. Speed and turn-rate inputs are synthetic simulation parameters unless supplied from a separately validated source. The 15 degrees/second value used in fixtures is synthetic and is not calibrated to an operational interceptor.

The dependency flow is one-way:

```text
ThreatState
    -> sample_threat_trajectory
    -> TrajectorySample records
    -> bounded-curvature reachability
    -> CandidateOpportunity records
```

There are no dependencies on `backend.exposure`, population data, footprint assessment or frontend code.

## Domain records

`ThreatState` contains a nonempty `threat_id`, finite metre coordinates, finite metres/second velocity components, and finite nonnegative `maximum_time_to_go_s`.

`InterceptorState` contains a nonempty `interceptor_id`, finite metre coordinates, finite heading, positive finite `speed_mps`, and positive finite `max_turn_rate_rad_s`. Heading is normalized to `[0, 2*pi)`. Speed and turn rate must produce a finite positive minimum turning radius.

`TrajectorySample` contains a positive one-based `sample_index`, strictly positive `time_from_start_s`, and finite metre coordinates.

`CandidateOpportunity` contains the requested IDs, sample fields and reachability evidence:

- `minimum_path_length_m`;
- `required_travel_time_s`;
- `time_margin_s = time_from_start_s - required_travel_time_s`;
- `reachable`.

Generated candidates always populate all three metrics. The record type permits all three to be `None` together for downstream unevaluated representations, but a record cannot be reachable without metrics. All records are immutable. Invalid construction raises `ValueError`; values are not clamped or coerced, and booleans are not accepted as numbers.

## Trajectory sampling

`sample_threat_trajectory(threat, number_of_samples=50)` returns a tuple of exactly `number_of_samples` future samples when `T > 0`, using:

```text
t[k] = (k / K) * T, k = 1..K
x(t) = x0 + vx*t
y(t) = y0 + vy*t
```

The sample count is configurable and must be a positive integer. When `T == 0`, the result is empty rather than duplicate current-position samples. No `t=0` sample, acceleration, noise, course update or metadata is generated.

## Free-terminal-heading bounded-curvature path

The reachability solver transforms the target to an interceptor-local frame and scales by:

```text
R_min = speed_mps / max_turn_rate_rad_s
```

It geometrically evaluates the complete free-terminal-heading candidate families for the obstacle-free, forward-only Dubins model:

- straight or maximum-curvature arc followed by a tangent straight segment (`S`, `L-S`, `R-S`);
- two tangent opposite-direction maximum-curvature arcs for a target inside an initial turning disc (`R-L`, `L-R`).

`C-S` length is the directed arc length plus `sqrt(D^2 - R^2)`. `C-C` candidates are obtained by intersecting the radius-`2R` locus of the second circle center with the radius-`R` target circle, evaluating both solutions, and retaining the shortest finite result. The terminal heading emerges from the path; no final heading is prescribed or sampled in production.

The optimal family can change discontinuously at an initial turning-circle boundary. A global-to-local coordinate transform can move an analytically exact boundary point a few floating-point units to either side. Boundary classification therefore uses a narrow scale-aware tolerance: a base relative tolerance of `1e-12`, increased only enough to cover 16 coordinate-scale ulps after normalization. If coordinate precision would require more than a `1e-9` relative band, calculation fails instead of materially expanding the boundary. Within the band, the exact represented-point construction and the neighboring degenerate boundary arc are both evaluated and the shortest numerically valid result is retained. This policy absorbs representation error only; it does not sanitize ordinary physical inputs.

Square-root or inverse-trigonometric domains are bounded only within that documented floating-point tolerance. Nonrepresentable geometry raises `ValueError`; Euclidean distance is never substituted.

## Reachability and identifiers

For each sample:

```text
required_travel_time_s = minimum_path_length_m / speed_mps
time_margin_s = time_from_start_s - required_travel_time_s
reachable = time_margin_s >= -1e-9
```

The unmodified margin is retained. The absolute `1e-9` second comparison tolerance is exported as `REACHABILITY_TIME_TOLERANCE_S`.

`generate_candidate_opportunities(threat, interceptor, number_of_samples=50)` retains reachable and unreachable samples in chronological order. IDs are deterministic:

```text
{threat_id}__{interceptor_id}__k{sample_index}
```

Repeated identical inputs produce equal immutable records with no timestamps, random IDs or runtime metadata.
