# Backend demo summary

Use `planning-result/1` and load [demo-planning-result.json](../data/results/demo-planning-result.json). The sole frontend contract definition remains [API-DESIGN.md](../frontend/docs/API-DESIGN.md). This document explains the demo, not a second API definition.

## Machine-side flow

Supplied threat state → 50 future trajectory samples → bounded-curvature reachability → synthetic success enrichment → supplied circular consequence footprints → population exposure → Pareto filtering → representative alternatives → planning-result/1 → frontend / human review.

Calculated by the backend: trajectory samples from supplied motion, reachability, geographic population exposure, Pareto membership, representative categories and factual comparison deltas. All 50 opportunities remain in the handoff; unreachable and dominated candidates are excluded from the decision frontier, not erased.

Synthetic/supplied: fictional threat path and launch origin, 225 m/s threat speed, 500 m/s interceptor speed, 15 deg/s turn limit, 500 m consequence radius and linear success profile (0.97 initial, 0.004/s decay, 0.70 floor). The UTC start 2026-09-15T00:00:00Z and 1000 m visualization height have no model significance. No physical debris trajectory or operational calibration is claimed.

## Separate Singapore demo

The fictional eastbound Ang Mo Kio–Serangoon path runs from EPSG:3414 (27300,39500) to (31800,39500) over 20 seconds. The launch origin is (26600,38500). Both are comfortably inside Canvas bounds. Real prepared Census 2020 resident population and MP2019 boundaries supply the geographic evidence. Population data are not altered to produce the story. The engineering fixture remains separate and unchanged.

| Candidate/category | Time (s) | Supplied success | People potentially exposed | Exposure change vs early |
|---|---:|---:|---:|---:|
| Early / highest supplied success (`k11`) | 4.4000 | 0.9524 | 15,251.8400 | 0.0000% |
| Middle / dominated high exposure (`k32`) | 12.8000 | 0.9188 | 19,465.8221 | 27.6293% |
| Lowest exposure (`k46`) | 18.4000 | 0.8964 | 1,643.1006 | -89.2269% |

A middle candidate is shown only when computed exposure exceeds both endpoint representatives and backend dominance evidence exists. Exposure means estimated people potentially within the supplied area, not casualties or identified people saved. The human retains go/no-go authority.

## Sensitivity evidence

The qualitative trade-off persisted in 36/36 tested synthetic configurations; 36/36 met the reporting criterion of at least 20% and 100 fewer people potentially exposed. This is sensitivity within a small synthetic parameter grid on one selected corridor, not operational or real-world robustness. See [the generated study](specifications/mvp-sensitivity.md) for coverage effects, outcome reasons and limitations.

## Reproduce the handoff

```sh
.venv/bin/python -B scripts/export_static_mvp_planning_result.py --scenario data/scenarios/demo-singapore.json --output data/results/demo-planning-result.json
.venv/bin/python -B scripts/run_mvp_sensitivity.py
.venv/bin/python -B scripts/benchmark_planning_result.py --scenario data/scenarios/demo-singapore.json --output data/results/demo-planning-result-benchmark.json
```

Prepared population must already exist locally at the pinned identity in `demo-singapore.json`. The [benchmark artifact](../data/results/demo-planning-result-benchmark.json) records planning, presentation and total over one warm-up and seven measured runs; population preparation, text encoding, file IO, network and frontend rendering are excluded.

Frontend rendering, camera, animation, cards and controls belong to the frontend teammate. No model expansion accompanies this work; [the post-MVP backlog](MVP_SCOPE_AND_BACKLOG.md) remains deferred.
