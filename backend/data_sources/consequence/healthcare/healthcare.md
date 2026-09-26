# Healthcare and education consequence profiles

Model: [singapore-consequence-model.md](../docs/singapore-consequence-model.md). Folder overview: [consequence.md](../consequence.md).


Conditional consequence profiles for **public acute hospitals** (category `health_emergency`) and **MOE schools**
(category `commercial_civic`, education role). Each site gets one `Profile` per transport condition (six recurring
time windows), scored by `scoring.py` (policy `demo-v2`) into (C, E, R, A) with a secondary tie-breaker score, a veto status and flags; see
model doc sections 6-7. D and X are not produced; the scorer records them in `dimensions_missing`. Code: `hospitals.py`, `schools.py` (this folder); run with `../pipeline.py healthcare`.

The first run downloads the MOH workbooks and data.gov.sg tables and geocodes about 350 postal codes through OneMap
(about 6 minutes, cached and resumable). No API key is needed. `--refresh` re-downloads the weekly MOH workbooks.
Outputs are `healthcare_output_sites.geojson`, `healthcare_output.csv`, `education_output_sites.geojson`,
`education_output.csv` (43 columns: ids, the C/O_display/E/D/X/R/A vector, secondary score, veto status and reasons,
`population_method` and `overlap_area_km2`, all eight flags; raw inputs are not written) and `healthcare_output_provenance.json` (checksums, reconciliations and every assumption constant).

## Sources (all public download or API)

| Source | Access | Used for |
|---|---|---|
| MOH Beds Occupancy Rate, daily per hospital since 2018 | weekly XLSX linked from the MOH statistics page (link scraped; needs a browser User-Agent) | inpatients, spare beds elsewhere |
| MOH Attendances at Emergency Medicine Departments, daily per hospital since 2023 | weekly XLSX from the MOH statistics page | ED arrivals |
| SingStat Hospital Admissions and Outpatient Attendances `d_b7dd65c9e72c036f1724a08dc69f41bd` | data.gov.sg datastore | national A&E total (reconciliation), ambulance share |
| SingStat Beds in Inpatient Facilities `d_0f8f02e6e821fc88aa96442656b69241` | datastore | public acute bed total (reconciliation) |
| MOH Hospital Admission Rate by Age and Sex `d_dd32a9abff167b63efc11fb2f25cb341` | datastore | share of admissions aged 65+ |
| SingStat Census 2020 residents by age and sex (repository acquirer) | datastore | weights for the admission rates |
| SCDF Emergency Medical Services, Annual `d_d0b4ca9fad1c5fee38d7ddfd7303845f` | datastore | emergency calls, hence ambulance-arrival share of ED patients |
| MOE General information of schools `d_688b934f82c1059ed0a6993d2a829089` | datastore (337 schools) | school sites, level, postal code |
| MOE Students, Education Officers and Partners by Level `d_dc92b9d107acfa23e1df76b1a33ffb4a` | datastore | enrolment and staff per level |
| OneMap Search | API by postal code | coordinates (SVY21) |

Hospital bed counts are not in any download. They are a cited table in `hospitals.py` (`HOSPITALS`), each with a
low/central/high band and source URL, and are reconciled against SingStat's national public acute total in
`healthcare_output_provenance.json`.

## Hospital method

**Occupancy (N).** inpatients (beds x BOR) + ED patients present (daily arrivals / 24 x hour factor x stay) + staff on
shift + visitors. BOR and ED are p10/p50/p90 over days since 2023-01-01 of the condition's day type (weekday or
weekend); BOR is a midnight census so it is used for every hour. Staff, visitors, ED stay and hour factors are grade D
assumptions, so the occupancy estimate is grade C.

**Service loss (E).** beneficiaries per hour = inpatients + ED arrivals per hour (measured, grade B). Loss fraction
and outage hours are assumptions. **Alternative capacity is measured**: empty beds at the other hospitals that day /
this hospital's inpatients, capped at 1. When neighbours are full, alternatives fall and E rises (spec §5,
substitute capacity). `single_point_of_failure` is set when median spare beds elsewhere cannot absorb the median
inpatient count.

**Vulnerability.** `medically_dependent` = patients / people present. `unable_to_self_evacuate` = non-ambulant
inpatients (assumption) + ambulance-borne ED patients, over people present. `age_vulnerable` = the 65+ share of acute
admissions (admission rate x Census residents), scaled by an assumed bed-day uplift, times the inpatient share.
`difficult_to_evacuate` and `outdoors` are assumption bands. `source_date` is the latest MOH observation, so the
shared `data_stale` flag reflects the feed.

## School method

MOE publishes enrolment and staff by level, not by school, so each school gets its level's mean (grade C) with a
0.6-1.5x size band. Presence by window is the spec §9 school-teaching row (grade D), term time only. `age_vulnerable`
is the share of occupants aged 12 or under (primary students), a reinterpretation for schools. Per-school
`unable_to_self_evacuate` and `medically_dependent` have no public source and stay `unavailable`. Service loss is
teaching hours lost with home-based learning as the alternative.

## Limitations

- Public hospitals only (the eight MOH-reported general hospitals plus Woodlands). Private hospitals, KKH, NUH
  children's, polyclinics, nursing homes and the SCDF fire stations are not modelled.
- MOH daily figures are hospital submissions for the previous week; bed counts are current published headline
  figures and change as wards open (Woodlands and Alexandra are ramping or redeveloping, hence their wide bands).
- ED patients present is a Little's-law style estimate, not a headcount.
- School occupancy is per-level mean, not per-school enrolment; vacation, exams, and events are not modelled.
- Every assumption band is uncalibrated. Calibrate against hospital operator data or MOE per-school enrolment.
- Ranking output is provisional, as for the other categories. At the demo-v2 placeholder thresholds all 54 hospital
  rows are vetoed (central C up to 83.6 against an essential threshold of 5).
