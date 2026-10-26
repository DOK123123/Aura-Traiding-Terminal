"""Offline safety checks for isolated manual paper. No external services."""
from decimal import Decimal
import pytest
from app.manual_paper.core import ManualPaper


def test_long_profit_and_fees():
    ledger = ManualPaper()
    ledger.open("LONG", "80000", "79500", "81000", "0.025")
    trade = ledger.close("81000")
    assert trade["gross"] == Decimal("25")
    assert trade["fees"] == Decimal("2.41500")
    assert trade["net"] == Decimal("22.58500")
    assert ledger.balance == Decimal("10022.58500")
    assert len(ledger.trades) == 1


def test_short_stop_first_when_both_touched():
    ledger = ManualPaper()
    ledger.open("SHORT", "80000", "80500", "79000", "0.025")
    trade = ledger.on_closed_candle("80600", "78900", "80000")
    assert trade["exit"] == Decimal("80500")
    assert trade["net"] < 0


@pytest.mark.parametrize("side,entry,stop,target,qty", [
    ("LONG", "80000", "81000", "82000", "0.01"),
    ("SHORT", "80000", "79000", "78000", "0.01"),
    ("LONG", "80000", "79000", "81000", "0.1"),
    ("LONG", "80000", "79000", "81000", "0.025"),
    ("LONG", "nan", "79000", "81000", "0.01"),
])
def test_invalid_orders(side, entry, stop, target, qty):
    with pytest.raises(ValueError):
        ManualPaper().open(side, entry, stop, target, qty)


def test_no_double_entry_or_double_close():
    ledger = ManualPaper()
    ledger.open("LONG", "80000", "79500", "81000", "0.01")
    with pytest.raises(ValueError, match="POSITION_ALREADY_OPEN"):
        ledger.open("SHORT", "80000", "80500", "79000", "0.01")
    ledger.close("80000")
    with pytest.raises(ValueError, match="NO_POSITION"):
        ledger.close("80000")


def test_no_fill_on_unreached_candle():
    ledger = ManualPaper()
    ledger.open("LONG", "80000", "79500", "81000", "0.01")
    assert ledger.on_closed_candle("80500", "79900", "80200") is None
    assert ledger.position is not None
