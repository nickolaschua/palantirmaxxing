# PEC explanation record — planning

**Status: planned and unimplemented.** This document prepares the [future explanations module](../../backend/explanations/explanations.md). It records boundaries and decisions before implementation, not a final payload schema or a frontend design. The existing [PEC contract](../../contracts/pec.md) remains authoritative. Illustrations in the [frontend handoff](pec-frontend-handoff.md) and example results do not establish product requirements.

## Purpose and constraints

Help users understand supplied-footprint population exposure through individual zone contributions, unique exposure versus person-exposures and multiple-event exposure, missing population coverage, and input assumptions/provenance.

The future module may package existing contributions into understandable facts; associate them with episode, event and zone IDs (and preserve footprint identity); distinguish known-area subtotals from complete totals; describe overlapping-event metrics; attach matching dataset provenance, assumptions and settings; and generate deterministic factual text from recorded results if the frontend needs it.

It must preserve source PEC values, statuses and null semantics. Unrounded values remain authoritative; display formatting must not change them. It must remain independent of layout, never independently recalculate exposure or alter results, and never invent causal claims or use an LLM to invent explanations. Exposure supports no claims about casualties, building occupancy or real-world hazard validity. Historical residents and uniform zone density are model assumptions, not observations of people physically present. Event time is descriptive; episode metrics do not describe simultaneous exposure.

Calculation and any future geometry computation belong in [exposure](../../backend/exposure/exposure.md); source acquisition/provenance in [data sources](../../backend/data_sources/data_sources.md); loading, execution and persistence coordination in [orchestration](../../backend/orchestration/orchestration.md); transport in [API](../../backend/api/api.md); presentation in the frontend. Reuse these locations. Final payload contracts and examples belong in `contracts/` once agreed.

## Existing evidence and missing information

Checked against [calculator source](../../backend/exposure/calculator.py), [dataset adapter](../../backend/exposure/dataset.py), [PEC specification](pec.md), [contract](../../contracts/pec.md), [reference result](../../contracts/examples/pec-result.json), local coverage results and the frontend handoff.

| Information | Available now | Boundary for future work |
|---|---|---|
| Identity and supplied footprint | `episode_id`; event `event_id`, `footprint_id`, centre/radius and optional time. Events are sorted by ID. | Scope event identity by episode and exact result; IDs alone do not identify a recalculated run. No exact-result identity/retention mechanism is selected. |
| Individual event zone contributions | `zone_breakdown` includes `zone_id`, population, density, overlap area and estimated people exposed. Positive-area overlaps include known-zero zones; boundary touches have no row. | Package existing rows without recalculation. Names require matching display/reference data; selection and summarisation policy remain open. |
| Episode metrics | Unique exposure counts each location once over the event union; person-exposures sum event exposures; multiple-event exposure counts locations in at least two distinct events once, including triple overlap. Complete and known-area variants are returned. | Do not sum event rows to claim unique exposure or subtract unique from person-exposures to claim multiple-event exposure. Episode union/multiple zone breakdowns are computed internally but discarded, not returned. Exposing them needs a calculator/output extension. |
| Coverage | Event/episode status and uncovered area; event coverage fraction and polygon area. Partial complete totals are null; known-area subtotals remain available. | Episode missing area is a union measure, not the sum of event missing areas. Area coverage is not population coverage; do not extrapolate missing population from it. |
| Geometry | Results repeat circle parameters and resolution settings. | No footprint vertices, zone geometry, event-zone intersections, selectable overlap regions or coverage-gap polygons are returned. Internal union/intersection geometry is not an output. Exact exports, attribution to event combinations, projection to WGS84 and geometry identity need separately agreed computation/output work; the explanation adapter must not silently reconstruct calculations. |
| Provenance and settings | Metadata records dataset ID/version, normalized population-envelope SHA-256, schema/calculator/library versions, CRS, circle approximation, tolerances and assumptions. | The checksum is not a file-byte hash or episode/result hash. Rich source dates/references, retrieval meaning and exclusion reasons require matching [population provenance and validation artifacts](../../contracts/population-dataset.md). They are not all embedded in PEC results. |
| Missing-coverage attribution | Uncovered area is known; matching validation/display data records excluded zones and reasons. | General attribution of a particular gap to a zone needs geometry evidence. Excluded shapes alone are not a complete gap layer: footprints can extend beyond all source zones. Diagnostic Bidadari attribution is case-specific. |
| Factual text | Numerical facts and recorded assumptions can support deterministic templates. | No text adapter or explanation contract exists. Text form, locale, terminology and frontend need remain to be agreed. |

Preserve `invalid_input` errors without inventing success aggregates or metadata. Null means unavailable/undefined, not zero. Empty episodes have zero totals; zero-radius events have zero area/exposure and null coverage fraction. A partial episode keeps all three complete totals null even when individual events are complete. A summary must not relabel a selected subset as the full result or silently drop authoritative contributions.

The checked-in synthetic result has complete coverage, two disjoint events, unique exposure `50.245298511276054`, person-exposures `50.24529851127604`, and multiple-event exposure `0.0`. Preserve these values, including ordinary floating-point differences; the example does not choose demo interactions.

## Verified approximation-sensitive coverage

The [coverage investigation](pec-coverage-investigation.md) and [comparison snapshot](pec-coverage-comparison.json) report no production bug. On 15 September 2026, a read-only, in-memory check using the existing calculator, archived benchmark episode and local prepared dataset reproduced event-090 at both supported resolutions. Dataset version was `sg-residents-2020-mp2019-cbb1c395f60918c1`, normalized checksum `4fa83ffefec87ddeb85e77d9b77d41fd8aea6beb9068eaaf926e9e79352054c4`, matching the report.

