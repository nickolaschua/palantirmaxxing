# Singapore v2 scenario audit

This report is generated from `scenario-audit-v2.json`; it contains no runtime timestamps or machine timings.

## Dimensions considered

| Dimension | Coverage |
|---|---|
| Active scale | 2–8 threats and 3–8 one-use interceptors |
| Detection cadence | gapped, burst, and separated-wave event streams |
| Ingress geography | eight centroid-bearing sectors |
| Terminal geography | fixed 4×4 projected main-island grid |
| Reachability structure | consequence-eligible bipartite edge density and degrees |
| Matching structure | complete, critical-edge, and capped matching counts |
| Timing slack | minimum and median earliest eligible pair margins |
| Consequence contrast | online naive cost versus exact immutable-rank cost |
| Distribution shift | held-out ingress sectors and two-wave cadence |

## Profiles and intended split use

| Profile | Episodes | Counts | Cadence | Intended use |
|---|---:|---|---|---|
| warmup | 100 | 2–3 threats; one extra interceptor | gaps 8.0–15.0 s | core |
| balanced | 180 | 4–6 threats; equal interceptors | gaps 2.0–8.0 s | core |
| full-standard | 180 | 8–8 threats; equal interceptors | gaps 0.5–4.0 s | core |
| burst-contention | 180 | 6–8 threats; equal interceptors | burst 4 inside 2.0 s | core |
| low-slack | 180 | 8–8 threats; equal interceptors | gaps 0.5–3.0 s | core |
| consequence-contrast | 180 | 4–8 threats; equal interceptors | gaps 1.0–6.0 s | core |

## Profile outcomes

| Profile | Audited | Naive complete | Exact complete | Edge density p05 / median / p95 | Attempt p95 |
|---|---:|---:|---:|---|---:|
| warmup | 100 | 100 (100.00%) | 100 (100.00%) | 1.000 / 1.000 / 1.000 | 1.00 |
| balanced | 180 | 180 (100.00%) | 180 (100.00%) | 0.720 / 0.812 / 0.840 | 16.05 |
| full-standard | 180 | 180 (100.00%) | 180 (100.00%) | 0.734 / 0.812 / 0.844 | 16.00 |
| burst-contention | 180 | 180 (100.00%) | 180 (100.00%) | 0.448 / 0.556 / 0.694 | 7.00 |
| low-slack | 180 | 180 (100.00%) | 180 (100.00%) | 0.438 / 0.484 / 0.547 | 25.10 |
| consequence-contrast | 180 | 180 (100.00%) | 180 (100.00%) | 0.680 / 0.796 / 0.840 | 11.00 |

## Complete distributions (including empty bins)

### Matching edge density

| Bin | Episodes |
|---|---:|
| [0,0.25) | 0 |
| [0.25,0.4) | 2 |
| [0.4,0.55) | 257 |
| [0.55,0.7) | 123 |
| [0.7,0.85) | 518 |
| [0.85,1] | 100 |

### Median pair-best time margin

| Bin (seconds) | Episodes |
|---|---:|
| [-100,0) | 0 |
| [0,5) | 971 |
| [5,10) | 29 |
| [10,20) | 0 |
| [20,40) | 0 |
| [40,100] | 0 |

### Complete matching counts

Counts are exact below 10,000 and capped at 10,000.

| Bin | Episodes |
|---|---:|
| 0 | 0 |
| 1 | 0 |
| 2-9 | 86 |
| 10-99 | 304 |
| 100-999 | 375 |
| 1000-9999 | 235 |
| 10000 (cap) | 0 |

Complete-matching count quantiles: `{"count": 1000, "maximum": 9264.0, "mean": 1230.534, "median": 125.0, "minimum": 2.0, "p05": 6.0, "p25": 25.5, "p75": 750.0, "p95": 6843.599999999997}`

