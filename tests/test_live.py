import asyncio
import json
import time
import httpx

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.live import btc_messages, parse_binance, snapshot
from app.market_state import LiveWindow
from app.models import Candle
from app.providers import DataUnavailable
from tests.test_gold import Socket


def history(count=500):
    end = int(time.time())//60*60
    return [Candle(end-(count-i)*60,100,102,99,101,5) for i in range(count)]


def event(stamp, closed=False, price=101, event_time=None):
    return {'e':'kline','s':'BTCUSDT','E':event_time or int(time.time()*1000),
            'k':{'s':'BTCUSDT','i':'1m','t':stamp*1000,'o':'100','h':'105','l':'98',
                 'c':str(price),'v':'12','x':closed}}


def test_window_replace_roll_and_exact_count():
    seed = history()
    window = LiveWindow(seed,'1m',500)
    t = seed[-1].time+60
    first = Candle(t,100,105,98,101,12)
    assert window.apply(first,False,1) is True
    assert len(window.candles) == 500
    assert window.apply(Candle(t,100,106,97,104,20),False,2) is False
    assert window.candles[-1].volume == 20
    assert window.apply(first,False,1) is None  # out of order must not roll back
    assert window.apply(Candle(t,100,106,97,104,21),True,3) is False
    assert window.apply(first,False,4) is None  # final cannot become provisional
    assert window.apply(Candle(t+60,104,107,103,106,3),False,5) is True
    assert len(window.candles) == 500


def test_gap_and_missing_final_require_rebootstrap():
    seed = history()
    window = LiveWindow(seed,'1m',500)
    with pytest.raises(DataUnavailable,match='gap'):
        window.apply(Candle(seed[-1].time+120,100,102,99,101,2),False,1)
    window.apply(Candle(seed[-1].time+60,100,102,99,101,2),False,1)
    with pytest.raises(DataUnavailable,match='gap'):
        window.apply(Candle(seed[-1].time+120,100,102,99,101,2),False,2)


def test_binance_parser_validates_symbol_and_ohlcv():
    raw = event(int(time.time())//60*60)
    candle, closed, stamp = parse_binance(raw,'1m')
    assert candle.volume == 12 and not closed
    raw['k']['s']='XAUUSD'
    with pytest.raises(DataUnavailable): parse_binance(raw,'1m')
    raw['k']['s']='BTCUSDT'; raw['k']['c']='nan'
    with pytest.raises(ValueError): parse_binance(raw,'1m')


def test_snapshot_polling_never_claims_streaming():
    result = snapshot(history(),'XAUUSD','1m','OANDA','polling',closed=False)
    assert result['mode'] == 'polling' and result['event_time'] is None
    assert not result['current_closed']
    assert not result['stale']  # Recent polling data is fresh, but is not streaming.
    old = [Candle(c.time-600,c.open,c.high,c.low,c.close,c.volume) for c in history()]
    assert snapshot(old,'XAUUSD','1m','OANDA','polling',closed=False)['stale']


def test_stream_updates_recalculate_and_do_not_accumulate_volume(monkeypatch):
    seed = [Candle(c.time,100,102,99,100+i%2,5) for i,c in enumerate(history())]
    t = seed[-1].time+60
    now = int(time.time()*1000)
    class Upstream(Socket):
        async def recv(self): return self.messages.pop(0)
    socket = Upstream([json.dumps(event(t,price=102,event_time=now)),
                       json.dumps(event(t,price=104,event_time=now+1))])
    class Provider:
        name='Binance'
        async def fetch(self,*args,**kwargs): return seed
    monkeypatch.setattr('app.live.connect',lambda *a,**kw: socket)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200,json={'serverTime':int(time.time()*1000)}))) as client:
            generator=btc_messages(client,Provider(),'1m',500)
            bootstrap=await anext(generator)
            first=await anext(generator)
            second=await anext(generator)
            await generator.aclose()
            return bootstrap,first,second
    bootstrap,first,second=asyncio.run(run())
    assert bootstrap['type']=='snapshot'
    assert first['rolled'] and not second['rolled']
    assert first['candle']['volume']==second['candle']['volume']==12
    assert first['analysis']['ema20'] != second['analysis']['ema20']
    assert first['analysis']['rsi'] != second['analysis']['rsi']
    assert len(second['analysis']['series']['ema20'])==1
    assert len(first['candles'])==500


def test_websocket_query_validation():
    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws/market?symbol=ETHUSDT'): pass


def test_browser_disconnect_cancels_producer(monkeypatch):
    stopped=asyncio.Event()
    async def messages(*args):
        try:
            yield {'type':'status','state':'test','message':'ready'}
            await asyncio.sleep(60)
        finally:
            stopped.set()
    monkeypatch.setattr('app.bitget_chart.chart_messages',messages)
    from app.live import serve_market
    from starlette.websockets import WebSocketDisconnect
    async def run():
        sent=asyncio.Event()
        class BrowserSocket:
            query_params={}
            async def accept(self): pass
            async def send_json(self,data):
                assert data['message']=='ready'
                sent.set()
            async def receive_text(self):
                await sent.wait()
                raise WebSocketDisconnect()
        await serve_market(BrowserSocket(),None,{'BTCUSDT':object()})
        assert stopped.is_set()
    asyncio.run(run())
