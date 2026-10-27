"""Fail-closed verification of public Bitget closed-candle snapshots.

Pure functions only: no network calls, no production API or trade execution.
The caller must fetch *independent* overlapping snapshots and validate each.
"""
from decimal import Decimal
from .core import number

class QuoteRejected(ValueError):
    pass

def verified_close(first, second, *, now, timeframe_seconds=900):
    """Return a trusted closed-candle price only for matching fresh snapshots.

    Snapshots are dicts with 'source', 'symbol', 'timeframe', 'candles'.
    Candle timestamps are UNIX seconds and OHLCV values must be positive/valid.
    This does not certify exchange fills or protect against a common upstream bug.
    """
    if timeframe_seconds not in (60, 300, 900, 3600):
        raise QuoteRejected("INVALID_TIMEFRAME")
    def check(snapshot):
        if not isinstance(snapshot, dict):
            raise QuoteRejected("INVALID_SNAPSHOT")
        if (snapshot.get("symbol") != "BTCUSDT" or
            snapshot.get("source") != "Bitget USDT-M Futures" or
            snapshot.get("timeframe") != timeframe_seconds):
            raise QuoteRejected("SOURCE_MISMATCH")
        candles = snapshot.get("candles")
        if not isinstance(candles, list) or len(candles) < 2:
            raise QuoteRejected("INSUFFICIENT_HISTORY")
        checked = []
        for row in candles:
            if not isinstance(row, dict):
                raise QuoteRejected("INVALID_CANDLE")
            t = row.get("time")
            if type(t) is not int or t <= 0 or t % timeframe_seconds:
                raise QuoteRejected("INVALID_TIMESTAMP")
            try:
                o, h, l, c = [number(row[k]) for k in ("open", "high", "low", "close")]
                v = Decimal(str(row["volume"]))
            except (KeyError, ValueError, TypeError, ArithmeticError):
                raise QuoteRejected("INVALID_CANDLE") from None
            if not v.is_finite() or v < 0 or l > min(o,c) or h < max(o,c,l):
                raise QuoteRejected("INVALID_CANDLE")
            checked.append((t,o,h,l,c,v))
        if any(b[0] - a[0] != timeframe_seconds for a,b in zip(checked,checked[1:])):
            raise QuoteRejected("HISTORY_GAP_OR_DUPLICATE")
        end = checked[-1][0] + timeframe_seconds
        if end > now or now - end >= timeframe_seconds:
            raise QuoteRejected("STALE_CANDLE")
        return checked
    a,b = check(first),check(second)
    if a != b:
        raise QuoteRejected("HISTORY_CANDLE_CHANGED")
    return dict(time=a[-1][0], price=a[-1][4], source="Bitget USDT-M Futures",
                timeframe=timeframe_seconds)
