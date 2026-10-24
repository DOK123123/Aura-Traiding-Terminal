"""Public Bitget USDT-M chart data. No account credentials or exchange writes."""
import asyncio
import time
import httpx
from .models import Candle, INTERVALS, validate_candles
from .providers import DataUnavailable

SOURCE = 'Bitget · USDT-M Futures / api.bitget.com'
BASE = 'https://api.bitget.com'
GRANULARITY = {'1m':'1m', '5m':'5m', '15m':'15m', '1h':'1H'}


class BitgetProvider:
    name = SOURCE
    note = 'BTCUSDT USDT-M Futures · объём BTC · публичные данные Bitget.'

    async def request(self, client, path, params):
        if path not in {'/api/v2/public/time', '/api/v2/mix/market/history-candles'}:
            raise DataUnavailable('Unsupported Bitget public endpoint')
        response = await client.get(BASE + path, params=params, follow_redirects=False, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get('code') != '00000':
            raise DataUnavailable('Bitget public data unavailable')
        return data

    async def server_time(self, client):
        data = await self.request(client, '/api/v2/public/time', {})
        try:
            stamp = int(data['data']['serverTime'])
        except (KeyError, TypeError, ValueError):
            raise DataUnavailable('Invalid Bitget server time') from None
        if not -3000 <= time.time()*1000 - stamp <= 10000:
            raise DataUnavailable('Bitget server clock is stale or unsynchronized')
        return stamp

    async def fetch(self, client, timeframe, count, *, now_ms=None):
        if timeframe not in GRANULARITY or type(count) is not int or not 1 <= count <= 10000:
            raise DataUnavailable('Invalid Bitget chart request')
        now = await self.server_time(client) if now_ms is None else now_ms
        step = INTERVALS[timeframe]
        end = int(now // (step * 1000)) * step * 1000
        rows = {}
        async with asyncio.timeout(90):
            for _ in range((count + 199) // 200):
                size = min(200, count - len(rows))
                left = end - size * step * 1000
                data = await self.request(client, '/api/v2/mix/market/history-candles', {
                    'symbol':'BTCUSDT', 'productType':'USDT-FUTURES',
                    'granularity':GRANULARITY[timeframe], 'startTime':left,
                    'endTime':end, 'limit':size})
                batch = data.get('data')
                if not isinstance(batch, list) or not batch or len(batch) > size:
                    raise DataUnavailable('Incomplete Bitget history')
                previous = None
                for row in batch:
                    if not isinstance(row, list) or len(row) != 7:
                        raise DataUnavailable('Invalid Bitget candle')
                    at = int(row[0])
                    if at % (step * 1000) or not left <= at < end or (previous is not None and at <= previous):
                        raise DataUnavailable('Invalid Bitget candle timestamps')
                    previous = at
                    candle = Candle(at // 1000, *map(float, row[1:6]))
                    if candle.time in rows:
                        raise DataUnavailable('Duplicate Bitget candle')
                    rows[candle.time] = candle
                oldest = int(batch[0][0])
                if oldest >= end:
                    raise DataUnavailable('Bitget pagination stalled')
                end = oldest
                if len(rows) == count:
                    break
        candles = sorted(rows.values(), key=lambda c:c.time)
        validate_candles(candles, timeframe, now=now/1000, contiguous=True, count=count)
        if candles[-1].time + step != int(now // (step*1000))*step:
            raise DataUnavailable('Bitget history is stale')
        return candles


async def chart_messages(client, provider, timeframe, limit):
    """Closed-candle polling; explicitly not a tick-level or WebSocket quote."""
    from .live import snapshot
    delay = 5
    candles = None
    last_end = None
    while True:
        try:
            server_ms = await provider.server_time(client)
            clock_offset = server_ms/1000-time.time()
            end = int(server_ms // (INTERVALS[timeframe]*1000)) * INTERVALS[timeframe]
            if candles is None or last_end is None or end-last_end > INTERVALS[timeframe] or end < last_end:
                candles = await provider.fetch(client, timeframe, limit, now_ms=server_ms)
            elif end != last_end:
                tail = await provider.fetch(client, timeframe, 2, now_ms=server_ms)
                merged = {c.time:c for c in candles}
                merged.update({c.time:c for c in tail})
                candles = sorted(merged.values(), key=lambda c:c.time)[-limit:]
                validate_candles(candles, timeframe, now=server_ms/1000, contiguous=True, count=limit)
            last_end = end
            yield snapshot(candles, 'BTCUSDT', timeframe, SOURCE, 'polling',
                event_time=server_ms, clock_offset=clock_offset,
                note='Bitget Futures · проверка каждые 5 с · только закрытые свечи; цена последнего закрытия, не текущая цена сделки.')
            delay = 5
        except (httpx.HTTPError, DataUnavailable, ValueError, KeyError, TypeError, IndexError, TimeoutError):
            candles = None
            yield {'type':'status', 'state':'unavailable', 'message':'Bitget недоступен или данные некорректны. Сигнал отключён; повтор автоматически.'}
            delay = min(30, delay*2)
        await asyncio.sleep(delay)
