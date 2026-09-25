"""LTA DataMall access: road speed bands and monthly train passenger volumes.

Everything here is optional. Without LTA_ACCOUNT_KEY the callers fall back to
OSM proxies (roads) or mark station occupancy unavailable (rail). Passenger
volume downloads are cached under cache/transport/datamall/ and checksummed so a run
can be reproduced offline.

The PV/Train and PV/ODTrain column layout below follows the DataMall API guide
but has not been exercised against the live service (no key was available);
the parsers are tested on fixtures only.
"""
from __future__ import annotations

import calendar
import hashlib
import io
import logging
import os
from pathlib import Path
import time
import zipfile

import pandas as pd
import requests

from backend.data_sources.consequence.conditions import CONDITIONS, hours
from backend.data_sources.consequence.paths import DATAMALL_CACHE

log = logging.getLogger(__name__)

LTA_ACCOUNT_KEY = os.environ.get('LTA_ACCOUNT_KEY')
DATAMALL_SPEEDBANDS_URL = 'http://datamall2.mytransport.sg/ltaodataservice/v3/TrafficSpeedBands'
DATAMALL_PV_URL = 'http://datamall2.mytransport.sg/ltaodataservice/PV/{kind}'
CACHE_DIR = DATAMALL_CACHE

# Month-to-month and holiday variation around the monthly mean (assumption, uncalibrated).
MONTHLY_VARIATION = (0.85, 1.0, 1.15)


def _headers() -> dict:
    return {'AccountKey': LTA_ACCOUNT_KEY, 'accept': 'application/json'}


def fetch_speedbands() -> pd.DataFrame:
    rows, skip = [], 0
    while True:
        resp = requests.get(DATAMALL_SPEEDBANDS_URL, headers=_headers(), params={'$skip': skip}, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get('value', [])
        if not batch:
            break
        rows.extend(batch)
        skip += len(batch)
        time.sleep(0.2)
        if len(batch) < 500:
            break
    log.info('Fetched %d speed-band links from DataMall', len(rows))
    return pd.DataFrame(rows)


def fetch_passenger_volume(kind: str, month: str, cache_dir: Path = CACHE_DIR) -> tuple:
    """Download PV/<kind> for a YYYYMM month (kind: Train or ODTrain). Returns (DataFrame, sha256).

    DataMall answers with a short-lived link to a (usually zipped) CSV.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f'{kind}-{month}.csv'
    if not cached.exists():
        resp = requests.get(DATAMALL_PV_URL.format(kind=kind), headers=_headers(),
                            params={'Date': month}, timeout=30)
        resp.raise_for_status()
        link = resp.json()['value'][0]['Link']
        blob = requests.get(link, timeout=120)
        blob.raise_for_status()
        content = blob.content
        if zipfile.is_zipfile(io.BytesIO(content)):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                content = archive.read(next(n for n in archive.namelist() if n.lower().endswith('.csv')))
        cached.write_bytes(content)
    data = cached.read_bytes()
    return pd.read_csv(io.BytesIO(data)), hashlib.sha256(data).hexdigest()


def day_counts(month: str) -> dict:
    """Weekday and weekend day counts for YYYYMM. Public holidays are not separated (DataMall
    files them under the weekend/holiday day type), so the weekend count is a lower bound."""
    year, mon = int(month[:4]), int(month[4:])
    counts = {'weekday': 0, 'weekend': 0}
    for day in range(1, calendar.monthrange(year, mon)[1] + 1):
        counts['weekday' if calendar.weekday(year, mon, day) < 5 else 'weekend'] += 1
    return counts


def _day_type(label: str) -> str:
    return 'weekday' if str(label).upper().startswith('WEEKDAY') else 'weekend'


def station_hourly_flows(volumes: pd.DataFrame, month: str) -> dict:
    """{(station_code, condition_id): mean people tapping in + out per hour} for one month."""
    days = day_counts(month)
    df = volumes.copy()
    df['day_type'] = df['DAY_TYPE'].map(_day_type)
    df['flow'] = df['TOTAL_TAP_IN_VOLUME'] + df['TOTAL_TAP_OUT_VOLUME']
    flows = {}
    for condition in CONDITIONS:
        window = set(hours(condition))
        sel = df[(df['day_type'] == condition.day_type) & (df['TIME_PER_HOUR'].isin(window))]
        totals = sel.groupby('PT_CODE')['flow'].sum()
        for code, total in totals.items():
            flows[(code, condition.condition_id)] = total / len(window) / days[condition.day_type]
    return flows


def od_hourly_trips(od: pd.DataFrame, month: str) -> dict:
    """{(origin_code, destination_code, condition_id): mean trips per hour} for one month."""
    days = day_counts(month)
    df = od.copy()
    df['day_type'] = df['DAY_TYPE'].map(_day_type)
    trips = {}
    for condition in CONDITIONS:
        window = set(hours(condition))
        sel = df[(df['day_type'] == condition.day_type) & (df['TIME_PER_HOUR'].isin(window))]
        totals = sel.groupby(['ORIGIN_PT_CODE', 'DESTINATION_PT_CODE'])['TOTAL_TRIPS'].sum()
        for (origin, destination), total in totals.items():
            trips[(origin, destination, condition.condition_id)] = total / len(window) / days[condition.day_type]
    return trips
