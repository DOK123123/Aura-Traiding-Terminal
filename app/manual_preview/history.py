"""Bounded, public-only historical candles. No account or execution dependencies."""
import asyncio
import gzip
import hashlib
import json
import math
from pathlib import Path

STEPS = {'15m': 900, '1h': 3600, '4h': 14400}
HISTORY_URL = 'https://api.bitget.com/api/v2/mix/market/history-candles'
ARCHIVE = Path(__file__).resolve().parents[2] / 'research/strategy_engine/bitget-2026-07-10-15m.json.gz'


def bounds(frame: str, start: int, end: int, now: float) -> tuple[int, int]:
    step = STEPS.get(frame)
    if (not step or type(start) is not int or type(end) is not int
            or start % step or end % step or start < 200 * step
            or end <= start or end > int(now // step) * step
            or (end - start) // step > 6000):
        raise ValueError('INVALID_REPLAY_PERIOD_MAX_6000_CANDLES')
    return step, start - 200 * step


def validate(bars: list, step: int, first: int, end: int) -> list:
    expected = (end - first) // step
    if not isinstance(bars, list) or len(bars) != expected:
        raise ValueError('INCOMPLETE_REPLAY_HISTORY')
    for i, bar in enumerate(bars):
        if (not isinstance(bar, dict) or type(bar.get('time')) is not int
                or bar['time'] != first + i * step):
            raise ValueError('REPLAY_GAP_OR_DUPLICATE')
        if not all(type(bar.get(k)) in (float, int) and math.isfinite(bar[k])
                   for k in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('INVALID_REPLAY_NUMBER')
        if (min(bar['open'], bar['high'], bar['low'], bar['close']) <= 0
                or bar['volume'] < 0 or bar['low'] > min(bar['open'], bar['close'])
                or bar['high'] < max(bar['open'], bar['close'])):
            raise ValueError('INVALID_REPLAY_OHLCV')
    return bars


def envelope(bars: list, frame: str, start: int, end: int, source: str) -> dict:
    return {'scope': 'HISTORICAL_REPLAY_ONLY', 'symbol': 'BTCUSDT', 'product': 'USDT-FUTURES',
            'source': source, 'timeframe': frame, 'start': start, 'end': end, 'warmup': 200,
            'quote_model': {'full_spread_bps': 2, 'slippage_bps_per_side': 5,
                            'fee_bps_per_side': 10, 'historical_bid_ask': False,
                            'funding': 'NOT_MODELED'},
            'edge': 'UNVALIDATED', 'statistical_result': 'NOT_EVALUATED',
            'sha256': hashlib.sha256(json.dumps(bars, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'bars': bars}


def archive_history(frame: str, start: int, end: int, now: float) -> dict:
    step, first = bounds(frame, start, end, now)
    # Known repository artifact; user input cannot select a file or URL.
    base = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
    selected = [b for b in base if first <= b['time'] < end]
    validate(selected, 900, first, end)
    bars = []
    for i in range(0, len(selected), step // 900):
        group = selected[i:i + step // 900]
        bars.append({'time': group[0]['time'], 'open': group[0]['open'],
                     'high': max(b['high'] for b in group), 'low': min(b['low'] for b in group),
                     'close': group[-1]['close'], 'volume': sum(b['volume'] for b in group)})
    validate(bars, step, first, end)
    return envelope(bars, frame, start, end, 'BITGET_SAVED_REAL_ARCHIVE_2026_07_01_TO_10_29')


async def public_history(client, frame: str, start: int, end: int, now: float) -> dict:
    step, first = bounds(frame, start, end, now)
    cursor = end * 1000
    found = {}
    async with asyncio.timeout(60):
        for _ in range(34):
            async with client.stream('GET', HISTORY_URL,
                    params={'symbol': 'BTCUSDT', 'productType': 'USDT-FUTURES',
                            'granularity': {'1h': '1H', '4h': '4H'}.get(frame, frame),
                            'limit': '200', 'endTime': str(cursor)},
                    timeout=8, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError('BITGET_HISTORY_UNAVAILABLE')
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 200000:
                        raise ValueError('BITGET_HISTORY_RESPONSE_LIMIT')
            body = json.loads(raw)
            rows = body.get('data') if isinstance(body, dict) and body.get('code') == '00000' else None
            if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
                raise ValueError('BITGET_HISTORY_EMPTY_OR_INVALID')
            oldest = cursor
            for row in rows:
                if not isinstance(row, list) or len(row) < 6:
                    raise ValueError('BITGET_HISTORY_INVALID_ROW')
                stamp = float(row[0])
                if not math.isfinite(stamp) or stamp % (step * 1000) or stamp >= cursor + step * 1000:
                    raise ValueError('BITGET_HISTORY_INVALID_TIME')
                oldest = min(oldest, int(stamp))
                if first * 1000 <= stamp < end * 1000:
                    bar = dict(zip(('open', 'high', 'low', 'close', 'volume'), map(float, row[1:6])))
                    bar['time'] = int(stamp) // 1000
                    if bar['time'] in found and found[bar['time']] != bar:
                        raise ValueError('BITGET_HISTORY_CONFLICT')
                    found[bar['time']] = bar
            if oldest >= cursor:
                raise ValueError('BITGET_HISTORY_PAGINATION_STALLED')
            if oldest <= first * 1000:
                break
            # An exclusive cursor supports both inclusive and exclusive upstream responses.
            cursor = oldest
            await asyncio.sleep(.1)
    bars = [found[t] for t in sorted(found)]
    validate(bars, step, first, end)
    return envelope(bars, frame, start, end, 'BITGET_PUBLIC_HISTORY_API')
