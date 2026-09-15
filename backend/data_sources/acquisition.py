"""Cached, atomic official source acquisition. Signed download URLs are never stored."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .population import POPULATION_ID, BOUNDARY_ID, EXPECTED_POPULATION_ROWS, EXPECTED_BOUNDARIES, load_population

SOURCE_URLS = {name: f'https://data.gov.sg/datasets/{id}/view'
               for name, id in [('population', POPULATION_ID), ('boundaries', BOUNDARY_ID)]}
POPULATION_API = f'https://data.gov.sg/api/action/datastore_search?resource_id={POPULATION_ID}'
BOUNDARY_API = f'https://api-open.data.gov.sg/v1/public/api/datasets/{BOUNDARY_ID}/poll-download'


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, content: bytes):
    """Write in the destination filesystem; failed writes never truncate prior data."""
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def get(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Singapore population research prototype)', 'Accept': '*/*'}
    # Send optional credentials only to the government API, never the signed blob URL.
    if os.environ.get('DATA_GOV_SG_API_KEY') and urllib.parse.urlparse(url).hostname in ('data.gov.sg', 'api-open.data.gov.sg'):
        headers['x-api-key'] = os.environ['DATA_GOV_SG_API_KEY']
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                body = response.read()
                length = response.headers.get('Content-Length')
                if length and len(body) != int(length):
                    raise ValueError('Truncated download')
                return body
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                # Do not expose signed query strings in error logs.
                raise ValueError(f'Download failed: HTTP {error.code} from {urllib.parse.urlparse(url).hostname}') from None
            time.sleep(12)
    raise ValueError('Download retries exhausted')


def validate_boundary(data):
    doc = json.loads(data)
    if doc.get('type') != 'FeatureCollection' or not isinstance(doc.get('features'), list):
        raise ValueError('Expected complete official boundary GeoJSON FeatureCollection')
    if len(doc['features']) != EXPECTED_BOUNDARIES:
        raise ValueError(f'Boundary count changed: expected {EXPECTED_BOUNDARIES}; review source vintage before accepting')
    for feature in doc['features']:
        if not {'SUBZONE_C', 'SUBZONE_N', 'PLN_AREA_C', 'PLN_AREA_N'} <= feature.get('properties', {}).keys():
            raise ValueError('Boundary properties do not match inspected MP2019 source')
    return doc


def verify_cache(raw: Path):
    manifest = json.loads((raw / 'acquisition.json').read_bytes())
    for name, source in manifest['sources'].items():
        content = (raw / source['file']).read_bytes()
        if checksum(content) != source['sha256']:
            raise ValueError(f'Cached {name} checksum mismatch; reacquire or import explicitly')
    population = raw / manifest['sources']['population']['file']
    if len(load_population(population)) != EXPECTED_POPULATION_ROWS:
        raise ValueError('Incomplete cached population')
    validate_boundary((raw / manifest['sources']['boundaries']['file']).read_bytes())
    return manifest


def acquire(raw: Path, refresh=False, population_file=None, boundary_file=None):
    if bool(population_file) != bool(boundary_file):
        raise ValueError('Supply both --population-file and --boundary-file for an explicit local import')
    if not population_file and not refresh and (raw / 'acquisition.json').exists():
        return verify_cache(raw)
    retrieval = datetime.now(timezone.utc).isoformat()
    if population_file:
        population_file, boundary_file = Path(population_file), Path(boundary_file)
        population = population_file.read_bytes()
        boundaries = boundary_file.read_bytes()
        population_name = 'population.csv' if population_file.suffix.lower() == '.csv' else 'population-api.json'
        method = 'local_official_files'
    else:
        # Explicit order and a complete download in one response; total and contiguous
        # _id validation detect a server-side cap instead of accepting partial rows.
        population = get(POPULATION_API + '&limit=1000&sort=_id%20asc')
        population_name = 'population-api.json'
        poll = json.loads(get(BOUNDARY_API))
        if poll.get('code') != 0 or not poll.get('data', {}).get('url'):
            raise ValueError('Official boundary download is not ready; cache unchanged, retry later')
        boundaries = get(poll['data']['url'])
        method = 'official_complete_api_and_poll_download'
    # Validate in temporary files before touching the cache.
    with tempfile.TemporaryDirectory(prefix='sdth-source-') as temp:
        pp = Path(temp) / population_name
        pp.write_bytes(population)
        if len(load_population(pp)) != EXPECTED_POPULATION_ROWS:
            raise ValueError('Population row count differs from the published 388 rows')
    validate_boundary(boundaries)
    manifest = dict(population_year=2020, boundary_vintage=2019, retrieved_at=retrieval,
                    retrieval_meaning='Local import time; original download date unknown' if population_file else 'Official download time (UTC)',
                    method=method, sources={})
    for name, id, filename, data, access in [
        ('population', POPULATION_ID, population_name, population, POPULATION_API),
        ('boundaries', BOUNDARY_ID, 'boundaries.geojson', boundaries, BOUNDARY_API)]:
        manifest['sources'][name] = dict(dataset_id=id, source_url=SOURCE_URLS[name], access_url=access,
                                       file=filename, sha256=checksum(data), bytes=len(data))
    manifest['completeness'] = dict(population_records=388, population_evidence='API total and consecutive _id 1..388, or official CSV row count; dataset page publishes 388',
                                    boundary_features=332, boundary_evidence='Complete poll-download blob with Content-Length check; 332 features in inspected MP2019 snapshot; no independent feature-count metadata available')
    # Publish manifest last: interruption cannot make a mismatched cache appear valid.
    atomic_write(raw / population_name, population)
    atomic_write(raw / 'boundaries.geojson', boundaries)
    atomic_write(raw / 'acquisition.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return manifest
