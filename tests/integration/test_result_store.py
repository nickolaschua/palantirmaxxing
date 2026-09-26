"""Real file operations and independent restart checks, isolated from curated data."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

from backend.api.store import ResultNotFound, ResultStore, StoreUnavailable
from backend.api.validation import InvalidResult

ROOT = Path(__file__).resolve().parents[2]


class ResultStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.payload = json.loads((ROOT / 'data/results/demo-planning-result.json').read_text())
        self.store = ResultStore(self.directory, clock=lambda: datetime(2026, 9, 26, tzinfo=timezone.utc))

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def test_identity_order_immutable_restart_and_identical_publications(self):
        a = self.store.publish('planning', self.payload)
        older = deepcopy(self.payload)
        older['start'] = '2020-01-01T00:00:00Z'
        b = self.store.publish('planning', older)
        c = self.store.publish('planning', older)
        self.assertEqual(a['publishedAt'], b['publishedAt'])
        self.assertNotEqual(b['resultId'], c['resultId'])
        self.assertEqual(self.store.get('planning'), c)
        self.assertEqual(self.store.get('planning', a['resultId']), a)
        # Caller mutation cannot rewrite the persisted snapshot.
        c['result']['scenarioId'] = 'mutated-caller-copy'
        self.assertNotEqual(self.store.get('planning')['result']['scenarioId'], 'mutated-caller-copy')
        self.store.close()
        code = ('import json,sys; from backend.api.store import ResultStore; '
                's=ResultStore(sys.argv[1]); '
                'print(json.dumps([s.get("planning"),s.get("planning",sys.argv[2])])); s.close()')
        result = subprocess.run([sys.executable, '-c', code, str(self.directory), a['resultId']],
                                cwd=ROOT, capture_output=True, text=True, check=True, timeout=15)
        latest, lookup = json.loads(result.stdout)
        self.assertEqual(latest['resultId'], c['resultId'])
        self.assertEqual(lookup, a)

    def test_validation_and_index_failure_never_replace_latest(self):
        a = self.store.publish('planning', self.payload)
        invalid = deepcopy(self.payload)
        invalid['threat']['samples'] = invalid['threat']['samples'][:1]
        with self.assertRaises(InvalidResult):
            self.store.publish('planning', invalid)
        self.assertEqual(self.store.get('planning'), a)
        def fail():
            raise OSError('injected failure before index replacement')
        self.store.before_index_replace = fail
        with self.assertRaises(StoreUnavailable):
            self.store.publish('planning', self.payload)
        (self.directory / (str(uuid.uuid4()) + '.json')).write_text('{"orphan":true}')
        (self.directory / '.orphan.tmp').write_text('incomplete')
        self.assertEqual(self.store.get('planning'), a)
        self.store.close()
        self.store = ResultStore(self.directory)
        self.assertEqual(self.store.get('planning'), a)

    def test_concurrent_publication_one_writer_and_unique_sequence(self):
        with self.assertRaises(StoreUnavailable):
            ResultStore(self.directory)
        with ThreadPoolExecutor(max_workers=8) as pool:
            publications = list(pool.map(lambda _: self.store.publish('planning', self.payload), range(20)))
        self.assertEqual(len({row['resultId'] for row in publications}), 20)
        index = json.loads((self.directory / 'index.json').read_text())
        self.assertEqual(sorted(row['sequence'] for row in index['records'].values()), list(range(1, 21)))
        latest_id = max(index['records'], key=lambda key: index['records'][key]['sequence'])
        self.assertEqual(self.store.get('planning')['resultId'], latest_id)
        for publication in publications:
            self.assertEqual(self.store.get('planning', publication['resultId']), publication)

    def test_missing_wrong_kind_orphan_and_traversal(self):
        with self.assertRaises(ResultNotFound):
            self.store.get('planning')
        published = self.store.publish('planning', self.payload)
        orphan_id = str(uuid.uuid4())
        (self.directory / (orphan_id + '.json')).write_text(json.dumps(published))
        for identity in ('../index', '/etc/passwd', '%2e%2e%2findex', orphan_id, str(uuid.uuid4())):
            with self.assertRaises(ResultNotFound):
                self.store.get('planning', identity)
        with self.assertRaises(ResultNotFound):
            self.store.get('simulation', published['resultId'])
