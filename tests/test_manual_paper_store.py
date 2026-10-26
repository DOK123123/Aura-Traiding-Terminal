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
