"""Offline store tests; never touch production databases."""
import pytest
from app.manual_paper.core import ManualPaper
from app.manual_paper.store import ManualStore


def test_round_trip_and_no_reset(tmp_path):
    store = ManualStore(str(tmp_path / "manual-paper.sqlite"))
    assert store.load() == (None, 0)
    ledger = ManualPaper()
    ledger.open("LONG", "80000", "79500", "81000", "0.01", candle_time=1793007000)
    assert store.save(ledger, 0) == 1
    loaded, version = ManualStore(str(tmp_path / "manual-paper.sqlite")).load()
    assert version == 1
    assert loaded.position == ledger.position
    assert loaded.balance == ledger.balance
    loaded.close("81000")
    assert store.save(loaded, version) == 2
    restored, version = store.load()
    assert version == 2
    assert restored.position is None
    assert restored.trades == loaded.trades
    assert restored.realized == loaded.realized


def test_reject_stale_version(tmp_path):
    store = ManualStore(str(tmp_path / "ledger.sqlite"))
    store.save(ManualPaper(), 0)
    with pytest.raises(ValueError, match="CONCURRENT_UPDATE"):
        store.save(ManualPaper(), 0)


def test_reject_relative_storage_path():
    with pytest.raises(ValueError, match="ABSOLUTE_PATH_REQUIRED"):
        ManualStore("manual-paper.sqlite")


def test_do_not_replay_entry_candle():
    ledger = ManualPaper()
    ledger.open("LONG", "80000", "79500", "81000", "0.01", candle_time=1793007000)
    with pytest.raises(ValueError, match="CANDLE_NOT_AFTER_ENTRY"):
        ledger.on_closed_candle("81500", "79000", "80000", candle_time=1793007000)
    assert ledger.position is not None
    trade = ledger.on_closed_candle("81500", "79000", "80000", candle_time=1793007900)
    assert trade["exit"] == ledger.trades[-1]["exit"]


def test_cold_start_wal_busy_retries_initialization_only(tmp_path,monkeypatch):
    import sqlite3
    from app.manual_paper.commands import ManualCommands
    from app.manual_paper.store import ManualStore
    real_connect=sqlite3.connect;attempts=[]
    class Connection:
        def __init__(self,*a,**kw):self.inner=real_connect(*a,**kw)
        def __getattr__(self,name):return getattr(self.inner,name)
        def execute(self,sql,*a):
            if sql=='PRAGMA journal_mode=WAL':
                attempts.append(sql)
                if len(attempts)==1:
                    error=sqlite3.OperationalError('dummy cold-start writer lock')
                    error.sqlite_errorcode=sqlite3.SQLITE_BUSY
                    raise error
            return self.inner.execute(sql,*a)
    monkeypatch.setattr(sqlite3,'connect',Connection)
    store=ManualStore(tmp_path/'manual-paper.sqlite3')
    cmd=ManualCommands(store)
    q={'source':'Bitget USDT-M Futures','time':1793007900000,'price':'80000'}
    first=cmd.open('a'*32,'LONG','0.01','79500','81000',q)
    assert cmd.open('a'*32,'LONG','0.01','79500','81000',q)==first
    ledger,version=store.load()
    assert len(attempts)==2 and version==1 and str(ledger.balance)=='9999.520000'
    assert ledger.position.id=='a'*32
