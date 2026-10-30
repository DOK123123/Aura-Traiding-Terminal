"""Fixed Bitget public GET transport, strict market identity and bounded bodies."""
import asyncio
import json
import math
import time

import httpx

SOURCE = 'BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2'
STEPS = {'5m': 300, '15m': 900, '1h': 3600, '4h': 14400}
PATHS = frozenset({'history-candles', 'history-fund-rate', 'candles', 'ticker'})
BASE = 'https://api.bitget.com/api/v2/mix/market/'


def validate_bars(rows: list, step: int, *, contiguous: bool = True) -> list:
    if not isinstance(rows, list) or not rows:
        raise ValueError('EMPTY_HISTORY')
    previous = None
    for b in rows:
        if (not isinstance(b, list) or len(b) != 6 or type(b[0]) is not int
                or b[0] < 0 or b[0] % step
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in b[1:])
                or min(b[1:5]) <= 0 or b[5] < 0 or b[3] > min(b[1], b[4])
                or b[2] < max(b[1], b[4]) or b[3] > b[2]
                or previous is not None and (b[0] <= previous or contiguous and b[0] != previous + step)):
            raise ValueError('INVALID_OHLCV_OR_GAP')
        previous = b[0]
    return rows


def parse_bars(raw: list, step: int) -> list:
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError('INVALID_MARKET_ROWS')
    found = {}
    for row in raw:
        if not isinstance(row, list) or len(row) < 6:
            raise ValueError('INVALID_MARKET_ROW')
        stamp = float(row[0])
        if not math.isfinite(stamp) or stamp % (step * 1000):
            raise ValueError('INVALID_MARKET_TIMESTAMP')
        b = [int(stamp) // 1000, *map(float, row[1:6])]
        if b[0] in found and found[b[0]] != b:
            raise ValueError('CONFLICTING_DUPLICATE')
        found[b[0]] = b
    return validate_bars([found[t] for t in sorted(found)], step, contiguous=False) if found else []


class PublicMarket:
    def __init__(self, client=None):
        self.client = client or httpx.AsyncClient(timeout=12, follow_redirects=False)
        self.owned = client is None

    async def close(self):
        if self.owned:
            await self.client.aclose()

    async def get(self, path: str, **params):
        if path not in PATHS or any(k not in {'granularity', 'limit', 'endTime', 'startTime', 'pageSize', 'pageNo'} for k in params):
            raise ValueError('PUBLIC_GET_ALLOWLIST')
        params = {'symbol': 'BTCUSDT', 'productType': 'USDT-FUTURES', **params}
        async with self.client.stream('GET', BASE + path, params=params,
                                     headers={'Cache-Control': 'no-cache'}, timeout=12,
                                     follow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError('BITGET_PUBLIC_UNAVAILABLE')
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 400000:
                    raise ValueError('MARKET_RESPONSE_LIMIT')
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get('code') != '00000' or not isinstance(value.get('data'), list):
            raise ValueError('INVALID_BITGET_RESPONSE')
        return value

    async def snapshot(self, frame: str) -> dict:
        if frame not in STEPS:
            raise ValueError('INVALID_FRAME')
        step = STEPS[frame]
        response = await self.get('candles', granularity={'1h': '1H', '4h': '4H'}.get(frame, frame), limit=260)
        quote_response = await self.get('ticker')
        now = time.time()
        bars = [b for b in parse_bars(response['data'], step) if b[0] + step <= now]
        validate_bars(bars, step)
        if len(bars) < 250 or bars[-1][0] + step != int(now // step) * step:
            raise ValueError('STALE_OR_INCOMPLETE_CANDLES')
        data = quote_response['data']
        if len(data) != 1 or data[0].get('symbol') != 'BTCUSDT':
            raise ValueError('MARKET_IDENTITY_MISMATCH')
        q = data[0]
        quote = {'bid': float(q['bidPr']), 'ask': float(q['askPr']), 'last': float(q['lastPr']),
                 'time': float(q['ts']) / 1000, 'received_at': now, 'source': SOURCE}
        if not fresh_quote(quote, now):
            raise ValueError('STALE_OR_CONFLICTING_QUOTE')
        return {'source': SOURCE, 'frame': frame, 'step': step, 'bars': bars[-260:], 'quote': quote}


def fresh_quote(q: dict, now: float) -> bool:
    try:
        bid, ask, last, at, received = (q[k] for k in ('bid', 'ask', 'last', 'time', 'received_at'))
        return (q['source'] == SOURCE and all(type(x) in (int, float) and math.isfinite(x) for x in (bid, ask, last, at, received, now))
                and 0 < bid <= ask and (ask - bid) / bid <= .002
                and bid * .99 <= last <= ask * 1.01
                and 0 <= now - at <= 5 and 0 <= now - received <= 5)
    except (KeyError, TypeError):
        return False
