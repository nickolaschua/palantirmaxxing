# Planning

Implemented Phases A-C of the synthetic candidate-opportunity pipeline:

- `trajectory.py` samples a constant-velocity threat trajectory at configurable, uniformly spaced future times. The default is 50 samples; zero time-to-go produces no future samples.
- `reachability.py` calculates the shortest obstacle-free, forward-only bounded-curvature path from an initial interceptor pose to a point with free terminal heading. It returns path length and deterministic timing evidence; it does not use Euclidean distance as a reachability substitute.
- `opportunities.py` evaluates every trajectory sample and retains both reachable and unreachable candidate records.
- `__init__.py` exposes the reusable planning interface.

The planning package depends only on `backend.domain` and the Python standard library. It does not import PEC, population data, footprint generation, orchestration, recommendation logic or frontend code. See the [candidate-opportunity contract](../../contracts/candidate-opportunities.md).

Interceptor speed and maximum turn rate are synthetic/configurable kinematic inputs. Test fixtures using 15 degrees/second choose that value only to exercise a nontrivial reachable set; it is not calibrated to an operational interceptor.
