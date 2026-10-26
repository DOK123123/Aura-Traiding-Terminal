"""Bitget-only server quote adapter for isolated Manual Paper prototype.

This module is not mounted in production. It fetches two independent
closed-candle windows, never accepts client-submitted execution prices,
and fails closed when Bitget changes the returned history.
"""
import httpx
from app.providers import DataUnavailable
from .quotes import verified_close, QuoteRejected
from app.bitget_chart import BitgetProvider
from app.models import INTERVALS

SOURCE = "Bitget USDT-M Futures"

async def fetch_verified_quote(client, *, timeframe="15m", now=None):
    if timeframe not in INTERVALS:
        raise QuoteRejected("INVALID_TIMEFRAME")
    provider = BitgetProvider()
    # Fetch the server time once, then two fresh independent HTTP snapshots.
    server_ms = await provider.server_time(client)
    if now is not None and abs(float(now) - server_ms / 1000) > 15:
        raise QuoteRejected("SERVER_TIME_MISMATCH")
    count = 3
    try:
        first = await provider.fetch(client, timeframe, count, now_ms=server_ms)
        second = await provider.fetch(client, timeframe, count, now_ms=server_ms)
    except (httpx.HTTPError, DataUnavailable, ValueError, TimeoutError, OSError) as exc:
        raise QuoteRejected("MARKET_UNAVAILABLE") from exc
    def snapshot(candles):
        return {
            "source": SOURCE,
            "symbol": "BTCUSDT",
            "timeframe": INTERVALS[timeframe],
            "candles": [{
                "time": c.time,
                "open": str(c.open),
                "high": str(c.high),
                "low": str(c.low),
                "close": str(c.close),
                "volume": str(c.volume),
            } for c in candles],
        }
    # Do not trust a once-fresh quote if HTTP requests took too long.
    current_ms = await provider.server_time(client)
    return verified_close(snapshot(first), snapshot(second),
                          now=current_ms / 1000,
                          timeframe_seconds=INTERVALS[timeframe])
