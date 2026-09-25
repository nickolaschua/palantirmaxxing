"""Decode the frontend's OSM military polygons into GeoJSON and CSV.

Run from the repo root:  python backend/data_sources/consequence/defence/geography/build_military_areas.py

Reads frontend/src/demo/military.json (read-only): OpenStreetMap landuse=military rings, stored as integer
degrees x 1e5, delta-encoded after the first point. Writes defence_output_sites.geojson (WGS84) and
defence_output.csv into output/defence/. Geography only: no capability, readiness or function data.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re

import geopandas as gpd
from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "output" / "defence"  # derived files go to the git-ignored output folder
SOURCE = HERE.parents[4] / "frontend" / "src" / "demo" / "military.json"
AIR_BASE = re.compile(r"air\s?base", re.IGNORECASE)


def decode(encoded: list) -> list:
    x, y = encoded[0], encoded[1]
    points = [(x / 1e5, y / 1e5)]
    for i in range(2, len(encoded), 2):
        x += encoded[i]
        y += encoded[i + 1]
        points.append((x / 1e5, y / 1e5))
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def main() -> None:
    areas = json.loads(SOURCE.read_text(encoding="utf-8"))["military"]
    frame = gpd.GeoDataFrame(
        [{"id": f"military-{i}", "name": a["name"] or "", "vertices": len(a["ring"]) // 2,
          "name_contains_air_base": bool(a["name"] and AIR_BASE.search(a["name"]))} for i, a in enumerate(areas)],
        geometry=[Polygon(decode(a["ring"])) for a in areas], crs="EPSG:4326")
    invalid = int((~frame.geometry.is_valid).sum())
    projected = frame.to_crs("EPSG:3414")
    centre = projected.centroid.to_crs("EPSG:4326")
    frame["area_m2"] = projected.area.round(1)
    frame["centroid_lat"] = centre.y.round(6)
    frame["centroid_lon"] = centre.x.round(6)
    frame["source"] = "OpenStreetMap landuse=military (via frontend/src/demo/military.json)"

    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_file(OUT / "defence_output_sites.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)
    columns = ["id", "name", "name_contains_air_base", "centroid_lat", "centroid_lon", "area_m2", "vertices", "source"]
    with (OUT / "defence_output.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns + ["geometry_wkt"])
        for _, row in frame.iterrows():
            writer.writerow([row[c] for c in columns] + [row.geometry.wkt])
    print(f"{len(frame)} areas ({int((frame.name != '').sum())} named, {int(frame.name_contains_air_base.sum())} air-base names), "
          f"{invalid} invalid geometries")


if __name__ == "__main__":
    main()
