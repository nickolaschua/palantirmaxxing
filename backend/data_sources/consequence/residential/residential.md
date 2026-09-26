# Residential consequence profiles

Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md).


Conditional consequence profiles (category `residential`) for Singapore housing. Each site gets one `Profile` per
transport condition (six recurring time windows), scored by `scoring.py` (policy `demo-v2`) into the vector (C, E, R, A) with a secondary tie-breaker score, a veto status and
flags; see the model doc sections 6-7 for the formulas, thresholds and ranking. D and X are not produced yet; the scorer
records them in `dimensions_missing`. Output columns are listed in the `pipeline.py` docstring. Code: `residential.py` (this folder); run with
`../pipeline.py residential`.

The first run downloads about 190 MB into `cache/sources/` and geocodes ~10,800 HDB blocks through OneMap: about
3 hours without a token (OneMap tolerates ~1 call/second), about 45 minutes with a free `ONEMAP_TOKEN`. The geocode
cache is resumable. No key is required.

## Sources (all public download or API)

| Source | Dataset | Used for |
|---|---|---|
| SingStat Census 2020, residents by subzone, age, sex | `d_d95ae740c0f8961a0b10435836660ce0` (via the repository's `acquire`) | age-vulnerable share per subzone |
| SingStat Census 2020, residents by subzone and dwelling type | `d_7f243956483d5901f237e6f87b096636` | residents per subzone in each HDB flat group, condominiums, landed, other |
| HDB Property Information | `d_17f5382f26140b1fdae0ba2ef6239d2f` | units per block by flat type, top floor, year completed |
| URA Master Plan 2019 Subzone Boundary | `d_8594ae9ff96d0c708bc2af633048edfb` (via `acquire`) | subzone polygons |
| URA Master Plan 2019 Land Use | `d_90d86daa5bfaa371668b84fa5f01424f` | residential parcels: plot area and GPR |
| OneMap Search | `onemap.gov.sg/api/common/elastic/search` | block coordinates (SVY21) |

## Method

**Sites.** `hdb_block` (a point per HDB block), `private_residential` (one URA residential parcel that holds no HDB
block), `private_landed` (all landed lots, GPR `LND`, merged per subzone: about 59,000 lots would otherwise
swamp the output) and `subzone_remainder` (census residents that no site could take).

**Residents.** For each subzone and flat group, residents per unit = census residents / units in blocks completed by
2020. A block's residents = its units x those rates. Blocks completed after 2020, and groups the census left blank,
use the national rate for the group; these are *extra* estimates and are reported apart from the census total.
Private housing: landed residents go to landed parcels and condominium + other residents to the remaining
parcels, each by floor area (plot area x GPR; `LND` assumes 1.4 and non-numeric GPR such as `EVA`/`SDP` assumes 1.0,
both flagged in `raw`). A pool with no parcels of its own kind falls back to the other kind, then to the remainder.
`residential_output_provenance.json` reconciles placed residents against the census total; the difference must be zero.

**Occupancy (N).** residents x share at home for the condition x non-resident uplift, low/central/high. N feeds the
expected casualties C. Night windows hold more people than midday. The six home fractions and the uplift are in
model doc section 9. Residents carry an extra low/high band by how they were obtained: census subzone rate
0.90-1.10, national rate 0.70-1.30, floor-area share 0.60-1.50.

**Area sites.** `private_landed` and `subzone_remainder` rows count only the residents inside the placeholder
footprint (areal density, model doc section 9.1; radius `footprint_radius_m` in `data/scenarios/demo-singapore.json`, currently
100 m). `population_method` and `overlap_area_km2` record this. HDB blocks and private parcels are `direct`.

**Vulnerability.** `age_vulnerable` is the census share aged under 5 or 65 and over (grade C, subzone). By day its
upper bound rises to share / home fraction. `difficult_to_evacuate` is the share of floors above level 12 for HDB
blocks (grade D: the threshold is an assumption); it is unavailable for private sites. `unable_to_self_evacuate`
and `medically_dependent` have no public subzone or block source and stay `unavailable`, so C's upper bound widens
instead of assuming zero.

**Service loss (E): shelter displacement.** Beneficiaries are the residents; loss fraction, displacement duration,
alternative accommodation, recovery time and hazard are uncalibrated assumptions (grade D). Every constant is
defined near the top of the Profiles and allocation sections of `residential.py` and copied to `residential_output_provenance.json`.

## Limitations

- The census is 2020 and the HDB stock is current. Blocks built since rely on national rates, and census
  rounding to the nearest 10 affects small subzone groups.
- Estates redeveloped since 2020 (Commonwealth and Tanglin Halt) have fewer units than in the census, so their
  surviving blocks get inflated residents per unit (43 of 10,759 blocks exceed 4, against a typical 3.0-3.4). The
  census total is conserved: residents move onto surviving blocks, none are created.
- `source_date` is left empty on census-derived values because the shared 400-day staleness flag would otherwise
  mark every row `data_stale`; the vintage is in each estimate's `source` and in the provenance file.
- `high_human_exposure` trips at central C >= 10 expected casualties, so it can fire for the largest sites (the
  2026-09-25 run, with the 500 m footprint, had 1,148 vetoed rows out of 203,526, maximum central C 44.9).
- Blocks OneMap cannot match (37 in the first run) are excluded and listed in provenance; their subzone's census
  residents spread over the blocks that were placed. A residential parcel whose HDB block failed to geocode is not
  dropped and may receive private residents.
- Blocks are points, not footprints.
