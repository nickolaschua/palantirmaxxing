# Continuous-event simulation

`backend.simulation` is an isolated, deterministic episode layer around the
existing candidate-opportunity and bounded-curvature reachability code. It does
not modify or replace the static scenario evaluator.

An episode contains at most eight scheduled threats, eight one-use interceptor
resources and twenty candidate samples per threat/interceptor pair. Future
threats stay hidden until their detection event. Assignments are tentative and
replaceable until `interception_time - required_travel_time`; at that lock event
the interceptor is consumed for the rest of the episode.

The `ConsequenceProvider` protocol is the integration boundary for an external
aggregate scorer. `DeterministicToyProvider` exists only to validate simulator,
recorder and learning plumbing. Its outputs must not be presented as project
performance evidence.

`SingaporeScenarioGenerator` adds the frozen `singapore-scenario/1` contract and
produces `simulation-episode/2` records with 3D parabolic threat samples. It
requires a complete eight-threat/eight-interceptor matching before accepting an
episode. Interceptor reachability intentionally remains two-dimensional.

`SingaporeConsequenceProvider` is the versioned Emmanuel demo-v2 adapter. It
clips shared 128-edge supplied circles to the main island, evaluates population
and checked-in sector sites, preserves unavailable evidence, and maps the
existing Emmanuel rank order to an ordinal training cost. Every threat's full
160-candidate universe is ranked once at detection; eligibility, casualty/site
evidence, rank context, and cost are immutable for the episode. Reservations
and time can invalidate actions but never renormalize surviving costs.
Assignment locks snapshot the assessment. An unhandled Singapore threat is a
terminated `constraint_violation:unhandled_threat` with finite cost 9.0; genuine
provider failures and malformed states remain truncations.

Equal timestamps use the fixed order detection, assignment lock, interception
outcome, threat expiry and episode end, with entity IDs as deterministic ties.
`feasible-immediate-matching/1` is an offline full-episode comparator. It picks
the earliest eligible candidate for every threat/interceptor pair (greatest
margin and stable IDs break ties) and solves a complete one-to-one assignment
that minimizes total interception time. `optimal-fixed-rank-assignment/1` uses
an eight-interceptor bitmask dynamic program over each pair's lowest immutable
cost. It is exact only for the declared fixed-rank additive assignment model;
both plans are replayed through this event engine.

`factories.py` exposes explicit `toy|singapore-demo-v2` and
`synthetic|singapore-v1` runtime choices. `suites.py` owns the version-4 split
manifest, keeps the generic bounded oracle separate from the full-size
Singapore assignment reference, and rejects hashes repeated across partitions.
