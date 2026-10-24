import asyncio
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from app.bitget_chart import BitgetProvider, SOURCE
from app.providers import DataUnavailable
from app.main import app


def run(coro):
    return asyncio.run(coro)


def test_paginated_history_exact_boundaries_base_volume_and_identity():
    now = int(time.time()) // 900 * 900 * 1000 + 1000
    requests = []
    def handler(request):
        assert request.method == 'GET' and request.url.host == 'api.bitget.com'
        assert 'authorization' not in request.headers
        requests.append(request)
        q = request.url.params
        left, end = int(q['startTime']), int(q['endTime'])
        assert end % 900000 == 0
        rows = [[str(t),'100','102','99','101','7','707'] for t in range(left,end,900000)]
        return httpx.Response(200,json={'code':'00000','data':rows})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await BitgetProvider().fetch(client,'15m',500,now_ms=now)
    rows = run(scenario())
    assert len(rows) == 500 and len(requests) == 3
    assert rows[-1].time + 900 == now//900000*900
    assert rows[0].volume == 7  # base volume, not quote turnover
    assert SOURCE == 'Bitget · USDT-M Futures / api.bitget.com'


@pytest.mark.parametrize('fault',['gap','duplicate','nan','future','api_error','redirect'])
def test_bad_data_never_falls_back(fault):
    now = int(time.time())//60000*60000+1000
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        end=int(request.url.params['endTime'])
        rows=[[str(t),'100','102','99','101','7','707'] for t in range(end-3*60000,end,60000)]
        if fault=='gap': rows.pop(1)
        if fault=='duplicate': rows[1]=rows[0]
        if fault=='nan': rows[1][4]='nan'
        if fault=='future': rows[-1][0]=str(end)
        if fault=='api_error':return httpx.Response(200,json={'code':'40000','data':rows})
        if fault=='redirect':return httpx.Response(302,headers={'Location':'https://example.com'})
        return httpx.Response(200,json={'code':'00000','data':rows})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await BitgetProvider().fetch(client,'1m',3,now_ms=now)
    with pytest.raises((ValueError,DataUnavailable,httpx.HTTPError)):
        run(scenario())
    assert set(calls)=={'api.bitget.com'}


def test_retired_routes_do_not_dispatch_or_mutate():
    # No lifespan / real upstream or storage is necessary to reject old routes.
    with TestClient(app,raise_server_exceptions=True) as client:
        for path in ['/api/bybit-demo/account','/api/bybit-linear/quote','/api/auto42/tick',
                     '/api/paper/positions/open','/api/practice/start','/api/lab/run']:
            r=client.post(path)
            assert r.status_code==410
            assert r.json()['code']=='LEGACY_PROVIDER_RETIRED'
        assert client.get('/api/market?symbol=XAUUSD').status_code==422
        page=client.get('/').text
        assert 'bybit_demo.js' not in page and 'auto42.js' not in page
        assert 'id="active43-panel" open' in page


def test_source_archive_is_separate_and_rejects_gold_before_fetch(tmp_path):
    from app.models import Candle
    from app.patterns.history import Archive, HistoryService
    archive=Archive(tmp_path/'archive.db')
    old=[Candle(0,100,102,99,101,7)]
    new=[Candle(0,200,202,199,201,8)]
    archive.save('BTCUSDT','1m','Binance · Spot',old)
    archive.save('BTCUSDT','1m',SOURCE,new)
    assert archive.read('BTCUSDT','1m',SOURCE)==new
    assert archive.read('BTCUSDT','1m','Binance · Spot')==old
    with pytest.raises(DataUnavailable):
        run(HistoryService(archive).get(None,'XAUUSD','1m'))


def test_clock_and_endpoint_checks_fail_closed():
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={'code':'00000','data':{'serverTime':'1000'}})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(DataUnavailable):
                await BitgetProvider().server_time(client)
            with pytest.raises(DataUnavailable):
                await BitgetProvider().request(client,'/api/v2/mix/order/place-order',{})
    run(scenario())
    assert calls==['/api/v2/public/time']


def test_startup_never_constructs_retired_account_clients(monkeypatch):
    import app.main as main
    def forbidden(*args,**kwargs):
        raise AssertionError('A retired account must not be constructed or seeded')
    for name in ['TestnetReader','BybitDemoReader','configured_linear','configured_practice',
                 'configured_auto42','configured_forward','configured_diagnostics','PaperService']:
        monkeypatch.setattr(main,name,forbidden)
    with TestClient(main.app) as client:
        assert client.get('/api/health').status_code==200
        for path in ['/api/bybit-demo/account','/api/bybit-linear/ticker','/api/auto42/status',
                     '/api/paper/state','/api/practice/state','/api/lab/experiments']:
            for method in ['get','post','put','delete']:
                assert getattr(client,method)(path).status_code==410


def test_polling_rolls_on_closed_boundary_and_failure_clears_data(monkeypatch):
    from app.bitget_chart import chart_messages
    from app.models import Candle
    end=int(time.time())//60*60
    class Provider:
        def __init__(self):self.calls=0
        async def server_time(self,client):
            self.calls+=1
            if self.calls==3:raise DataUnavailable('offline')
            return (end+(self.calls-1)*60)*1000
        async def fetch(self,client,timeframe,count,now_ms):
            stop=now_ms//1000
            return [Candle(t,100,102,99,101,7) for t in range(stop-count*60,stop,60)]
    async def no_sleep(*args):pass
    monkeypatch.setattr('app.bitget_chart.asyncio.sleep',no_sleep)
    async def scenario():
        stream=chart_messages(None,Provider(),'1m',60)
        try:return [await anext(stream),await anext(stream),await anext(stream)]
        finally:await stream.aclose()
    first,second,failure=run(scenario())
    assert first['mode']=='polling' and first['current_closed'] is True
    assert first['candles'][-1]['time']==end-60
    assert second['candles'][-1]['time']==end and len(second['candles'])==60
    assert failure['type']=='status' and failure['state']=='unavailable'
    assert 'candles' not in failure and 'analysis' not in failure