Critical-edge count quantiles: `{"count": 1000, "maximum": 3.0, "mean": 0.694, "median": 0.0, "minimum": 0.0, "p05": 0.0, "p25": 0.0, "p75": 1.0, "p95": 3.0}`

### Spatial and cadence coverage

Ingress detection counts: `{"0": 1027, "1": 628, "2": 938, "3": 657, "4": 768, "5": 925, "6": 678, "7": 835}`

Terminal-grid detection counts: `{"0": 888, "1": 222, "10": 310, "11": 1043, "12": 215, "13": 839, "14": 361, "15": 0, "2": 299, "3": 0, "4": 521, "5": 256, "6": 337, "7": 607, "8": 378, "9": 180}`

Threat-count and consecutive detection-gap distributions by profile:
- `warmup`: threat counts `{"2": 45, "3": 55, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0}`; gap quantiles (seconds) `{"count": 155, "maximum": 14.949922265, "mean": 11.648789631303226, "median": 11.93211926, "minimum": 8.133692589, "p05": 8.3469898294, "p25": 9.8097925125, "p75": 13.3140949835, "p95": 14.590341453499999}`
- `balanced`: threat counts `{"2": 0, "3": 0, "4": 33, "5": 76, "6": 71, "7": 0, "8": 0}`; gap quantiles (seconds) `{"count": 758, "maximum": 7.994266291999999, "mean": 5.049336270246702, "median": 5.0096845375, "minimum": 2.015851532, "p05": 2.441335923299999, "p25": 3.5764603304999993, "p75": 6.485184121000001, "p95": 7.725793507}`
- `full-standard`: threat counts `{"2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 180}`; gap quantiles (seconds) `{"count": 1260, "maximum": 3.998087608999999, "mean": 2.241777991245238, "median": 2.236767638, "minimum": 0.5039389169999993, "p05": 0.6725462028500004, "p25": 1.3671122942500005, "p75": 3.1229398495, "p95": 3.7951284268499994}`
- `burst-contention`: threat counts `{"2": 0, "3": 0, "4": 0, "5": 0, "6": 55, "7": 75, "8": 50}`; gap quantiles (seconds) `{"count": 1075, "maximum": 3.999000172, "mean": 1.4621933238148836, "median": 1.10077882, "minimum": 0.00026142500000014834, "p05": 0.06897942469999988, "p25": 0.31503016250000004, "p75": 2.5964708709999993, "p95": 3.6601584820999995}`
- `low-slack`: threat counts `{"2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 180}`; gap quantiles (seconds) `{"count": 1260, "maximum": 2.995697614, "mean": 1.7294313397714285, "median": 1.740077534, "minimum": 0.5017875600000004, "p05": 0.6041458228000001, "p25": 1.1244818932500005, "p75": 2.35236873975, "p95": 2.86194788695}`
- `consequence-contrast`: threat counts `{"2": 0, "3": 0, "4": 24, "5": 31, "6": 41, "7": 41, "8": 43}`; gap quantiles (seconds) `{"count": 948, "maximum": 5.994494276, "mean": 3.4341957125348097, "median": 3.3578738899999996, "minimum": 1.002499899, "p05": 1.28516457445, "p25": 2.1969823077500004, "p75": 4.65529406075, "p95": 5.687172143649999}`

## Naive and exact outcomes

Naive termination reasons: `{"all_threats_resolved": 1000}`

Exact termination reasons: `{"all_threats_resolved": 1000}`

Unavailable consequence-component episode counts: `{"education": 1000, "healthcare": 1000, "richer_residential_services": 1000, "transport": 1000}`

Paired-complete relative-improvement quantiles: `{"count": 1000, "maximum": 1.0, "mean": 0.5474023716824296, "median": 0.5505139558510996, "minimum": 0.07389249703065372, "p05": 0.2986051591946646, "p25": 0.4547613759653639, "p75": 0.6336564024094067, "p95": 0.8013467457043442}`

