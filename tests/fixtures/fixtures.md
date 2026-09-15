# Fixtures

Small offline examples: `population-sample.json` excerpts the first six Census 2020 API rows and the `_id`, `Number`, `Total_Total` columns; `boundary-sample.geojson` preserves full geometry/properties for the corresponding four Ang Mo Kio subzones. These are deliberate excerpts, not complete official snapshots. Original dataset IDs/links are documented in `docs/specifications/population-data.md`; full-file checksums are in `data/processed/provenance.json`.

Unit tests additionally construct tiny synthetic geometries and malformed records to test edge cases. These test inputs are versionable. Full source datasets belong in `data/raw/`, working scenarios in `data/scenarios/`, and illustrative contract payloads in `contracts/examples/`.

`pec-population.json` is a fully synthetic `pec-population/1` dataset: two adjacent 200 m² rectangles with densities 2 and 4 people/m². It supports the runnable `data/scenarios/pec-example.json` episode. These deliberately synthetic EPSG:3414 coordinates are not real population observations. PEC unit tests construct additional small known-answer polygons, circles, holes and invalid inputs.

`pec-boundary-gap.json` describes a synthetic triangular excluded gap whose apex is midway between a 128-edge chord and the ideal circle at the chord’s angular midpoint. It provides an interpretable regression for resolution-sensitive coverage without using source population geometry.

`static-mvp-population.json` contains three adjacent synthetic rectangles with
lower, higher, then lower density along the deterministic scenario path. Its
coordinates and counts exist only to exercise complete-coverage PEC and
success/exposure trade-offs; they do not describe real geography or hazards.
