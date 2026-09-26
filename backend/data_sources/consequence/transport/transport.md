# Transport consequence profiles (roads + MRT/LRT)

Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md).


Scores Singapore road segments and rail stations under the conditional consequence model in
the model. This replaces the earlier road criticality
index: the fixed 40/20/25/15 composite, the junction score and the folium map are gone. Its raw evidence
(betweenness, detour cost, road class, structure proximity) is kept per site.

Code: `roads.py`, `rail.py`, `datamall.py` (this folder); run with `../pipeline.py transport`. Needs network for OpenStreetMap. Roads also need `data/processed/population-projected.json` from `scripts/population_data.py` (read only; the population dataset version is recorded in provenance). Station volumes need `LTA_ACCOUNT_KEY` and `--volume-month`. **No key is the expected case for now**: stations then use a category prior (see Rail) and everything still runs. Other env vars: `SG_BRIDGE_DIRECT_URL` / `SG_BRIDGE_DATASET_ID`, `BETWEENNESS_K`, `REDUNDANCY_TOP_N_EDGES`.

## Outputs (`output/transport/`)

- `transport_output.csv` - one row per site and condition, **43 columns**, following the consequence
  model's full vector:
  - **C, O_display, E, D, X, R, A and the secondary score**, each as `_low/_central/_high` (formulas and ranking:
    model doc sections 6-7). D and X have no source for transport, so they are blank (never zero) and listed in
    `dimensions_missing`; the secondary score renormalises over the dimensions present.
  - **Veto**: `veto_status`, `veto_reasons_civilian`, `veto_reasons_capability`, plus `population_method` and
    `overlap_area_km2` (transport sites are `direct`).
  - **All eight flags** as `flag_*` columns (`True`, `False` or `unavailable` where the input needed to judge
    it is absent: `mass_vulnerability_condition`, `minimum_capability_breach`).
  - `site_id`, `condition_id`, `role`, `rankable`, `dimensions_missing`, `policy_version`.
- `transport_output_inputs.csv` - same rows, keyed by `site_id` + `condition_id`. Starts with the readable location:
  `name`, station `codes` and `lat`/`lon` (WGS84; a representative point on the segment for roads). Then raw inputs with low/central/high,
  state and grade (occupancy, beneficiaries, loss, outage hours, alternative capacity, recovery, the five
  vulnerability and five hazard components), dimension statuses and reasons. Kept so raw values stay beside
  the derived scores; safe to ignore.
- `transport_output_sites.geojson` - one feature per site with its raw evidence.
- `transport_output_provenance.json` - population dataset version, graph sizes, DataMall months and checksums, every assumption.

The format is deliberately plain so it can change when the consumer is decided.

## Conditions

Six, all in the normal operating state: weekday AM peak (07-09), midday (09-17), PM peak (17-20), weekday night
(20-07), weekend day (07-20), weekend night (20-07). Closed and degraded states are deferred.

## Roads

- Demand: each subzone's residents are split over the graph nodes inside it. Sampled subset betweenness between
  population-weighted origins and destinations gives `trip_share`, the share of trips using a segment.
  Demand is population x population with no distance decay, so long trips are over-weighted.
- Service loss E: `trip_share x residents x trips/day x hourly share`, reduced by alternative capacity
  `1/(1+detour_ratio)` (zero when removal disconnects the endpoints, which also raises
  `single_point_of_failure`). Detour is only evaluated for the top N edges; the rest get the full 0-1 range.
- Occupancy: lane-km x vehicles per lane-km x persons per vehicle. Recovery: 6-24 h, or 4-14 days within 25 m of a
  bridge, flyover or underpass.
- Every one of these is grade D (`derived` or `assumption`). Singapore publishes no link-level traffic volumes.

## Rail

- Stations come from OpenStreetMap. Interchanges merge by shared code or same name within 500 m. Track links are
  inferred from consecutive station codes, with a documented table for the Changi branch, the STC/PTC LRT loops
  and skipped numbers (CC18).
- A station is a `single_point_of_failure` when removing it splits the network. Line ends are not.
- **Without DataMall (default): category prior**, per the model's §9 conditional occupancy idea. Daily tap-in + tap-out
  is set by station class (LRT 1k-15k, MRT 10k-90k, interchange 30k-250k; central 5k / 40k / 100k), spread over the
  day with the road hourly shares, occupancy = hourly taps x dwell time. State `assumption`, grade D, wide bounds.
  These numbers are guesses, not statistics. Through-passengers are not modelled without PV/ODTrain.
  Consequence: **stations of one class score identically**, so the ranking within a class comes only from cut
  stations and the walking-alternative proxy. Read station results as class-level until real volumes exist.
- With DataMall (if a key ever becomes available): occupancy = tap in+out per hour x dwell time; demand adds
  through-passengers from PV/ODTrain assigned to hop-shortest paths. Grade C.

## Limitations

- **No DataMall key.** Station occupancy and demand come from the category prior above. The optional PV/Train and
  PV/ODTrain path follows the DataMall guide and is exercised on fixtures only.
- **The road stage has not been run on real data**: the prepared population file was not present. Rail has run
  against OSM (219 sites, 246 links, no isolated stations).
- Rail topology is inferred from codes, not track geometry; LRT layouts beyond the listed loops are simple chains.
- Weekend counts include public holidays, which DataMall files under the weekend/holiday day type.
- All coefficients (trips per person, vehicle density, hourly shares, dwell, recovery times, alternative
  capacity) are uncalibrated assumptions, listed in `transport_output_provenance.json`.
- Vulnerability is unknown for transport, so C bounds widen (V=0 at low/central, V=100 at high).
- Dimensions D (capability) and X (cascades) are absent and reported in `dimensions_missing`.
- Requires OSMnx 1.x and pandas < 3. The old code needed Python 3.10+; new modules use
  `from __future__ import annotations` but the population code base states 3.9.
