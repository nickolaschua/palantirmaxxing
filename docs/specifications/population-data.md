# Singapore Census 2020 population preparation

Implemented milestone: reproducible population-data acquisition, geographic validation and presentation. No PEC exposure calculation, footprint simulation, optimisation, API service or database is implemented.

## Sources and inspected access

- [SingStat resident population by planning area/subzone, age and sex, Census 2020](https://data.gov.sg/datasets/d_d95ae740c0f8961a0b10435836660ce0/view), dataset `d_d95ae740c0f8961a0b10435836660ce0`. The supplied datastore endpoint remains operational. An explicit `limit=1000&sort=_id%20asc` returns all 388 rows; acquisition verifies response success, resource ID, `total`, length and consecutive `_id` 1…388. It fails rather than accepting a server-capped response. The portal also publishes 388 rows and 61 data columns (the API adds `_id`).
- [URA Master Plan 2019 Subzone Boundary (No Sea), GeoJSON](https://data.gov.sg/datasets/d_8594ae9ff96d0c708bc2af633048edfb/view), dataset `d_8594ae9ff96d0c708bc2af633048edfb`. Uses the [documented download workflow](https://guide.data.gov.sg/developer-guide/dataset-apis/download-dataset): non-CSV files can skip initiate-download; poll-download supplies the complete blob URL. HTTP body length is checked when supplied. The complete inspected file has 332 features: 321 Polygons and 11 MultiPolygons. An independent official feature-count metadata response was unavailable; 332 is an inspected-snapshot guard, not a separately published count. Signed URL credentials are neither stored nor logged.

Initial Python-default requests to the boundary endpoint returned 403; requests with an explicit User-Agent succeeded. No endpoint, population year or boundary vintage was substituted. Separate metadata endpoint attempts returned 403. Source web pages, response metadata and the complete boundary file were inspected instead.

Census year is **2020**. Population source publication/update date is **18 June 2021**, distinct from later portal catalogue updates. Boundary vintage is **Master Plan 2019**; the portal labels its data period September 2021 and catalogue update 3 December 2025. Retrieval time is separately recorded in UTC. The sources are provided under the [Singapore Open Data Licence](https://data.gov.sg/open-data-licence).

## Population interpretation and hierarchy

`Total_Total` means total across ages and sexes, in people; it is not a sum calculated from already-rounded age/sex columns. `Number` holds ordered geographic labels: one `Total` national row, followed by 55 planning-area headings and their subzones. Headings end in a hyphen plus `Total`; the actual `Changi- Total` lacks a space before the hyphen. Parsing uses that documented/observed structure and preserves row order. It rejects orphan subzones and repeated headings. The 56 aggregates are retained solely for reconciliation; the 332 subzone rows are potential zones.

[SingStat Table Builder CT/17560](https://tablebuilder.singstat.gov.sg/table/CT/17560) explains its dash as nil, negligible or not significant, and warns that rounded numbers may not add to totals. This does **not** establish that every dash is an exact zero. Dash values are preserved and assigned `qualified_nil_or_negligible` with null population. The source has 52 dashes in the selected column: six aggregates and 46 subzones. Numeric zero, when supplied, is `known_zero`; none occurs in this snapshot. Blank/null, `na`, unrecognised qualification markers and invalid numbers have separate statuses. No suppression threshold or exact rounding increment is inferred. No reconciliation adjustment is performed.

Residents are citizens and permanent residents. This is historical residential population, not live crowd levels, everyone physically present, or building-level occupancy.

## Join rules

Boundary properties include `SUBZONE_C`, `SUBZONE_N`, `PLN_AREA_C`, `PLN_AREA_N`, `OBJECTID`, region fields, source update fields and `SHAPE.AREA`/`SHAPE.LEN`. Population rows do not contain stable boundary codes, so the join uses the exact pair of planning-area/subzone names after Unicode NFC, trim/whitespace collapse and uppercase. Punctuation is preserved. **No aliases or fuzzy matches are used** (`ALIASES = {}`). The matched boundary `SUBZONE_C` becomes the zone ID. Both source naming forms remain available.

All 332 subzone pairs match uniquely. Duplicate population keys, boundary keys and zone IDs, ambiguous joins and unmatched records in both directions are machine-reported. Ambiguous zones are ineligible; nothing silently selects one candidate.

## Coordinates, geometry and area

The boundary file is GeoJSON without a `crs` member, using RFC 7946 WGS84 longitude/latitude degrees. Coordinate ranges were checked and axes verified. Transformations use pyproj with `always_xy=True`, no ballpark transform, to **EPSG:3414 (SVY21 / Singapore TM)**, with easting/northing in metres. This is Singapore's local Transverse Mercator plane system; the [Singapore Land Authority definition](https://app.sla.gov.sg/sirent/About/PlaneCoordinateSystem) supplies the projection origin, false easting 28001.642 m, false northing 38744.572 m and WGS84 ellipsoid. An automated control-point test verifies the projection origin. Calculated source-area agreement is within 0.001 m² of the supplied `SHAPE.AREA` values, corroborating the coordinate interpretation.

Area is computed on full-resolution projected geometry, never on degree coordinates. Density is people divided by that supplied-zone area, displayed as people/km². Despite the source's “No Sea” title, no independent inland-water subtraction is performed, so the denominator is **supplied zone geometry area**, not guaranteed land-only area.

No geometry repair or simplification occurs. Six source/projected geometries have ring self-intersections; their IDs/reasons are retained, their area/density is null, and they are excluded from projected candidates. Among valid polygons, all intersecting pairs are checked with a spatial index. Seven positive-area overlaps involve 11 zones, including slivers; largest overlap is about 0.319229 m². The exclusion threshold is strictly greater than zero, with no undocumented tolerance. Both participants are excluded. Shared zero-area boundaries are allowed. All candidate pairs are consequently non-overlapping at the pinned GEOS/PROJ precision.

Original source geometry remains in the geographic artifact, including the flagged invalid shapes; it is a display/reference file, not computationally validated PEC input. Offshore subzones are preserved. All extents fit the existing rectangular camera bounds, but the viewer's existing two-polygon city/coastline clipping does not cover all offshore zones. Population polygons use a separate, unclipped layer; a visible globe supplies terrain under offshore polygons even with photorealistic tiles. Invalid source shapes may have ambiguous visual interiors and are identified in details.

## Results and readiness

The inspected run has 332 matched zones, zero unmatched/duplicate/ambiguous joins, 286 known populations and 46 qualified unknowns. There are 275 eligible zones and 57 exclusions (reasons overlap). Known displayed population sums to **4,044,340**, versus published national **4,044,210**, a **+130** difference. Known planning-area totals sum to **4,044,250**. The candidate subset contains **3,982,190** people over about **502.765 km²** of supplied zone geometry.

Rounding and qualified unknowns limit reconciliation. Full per-area differences, source aggregates, exclusions and overlap areas are in the [validation summary](../../data/processed/validation-summary.md) and [machine report](../../data/processed/validation-report.json). Do not force totals to match or label the entire dataset PEC-ready. The projected file is a validated **partial-coverage candidate input** accepted by the standalone [PEC v0.1 specification](pec.md). PEC preserves historical rounded counts, validates the eligible subset again, and reports null complete exposure totals when a supplied footprint or episode extends beyond known coverage. Preparation eligibility rules remain unchanged.

## Reproduction and display decisions

Python 3.9–3.12 preparation uses pinned Shapely 2.0.7, pyproj 3.6.1, NumPy 1.26.4 and certifi 2025.1.31. Python 3.9 was available locally, so this compatible stack was selected after newer package versions proved unavailable for that interpreter. Runtime library/GEOS/PROJ versions are recorded. No general backend framework has been selected.

Acquisition reuses checksum-verified cache by default. `--refresh` is explicit; downloads and completeness checks finish before atomic file writes. The manifest is published last, so interrupted/mismatched caches fail verification. Local imports accept complete official CSV or API JSON plus official boundary GeoJSON; original source files are copied unchanged and retrieval metadata clearly labels local-import time rather than inventing the original download date. All transformations are offline. Same cached inputs/settings produce byte-identical outputs; changing retrieval metadata alone does not change substantive dataset identity.

Display uses a five-step pale-blue-to-purple sequential scale (`#edf8fb`, `#b3cde3`, `#8c96c6`, `#8856a7`, `#810f7c`) with grey `#909ba5` for unavailable values. Count breaks: 1,000 / 10,000 / 20,000 / 40,000 people. Density breaks: 1,000 / 5,000 / 10,000 / 20,000 people/km². Breaks remain fixed while filtering; the chart's bars scale to its filtered maximum, with exact labels and descending ranking. Unknown metric values are omitted from ranking but remain in the map and searchable list. Selection uses a pale-lilac highlight. This palette is separate from any future hazard/exposure presentation.

The reusable Canvas polygon layer owns GeoJSON loading, per-feature styling, visibility and stable-ID hover/click picking (including multipart zones). The application owns data interpretation, controls, filtering and chart/details. A local plain globe is the no-credentials mode; existing remote basemaps remain selectable. The original custom land/road ground primitives are temporarily hidden while a polygon overlay is enabled so they cannot overpaint it, and restored when disabled; remote city tiles remain available. Basemap replacement loads before discarding the previous map so failed credentials leave the current layer available. No official data fetching/joining occurs in the browser.

See [root commands](../../README.md) and [frontend verification](../../frontend/docs/POPULATION-VERIFICATION.md).
