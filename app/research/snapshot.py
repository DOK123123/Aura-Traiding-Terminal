"""Bounded portable research-only snapshots. No SQL, execution or HTTP writes."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
from app.lab.models import LabError, canonical, digest
from .artifacts import ARRAYS, CHUNK_LIMIT, COMPACT_LIMIT, TOTAL_LIMIT, checked_manifest, decode, unpack_chunk, bad

FORMAT = 'AURA_PUBLIC_RESEARCH_SNAPSHOT_1'
INDEX_LIMIT = COMPACT_LIMIT + 4096
PACKED_LIMIT = 16 * 1024**2
ROOT = Path(__file__).resolve().parents[2]
APPROVED = ROOT / 'docs/research-snapshot'
SENSITIVE = re.compile(r'api[_-]?key|api[_-]?secret|password|authorization|access[_-]?token|private[_-]?key|llm_calls|prompt|completion', re.I)
CREDENTIAL = re.compile(r'Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|-----BEGIN .*PRIVATE KEY|https?://[^\s/]+:[^\s/]+@', re.I)


def public_data(value, depth=0):
    """Fail closed on credential-bearing metadata, never read environment values."""
    if depth > 24: bad()
    if type(value) is dict:
        for k, v in value.items():
            if not isinstance(k, str) or SENSITIVE.search(k): bad()
            public_data(v, depth + 1)
    elif type(value) is list:
        for v in value: public_data(v, depth + 1)
    elif type(value) is str:
        if len(value) > 8192 or CREDENTIAL.search(value): bad()
    elif value is not None and type(value) not in (bool, int, float): bad()


def safe_dir(path):
    p = Path(path).absolute()
    if any(x.is_symlink() for x in (p, *p.parents)): bad()
    return p


def read_file(path, limit):
    safe_dir(path)
    try:
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > limit: bad()
        with path.open('rb') as f: data = f.read(limit + 1)
        if len(data) > limit: bad()
        return data
    except OSError: bad()


def chunk_name(run, kind, ordinal):
    return f'chunk-{run}-{kind}-{ordinal}.gz'


class SnapshotStore:
    """Same read interface as Store, backed by immutable public artifacts only."""
    readonly = True

    def __init__(self, directory):
        self.directory = safe_dir(directory)
        raw = read_file(self.directory / 'index.json', INDEX_LIMIT)
        self.index = decode(raw)
        index = self.index
        if type(index) is not dict or set(index) != {'format', 'row', 'checksum'} or index['format'] != FORMAT: bad()
        if digest({k:v for k,v in index.items() if k != 'checksum'}) != index['checksum']: bad()
        row = index['row']
        if type(row) is not dict or set(row) != {'id','fingerprint','hypothesis','state','created','updated','config','report'}: bad()
        if not re.fullmatch('[0-9a-f]{32}', str(row['id'])) or type(row['created']) is not int or type(row['updated']) is not int: bad()
        report = checked_manifest(row['report'])
        if row['state'] != report['auditor']['status'] or row['config'] != report['config'] or row['fingerprint'] != digest(row['config']) or row['hypothesis'] != row['config'].get('hypothesis'): bad()
        if report.get('llm_used') is not False: bad()
        public_data(index)
        self.names = {'index.json'}
        total = chunks = packed = 0
        for run in report['runs']:
            for kind, ref in run['artifacts'].items():
                for d in ref['chunks']:
                    self.names.add(chunk_name(run['run_key'], kind, d['ordinal']))
                    total += d['bytes']; chunks += 1
        if total > TOTAL_LIMIT or chunks > 2048: bad()
        for f in self.directory.iterdir():
            if f.name not in self.names or not f.is_file() or f.is_symlink() or f.stat().st_nlink != 1: bad()
            packed += f.stat().st_size
        if packed > PACKED_LIMIT or {p.name for p in self.directory.iterdir()} != self.names: bad()

    def list(self):
        return [{k:self.index['row'][k] for k in ('id','hypothesis','state','created','updated')} | {'error':None}]

    def calls(self): return []

    def get(self, ident):
        if ident != self.index['row']['id']: raise LabError('RESEARCH_NOT_FOUND')
        return deepcopy(self.index['row']) | dict(error=None, attempt=None, events=[], event_total=0, publication='OWNER_REVIEWED_GIT_SNAPSHOT')

    def events(self, ident, after=0, limit=100):
        self.get(ident)
        return dict(id=ident, events=[], next_after=None, research_only=True)

    def page(self, ident, run_key, kind, offset=0, limit=100):
        row = self.get(ident)
        if kind not in ARRAYS or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100: raise LabError('INVALID_DATA')
        run = next((r for r in row['report']['runs'] if r['run_key'] == run_key), None)
        if run is None: raise LabError('RESEARCH_NOT_FOUND')
        ref = run['artifacts'][kind]; values = []
        if offset < ref['records']:
            d = next(d for d in ref['chunks'] if d['start'] <= offset < d['start'] + d['count'])
            raw = read_file(self.directory / chunk_name(run_key, kind, d['ordinal']), CHUNK_LIMIT + 1024)
            records = unpack_chunk(raw, d); public_data(records)
            left = offset - d['start']; values = records[left:left+limit]
        return dict(id=ident, run_key=run_key, kind=kind, records=values, total=ref['records'], offset=offset, next_offset=offset+len(values) if offset+len(values)<ref['records'] else None, research_only=True)

    def verify(self):
        for run in self.index['row']['report']['runs']:
            for kind, ref in run['artifacts'].items():
                h = hashlib.sha256(); offset = 0
                while offset < ref['records']:
                    page = self.page(self.index['row']['id'], run['run_key'], kind, offset)
                    for record in page['records']: h.update(canonical(record) + b'\n')
                    offset += len(page['records'])
                if h.hexdigest() != ref['sha256']: bad()
        return dict(status='PASS', checksum=self.index['checksum'], publication='PUBLIC_DATA_REQUIRES_OWNER_REVIEW')


def export_snapshot(store, ident, destination):
    """CLI only. Export completed public results, never credentials/LLM logs/DB."""
    row = store.get(ident)
    attempt = row['attempt']
    if row['report'] is None: raise LabError('RESEARCH_NOT_FOUND')
    row = {k:row[k] for k in ('id','fingerprint','hypothesis','state','created','updated','config','report')}
    index = dict(format=FORMAT, row=row); public_data(index); index['checksum'] = digest(index)
    dest = safe_dir(destination)
    if dest.exists(): raise LabError('RESEARCH_ALREADY_PROCESSED')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=dest.parent) as temp:
        stage = Path(temp) / 'bundle'; stage.mkdir()
        raw = canonical(index)
        if len(raw) > INDEX_LIMIT: bad()
        (stage/'index.json').write_bytes(raw)
        size = len(raw)
        with store.connect() as c:
            for run in row['report']['runs']:
                for kind, ref in run['artifacts'].items():
                    for d in ref['chunks']:
                        found = c.execute('select case when length(payload)<=? then payload else null end payload from chunks where job_id=? and attempt=? and run_key=? and kind=? and ordinal=?', (CHUNK_LIMIT+1024, ident, attempt, run['run_key'], kind, d['ordinal'])).fetchone()
                        if found is None or found['payload'] is None: bad()
                        size += len(found['payload'])
                        if size > PACKED_LIMIT: bad()
                        public_data(unpack_chunk(found['payload'], d))
                        (stage/chunk_name(run['run_key'],kind,d['ordinal'])).write_bytes(found['payload'])
        result = SnapshotStore(stage).verify()
        # Exclusive publication; never overwrite a prior snapshot, even on races.
        try: dest.mkdir()
        except FileExistsError: raise LabError('RESEARCH_ALREADY_PROCESSED') from None
        try:
            for f in stage.iterdir(): shutil.copyfile(f, dest/f.name)
            SnapshotStore(dest).verify()
        except BaseException:
            shutil.rmtree(dest); raise
        return result


def publish_snapshot(bundle, expected_checksum):
    """Offline owner-reviewed Git staging only; never production filesystem writes."""
    if os.getenv('RENDER'): raise LabError('RESEARCH_LOCAL_WORKBENCH_REQUIRED')
    source = SnapshotStore(bundle)
    if source.index['checksum'] != expected_checksum: bad()
    source.verify()
    if APPROVED.exists(): raise LabError('RESEARCH_ALREADY_PROCESSED')
    # Only this fixed research-artifact destination; no supplied SQL or file paths.
    safe_dir(APPROVED)
    try: APPROVED.mkdir()
    except FileExistsError: raise LabError('RESEARCH_ALREADY_PROCESSED') from None
    try:
        for name in source.names: shutil.copyfile(source.directory/name, APPROVED/name)
        SnapshotStore(APPROVED).verify()
    except BaseException:
        shutil.rmtree(APPROVED); raise
    return dict(status='STAGED_FOR_GIT_REVIEW_NOT_DEPLOYED', checksum=expected_checksum)
