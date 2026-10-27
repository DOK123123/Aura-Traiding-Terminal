import asyncio
from copy import deepcopy
from unittest.mock import patch,AsyncMock
import httpx
import pytest
from fastapi import FastAPI
from app.active43.bitget import Client,TIME,HISTORY,CONTRACTS
from app.aura_trader5_api import router
from app.aura_trader5_service import AnalystService
from app.aura_trader5_scenarios import STEPS
from tests.test_aura_trader5_scenarios import windows,NOW


def setup(failure=None):
    calls=[];clock=[NOW];data=windows()
    async def handler(request):
        calls.append(request)
        assert request.method=='GET' and request.url.host=='api.bitget.com'
        assert 'Authorization' not in request.headers
        body=dict(code='00000',requestTime=int(clock[0]*1000))
        path=request.url.path
        if failure=='timeout':raise httpx.ReadTimeout('DUMMY_INTERNAL_ERROR')
        if failure=='rate':return httpx.Response(429,json={'code':'429'})
        if failure=='region':return httpx.Response(403)
        if path==TIME:body['data']={'serverTime':str(int(clock[0]*1000))}
        elif path==CONTRACTS:body['data']=[dict(symbol='BTCUSDT',baseCoin='BTC',quoteCoin='USDT',symbolType='perpetual',symbolStatus='normal',supportMarginCoins=['USDT'],pricePlace='1',priceEndStep='1')]
        elif path==HISTORY:
            assert request.url.params['symbol']=='BTCUSDT' and request.url.params['productType']=='USDT-FUTURES'
            tf={'5m':'5m','15m':'15m','1H':'1h','4H':'4h'}[request.url.params['granularity']]
            rows=[[str(b.time*1000),*[str(getattr(b,k)) for k in ('open','high','low','close','volume')],'1000'] for b in data[tf]]
            if failure=='gap':rows.pop(5)
            if failure=='stale':body['requestTime']-=11000
            body['data']=rows
        else:raise AssertionError('PRIVATE_OR_UNKNOWN_PATH')
        return httpx.Response(200,json=body)
    client=Client(transport=httpx.MockTransport(handler),clock=lambda:clock[0])
    service=AnalystService(client,clock=lambda:clock[0])
    return service,calls,clock


def test_actual_public_parser_to_four_frames_and_read_only_api():
    async def run():
        s,calls,clock=setup();app=FastAPI();app.include_router(router);app.state.aura_analyst=s
        with patch('app.active43.service.Service.tick',AsyncMock(side_effect=AssertionError('NO_TRADING'))),patch('app.active43.storage.Store.commit',AsyncMock(side_effect=AssertionError('NO_WRITES'))):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                r=await c.get('/api/analyst');assert r.status_code==200
                b=r.json();assert b['state']=='LONG',b
                assert set(b['frames'])==set(STEPS) and b['scenario']['net_rr']>=1.5
                assert b['read_only'] and b['manual_only'] and not b['exchange_execution']
                assert 'no-store' in r.headers['cache-control']
                assert (await c.post('/api/analyst')).status_code==405
                before=len(calls);again=await c.get('/api/analyst');assert again.json()==b and len(calls)==before
        assert {r.url.path for r in calls}=={TIME,CONTRACTS,HISTORY}
        assert len(calls)==6
        await s.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure,code',[('timeout','UPSTREAM_TIMEOUT'),('rate','RATE_LIMIT'),('region','REGION_OR_ACCESS_RESTRICTED'),('gap','MISSING_CANDLES'),('stale','UPSTREAM_CLOCK_OR_STALE_RESPONSE')])
def test_source_failures_return_wait_without_stale_scenario(failure,code):
    async def run():
        s,calls,clock=setup(failure)
        r=await s.inspect();assert r['state']=='WAIT' and r['scenario'] is None and code in r['reasons'],r
        assert 'DUMMY_INTERNAL_ERROR' not in str(r)
        if failure=='rate':
            clock[0]+=31;n=len(calls)
            assert (await s.inspect())['reasons']==['RATE_LIMIT_COOLDOWN'] and n==len(calls)
        await s.close()
    asyncio.run(run())


def test_cache_copy_and_expiry_do_not_mutate_or_reuse_plan_on_new_close():
    async def run():
        s,calls,clock=setup();r=await s.inspect();r['frames']['5m']['ema20']=0
        assert (await s.inspect())['frames']['5m']['ema20']>0
        clock[0]=NOW//300*300+301
        r=await s.inspect();assert r['state']=='WAIT' and r['scenario'] is None
        await s.close()
    asyncio.run(run())


def test_concurrent_call_is_bounded_without_waiting_on_trading_locks():
    async def run():
        s,calls,clock=setup();await s.lock.acquire()
        r=await s.inspect();assert r['reasons']==['ANALYSIS_BUSY'] and not calls
        s.lock.release();await s.close()
    asyncio.run(run())


def test_snapshot_crossing_closed_boundary_fails_closed():
    async def run():
        s,calls,clock=setup();original=s.client.candles
        async def delayed(*args):
            result=await original(*args)
            if len(calls)>=6:clock[0]=NOW//300*300+301
            return result
        s.client.candles=delayed
        r=await s.inspect();assert r['state']=='WAIT' and r['scenario'] is None
        await s.close()
    asyncio.run(run())


def test_unknown_upstream_code_is_redacted():
    async def run():
        from app.active43.bitget import MarketError
        s,calls,clock=setup()
        async def broken(*args):raise MarketError('DUMMY_PRIVATE_SERVER_VALUE')
        s.client.get=broken
        r=await s.inspect();assert r['state']=='WAIT' and r['scenario'] is None
        assert 'DUMMY_PRIVATE' not in str(r)
        await s.close()
    asyncio.run(run())


def test_analyst_cleanup_failure_cannot_skip_existing_controller_cleanup(monkeypatch):
    from types import SimpleNamespace
    from app import main
    async def run():
        active=SimpleNamespace(close=AsyncMock())
        analyst=SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('DUMMY_CLEANUP_FAILURE')))
        monkeypatch.setattr(main,'configured_active43',lambda:active)
        monkeypatch.setattr(main,'AnalystService',lambda:analyst)
        app=FastAPI()
        with pytest.raises(RuntimeError,match='DUMMY_CLEANUP_FAILURE'):
            async with main.lifespan(app):pass
        active.close.assert_awaited_once()
    asyncio.run(run())


def test_public_client_is_lazy_and_initialization_failure_is_a_wait(monkeypatch):
    import app.aura_trader5_service as module
    async def run():
        def invalid(**kwargs):raise ValueError('DUMMY_PRIVATE_TLS_CONFIGURATION')
        monkeypatch.setattr(module,'Client',invalid)
        s=AnalystService(clock=lambda:NOW)
        assert s.client is None
        result=await s.inspect();assert result['state']=='WAIT' and result['scenario'] is None
        assert 'DUMMY_PRIVATE' not in str(result)
        await s.close();assert (await s.inspect())['reasons']==['ANALYST_UNAVAILABLE']
    asyncio.run(run())


def test_exchange_boundary_disagreement_never_uses_a_forming_bar():
    async def run():
        s,calls,clock=setup();clock[0]=NOW//300*300+.5;original=s.client.get
        async def behind(path,params):
            result=await original(path,params)
            if path==TIME:result['data']['serverTime']=str(int(clock[0]*1000)-1000)
            return result
        s.client.get=behind
        result=await s.inspect()
        assert result['state']=='WAIT' and result['scenario'] is None,result
        await s.close()
    asyncio.run(run())
