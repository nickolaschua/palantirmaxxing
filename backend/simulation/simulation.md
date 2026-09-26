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
existing Emmanuel rank order to a normalized ordinal training cost. Assignment
locks snapshot the assessment. Unhandled threats are constraint failures and
the provider emits no persistent operational-state update.

Equal timestamps use the fixed order detection, assignment lock, interception
outcome, threat expiry and episode end, with entity IDs as deterministic ties.
The immediate-interception baseline assigns a threat only once and chooses the
earliest feasible intercept, then greatest margin, interceptor ID and
opportunity ID.

`factories.py` exposes explicit `toy|singapore-demo-v2` and
`synthetic|singapore-v1` runtime choices. `suites.py` owns the version-3 split
manifest and rejects canonical episode hashes repeated across partitions.
