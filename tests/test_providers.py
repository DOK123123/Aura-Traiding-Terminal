import asyncio
from datetime import datetime, timezone
import lzma
import struct

import httpx
import pytest

from app.models import Candle
from app.providers import BinanceProvider, DukascopyProvider, aggregate, decode_bi5


def test_dukascopy_binary_scale_and_order():
    origin = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    binary = struct.pack('>5If', 60, 2650000, 2651500, 2649000, 2653000, 12.5)
    assert decode_bi5(lzma.compress(binary), origin) == [Candle(origin + 60, 2650, 2653, 2649, 2651.5, 12.5)]


def test_aggregate_ohlcv_dedup_and_unclosed():
    bars = [Candle(i * 60, 100 + i, 102 + i, 99 + i, 101 + i, 1) for i in range(7)]
    result = aggregate(bars + [bars[0]], 300, 60, 420)
    assert result == [Candle(0, 100, 106, 99, 105, 5)]


def test_incomplete_published_bucket_excluded():
    bars = [Candle(i * 60, 100, 101, 99, 100, 1) for i in range(7)]
    assert len(aggregate(bars, 300, 60, 10000)) == 1


def test_binance_pagination_closed_sorted(monkeypatch):
    monkeypatch.setattr('app.providers.time.time', lambda: 3000 * 60 + 30)
    calls = []

    def handler(request):
        calls.append(request)
        end = int(request.url.params['endTime'])
        last = min(3000, end // 60000)
        limit = int(request.url.params['limit'])
        return httpx.Response(200, json=[
            [i * 60000, '100', '102', '99', '101', '10', (i + 1) * 60000 - 1]
            for i in range(max(0, last - limit + 1), last + 1)
        ])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await BinanceProvider().fetch(client, '1m', 2000)

    result = asyncio.run(run())
    assert len(result) == 2000
    assert len(calls) == 3
    assert result[0].time == 1000 * 60
    assert result[-1].time == 2999 * 60
    assert len({c.time for c in result}) == 2000


@pytest.mark.parametrize('price', [float('nan'), float('inf'), -1])
def test_invalid_candles_rejected(price):
    with pytest.raises(ValueError):
        Candle(0, price, price, price, price, 1)


def test_dukascopy_retry_and_cache(monkeypatch, tmp_path):
    monkeypatch.setattr('app.providers.CACHE', tmp_path)
    calls = []
    waits = []
    payload = lzma.compress(struct.pack('>5If', 60, 2650000, 2651500, 2649000, 2653000, 12.5))
    async def sleep(seconds):
        waits.append(seconds)
    monkeypatch.setattr('app.providers.asyncio.sleep', sleep)
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After': '3'}) if len(calls) == 1 else httpx.Response(200, content=payload)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            date = datetime(2026, 1, 1, tzinfo=timezone.utc)
            provider = DukascopyProvider()
            first = await provider._file(client, date, False)
            second = await provider._file(client, date, False)
            assert first == second
            assert first[0].close == 2651.5
    asyncio.run(run())
    assert len(calls) == 2
    assert waits == [3]
