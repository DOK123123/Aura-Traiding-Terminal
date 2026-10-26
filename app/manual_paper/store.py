"""Network-free transactional Manual Paper ledger and permanent request receipts.

The runtime configuration requires a verified persistent mount on Render.
SQLite connections are always closed, including failed transactions.
"""
import json
import hashlib
import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from .core import ManualPaper, Position


class ManualStore:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError("ABSOLUTE_PATH_REQUIRED")
        if not self.path.parent.is_dir():
            raise ValueError("STORAGE_DIRECTORY_MISSING")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {'state','requests'}:
                raise ValueError('STORAGE_SCOPE_MISMATCH')
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL, version INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL)")
            db.execute("CREATE TRIGGER IF NOT EXISTS manual_requests_no_update BEFORE UPDATE ON requests BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END")
            db.execute("CREATE TRIGGER IF NOT EXISTS manual_requests_no_delete BEFORE DELETE ON requests BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END")
            # One SQL statement: two separate reads can straddle another commit.
            has_state, has_requests = db.execute('SELECT EXISTS(SELECT 1 FROM state), EXISTS(SELECT 1 FROM requests)').fetchone()
            if not has_state and has_requests:
                raise ValueError('CORRUPT_JOURNAL')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def encode(ledger):
        return json.dumps({
            "balance": str(ledger.balance),
            "starting_balance": str(ledger.starting_balance),
            "fee_rate": str(ledger.fee_rate),
            "max_risk": str(ledger.max_risk),
            "max_notional": str(ledger.max_notional),
            "realized": str(ledger.realized),
            "position": None if ledger.position is None else {
                "side": ledger.position.side,
                "quantity": str(ledger.position.quantity),
                "entry": str(ledger.position.entry),
                "stop": str(ledger.position.stop),
                "target": str(ledger.position.target),
                "entry_fee": str(ledger.position.entry_fee),
                "entry_candle_time": ledger.position.entry_candle_time,
                "id": ledger.position.id,
            },
            "trades": [{k: str(v) if isinstance(v, Decimal) else v for k, v in t.items()} for t in ledger.trades],
        }, sort_keys=True)

    @staticmethod
    def decode(payload):
        data = json.loads(payload)
        ledger = ManualPaper(data["starting_balance"], data["fee_rate"],
                             data["max_risk"], data["max_notional"])
        ledger.balance = Decimal(data["balance"])
        ledger.realized = Decimal(data["realized"])
        ledger.trades = [{k: (Decimal(v) if k in {"entry","exit","quantity","gross","fees","net","stop","target"} else v) for k,v in t.items()}
                         for t in data["trades"]]
        if data["position"] is not None:
            p = data["position"]
            ledger.position = Position(p["side"], *(Decimal(p[k]) for k in
                ("quantity", "entry", "stop", "target", "entry_fee")),
                p["entry_candle_time"], p.get("id"))
        ledger.validate()
        return ledger

    def load(self):
        with self._connect() as db:
            row = db.execute("SELECT data,version FROM state WHERE id=1").fetchone()
            if row is None:
                return None, 0
            if type(row[1]) is not int or row[1]<1:
                raise ValueError("CORRUPT_JOURNAL")
            return self.decode(row[0]), row[1]

    def save(self, ledger, expected_version):
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("INVALID_VERSION")
        ledger.validate()
        payload = self.encode(ledger)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version FROM state WHERE id=1").fetchone()
            current = row[0] if row else 0
            if current != expected_version:
                raise ValueError("CONCURRENT_UPDATE")
            if row is None:
                db.execute("INSERT INTO state(id,data,version) VALUES(1,?,1)", (payload,))
            else:
                db.execute("UPDATE state SET data=?,version=? WHERE id=1",
                           (payload, current+1))
            return current+1

    @staticmethod
    def fingerprint(command, arguments):
        return hashlib.sha256(json.dumps([command, arguments], sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def lookup(self, request_id, command, arguments):
        with self._connect() as db:
            previous = db.execute("SELECT fingerprint,result FROM requests WHERE id=?", (request_id,)).fetchone()
            if previous:
                if previous[0] != self.fingerprint(command, arguments):
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return json.loads(previous[1])
        return None

    def execute(self, request_id, command, arguments, apply_command):
        """Atomic, idempotent ledger transition. Caller supplies verified quote.

        apply_command(ledger) mutates ledger and returns a JSON-serializable
        receipt. No exchange requests or await operations inside the lock.
        """
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise ValueError("INVALID_REQUEST_ID")
        fingerprint = self.fingerprint(command, arguments)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT fingerprint,result FROM requests WHERE id=?", (request_id,)
            ).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return json.loads(previous[1])
            row = db.execute("SELECT data,version FROM state WHERE id=1").fetchone()
            ledger = self.decode(row[0]) if row else ManualPaper()
            result = apply_command(ledger)
            ledger.validate()
            receipt = {"request_id": request_id, "command": command,
                       "version": (row[1] if row else 0) + 1,
                       "balance": str(ledger.balance), "result": result}
            encoded = json.dumps(receipt, sort_keys=True)
            if row:
                db.execute("UPDATE state SET data=?,version=? WHERE id=1",
                           (self.encode(ledger), row[1]+1))
            else:
                db.execute("INSERT INTO state(id,data,version) VALUES(1,?,1)",
                           (self.encode(ledger),))
            db.execute("INSERT INTO requests(id,fingerprint,result) VALUES(?,?,?)",
                       (request_id, fingerprint, encoded))
            return receipt