- 128 edges: `complete`, missing area `0.0 m²`, known and complete event exposure `138322.2008356021`.
- 256 edges: `partial_coverage`, missing area `0.011656080614812764 m²`, known event exposure `138355.165401054`, complete event exposure null.
- Projecting the matching display Bidadari (`TPSZ10`) geometry for diagnostic attribution reproduced the entire 256-edge missing area; subtracting Bidadari from the gap left zero area. Bidadari is excluded for `population_qualified_nil_or_negligible`, with null population, not zero population. No reference geometry was substituted into PEC coverage.

This supports the report: the finer inscribed polygon enters excluded Bidadari. No production bug was found. **“Complete” describes coverage of the calculation polygon within the recorded absolute area tolerance, not guaranteed coverage of the ideal circle.** PEC uses the same polygon for area, intersections, exposure and coverage. Missing area greater than `1e-6 m²` is partial; a rounded percentage must never determine status. A partial event can display a coverage percentage rounded to 100%. Measured missing area remains recorded even below tolerance.

The report separately establishes that the full benchmark episode is partial at every investigated resolution; the event status change is not an episode status change. The focused check above did not rerun the full investigation. Production remains 128 edges by default with 256 supported; neither guarantees ideal-circle coverage. Conservative ideal-circle classification would require a separate policy, specification and validation, not an explanation-layer correction. How the demo communicates approximation sensitivity remains unresolved.

## Pending decisions

Owners below are proposed responsible roles, not recorded assignments. No explicit product decision resolving these questions was found. Existing calculation semantics are constraints, not decisions about the future experience.

| Question | Why it matters | Who should decide | Current status | Which implementation work depends on it |
|---|---|---|---|---|
| Which user questions should the demo answer? | Determines useful facts and scope. | Demo/product owner with frontend and PEC owners | Unresolved | Question-to-output mapping and acceptance scenarios |
| Event-level, episode-level, or both explanations? | Scope changes attribution and selection semantics. | Demo/product and frontend owners with PEC owner | Unresolved | Record granularity, identity and adapter scope |
| Text, structured facts, geometry, or a combination? | Each form needs different contracts and consumers. | Frontend and PEC owners with demo/product owner | Unresolved | Versioned contract, text templates and any geometry export |
| All contributing zones or a summary? | Detail affects auditability, navigation and size. | Demo/product and frontend owners | Unresolved | Selection/ranking, summary rules and completeness labelling |
| Selectable overlap regions or coverage gaps? | Metrics alone cannot support spatial picking. | Demo/product and frontend owners with PEC owner | Unresolved | Geometry computation/export, region identity, transforms and picking |
| Save records with results or generate on demand? | Controls retention, reproducibility and latency. | Backend/orchestration owner with demo/product owner | Unresolved | Persistence, invocation and caching |
| How do explanations stay linked to exact dataset and calculator versions and the exact result? | Existing metadata helps, but IDs alone do not distinguish runs; source artifacts must match. | PEC/data and backend owners | Unresolved | Result/episode identity, provenance linkage, retention and adapter/contract versioning |
| What display rounding and terminology should be used? | Fractional estimates, units, nulls and subtotals must remain understandable. | Demo/product and frontend owners with PEC owner | Unresolved | Formatting and deterministic text; unrounded PEC values remain authoritative |
| What interaction speed and payload size are expected? | Local calculator timings do not establish end-to-end performance. | Frontend and backend owners with demo/product owner | Unresolved | Performance budget, geometry/detail scope, caching and measurement |
| How is approximation-sensitive coverage communicated? | Polygon completeness does not guarantee ideal-circle coverage. | Demo/product and frontend owners with PEC owner | Unresolved | Resolution/tolerance wording and UI verification; any stronger classification requires separate PEC work |

## Future implementation sequence — do not execute yet

1. Agree on the demo interactions and questions, with explicit scope and acceptance examples.
2. Map each question to existing PEC output, including exact source fields, IDs, units, status and null handling.
3. Identify genuinely missing information. Separate reference-data joins from new computation or geometry exports; agree any PEC changes independently.
4. Finalise a versioned explanation contract with examples in the existing `contracts/` structure, including exact-result linkage and complete, partial, invalid and empty cases.
5. Implement a small deterministic adapter in `backend/explanations/` that consumes authoritative results and agreed matching references.
6. Add consistency tests against source PEC results in the existing test structure, covering attribution, values, statuses, nulls and repeatability.
7. Integrate the frontend and verify the complete experience, including geometry correspondence if selected, terminology, traceability, latency and payload size.

## Future acceptance criteria

- Every displayed statement is traceable to the exact source result and field/IDs; provenance statements additionally identify matching reference evidence. Preserve dataset/checksum, calculator/settings and agreed record-version linkage.
- Unknown values remain unknown. Invalid inputs are not presented as successful zero exposure. Known-area subtotals never masquerade as complete totals.
- Explanations never disagree with underlying calculations or mutate them. Unrounded source numbers remain authoritative; formatting does not change status or imply false numerical equality.
- Unique, person-exposure and multiple-event measures retain their distinct meanings. Filtering or summary presentation cannot silently redefine their scope.
- Identical source results, agreed references and adapter/template version produce deterministic facts/text, without invented causal, occupancy, casualty or hazard-validity claims.
- Coverage wording explicitly concerns the recorded calculation polygon and tolerance. Any selected geometry is traceable to that calculation; missing geometry is not invented from areas or illustrative diagnostics.

This preparation adds documentation only. The explanation feature, contract, adapter, persistence and frontend integration remain unimplemented.
