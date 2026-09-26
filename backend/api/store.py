"""Single-writer, immutable result store with atomic publication indexing."""
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import threading
import uuid

from .validation import validate_result


class StoreUnavailable(RuntimeError):
    """A temporary storage failure which HTTP delivery can expose as 503."""


class ResultNotFound(LookupError):
    pass


def atomic_json(path, value, before_replace=None):
    """Flush content before rename; publish only complete UTF-8 strict JSON."""
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace:
            before_replace()
        os.replace(temporary, path)
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def canonical_id(identity):
    try:
        return isinstance(identity, str) and str(uuid.UUID(identity)) == identity
    except (ValueError, AttributeError):
        return False


class ResultStore:
    def __init__(self, directory, *, writable=True, clock=None, before_index_replace=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._writer = None
        self._closed = False
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.before_index_replace = before_index_replace
        if writable:
            self._writer = (self.directory / '.writer.lock').open('a')
            try:
                fcntl.flock(self._writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self._writer.close()
                self._writer = None
                raise StoreUnavailable(f'Publication store already has a writer: {self.directory}') from exc

    def close(self):
        with self._lock:
            self._closed = True
            if self._writer:
                fcntl.flock(self._writer.fileno(), fcntl.LOCK_UN)
                self._writer.close()
                self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _index(self):
        if self._closed:
            raise StoreUnavailable('Publication store is closed')
        path = self.directory / 'index.json'
        if not path.exists():
            return {'version': 1, 'sequence': 0, 'records': {}}
        try:
            index = json.loads(path.read_text(encoding='utf-8'))
            if index['version'] != 1 or type(index['sequence']) is not int or not isinstance(index['records'], dict):
                raise ValueError('Unsupported publication index')
            sequences = []
            for identity, record in index['records'].items():
                if not canonical_id(identity) or record['kind'] not in ('planning', 'simulation'):
                    raise ValueError('Invalid publication identity/kind')
                if type(record['sequence']) is not int or not 0 < record['sequence'] <= index['sequence']:
                    raise ValueError('Invalid publication sequence')
                sequences.append(record['sequence'])
            if len(sequences) != len(set(sequences)):
                raise ValueError('Duplicate publication sequence')
            return index
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise StoreUnavailable(f'Cannot read publication index: {exc}') from exc

    def completed_runs(self):
        with self._lock:
            return deepcopy(self._index().get('completedRuns', {}))

    def publish(self, kind, payload, *, completed_run=None):
        payload = deepcopy(payload)
        validate_result(kind, payload)
        with self._lock:
            if not self._writer or self._closed:
                raise StoreUnavailable('This store is not an active writer')
            index = self._index()
            identity = str(uuid.uuid4())
            published_at = self.clock()
            if published_at.tzinfo is None:
                raise ValueError('Publication clock must be timezone-aware')
            envelope = {'resultId': identity,
                        'publishedAt': published_at.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z'),
                        'result': payload}
            sequence = index['sequence'] + 1
            index['sequence'] = sequence
            index['records'][identity] = {'kind': kind, 'sequence': sequence}
            if completed_run is not None:
                if not canonical_id(completed_run.get('runId')) or completed_run.get('kind') != kind:
                    raise ValueError('Completed run identity/kind must match publication')
                # One index rename commits both the publication and the exact job
                # identity. A crash cannot leave a published result with a run
                # that is later misclassified as interrupted/failed.
                finished = dict(completed_run, status='succeeded', resultKind=kind,
                                resultId=identity, updatedAt=envelope['publishedAt'])
                index.setdefault('completedRuns', {})[finished['runId']] = finished
            try:
                atomic_json(self.directory / (identity + '.json'), envelope)
                atomic_json(self.directory / 'index.json', index, self.before_index_replace)
            except OSError as exc:
                raise StoreUnavailable(f'Cannot publish result: {exc}') from exc
            return envelope

    def get(self, kind, identity='latest'):
        if kind not in ('planning', 'simulation'):
            raise ResultNotFound('Unknown result kind')
        if identity != 'latest' and not canonical_id(identity):
            raise ResultNotFound('Unknown result identity')
        with self._lock:
            index = self._index()
            if identity == 'latest':
                matches = [(record['sequence'], key) for key, record in index['records'].items() if record['kind'] == kind]
                if not matches:
                    raise ResultNotFound('No published result')
                identity = max(matches)[1]
            record = index['records'].get(identity)
            if not record or record['kind'] != kind:
                raise ResultNotFound('No matching published result')
            try:
                envelope = json.loads((self.directory / (identity + '.json')).read_text(encoding='utf-8'))
                if envelope['resultId'] != identity:
                    raise ValueError('Snapshot identity differs from index')
                return envelope
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise StoreUnavailable(f'Cannot read publication snapshot: {exc}') from exc
