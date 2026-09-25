"""Public-data acquisition for every consequence sector. Everything is cached under cache/sources/.

Residential and school/hospital profiles share one data.gov.sg datastore reader, the repository's census
acquisition (age/sex table + MP2019 subzone boundaries) with its checksummed atomic download helpers, and
OneMap geocoding (blocks by address, postal codes by code). MOH publishes daily per-hospital bed occupancy and
emergency attendances as weekly XLSX files whose URLs change every week, so the link is scraped from the
statistics page. No API key is required; OneMap and data.gov.sg keys are sent when set (ONEMAP_TOKEN,
DATA_GOV_SG_API_KEY).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import openpyxl

from backend.data_sources.acquisition import acquire, atomic_write, checksum, get
from backend.data_sources.consequence.paths import SOURCES_CACHE

log = logging.getLogger(__name__)

CACHE = SOURCES_CACHE
DWELLING_ID = 'd_7f243956483d5901f237e6f87b096636'  # Census 2020 residents by subzone and dwelling type
HDB_ID = 'd_17f5382f26140b1fdae0ba2ef6239d2f'  # HDB Property Information
LANDUSE_ID = 'd_90d86daa5bfaa371668b84fa5f01424f'  # URA Master Plan 2019 Land Use layer
BEDS_ID = 'd_0f8f02e6e821fc88aa96442656b69241'  # SingStat Beds in Inpatient Facilities, Annual
ATTENDANCES_ID = 'd_b7dd65c9e72c036f1724a08dc69f41bd'  # SingStat Hospital Admissions and Outpatient Attendances
ADMISSION_RATE_ID = 'd_dd32a9abff167b63efc11fb2f25cb341'  # MOH Hospital Admission Rate by Age and Sex
EMS_ID = 'd_d0b4ca9fad1c5fee38d7ddfd7303845f'  # SCDF Emergency Medical Services, Annual
SCHOOLS_ID = 'd_688b934f82c1059ed0a6993d2a829089'  # MOE General information of schools
MOE_LEVEL_ID = 'd_dc92b9d107acfa23e1df76b1a33ffb4a'  # MOE Students, Education Officers and Partners by Level
DATASTORE = 'https://data.gov.sg/api/action/datastore_search'
POLL_DOWNLOAD = 'https://api-open.data.gov.sg/v1/public/api/datasets/%s/poll-download'
ONEMAP_SEARCH = 'https://www.onemap.gov.sg/api/common/elastic/search'
BOR_PAGE = ('https://www.moh.gov.sg/others/resources-and-statistics/'
            'healthcare-institution-statistics-beds-occupancy-rate-(bor)/')
EMD_PAGE = ('https://www.moh.gov.sg/others/resources-and-statistics/'
            'healthcare-institution-statistics-attendances-at-emergency-medicine-departments/')
PAGE = 5000
# Measured 2026-09-25: without a token OneMap returns 429 faster than ~1 call/s; a token allows 250/min.
GEOCODE_DELAY_S = 1.0
GEOCODE_DELAY_TOKEN_S = 0.25
XLSX_LINK = re.compile(r'https://isomer-user-content\.by\.gov\.sg/[^"\\<>]+?\.xlsx')
EXCEL_EPOCH = date(1899, 12, 30)


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def datastore_rows(resource_id: str, cache: Path = CACHE) -> dict:
    """All rows of a data.gov.sg datastore resource, paginated, cached and completeness-checked."""
    target = _mkdir(cache) / f'{resource_id}.json'
    if target.exists():
        return json.loads(target.read_text(encoding='utf-8'))
    rows, total = [], None
    while total is None or len(rows) < total:
        url = f'{DATASTORE}?resource_id={resource_id}&limit={PAGE}&offset={len(rows)}&sort=_id%20asc'
        result = json.loads(get(url))['result']
        total = result['total']
        if not result['records']:
            break
        rows += result['records']
    ids = [r.get('_id') for r in rows]
    if len(rows) != total or ids != list(range(1, total + 1)):
        raise ValueError(f'{resource_id}: incomplete download ({len(rows)} of {total} rows)')
    doc = dict(resource_id=resource_id, total=total, retrieved_at=datetime.now(timezone.utc).isoformat(),
               rows=rows)
    atomic_write(target, json.dumps(doc).encode('utf-8'))
    return doc


def load_census(cache: Path = CACHE) -> dict:
    """Age/sex census rows and the MP2019 subzone boundary features, via the repository acquirer."""
    raw = _mkdir(cache / 'census')
    manifest = acquire(raw)
    population = json.loads((raw / manifest['sources']['population']['file']).read_bytes())
    boundaries = json.loads((raw / manifest['sources']['boundaries']['file']).read_bytes())
    return dict(age_rows=population['result']['records'], features=boundaries['features'], manifest=manifest)


def landuse_path(cache: Path = CACHE) -> Path:
    """Download the URA MP2019 land-use GeoJSON once (about 175 MB) and return its cached path."""
    target = _mkdir(cache) / 'landuse-mp2019.geojson'
    if not target.exists():
        poll = json.loads(get(POLL_DOWNLOAD % LANDUSE_ID))
        if poll.get('code') != 0 or not poll.get('data', {}).get('url'):
            raise ValueError('Land-use download is not ready; retry later')
        body = get(poll['data']['url'])
        if not body.lstrip().startswith(b'{'):
            raise ValueError('Land-use download is not GeoJSON')
        atomic_write(target, body)
    return target


def file_sha256(path: Path) -> str:
    return checksum(path.read_bytes())


def _matches_street(street: str, road_name: str) -> bool:
    """HDB abbreviates streets (STH, AVE, BT); accept a hit when any street word is a prefix of a road word."""
    words = road_name.upper().replace("'", ' ').split()
    return any(w.startswith(t) for t in street.upper().replace("'", ' ').split() if len(t) >= 3 for w in words)


def pick_geocode(results: list, blk: str, street: str) -> dict | None:
    """First OneMap result with the same block number, a postal code and a matching street."""
    for r in results:
        if (str(r.get('BLK_NO', '')).upper() == blk.upper() and r.get('POSTAL', 'NIL') != 'NIL'
                and _matches_street(street, r.get('ROAD_NAME', ''))):
            return dict(x=float(r['X']), y=float(r['Y']), postal=r['POSTAL'], address=r.get('ADDRESS', ''))
    return None


def _onemap_block(blk: str, street: str) -> list:
    query = urllib.parse.urlencode(dict(searchVal=f'{blk} {street}', returnGeom='Y', getAddrDetails='Y', pageNum=1))
    headers = {'User-Agent': 'Mozilla/5.0 (Singapore consequence research prototype)'}
    if os.environ.get('ONEMAP_TOKEN'):
        headers['Authorization'] = os.environ['ONEMAP_TOKEN']
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(f'{ONEMAP_SEARCH}?{query}', headers=headers),
                                        timeout=30) as response:
                return json.loads(response.read()).get('results', [])
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(5 * (attempt + 1))
    raise ValueError(f'OneMap search failed for {blk} {street}')


def geocode_blocks(keys: list, cache: Path = CACHE) -> dict:
    """{'blk|street': {x, y, postal, address} or None} in EPSG:3414, resumable.

    A None entry is a recorded miss (no matching OneMap result), not an unattempted key.
    """
    target = _mkdir(cache) / 'onemap-geocode.json'
    done = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    todo = [k for k in keys if k not in done]
    log.info('Geocoding %d of %d blocks (rest cached)', len(todo), len(keys))
    for i, key in enumerate(todo, 1):
        blk, street = key.split('|', 1)
        done[key] = pick_geocode(_onemap_block(blk, street), blk, street)
        time.sleep(GEOCODE_DELAY_TOKEN_S if os.environ.get('ONEMAP_TOKEN') else GEOCODE_DELAY_S)
        if i % 50 == 0 or i == len(todo):
            atomic_write(target, json.dumps(done).encode('utf-8'))
            log.info('  geocoded %d / %d', i, len(todo))
    return done


def xlsx_link(html: str) -> str:
    """The single XLSX link on an MOH statistics page, with its path percent-encoded."""
    links = sorted(set(XLSX_LINK.findall(html)))
    if len(links) != 1:
        raise ValueError(f'expected one XLSX link on the MOH page, found {len(links)}')
    parts = urllib.parse.urlsplit(links[0])
    return urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(urllib.parse.unquote(parts.path))))


def moh_workbook(page_url: str, name: str, cache: Path = CACHE, refresh: bool = False) -> tuple:
    """(cached XLSX path, metadata) for the workbook linked from an MOH page; downloaded once unless refresh."""
    target, meta_path = _mkdir(cache) / f'{name}.xlsx', cache / f'{name}.json'
    if refresh or not target.exists() or not meta_path.exists():
        url = xlsx_link(get(page_url).decode('utf-8', 'replace'))
        body = get(url)
        if not body.startswith(b'PK'):
            raise ValueError(f'{name}: download is not an XLSX workbook')
        atomic_write(target, body)
        meta = dict(page=page_url, file=urllib.parse.unquote(url.rsplit('/', 1)[-1]), sha256=checksum(body),
                    retrieved_at=datetime.now(timezone.utc).isoformat())
        atomic_write(meta_path, json.dumps(meta, indent=2).encode('utf-8'))
    return target, json.loads(meta_path.read_text(encoding='utf-8'))


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 30000 < value < 80000:
        return EXCEL_EPOCH + timedelta(days=int(value))
    return None


def daily_series(path: Path) -> dict:
    """{hospital code: {date: value}} merged over every sheet with a 'Date' header row.

    The MOH workbooks hold a historical sheet and a latest-week sheet with the same layout: a header row whose
    first cell is 'Date', hospital codes across, then one row per day. Blank cells (a hospital not yet open) are
    skipped rather than read as zero.
    """
    out: dict = {}
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for sheet in workbook.worksheets:
        codes = None
        for row in sheet.iter_rows(values_only=True):
            if not row:
                continue
            if codes is None:
                if isinstance(row[0], str) and row[0].strip().lower() == 'date':
                    codes = [str(c).strip() if c is not None else None for c in row[1:]]
                continue
            day = _as_date(row[0])
            if day is None:
                continue
            for code, value in zip(codes, row[1:]):
                if code and isinstance(value, (int, float)) and not isinstance(value, bool):
                    out.setdefault(code, {})[day] = float(value)
    workbook.close()
    if not out:
        raise ValueError(f'{path.name}: no daily series found')
    return out


def load_census_age(cache: Path = CACHE) -> dict:
    """The national 'Total' row of Census 2020 residents by age and sex, via the repository acquirer."""
    rows = load_census(cache)['age_rows']
    total = [r for r in rows if str(r.get('Number', '')).strip() == 'Total']
    if len(total) != 1:
        raise ValueError('census age table has no single national Total row')
    return total[0]


def postal6(value) -> str:
    """Six-digit postal code; MOE drops the leading zero of codes such as 088256."""
    return str(value).strip().zfill(6)


def pick_postal(results: list, postal: str) -> dict | None:
    """First OneMap result carrying exactly this postal code."""
    for r in results:
        if str(r.get('POSTAL', '')) == postal:
            return dict(x=float(r['X']), y=float(r['Y']), address=r.get('ADDRESS', ''), building=r.get('BUILDING', ''))
    return None


def _onemap_postal(url: str) -> list:
    """OneMap results, retrying network failures (the shared get() retries only HTTP errors)."""
    for attempt in range(5):
        try:
            return json.loads(get(url)).get('results', [])
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            if attempt == 4:
                raise
            log.warning('OneMap call failed (%s); retrying', error)
            time.sleep(10 * (attempt + 1))


def geocode_postals(postals: list, cache: Path = CACHE) -> dict:
    """{postal: {x, y, address, building} or None} in EPSG:3414, cached and resumable. None is a recorded miss."""
    target = _mkdir(cache) / 'onemap-postal.json'
    done = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    postals = [postal6(p) for p in postals]
    todo = [p for p in dict.fromkeys(postals) if p not in done]
    log.info('Geocoding %d of %d postal codes (rest cached)', len(todo), len(set(postals)))
    for i, postal in enumerate(todo, 1):
        query = urllib.parse.urlencode(dict(searchVal=postal, returnGeom='Y', getAddrDetails='Y', pageNum=1))
        done[postal] = pick_postal(_onemap_postal(f'{ONEMAP_SEARCH}?{query}'), postal)
        time.sleep(GEOCODE_DELAY_S)
        if i % 25 == 0 or i == len(todo):
            atomic_write(target, json.dumps(done).encode('utf-8'))
    return done
