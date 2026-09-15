# Static machine-side MVP benchmark

The deterministic fixture uses intentionally scaled synthetic inputs chosen to
preserve the Phase A-C reachability pattern and exercise a low-to-high-to-lower
population trade-space. Its 10,000 m/s interceptor speed, 1,000 m/s threat
speed, 500 m footprint radius, coordinates, turn rate, population geometry and
population counts are not operational performance estimates.

The success profile is also synthetic: initial probability `0.97`, decrease
`0.004/s`, minimum `0.70`, and maximum `1.00`. It is not calibrated to an
interceptor.

## Deterministic result

- Total candidates: `50`
- Reachable candidates: `36`
- Complete-coverage candidates: `36`
- Eligible candidates: `36`
- Pareto-efficient candidates: `2`
- Pareto IDs: `synthetic-high-speed-threat__synthetic-interceptor__k15`,
  `synthetic-high-speed-threat__synthetic-interceptor__k37`
- `earliest_viable`: `synthetic-high-speed-threat__synthetic-interceptor__k15`
- `highest_success`: `synthetic-high-speed-threat__synthetic-interceptor__k15`
- `lowest_exposure`: `synthetic-high-speed-threat__synthetic-interceptor__k37`
- Unique representatives: `k15`, `k37` in stable category order.

Unrounded representative evidence:

| Candidate | Time (s) | Supplied success | People potentially exposed | Categories |
|---|---:|---:|---:|---|
| `k15` | 6.0 | 0.946 | 392.5413946193438 | earliest viable; highest success |
| `k37` | 14.8 | 0.9107999999999999 | 78.50827892386876 | lowest exposure |

Example dominance evidence:

- `k15` dominates `k16`: exposure is exactly
  `392.5413946193438` for both, while supplied success is `0.946` versus
  `0.9444`.
- `k20` has supplied success `0.938` and exposure
  `8047.098589696542`; its recorded dominators are `k15` through `k19`.
- `k37` dominates `k38`: their exposure values are equivalent within the
  documented exposure tolerance (`78.50827892386876` versus
  `78.5082789238689`), while success is strictly higher (`0.9107999999999999`
  versus `0.9092`).

No fixture candidates are equivalent in both objectives. Unit tests separately
verify that exact and within-tolerance two-objective equivalents remain
Pareto-efficient and record each other's IDs.

The complete unrounded `static-scenario-evaluation/1` result, including all 50
original opportunities, all 36 evaluated candidates, zone evidence, dominator
lists and PEC provenance, is generated at
`data/results/static-mvp-benchmark.json`. Its population checksum is
`c623ef3ea9db8b9091b4befb085fd35ded774617d5ce31f2db854591f2e3d64c`.

## Seven-run engineering benchmark

Measured on Python 3.9.6, macOS 26.5.1 ARM64, Shapely 2.0.7 / GEOS 3.11.4 and
pyproj 3.6.1. Population was prepared before timing. One complete warm-up was
excluded, followed by seven measured complete evaluations using
`perf_counter_ns`. File I/O and report formatting were outside timing. The
total is a caller-side measurement of each complete function invocation.

These seven runs are a small engineering benchmark, not rigorous performance
characterization.

| Run | Trajectory + reachability | Success enrichment | Footprint + exposure | Pareto | Representatives | Total |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.456542 | 0.016667 | 29.309583 | 1.769917 | 0.013083 | 31.593625 |
| 2 | 0.466542 | 0.018875 | 26.676750 | 1.283958 | 0.007959 | 28.484750 |
| 3 | 0.364875 | 0.015916 | 23.980250 | 1.496209 | 0.009666 | 25.904875 |
| 4 | 0.446000 | 0.063708 | 27.680584 | 1.452875 | 0.011375 | 29.688542 |
| 5 | 0.361584 | 0.014125 | 25.921583 | 1.298083 | 0.007792 | 27.629625 |
| 6 | 0.372708 | 0.014542 | 27.651833 | 1.286583 | 0.007584 | 29.359209 |
| 7 | 0.452875 | 0.018000 | 26.000708 | 1.261459 | 0.007375 | 27.769333 |

| Statistic | Trajectory + reachability | Success enrichment | Footprint + exposure | Pareto | Representatives | Total |
|---|---:|---:|---:|---:|---:|---:|
| Median | 0.446000 | 0.016667 | 26.676750 | 1.298083 | 0.007959 | 28.484750 |
| Minimum | 0.361584 | 0.014125 | 23.980250 | 1.261459 | 0.007375 | 25.904875 |
| Maximum | 0.466542 | 0.063708 | 29.309583 | 1.769917 | 0.013083 | 31.593625 |

Median end-to-end runtime was `28.484750 ms`, meeting the `<100 ms` target by
approximately `71.515250 ms`. Footprint construction, adapter validation, PEC
calculation and exposure joining were the dominant measured stage; no PEC
optimization or behavior change was introduced.

## Fifty-candidate inspection table

Internal calculation and structured output retain unrounded values. Values are
rounded only in this table.