Naive failures are reported as constraint outcomes and are excluded from consequence-improvement claims.

## Generation failures and retries

Failed generations: `0`.
Rejected deterministic attempts: `3951`.
Attempt quantiles: `{"count": 1000, "maximum": 52.0, "mean": 4.951, "median": 3.0, "minimum": 1.0, "p05": 1.0, "p25": 1.0, "p75": 6.0, "p95": 16.0}`

## Frozen Goldilocks gates

| Gate | Passed | Observed | Requirement |
|---|---|---|---|
| `episode_count` | yes | `{"audited": 1000, "requested": 1000}` | exactly 1,000 requested and 1,000 audited episodes |
| `zero_silent_exclusions` | yes | `{"exclusions": 0, "failed_generations": 0}` | zero exclusions and zero failed generations |
| `unique_hashes` | yes | `{"total": 1000, "unique": 1000}` | 100% unique canonical hashes |
| `deterministic_regeneration` | yes | `{"passed": 1000, "total": 1000}` | 100% deterministic regeneration |
| `matching_and_exact_completion` | yes | `{"complete_matchable": 1000, "exact_completed": 1000, "total": 1000}` | 100% complete matchability and exact-reference completion |
| `profile_predicates` | yes | `{"passed": 1000, "total": 1000}` | 100% profile-predicate compliance |
| `generation_attempts` | yes | `{"maximum": 52, "p95": 16.0}` | maximum <= 200 and p95 <= 25 |
| `naive_completion_warmup` | yes | `{"completed": 100, "rate": 1.0, "total": 100}` | naive completion >= 98% |
| `naive_completion_balanced` | yes | `{"completed": 180, "rate": 1.0, "total": 180}` | naive completion >= 95% |
| `naive_completion_full-standard` | yes | `{"completed": 180, "rate": 1.0, "total": 180}` | naive completion >= 90% |
| `naive_completion_burst-contention` | yes | `{"completed": 180, "rate": 1.0, "total": 180}` | naive completion >= 75% |
| `naive_completion_low-slack` | yes | `{"completed": 180, "rate": 1.0, "total": 180}` | naive completion >= 70% |
| `naive_completion_consequence-contrast` | yes | `{"completed": 180, "rate": 1.0, "total": 180}` | naive completion >= 90% |
| `paired_complete_full_size` | yes | `{"paired": 453, "rate": 1.0, "total": 453}` | at least 70% of full-size core episodes paired-complete |
| `exact_strictly_better` | yes | `{"better": 453, "paired": 453, "rate": 1.0}` | exact strictly better in at least 50% of paired-complete full-size cases |
| `paired_median_relative_improvement` | yes | `0.5259505699867102` | paired-complete median relative improvement >= 10% |
| `consequence_contrast` | yes | `{"passed": 180, "total": 180}` | every consequence-contrast episode passes 0.25 absolute and 15% relative |
| `ingress_balance` | yes | `{"counts": {"0": 1027, "1": 628, "2": 938, "3": 657, "4": 768, "5": 925, "6": 678, "7": 835}, "maximum_share": 0.15907682775712514}` | no non-OOD ingress sector contains more than 25% of detections |
| `not_fully_connected` | yes | `{"not_fully_connected": 900, "rate": 1.0, "total": 900}` | at least 90% of non-warmup graphs are not fully connected |

Overall gate result: **PASS**.

## Synthetic and assumption-grade limitations

- All episodes are operationally synthetic and are not threat or weapon-performance predictions.
- The supplied 100 m area is an input assumption rather than a validated physical effect.
- Civilian consequence estimates are assumption-grade; unavailable sectors remain explicit.
- The exact proof covers immutable additive fixed-rank costs and one-use interceptors only.
- No resource failures, sensor noise, trajectory updates, heterogeneous interceptor classes, or changed footprint physics are represented.
- Audit seeds are development-only and are excluded from training and frozen evaluation splits.
