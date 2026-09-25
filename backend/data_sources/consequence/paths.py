"""Local cache and output locations, kept inside this package so runs never write elsewhere."""
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
CACHE = PACKAGE / "cache"
OUTPUT = PACKAGE / "output"
POPULATION = REPO / "data" / "processed" / "population-projected.json"
SCENARIO = REPO / "data" / "scenarios" / "demo-singapore.json"  # read-only: placeholder footprint radius

SOURCES_CACHE = CACHE / "sources"  # data.gov.sg, MOH, census and OneMap downloads
DATAMALL_CACHE = CACHE / "transport" / "datamall"
OSMNX_CACHE = CACHE / "transport" / "osmnx"
