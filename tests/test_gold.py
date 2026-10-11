import asyncio
from datetime import datetime, timezone
import json
import lzma
import time

import httpx
import pytest

from app.gold import CandleBatch, FrameDecoder, GoldProvider, TradingViewGoldProvider, cooldown, frame
from app.models import Candle
from app.providers import DataUnavailable


def bars(count=500, step=60):
    end = int(time.time()) // step * step
    return [Candle(end - (count - i) * step, 100, 102, 99, 101, None) for i in range(count)]


class Feed:
    def __init__(self, name, result=None, error=None):
        self.name, self.note, self.result, self.error = name, name + ' note', result, error
        self.calls = 0

    async def fetch(self, *args):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_primary_success_does_not_use_fallback():
    primary, secondary = Feed('primary', bars()), Feed('secondary', bars())
    result = asyncio.run(GoldProvider(primary, secondary).fetch(None, '1m', 500))
    assert result.source == 'primary' and not result.fallback
    assert secondary.calls == 0


@pytest.mark.parametrize('error', [httpx.ConnectError('offline'), TimeoutError(),
                                  lzma.LZMAError('corrupt'), ValueError('invalid')])
def test_failure_falls_back_without_mixing_sources(error):
    primary, secondary = Feed('primary', error=error), Feed('secondary', bars())
    result = asyncio.run(GoldProvider(primary, secondary).fetch(None, '1m', 500))
    assert result == secondary.result
    assert result.source == 'secondary' and result.fallback and result.reason


@pytest.mark.parametrize('status', [429,503])
def test_cooldown_avoids_repeated_primary_requests_and_recovers(status):
    response = httpx.Response(status, headers={'Retry-After': '180'}, request=httpx.Request('GET','https://example.com'))
    primary = Feed('primary', error=httpx.HTTPStatusError('blocked', request=response.request, response=response))
    secondary = Feed('secondary', bars())
    provider = GoldProvider(primary, secondary)
    async def run():
        first = await provider.fetch(None, '1m', 500)
        assert first.reason == f'HTTP {status}'
        assert provider.retry_at >= time.monotonic() + 179
        await provider.fetch(None, '1m', 500)
        assert primary.calls == 1
        primary.error, primary.result, provider.retry_at = None, bars(), 0
        recovered = await provider.fetch(None, '1m', 500)
        assert recovered.source == 'primary' and not recovered.fallback
        assert first.source == 'secondary'  # immutable provenance of earlier response
    asyncio.run(run())


def test_retry_after_http_date():
    response = httpx.Response(429, request=httpx.Request('GET','https://example.com'),
                             headers={'Retry-After': 'Fri, 11 Sep 2099 18:00:00 GMT'})
    error = httpx.HTTPStatusError('rate', request=response.request, response=response)
    assert cooldown(error) > 120


@pytest.mark.parametrize('bad', [bars(499), list(reversed(bars())), bars()[:-1] + [bars()[-2]],
                              [Candle(i * 60, 100, 102, 99, 101, 0) for i in range(500)],
                              lambda: bars()[:-1] + [Candle(int(time.time()) // 60 * 60,100,102,99,101,0)]])
def test_invalid_or_incomplete_primary_history_falls_back(bad):
    if callable(bad):
        bad = bad()
    result = asyncio.run(GoldProvider(Feed('primary',bad), Feed('secondary',bars())).fetch(None,'1m',500))
    assert result.fallback


def test_both_fail_no_generated_history():
    provider = GoldProvider(Feed('primary',error=TimeoutError()), Feed('secondary', bars(12)))
    with pytest.raises(DataUnavailable, match='12 из 500'):
        asyncio.run(provider.fetch(None,'1m',500))


def test_cancellation_does_not_start_fallback():
    primary = Feed('primary',error=asyncio.CancelledError())
    secondary = Feed('secondary',bars())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(GoldProvider(primary,secondary).fetch(None,'1m',500))
    assert secondary.calls == 0


def test_concurrent_gold_requests_probe_primary_once():
    primary, secondary = Feed('primary',error=TimeoutError()), Feed('secondary',bars())
    provider = GoldProvider(primary,secondary)
    async def run():
        return await asyncio.gather(*(provider.fetch(None,'1m',500) for _ in range(3)))
    assert all(result.fallback for result in asyncio.run(run()))
    assert primary.calls == 1


def test_chart_frames_split_combined_and_heartbeat():
    decoder = FrameDecoder()
    data = frame('{"m":"test","p":[]}') + frame('~h~123')
    assert decoder.feed(data[:2]) == []
    assert decoder.feed(data[2:8]) == []
    assert decoder.feed(data[8:]) == ['{"m":"test","p":[]}', '~h~123']


class Socket:
    def __init__(self, messages):
        self.messages, self.sent = messages, []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def send(self, data): self.sent.append(data)
    def __aiter__(self): return self
    async def __anext__(self):
        if not self.messages: raise StopAsyncIteration
        return self.messages.pop(0)


def message(method, params):
    return frame(json.dumps({'m':method, 'p':params}, separators=(',',':')))


def test_chart_protocol_filters_open_bars_preserves_missing_volume(monkeypatch):
    now = int(time.time()) // 60 * 60
    socket = Socket([
        frame('~h~123'),
        message('symbol_resolved',['cs','gold',{'name':'XAUUSD','exchange':'OANDA'}]),
        message('timescale_update',['cs',{'prices':{'s':[
            {'v':[now-60,100,102,99,101,None]}, {'v':[now,100,102,99,101,10]}]}}]),
        message('series_completed',['cs','prices'])])
    monkeypatch.setattr('app.gold.connect', lambda *a, **kw: socket)
    result = asyncio.run(TradingViewGoldProvider().fetch(None,'1m',1))
    assert result == [Candle(now-60,100,102,99,101,None)]
    assert frame('~h~123') in socket.sent


def test_wrong_resolved_instrument_rejected(monkeypatch):
    socket = Socket([message('symbol_resolved',['cs','gold',{'name':'GC1!','exchange':'COMEX'}])])
    monkeypatch.setattr('app.gold.connect',lambda *a,**kw: socket)
    with pytest.raises(DataUnavailable, match='Unexpected resolved'):
        asyncio.run(TradingViewGoldProvider().fetch(None,'1m',500))


def test_chart_stream_updates_current_candle_after_history(monkeypatch):
    now = int(time.time()) // 60 * 60
    socket = Socket([
        message('symbol_resolved',['cs','gold',{'name':'XAUUSD','exchange':'OANDA'}]),
        message('timescale_update',['cs',{'prices':{'s':[
            {'v':[now-60,100,102,99,101,12]}, {'v':[now,101,102,100,101,10]}]}}]),
        message('series_completed',['cs','prices']),
        message('du',['cs',{'prices':{'s':[{'v':[now,101,103,100,102,20]}]}}]),
    ])
    monkeypatch.setattr('app.gold.connect',lambda *a,**kw: socket)
    async def run():
        stream = TradingViewGoldProvider().stream('1m',2)
        try:
            first, second = await anext(stream), await anext(stream)
            assert len(first) == len(second) == 2
            assert first[0] == second[0]
            assert first[-1].volume == 10 and second[-1].volume == 20
            assert second[-1] == Candle(now,101,103,100,102,20)
        finally:
            await stream.aclose()
    asyncio.run(run())
