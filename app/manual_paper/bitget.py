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
    try:
        server_ms = await provider.server_time(client)
    except (httpx.HTTPError, DataUnavailable, ValueError, TimeoutError, OSError):
        raise QuoteRejected("MARKET_UNAVAILABLE") from None
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
    try:
        current_ms = await provider.server_time(client)
    except (httpx.HTTPError, DataUnavailable, ValueError, TimeoutError, OSError):
        raise QuoteRejected("MARKET_UNAVAILABLE") from None
    return verified_close(snapshot(first), snapshot(second),
                          now=current_ms / 1000,
                          timeframe_seconds=INTERVALS[timeframe])


async def fetch_execution_quote(client, *, clock=None):
    """Fresh BTCUSDT USDT-M bid/ask; fixed public GETs, no exchange keys.

    https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market
    Price is sampled top of book, not an exchange fill guarantee.
    """
    import asyncio
    import time
    from decimal import Decimal
    from .core import number
    clock = clock or time.time
    async def get(path, params):
        async with client.stream('GET', 'https://api.bitget.com'+path,
                                 params=params,follow_redirects=False,timeout=4) as r:
            r.raise_for_status()
            raw=bytearray()
            async for chunk in r.aiter_bytes():
                raw.extend(chunk)
                if len(raw)>32768:
                    raise QuoteRejected('INVALID_QUOTE')
            import json
            data=json.loads(raw)
            if not isinstance(data,dict) or data.get('code')!='00000':
                raise QuoteRejected('MARKET_UNAVAILABLE')
            return data
    try:
        async with asyncio.timeout(8):
            server=await get('/api/v2/public/time',{})
            server_ms=int(server['data']['serverTime'])
            if abs(server_ms-clock()*1000)>3000:
                raise QuoteRejected('SERVER_TIME_MISMATCH')
            data=await get('/api/v2/mix/market/ticker',dict(symbol='BTCUSDT',productType='USDT-FUTURES'))
            if not isinstance(data['data'],list) or len(data['data'])!=1:
                raise QuoteRejected('INVALID_QUOTE')
            row=data['data'][0]
            if row['symbol']!='BTCUSDT':
                raise QuoteRejected('SOURCE_MISMATCH')
            stamp=int(row['ts']); response_at=int(data['requestTime']); now=clock()*1000
            if not 0<=now-stamp<=5000 or not 0<=now-response_at<=5000 or stamp<server_ms-5000:
                raise QuoteRejected('STALE_QUOTE')
            bid,ask,last=[number(row[k]) for k in ('bidPr','askPr','lastPr')]
            bid_size,ask_size=[number(row[k]) for k in ('bidSz','askSz')]
            if bid>ask or (ask-bid)/bid>Decimal('0.005') or not bid*Decimal('.99')<=last<=ask*Decimal('1.01'):
                raise QuoteRejected('INVALID_QUOTE')
            return dict(source=SOURCE,symbol='BTCUSDT',product='USDT-FUTURES',time=stamp,
                        bid=bid,ask=ask,price=last,bid_size=bid_size,ask_size=ask_size)
    except QuoteRejected:
        raise
    except (httpx.HTTPError,DataUnavailable,ValueError,KeyError,TypeError,ArithmeticError,TimeoutError,OSError):
        raise QuoteRejected('MARKET_UNAVAILABLE') from None