| Sample | Time (s) | Position (m) | Reachable | Supplied success | People potentially exposed | Pareto | Categories |
|---:|---:|---|:---:|---:|---:|:---:|---|
| 1 | 0.4 | (50400, 20000) | no | — | — | no | — |
| 2 | 0.8 | (50800, 20000) | no | — | — | no | — |
| 3 | 1.2 | (51200, 20000) | no | — | — | no | — |
| 4 | 1.6 | (51600, 20000) | no | — | — | no | — |
| 5 | 2.0 | (52000, 20000) | no | — | — | no | — |
| 6 | 2.4 | (52400, 20000) | no | — | — | no | — |
| 7 | 2.8 | (52800, 20000) | no | — | — | no | — |
| 8 | 3.2 | (53200, 20000) | no | — | — | no | — |
| 9 | 3.6 | (53600, 20000) | no | — | — | no | — |
| 10 | 4.0 | (54000, 20000) | no | — | — | no | — |
| 11 | 4.4 | (54400, 20000) | no | — | — | no | — |
| 12 | 4.8 | (54800, 20000) | no | — | — | no | — |
| 13 | 5.2 | (55200, 20000) | no | — | — | no | — |
| 14 | 5.6 | (55600, 20000) | no | — | — | no | — |
| 15 | 6.0 | (56000, 20000) | yes | 0.9460 | 392.541 | yes | earliest_viable, highest_success |
| 16 | 6.4 | (56400, 20000) | yes | 0.9444 | 392.541 | no | — |
| 17 | 6.8 | (56800, 20000) | yes | 0.9428 | 392.541 | no | — |
| 18 | 7.2 | (57200, 20000) | yes | 0.9412 | 392.541 | no | — |
| 19 | 7.6 | (57600, 20000) | yes | 0.9396 | 1188.357 | no | — |
| 20 | 8.0 | (58000, 20000) | yes | 0.9380 | 8047.099 | no | — |
| 21 | 8.4 | (58400, 20000) | yes | 0.9364 | 14905.840 | no | — |
| 22 | 8.8 | (58800, 20000) | yes | 0.9348 | 15701.656 | no | — |
| 23 | 9.2 | (59200, 20000) | yes | 0.9332 | 15701.656 | no | — |
| 24 | 9.6 | (59600, 20000) | yes | 0.9316 | 15701.656 | no | — |
| 25 | 10.0 | (60000, 20000) | yes | 0.9300 | 15701.656 | no | — |
| 26 | 10.4 | (60400, 20000) | yes | 0.9284 | 15701.656 | no | — |
| 27 | 10.8 | (60800, 20000) | yes | 0.9268 | 15701.656 | no | — |
| 28 | 11.2 | (61200, 20000) | yes | 0.9252 | 15701.656 | no | — |
| 29 | 11.6 | (61600, 20000) | yes | 0.9236 | 15701.656 | no | — |
| 30 | 12.0 | (62000, 20000) | yes | 0.9220 | 15701.656 | no | — |
| 31 | 12.4 | (62400, 20000) | yes | 0.9204 | 15701.656 | no | — |
| 32 | 12.8 | (62800, 20000) | yes | 0.9188 | 15701.656 | no | — |
| 33 | 13.2 | (63200, 20000) | yes | 0.9172 | 15701.656 | no | — |
| 34 | 13.6 | (63600, 20000) | yes | 0.9156 | 14889.516 | no | — |
| 35 | 14.0 | (64000, 20000) | yes | 0.9140 | 7890.082 | no | — |
| 36 | 14.4 | (64400, 20000) | yes | 0.9124 | 890.648 | no | — |
| 37 | 14.8 | (64800, 20000) | yes | 0.9108 | 78.508 | yes | lowest_exposure |
| 38 | 15.2 | (65200, 20000) | yes | 0.9092 | 78.508 | no | — |
| 39 | 15.6 | (65600, 20000) | yes | 0.9076 | 78.508 | no | — |
| 40 | 16.0 | (66000, 20000) | yes | 0.9060 | 78.508 | no | — |
| 41 | 16.4 | (66400, 20000) | yes | 0.9044 | 78.508 | no | — |
| 42 | 16.8 | (66800, 20000) | yes | 0.9028 | 78.508 | no | — |
| 43 | 17.2 | (67200, 20000) | yes | 0.9012 | 78.508 | no | — |
| 44 | 17.6 | (67600, 20000) | yes | 0.8996 | 78.508 | no | — |
| 45 | 18.0 | (68000, 20000) | yes | 0.8980 | 78.508 | no | — |
| 46 | 18.4 | (68400, 20000) | yes | 0.8964 | 78.508 | no | — |
| 47 | 18.8 | (68800, 20000) | yes | 0.8948 | 78.508 | no | — |
| 48 | 19.2 | (69200, 20000) | yes | 0.8932 | 78.508 | no | — |
| 49 | 19.6 | (69600, 20000) | yes | 0.8916 | 78.508 | no | — |
| 50 | 20.0 | (70000, 20000) | yes | 0.8900 | 78.508 | no | — |
