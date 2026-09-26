# Singapore conditional consequence model and data plan

Status: research and implementation specification. The consequence vector, veto and ranking (sections 6-7) are implemented in `scoring.py` under policy `demo-v2`, and the residential profiles in `residential/residential.py`; this document describes that behaviour. Runtime policy, optimisation policy, and operational validation are not implemented by this document.

## 1. Purpose and boundary

The current repository calculates resident population potentially exposed within a caller-supplied footprint. That is useful but incomplete: a location can also contain vulnerable people, essential services, transport capacity, hazardous materials, or functions whose loss affects people elsewhere.

This specification defines a practical Singapore data model for describing those consequences before the policy or optimisation stage. It deliberately excludes debris physics. A later evaluator may combine a supplied hazard/footprint with these profiles, but this catalog must remain independently versioned and auditable.

The intended research architecture has no human decision in the runtime loop. Human safety, international humanitarian law, policy constraints, and authorised operational limits must therefore be encoded, tested, and approved before deployment rather than improvised during an episode. This document does not establish autonomous operational readiness or provide deployment guidance.

### 1.1 Offline-first autonomous runtime assumption

The consequence catalog must not depend on obtaining a live headcount during an incident. It instead supplies versioned conditional distributions learned or estimated before deployment:

```text
static Singapore geography and asset catalog
    + historical/administrative observations
    + time-of-day, day-type, season, event, and operating-state models
    -> conditional low/central/high values or probability distributions
    -> millions of sampled training scenarios
    -> trained sequential policy plus deterministic safety constraints
    -> low-latency autonomous runtime inference
```

Runtime inputs may identify the clock, day type, known closures, system degradation, and threat/resource state. They need not include live counts of people. Where runtime state is absent, the policy uses the predeclared distribution and must remain robust across its uncertainty range.

## 2. Research findings that change the model

Evidence from recent conflicts and established resilience guidance supports five design choices:

1. **Score functions, not labels.** A hospital, runway, substation, school, and residential block matter because of the people and functions present under current conditions, not because of a permanent category rank.
2. **Model current system state.** The consequence of losing one facility rises when alternatives are closed, overloaded, inaccessible, or already degraded. WHO HeRAMS explicitly monitors facility functionality, service availability, and access rather than merely counting buildings.
3. **Capture cascading effects.** Documented disruption of Ukrainian electricity infrastructure propagated into water, sewage, heating, health, education, the economy, and displacement. The ICRC describes these as reasonably foreseeable reverberating effects.
4. **Use functional recovery.** NIST resilience guidance measures restoration of function at staged levels such as 30%, 60%, and 90%, together with time to recovery.
5. **Do not let severe dimensions disappear in an average.** High immediate human exposure, collapse of an essential civilian service, or breach of an authorised minimum capability must remain visible as separate dimensions and flags.

Primary references:

