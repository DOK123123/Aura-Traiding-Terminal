"""SQLite transactions, durable local journal and consistent download backups."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

from .models import PaperError


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        if str(path) == ':memory:':
            raise PaperError('STORAGE_UNAVAILABLE')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.path.exists():
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            os.chmod(self.path, 0o600)
            with self.transaction() as db:
                db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                db.execute('''CREATE TABLE IF NOT EXISTS trades (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                    source TEXT NOT NULL, signal_id TEXT UNIQUE, close_seq INTEGER,
                    data TEXT NOT NULL)''')
                db.execute('CREATE INDEX IF NOT EXISTS open_scope ON trades(status,symbol,timeframe)')
                db.execute('''CREATE TABLE IF NOT EXISTS requests (
                    key TEXT PRIMARY KEY, kind TEXT NOT NULL, digest TEXT NOT NULL,
                    trade_id TEXT NOT NULL REFERENCES trades(id))''')
                db.execute('''CREATE TABLE IF NOT EXISTS curve (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL,
                    market_at INTEGER, balance TEXT NOT NULL, equity TEXT, peak TEXT NOT NULL,
                    drawdown_pct TEXT, maximum_drawdown_pct TEXT NOT NULL)''')
        except (OSError, sqlite3.Error):
            raise PaperError('STORAGE_UNAVAILABLE') from None

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            return db
        except BaseException:
            db.close()
            raise

    @contextmanager
    def transaction(self, *, write: bool = True):
        db = None
        try:
            db = self.connect()
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except sqlite3.Error:
            if db is not None:
                db.rollback()
            raise PaperError('STORAGE_UNAVAILABLE') from None
        except BaseException:
            if db is not None:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def get(db, key: str) -> str | None:
        row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return None if row is None else row['value']

    @staticmethod
    def set(db, key: str, value: str) -> None:
        db.execute('INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key,value))

    @staticmethod
    def trades(db, *, opened: bool = False) -> list[dict]:
        sql = "SELECT data FROM trades WHERE status='OPEN' ORDER BY seq" if opened else 'SELECT data FROM trades ORDER BY seq'
        return [json.loads(row['data']) for row in db.execute(sql)]

    @staticmethod
    def save(db, trade: dict) -> None:
        db.execute('''INSERT INTO trades(id,status,symbol,timeframe,source,signal_id,close_seq,data)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,
            close_seq=excluded.close_seq,data=excluded.data''',
            (trade['id'], trade['status'], trade['symbol'], trade['timeframe'], trade['source'],
             trade['signal_id'], trade.get('close_seq'), json.dumps(trade)))

    def backup(self) -> bytes:
        try:
            with self.transaction(write=False) as db:
                memory = sqlite3.connect(':memory:')
                try:
                    db.backup(memory)
                    memory.execute('PRAGMA journal_mode=MEMORY')
                    return memory.serialize()
                finally:
                    memory.close()
        except sqlite3.Error:
            raise PaperError('STORAGE_UNAVAILABLE') from None
