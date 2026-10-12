"""Independent immutable research snapshots/results; never accesses Paper SQLite."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib
from .models import LabError,canonical,digest

MAX_BYTES=25*1024*1024
RETENTION=10


def unpack(data):
    try:
        d=zlib.decompressobj();raw=d.decompress(data,MAX_BYTES+1)
        if len(raw)>MAX_BYTES or d.unconsumed_tail or not d.eof or d.unused_data:raise ValueError()
        return json.loads(raw),hashlib.sha256(raw).hexdigest()
    except (ValueError,zlib.error,TypeError):raise LabError('CORRUPT_EXPERIMENT') from None


class Store:
    def __init__(self,path,forbidden=()):self.path=Path(path);self.forbidden=tuple(Path(p) for p in forbidden)
    def connect(self):
        for protected in self.forbidden:
            if self.path.resolve()==protected.resolve():raise LabError('PATH_CONFLICT')
            if self.path.exists() and protected.exists() and self.path.stat().st_ino==protected.stat().st_ino and self.path.stat().st_dev==protected.stat().st_dev:
                raise LabError('PATH_CONFLICT')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=5)
        db.execute('''CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,snapshot BLOB NOT NULL,config TEXT NOT NULL,
            report BLOB NOT NULL,report_hash TEXT NOT NULL,created_at INTEGER NOT NULL)''')
        return db
    def save(self,snapshot,config,report):
        ident=digest(dict(dataset_id=digest(snapshot),config=config,software_hash=report['software_hash']))
        data=canonical(report)
        if len(data)>MAX_BYTES or len(canonical(snapshot))>MAX_BYTES:raise LabError('RESULT_LIMIT')
        try:
            with closing(self.connect()) as db,db:
                db.execute('INSERT OR IGNORE INTO experiments VALUES (?,?,?,?,?,?)',
                           (ident,zlib.compress(canonical(snapshot)),canonical(config).decode(),zlib.compress(data),hashlib.sha256(data).hexdigest(),report['dataset_end_exclusive']))
                # Keep the ten most recently inserted immutable experiments, regardless of date range.
                db.execute('DELETE FROM experiments WHERE id IN (SELECT id FROM experiments ORDER BY rowid DESC LIMIT -1 OFFSET ?)',(RETENTION,))
            return ident
        except (sqlite3.Error,OSError):raise LabError('STORAGE_UNAVAILABLE') from None
    def load(self,ident):
        try:
            with closing(self.connect()) as db:
                row=db.execute('SELECT * FROM experiments WHERE id=?',(ident,)).fetchone()
            if row is None:raise LabError('EXPERIMENT_NOT_FOUND')
            snapshot,snap_hash=unpack(row[1]);config=json.loads(row[2]);report,report_hash=unpack(row[3])
            if report_hash!=row[4] or snap_hash!=report['dataset_id'] or digest(dict(dataset_id=snap_hash,config=config,software_hash=report['software_hash']))!=ident:raise LabError('CORRUPT_EXPERIMENT')
            return snapshot,config,report
        except (sqlite3.Error,OSError):raise LabError('STORAGE_UNAVAILABLE') from None
        except (ValueError,KeyError,TypeError):raise LabError('CORRUPT_EXPERIMENT') from None
    def list(self):
        try:
            with closing(self.connect()) as db:
                return [dict(id=r[0],coverage_end=r[1]) for r in db.execute('SELECT id,created_at FROM experiments ORDER BY rowid DESC LIMIT 10')]
        except (sqlite3.Error,OSError):raise LabError('STORAGE_UNAVAILABLE') from None