- [ICRC: Explosive weapons with wide-area effects](https://www.icrc.org/en/publication/4575-explosive-weapons-wide-area-effect-deadly-choice-populated-areas-0)
- [ICRC: proportionality, precautions, and reverberating effects](https://international-review.icrc.org/articles/proportionality-and-precautions-attack-reverberating-effects-using-explosive-weapons)
- [UN Human Rights Monitoring Mission: harm from attacks on Ukraine's energy infrastructure](https://ukraine.un.org/en/278992-attacks-ukraine%E2%80%99s-energy-infrastructure-harm-civilian-population)
- [WHO HeRAMS Gaza hospital functionality](https://www.who.int/publications/m/item/herams-opt-gaza-snapshot-2024-06-hospitals-en)
- [WHO operational response and early recovery plan for the occupied Palestinian territory](https://www.emro.who.int/images/stories/palestine/WHO-operational-response-and-early-recovery-plan-for-oPt-2025.pdf)
- [CISA Infrastructure Resilience Planning Framework](https://www.cisa.gov/sites/default/files/2023-03/Infrastructure_Resilience_Planning_Framework_IRPF_508c.pdf)
- [NIST Community Resilience Planning Guide](https://www.nist.gov/system/files/community-resilience-planning-guide-volume-1.pdf)
- [NATO resilience and civil preparedness](https://www.nato.int/en/what-we-do/deterrence-and-defence/resilience-civil-preparedness-and-article-3)

## 3. Twelve category taxonomy

Categories organise data collection; they do not assign consequence by themselves. A site may have several categories and should be decomposed into independently meaningful components where data allow.

| Code | Category | Typical components |
|---|---|---|
| `aviation` | Aviation zones | terminals, runways, taxiways, aprons, air-freight and support facilities |
| `defence_security` | Defence and security | authorised abstract capability nodes and continuity functions |
| `energy` | Energy and fuel | generation, transmission, substations, gas and fuel storage |
| `water` | Water and drainage | treatment, pumping, reservoirs, drainage and used-water systems |
| `health_emergency` | Healthcare and emergency services | hospitals, clinics, nursing homes, ambulance and fire response |
| `transport` | Transport networks | rail, stations, roads, interchanges, depots and alternative routes |
| `port` | Port and maritime | terminals, berths, navigation, bunkering and maritime logistics |
| `residential` | Dense residential | HDB, private apartments, landed housing and supporting amenities |
| `commercial_civic` | Commercial and civic | offices, retail, government services, schools and tertiary campuses |
| `industrial_logistics` | Industrial and logistics | factories, warehouses, distribution and production clusters |
| `green_recreation` | Green, open and recreation | parks, sports grounds, nature areas and event spaces |
| `water_coastal` | Water bodies and coastal areas | reservoirs, waterways, coast, recreational waters and water intakes |

Schools and campuses may be stored as `commercial_civic` with `education` as a functional role. A mixed-use development should not be forced into one label.
## 4. Information states

Every value must declare how it was obtained:

| State | Meaning |
|---|---|
| `measured` | Direct current measurement from an identified source |
| `official_aggregate` | Official area/system statistic allocated to a site using a documented method |
| `derived` | Computed from official inputs and explicit assumptions |
| `operator_input` | Supplied by the responsible facility owner or agency |
| `restricted_input` | Approved abstract value; source details are intentionally omitted |
| `assumption` | Scenario value without empirical calibration |
| `unavailable` | No defensible value supplied; do not silently replace with zero |

Each value also carries a lower bound, central estimate, upper bound, observation time, source date, geographic resolution, method, and confidence grade.

## 5. Conditional state

Profiles are evaluated under a named condition, not permanently. At minimum preserve:

- local date and hour;
- weekday, weekend, public holiday, school term, and vacation state;
- normal, peak, reduced, closed, evacuated, event, surge, or emergency operation;
- scenario occupancy distribution or conditional occupancy model;
- available substitute capacity;
- existing degradation elsewhere in the system;
- active hazardous inventory band;
- access and restoration constraints; and
- data freshness and confidence.

Suggested recurring conditions:

| Category | Conditions to maintain |
|---|---|
| Aviation | peak/reduced operations; freight peak; contingency function active; runway availability; substitute capacity |
| Defence/security | normal/readiness state; approved capability required; substitute available; minimum-capability threshold |
| Energy/fuel | peak/off-peak demand; generation availability; reserve condition; fuel-inventory band |
| Water/drainage | normal/drought/heavy rain/flood; demand level; pump and alternative-supply availability |
| Healthcare/emergency | normal/surge; bed occupancy; emergency load; protected operating mode; transfer capacity |
| Transport | peak/off-peak/closed; service disruption; crowding; evacuation demand; alternative routes |
| Port/maritime | active/reduced shift; vessel and cargo state; hazardous-cargo band; berth alternatives |
| Residential | weekday day/evening/night; weekend; evacuation status; vulnerable-resident profile |
| Commercial/civic | working day/night/weekend/event; school term; government continuity function |
| Industrial/logistics | active/minimal/continuous shift; material inventory; production and supply-chain state |
| Green/recreation | empty/normal/weekend/event; weather; outdoor exposure; access state |
| Water/coastal | unoccupied/recreational/maritime activity; tide/rain; contamination sensitivity |

## 6. Raw consequence dimensions

The stored evidence should remain a vector. The proposed 0-100 values are presentation and policy inputs derived from raw measurements.

### 6.1 Human harm: expected casualties `C`

For each sampled scenario, estimate people present, `N`, including residents, staff, visitors, patients, students, and people in transit. `N` is drawn from the condition-specific occupancy distribution rather than queried from a required live feed. For area sites, `N` is only the share inside the footprint (section 9.1).

Estimate vulnerability from proportions in the current population:

```text
V = 100 * (
    0.30 * unable_to_self_evacuate
  + 0.25 * medically_dependent
  + 0.20 * difficult_to_evacuate
  + 0.15 * insufficiently_sheltered_or_outdoors
  + 0.10 * age_vulnerable
)

p_harm(V) = p_base * (1 + k * V / 100)
C = N * p_harm(V)
```

`C` is linear in people, so a mass-casualty site is never compressed. `p_base` (baseline harm probability for an unshielded person in the debris footprint, placeholder 0.01) and `k` (how much likelier a fully vulnerable person is to be harmed, placeholder 3) are uncalibrated `demo-v2` policy constants. Ranking by `C` does not depend on `p_base`; the veto threshold does. A missing vulnerability component counts 0 at low/central and 1 at high, so unknown vulnerability widens `C` rather than lowering it.

For dashboards only:

```text
O_display = min(100, 20 * log10(C + 1))
```

`O_display` is never used for veto flags, ranking or optimisation; only its low-high spread feeds `uncertainty_high`, because `C` itself is unbounded. The vulnerability inputs remain configurable policy assumptions until calibrated. Raw proportions must be retained. (Superseded `demo-v1`: `H = O * (0.60 + 0.40 * V / 100)` with `O = min(100, 20 * log10(N + 1))`; the log compression understated mass-casualty outcomes.)

### 6.2 Essential civilian-service loss `E`

```text
service_person_hours = beneficiaries * loss_fraction * outage_hours
effective_service_person_hours = service_person_hours * (1 - alternative_capacity_fraction)
```

Initial presentation bands:

| Effective service-person-hours | Score |
|---:|---:|
| below 1,000 | 10 |
| 1,000-9,999 | 25 |
| 10,000-99,999 | 40 |
| 100,000-999,999 | 60 |
| 1-9.99 million | 80 |
| 10 million or more | 100 |

The service type must remain visible; one million hours without electricity and one million hours of delayed recreation are not equivalent. Policy weights belong outside the physical profile.

### 6.3 Authorised capability continuity `D`

Do not infer sensitive sites, capacities, or dependencies from public data. Accept an authorised abstract input:

```text
D = 100
    * capability_share
    * loss_fraction
    * duration_severity
    * (1 - replacement_fraction)
```

The profile may additionally carry `minimum_capability_breach`. Detailed evidence stays in the owning system; the prototype stores only the approved value, version, and confidence. `scoring.py` does not evaluate the formula above: it takes the authorised `D` value from the profile's `capability` input as supplied, and `D` is none when no input exists. Residential profiles produce no `D`.

### 6.4 Cascading consequence `X`

Represent directed dependency edges such as electricity -> pumps, communications -> emergency coordination, transport -> staff access, and fuel -> backup generation. For each downstream service, calculate additional non-overlapping service-person-hours. Aggregate only after recording each contribution:

```text
X = min(100, sum(dependency_weight[j] * downstream_service_score[j]))
```

The evaluator must prevent the same outage population from being counted in both direct `E` and downstream `X` without an explicit reason.

Not yet implemented: `scoring.py` sets `X` to none because no dependency records are supplied, so `X` appears in `dimensions_missing` and drops out of the secondary score (its weight is renormalised over the present dimensions).

### 6.5 Functional recovery `R`

Track time to 30%, 60%, and 90% function. Use time to 90% for the initial presentation score:

| Time to 90% function | Score |
|---|---:|
| below 6 hours | 5 |
| 6-24 hours | 15 |
| 1-3 days | 30 |
| 4-14 days | 50 |
| 15-90 days | 75 |
| over 90 days | 100 |

Also record constraints such as scarce parts, specialist labour, unsafe access, testing, supply-chain delay, and temporary-service availability.

### 6.6 Additional hazard potential `A`

Store inventory bands rather than precise sensitive quantities when needed:

```text
A = 0.30 * flammable
  + 0.25 * toxic
  + 0.20 * explosive_or_high_energy
  + 0.15 * water_or_environmental_contamination
  + 0.10 * proximity_to_other_hazards
```

Each component is 0-100 and must state whether it is measured, operator-supplied, or assumed. A missing component counts 0 at low/central and 100 at high, so unknown hazard widens `A` rather than lowering it. This factor describes site potential only; it is not the probability that a hazard will be activated.

## 7. Veto, then rank, and non-compensatory flags

The preferred output is the full vector `(C, E, D, X, R, A)`. The `demo-v2` policy profile (versioned, not objective truth) judges sites in two steps instead of a compensatory weighted total.

**Step A, hard veto (evaluated first).** A site is `vetoed` when `high_human_exposure`, `essential_service_floor_breach` or `minimum_capability_breach` is true. Capability reasons (`minimum_capability_breach`) are reported separately from civilian-harm reasons. A site where no veto flag is true but one could not be judged (for example no authorised D input) is `unknown`, never a silent `pass`. The exception is a declared priority asset with no authorised capability input: it is precautionarily `vetoed` with the capability reason `priority_asset_capability_not_assessed`, never derived from its scores. Veto flags are magnitude-based: `high_human_exposure` trips at `C >= 10` expected casualties and `essential_service_floor_breach` at `E >= 80`. An essential site (priority asset, or category health_emergency, defence_security, aviation, energy, water or port) trips them at a lower magnitude (`C >= 5`, `E >= 60`), but a category never trips a flag by itself. All thresholds are placeholders.

A site is rankable only when both `C` and `E` are available. Rows with no `C` are listed after all others rather than dropped.

**Step B, lexicographic rank of survivors.** Survivors (`pass` and `unknown`) are ordered by `C`, lowest first. The lowest remaining `C` opens a tie band, `C <= max(1.10 * C_min, C_min + 0.5)`; inside it sites are ordered by

```text
secondary = 0.30*E + 0.30*D + 0.25*X + 0.10*R + 0.05*A   (renormalised over the dimensions present)
```

lowest first, and the next band starts after it. The fixed band keeps the rule transitive. Vetoed sites follow, ranked the same way, so an all-vetoed set still yields an ordering for the supervisor rather than an empty result.

(Superseded `demo-v1`: `total = 0.70*(0.35*H + 0.20*E + 0.20*D + 0.15*X + 0.05*R + 0.05*A) + 0.30*max(H, E, D)`, which let a severe result in one dimension be averaged away.)

Always report these flags separately:

- `high_human_exposure`: central `C` at or above the threshold above;
- `mass_vulnerability_condition`: `high_human_exposure` conditions plus central `V >= 50`; `unavailable` when no vulnerability component is available;
- `essential_service_floor_breach`: central `E` at or above the threshold above;
- `minimum_capability_breach`: from the authorised capability input; `unavailable` when none is supplied;
- `single_point_of_failure`: supplied on the profile;
- `hazard_inventory_high`: central `A >= 60`;
- `data_stale`: any occupancy, service or recovery input with a source date more than 400 days before the evaluation date; `unavailable` when no evaluation date is given; and
- `uncertainty_high`: a low-high spread of 40 or more in `O_display`, `E`, `D`, `X` or the secondary score.

A `priority_asset` marker is also reported when the profile declares one. Flag values are `true`, `false` or `unavailable`.

A hard flag must not be cleared merely because the scalar total is low.

## 8. Singapore public-data inventory

### 8.1 Common geography and demographics

| Need | Source | Resolution/use | Limitation |
|---|---|---|---|
| Address/building search, planning areas, thematic layers | [SLA OneMap APIs](https://www.onemap.gov.sg/apidocs/) | point, feature, and planning-area lookup | thematic coverage varies |
| Land-use classification | [URA Master Plan](https://www.ura.gov.sg/land-planning/master-plan/) and URA SPACE | parcel/zone classification | planned use is not live operation |
| Residents, age, sex, dwelling type | [SingStat/data.gov.sg Census 2020](https://data.gov.sg/datasets/d_d95ae740c0f8961a0b10435836660ce0/view) | planning area/subzone | historical residents, not live occupancy |
| Workplace geography | [Census 2020 geographic findings](https://www.singstat.gov.sg/-/media/files/publications/cop2020/sr2/findings2.pdf) | planning-area workplace profiles | insufficient for individual buildings |

The repository already prepares the official Census 2020 subzone population and URA MP2019 boundary sources. Reuse its provenance and null/coverage semantics rather than creating a competing population pipeline.

### 8.2 Sector sources and usable measures

| Category | Public sources | Measurements usable now | Inputs still needed |
|---|---|---|---|
| Aviation | [Changi traffic statistics](https://www.changiairport.com/en/corporate/about-us/traffic-statistics.html), [CAAS annual report](https://www.caas.gov.sg/docs/default-source/default-document-library/caas_ar_fy24-25-desktop.pdf) | monthly passengers, airfreight, commercial aircraft movements | hourly occupants, component function, runway/facility redundancy, restoration |
| Defence/security | none suitable for public reconstruction | no site-level public measure should be inferred | authorised abstract `D`, threshold and confidence only |
| Energy/fuel | [EMA Singapore Energy Statistics](https://www.ema.gov.sg/resources/singapore-energy-statistics), [EMA statistics](https://www.ema.gov.sg/resources/statistics) | national generation, consumption, demand, capacity and reliability | facility service share, network dependencies, spare capacity, restoration |
| Water/drainage | [PUB water loop](https://www.pub.gov.sg/Public/WaterLoop), [PUB potable-water dataset](https://data.gov.sg/datasets/d_cb1d25dd5cfde21bb9fa704af0e3a962/view), [PUB reports](https://www.pub.gov.sg/resources/publications) | national demand, domestic/non-domestic consumption, flood and system indicators | asset service areas, pump/treatment redundancy, recovery |
| Healthcare/emergency | [MOH bed occupancy](https://www.moh.gov.sg/others/resources-and-statistics/healthcare-institution-statistics-beds-occupancy-rate-%28bor%29/), [MOH beds](https://www.moh.gov.sg/others/resources-and-statistics/beds-in-inpatient-facilities-and-places-in-non-residential-long-term-care-facilities/), [SCDF statistics](https://www.scdf.gov.sg/home/about-scdf/media-room/publications/annual-statistics) | daily public-hospital occupancy, bed capacity, admissions/attendance, national EMS/fire demand | protected capacity, staff presence, transfer capacity, local response coverage |
| Transport | [LTA DataMall](https://datamall.lta.gov.sg/content/datamall/en/search_datasets.html) | station passengers, crowding, traffic counts/speeds, service alerts, routes and stations | restricted farecard detail where needed, recovery estimates |
| Port/maritime | [MPA maritime performance](https://www.mpa.gov.sg/media-centre/details/strong-growth-momentum-for-maritime-singapore) | vessel-arrival tonnage, cargo, containers and bunker volumes | terminal/vessel occupancy, cargo hazard, berth redundancy, restoration |
| Residential | repository population pipeline, OneMap, URA, SingStat, HDB Property Information | subzone residents, age, dwelling type, HDB units per block and residential geography | calibrated time-at-home coefficients, private-housing unit counts, current evacuation state |
| Commercial/civic | OneMap, URA, SingStat workplace geography, facility calendars | use class, location, aggregate workplace patterns, public events | tenant occupancy and continuity plans |
| Education within commercial/civic | [MOE education datasets](https://data.gov.sg/collections/2146/view), [Education Statistics Digest](https://www.moe.gov.sg/-/media/files/about-us/esd-2025.pdf) | system enrolment and institution directories where published | site enrolment, staff, timetable and event attendance when not public |
| Industrial/logistics | URA industrial zoning, EMA sector consumption, public company information | use class and aggregate sector activity | shifts, workforce, production share, inventory and dependencies |
| Green/recreation | [NParks facts and figures](https://www.nparks.gov.sg/portals/annualreport/facts-and-figures/), OneMap themes | park locations, areas and network statistics | hourly visitors and event attendance |
| Water/coastal | OneMap/PUB layers, NEA weather APIs, MPA statistics | water geography, rainfall/weather, aggregate maritime activity | local users/vessels, intake sensitivity, contamination consequence |

## 9. Offline conditional occupancy model

Live counts are optional enrichment, not a runtime dependency. Use a category baseline as a documented prior and represent uncertainty as a distribution:

```text
occupancy = capacity
          * time_condition_coefficient
          * event_factor
          * operating_status
          * sampled_variation
```

Initial uncalibrated coefficients:

| Functional type | Weekday day | Evening | Night | Weekend day |
|---|---:|---:|---:|---:|
| Residential | 0.55 | 0.85 | 0.95 | 0.75 |
| School teaching | 0.90 | 0.10 | 0.02 | 0.05 |
| University academic | 0.75 | 0.25 | 0.05 | 0.15 |
| University residence | 0.45 | 0.80 | 0.90 | 0.75 |
| Office | 0.85 | 0.15 | 0.05 | 0.10 |
| Retail | 0.50 | 0.80 | 0.05 | 0.85 |
| Hospital | 0.85 | 0.75 | 0.70 | 0.75 |
| One-shift industrial | 0.80 | 0.10 | 0.05 | 0.15 |
| Continuous industrial | 0.70 | 0.55 | 0.45 | 0.50 |
| Park/open space | 0.20 | 0.15 | 0.01 | 0.60 |

These are explicitly `assumption` values. Convert each coefficient into a distribution, for example a beta distribution bounded by plausible low/high values, rather than repeating one deterministic number in every episode. Validate them later against LTA temporal patterns, facility records, enrolment/timetables, event counts, or operator data. Never describe them as official Singapore statistics.

For residential areas the implementation (`residential/residential.py`) uses six conditions and a multiplicative non-resident uplift, replacing the four-column residential row above:

```text
occupancy = resident_population * home_fraction[condition] * non_resident_uplift
```

| Condition | Home fraction (low, central, high) |
|---|---|
| weekday AM peak | 0.55, 0.70, 0.85 |
| weekday midday | 0.40, 0.55, 0.70 |
| weekday PM peak | 0.60, 0.75, 0.90 |
| weekday night | 0.85, 0.92, 0.98 |
| weekend day | 0.60, 0.75, 0.90 |
| weekend night | 0.85, 0.92, 0.98 |

`non_resident_uplift` is (1.00, 1.05, 1.15) for visitors, domestic workers and others the census does not count as residents. Residents are allocated to blocks by HDB unit counts and to private parcels by plot area x GPR, with an extra low/high band on the resident count that depends on how it was obtained (census subzone rate 0.90-1.10, national rate 0.70-1.30, floor-area share 0.60-1.50). All values are uncalibrated assumptions; see `residential/residential.md`. Report ranges rather than false precision.

### 9.1 Area sites: people inside the footprint

Some residential sites are areas, not buildings: merged landed lots (`private_landed`, one per subzone) and `subzone_remainder`. Scored with every resident at one point, a neighbourhood would be compared with a single building, and linear `C` would magnify the mismatch. Tier 1 (`population_method = areal_density`) scales such a site's `N` by the share of its geometry inside the footprint:

```text
N_effective = N_site * overlap_area / site_area
```

This is assumption-grade: density is taken as uniform over the site geometry (roads, gardens and void decks included). Site-level scoring has no interception candidate, so the footprint is a placeholder circle on the site's representative point with the static scenario's supplied radius (`footprint_radius_m`, 100 m, in `data/scenarios/demo-singapore.json`). It is not debris physics, and it must be replaced by the candidate's own footprint once the candidate bridge exists. Buildings and parcels are `direct`.

Tier 2 (`building_level`: weighting by residential floor area within the footprint) is the named follow-up. It is deferred because it needs a building layer with residential floor area that is not yet integrated.

## 10. Data confidence and uncertainty

| Grade | Definition |
|---|---|
| `A` | current direct measurement with site-level resolution |
| `B` | recent official site-level administrative data |
| `C` | official area/system data allocated by a documented method |
| `D` | category proxy or explicit scenario assumption |
| `E` | unsupported expert judgement; unsuitable for automated ranking |

Calculate `low`, `central`, and `high` values through the same formulas. Publish results as, for example, `63 [48, 79]`, not merely `63`. Do not add uncertainty to harm as if uncertainty itself were damage. During training, sample across the distribution and deliberately oversample tails. At runtime, deterministic policy may use a conservative bound, a risk measure such as conditional value at risk, or an approved safe-state/abstention rule when inputs are outside the validated envelope.

## 11. Implementation sequence

1. Add the profile contract and validate hand-authored profiles.
2. Reuse the existing population dataset identity and subzone provenance.
3. Implement public adapters incrementally: residential, transport, healthcare, education, then aggregate energy/water/aviation/port indicators.
4. Preserve source-native values before calculating scores.
5. Add time-condition generation and low/central/high occupancy estimates.
6. Add service, dependency, recovery, and hazard evidence only where a source or explicit operator input exists.
7. Keep restricted capability input behind a small abstract interface.
8. Implement consequence-vector calculation separately from policy weighting.
9. Validate calculations with synthetic fixtures before connecting them to planning candidates.
10. Add sensitivity tests for coefficients, weights, stale data, and unavailable fields.

## 12. Scenario generation for reinforcement learning

The current static single-choice demonstration is mathematically closer to a contextual bandit than reinforcement learning. To make RL meaningful, each training episode must contain sequential state transitions:

- multiple or arriving threats;
- uncertain response outcomes;
- changing interceptor/resource availability;
- degraded assets and reduced substitute capacity;
- updated observations;
- cumulative service disruption and recovery; and
- a finite time horizon over which an early choice changes later options.

The environment state should contain only information the runtime system is expected to possess. Hidden simulator truth, such as the exact sampled occupancy, may determine reward but must not leak into policy observations.

Recommended episode structure:

```text
sample date/time and conditional Singapore state
    -> sample occupancy, service demand, asset availability, and uncertainty
    -> sample a sequence of threats and available resources
    -> policy chooses among feasible abstract response candidates
    -> simulator applies stochastic outcome and consequence transition
    -> update resources, asset functions, services, and uncertainty
    -> repeat until the episode terminates
```

The reward should retain separate components and constraints. A research starting point is:

```text
reward = mission_success_component
       - human_consequence_component
       - essential_service_component
       - authorised_capability_component
       - cascading_and_recovery_component
```

Hard constraints must be enforced outside the learned reward so that the policy cannot discover that violating them is worthwhile. Train against varied policy profiles only if the policy observation explicitly identifies the active profile.

Millions of episodes are useful only when scenario diversity, seeds, simulator versions, data versions, failures, and train/validation/test separation are preserved. Repeated near-identical samples do not provide millions of independent scenarios.

## 13. Minimum viable Singapore profile

A profile is usable when it has:

- stable site and condition IDs;
- geometry or an existing zone reference;
- at least one category and functional role;
- occupancy low/central/high with provenance;
- vulnerability components or explicit `unavailable` values;
- direct service beneficiaries and alternatives where applicable;
- authorised capability input only where provided;
- dependency records where known;
- recovery estimates with basis;
- hazard inventory bands with basis;
- confidence and freshness for every material input; and
- raw values in addition to all derived scores.

Missing values are not zero. A profile with insufficient evidence may still be displayed, but must not silently enter automated ranking.
