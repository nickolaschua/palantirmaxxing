# planning-result/1 payload contract

Canonical current planning payload, derived from
[the exporter](../backend/presentation/planning_result.py),
[the frontend parser](../frontend/src/demo/decision-model.ts), and the checked-in
[demo artifact](../data/results/demo-planning-result.json).
This supersedes the planning payload guidance in historical
[API-DESIGN.md](../frontend/docs/API-DESIGN.md) without modifying it.
See [HTTP delivery](frontend-backend-api.md) for the enclosing delivery identity
and [simulation-result/1](simulation-result.md) for the separate simulation schema.

## Required top-level structure

All numbers are finite JSON numbers. No NaN or infinity is permitted.

| Field | Type and meaning |
| --- | --- |
| schemaVersion | Exactly `planning-result/1` |
| scenarioId | Scenario identity string, not delivery resultId |
| start, end | ISO-8601 UTC scenario presentation timestamps |
| threat | Object with id string and samples array |
| candidates | Array of candidate objects below |
| paretoCandidateIds | Array of Pareto candidate ID strings |
| categoryAssignments | Object with earliestViable, highestSuccess, lowestExposure; each candidate ID or null |
| representativeCandidateIds | Ordered array of representative candidate IDs |
| comparisons | Ordered array of pairwise comparisons below |
| diagnostics | Object with totalCandidates, reachableCandidates, eligibleCandidates, paretoCandidates numeric counts |
| assumptions | Required display/model metadata below |
| populationProvenance | datasetId, datasetVersion, coordinateReferenceSystem strings; optional calculatorVersion string |

The parser is a display safety gate, not an exhaustive producer schema validator.
In particular the exporter can emit empty or one-sample results and a zero
supplied radius; the current frontend requires at least two ordered samples and a
positive assumptions.footprintRadiusM. Such exporter outputs are Unavailable in
this frontend, not silently repaired.

## Coordinates, clocks and ordering

The exporter converts projected EPSG:3414 easting/northing metres to WGS84
EPSG:4326 longitude/latitude degrees (always longitude first).
lon is within [-180, 180], lat within [-90, 90]. A threat sample contains
`time, lon, lat, height`. A candidate position contains `lon, lat, height`.
height is metres, copied from visualizationHeightM. It is synthetic display
height, not measured altitude, terrain elevation or a ballistic prediction.

start anchors a synthetic presentation clock. Candidate time equals start plus
timeFromStartS seconds; sample time is the same candidate instant. end is the
last sample time, or start for no samples. Exported timestamps use UTC Z and six
fractional digits. Publication time belongs only to the delivery envelope and
must not be substituted for these scenario clocks.

Samples and candidates preserve opportunity order; frontend samples must have
strictly increasing times. sampleIndex preserves the upstream opportunity index;
do not reinterpret it as a new display index. IDs are stable within the payload
and used for references, never inferred from array positions or shortened labels.
Candidate IDs must be unique. Pareto IDs reference evaluated candidates.
Representatives are Pareto members and are deduplicated in category order:
earliestViable, highestSuccess, lowestExposure. The UI displays options in that
representative order. Categories within a candidate follow earliest_viable,
highest_success, lowest_exposure; a candidate may carry multiple categories.
Null category assignments have no representative.

## Candidate fields

Every candidate supplies:

- id string; sampleIndex integer; timeFromStartS seconds; time UTC timestamp.
- position as above; reachable boolean.
- requiredTravelTimeS and timeMarginS, finite seconds or null.
- paretoEfficient boolean; categories array of category strings.
- eligibleForRecommendation boolean; ineligibilityReasons array of strings.

timeMarginS is the available delay from scenario start; the display countdown is
timeMarginS minus elapsed scenario seconds. Null means no supplied timing
evidence, not zero seconds.

An evaluated candidate additionally supplies:

- suppliedSuccessProbability, a finite probability on the 0–1 scale. The current
  model is synthetic; do not present it as calibrated operational success.
- footprint: id string and radiusM in metres, centered on candidate position.
- exposure: status (`complete` or `partial_coverage`),
  peoplePotentiallyExposed (number or null), knownAreaExposure (number), and
  coveredAreaFraction (fraction 0–1 or null).

Unreachable candidates omit success, footprint and exposure and have
eligibleForRecommendation false with reason unreachable. Missing evidence is not
zero. Partial coverage leaves peoplePotentiallyExposed null; knownAreaExposure is
the estimate in the known area and is not a complete total. A complete genuine
zero remains zero. Frontend representatives require a supplied positive footprint
radius. Neither the parser nor view invents omitted success/exposure evidence.

## Comparisons

Each comparison contains referenceCandidateId, comparisonCandidateId, deltaTimeS,
deltaSuccessProbability, deltaSuccessPercentagePoints,
deltaPeoplePotentiallyExposed, relativeExposureChange. All differences are
**comparison minus reference**. Time is seconds; probability delta is on the 0–1
scale; percentage-point delta is 100 times that value. Exposure delta is people.
Relative exposure is a fraction of reference exposure, not a percent.

The exporter emits every ordered pair of distinct representatives, reference
outermost and comparison innermost, preserving representative order. Time delta
is required finite. Success deltas are null when evidence is missing. Exposure
deltas are null unless both exposures are complete. Relative exposure is null
when comparison evidence is unavailable, reference exposure is zero, or the
computed value is nonfinite. Null must not be turned into a numeric zero.

## Assumptions and display wording

Required assumptions fields and current values are:

| Field | Current meaning/value |
| --- | --- |
| successModel | synthetic_linear_decay |
| footprintModel | supplied_fixed_circle |
| footprintRadiusM | Scenario-supplied radius in metres |
| populationExposureMeaning | estimated_people_potentially_exposed |
| kinematicsCalibration | synthetic_not_operational |
| visualizationHeightM | Synthetic display height in metres |
| heightMeaning | synthetic_visualization_only |
| scenarioTimeMeaning | synthetic_presentation_clock |

Use “supplied N m area,” “people potentially exposed” and “supplied success
(synthetic).” The radius is supplied scenario geometry, **not a validated blast
radius**. Exposure is not casualties. Population provenance identifies the
underlying calculation source and CRS; it does not change presentation lon/lat.

The frontend parser also accepts an optional candidate consequence extension:
total is a Figure or null, dimensions is an ordered array of
`{id, weight, value}`, where id is H/E/D/X/R/A and value is a Figure or null.
A Figure has finite central and nullable low/high, ordered low ≤ central ≤ high,
with optional confidence/source strings. Values are scores on 0–100, weights
are fractions, unavailable values are null. Optional scenario is display text.
The committed exporter does not produce this extension. The fixture loader
currently adds clearly labelled illustrative consequence values where omitted;
`illustrative: true` identifies this frontend demonstration enrichment. The
delivery adapter never adds it or changes the nested payload.

## Evolution and verification

Incompatible changes require a new schemaVersion; HTTP delivery changes follow
the separate /api/v2 rule. Planning does not replace simulation-result/1.
The actual committed artifact is used in adapter and view tests, with no edits
to backend code or result artifacts. Producer invariants documented here exceed
the existing frontend parser's validation coverage; tests do not establish
backend HTTP conformance or validate every producer invariant.
