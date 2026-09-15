# Processed

Population preparation outputs currently include `population-display.geojson`, `population-projected.json`, `provenance.json`, `validation-report.json` and [validation-summary.md](validation-summary.md). The geographic/projected data files are generated and ignored; the smaller provenance/reports remain versionable.

The display/reference file preserves all MP2019 zones, including qualified unknown values and flagged invalid geometry. The EPSG:3414 WKT file contains only validated, known-population, non-overlapping candidate zones. Coverage is partial: never treat it as a complete PEC-ready dataset. See the [contract](../../contracts/population-dataset.md).

Offline preparation consumes checksum-verified `data/raw/` and also writes the display copy to `frontend/public/`. Future validated population datasets belong here. Original downloads belong in `data/raw/`; exposure results belong in `data/results/`.
