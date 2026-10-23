"""Offline wall-clock/delay/502 regressions; no production market or trade writes."""
import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
from app.active43.bitget import Client, MarketError, TIME, TICKER, HISTORY
from app.active43.market import Market
from app.active43.service import Service
from scripts.verify_active43 import PublicFixture
from tests.test_active43_diagnostics import ReadOnlyStore, diagnostic_transport


@pytest.mark.parametrize('age', [-3001,-3000,0,10000,10001])
def test_exact_existing_clock_limits_remain_strict(age,caplog):
    async def run():
        now=1700000030
        client=Client(clock=lambda:now,transport=httpx.MockTransport(lambda _:None))
        at=now*1000-age
        if -3000<=age<=10000:
            assert client.fresh_time(at)==at
        else:
            with pytest.raises(MarketError) as exc:client.fresh_time(at)
            assert exc.value.code=='UPSTREAM_CLOCK_OR_STALE_RESPONSE'
            assert exc.value.freshness['age_ms']==age
            assert exc.value.freshness['max_age_ms']==10000
            assert exc.value.freshness['max_future_ms']==3000
            log=json.loads(caplog.records[-1].message)
            assert log['event']=='FRESHNESS_REJECTED' and log['component']=='ACTIVE43_BITGET_PUBLIC'
        await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('field', ['requestTime','serverTime','ticker.ts'])
def test_exact_stale_timestamp_source_is_identified_without_weakening_gate(field):
    async def run():
        fixture=PublicFixture()
        def handler(req):
            body=fixture.handler(req).json()
            stale=str(fixture.now[0]*1000-10001)
            if field=='requestTime':body['requestTime']=stale
            elif field=='serverTime' and req.url.path==TIME:body['data']['serverTime']=stale
            elif field=='ticker.ts' and req.url.path==TICKER:body['data'][0]['ts']=stale
            return httpx.Response(200,json=body)
        client=Client(clock=lambda:fixture.now[0],transport=httpx.MockTransport(handler))
        with pytest.raises(MarketError) as exc:await client.quote()
        assert exc.value.code=='UPSTREAM_CLOCK_OR_STALE_RESPONSE'
        assert exc.value.freshness['check']==field
        assert exc.value.freshness['age_ms']==10001
        await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('second', ['fresh','stale','502','timeout'])
def test_502_retry_validates_new_response_and_never_reuses_stale_data(second,caplog):
    async def run():
        fixture=PublicFixture();calls=[]
        def handler(req):
            calls.append(req)
            if len(calls)==1:return httpx.Response(502,text='PRIVATE_DUMMY_RESPONSE_NOT_LOGGED')
            if second=='502':return httpx.Response(502,text='PRIVATE_DUMMY_RESPONSE_NOT_LOGGED')
            if second=='timeout':raise httpx.ReadTimeout('PRIVATE_DUMMY_RESPONSE_NOT_LOGGED')
            body=fixture.handler(req).json()
            if second=='stale':body['requestTime']-=10001
            return httpx.Response(200,json=body)
        client=Client(clock=lambda:fixture.now[0],transport=httpx.MockTransport(handler))
        if second=='fresh':await client.check_time()
        else:
            expected={'stale':'UPSTREAM_CLOCK_OR_STALE_RESPONSE','502':'HTTP_ERROR','timeout':'UPSTREAM_TIMEOUT'}[second]
            with pytest.raises(MarketError,match=expected):await client.check_time()
        assert len(calls)==2 and all(r.method=='GET' and r.url.host=='api.bitget.com' for r in calls)
        entries=[json.loads(r.message) for r in caplog.records]
        assert entries[0]['event']=='REQUEST_RETRY' and entries[0]['http_status']==502
        assert 'PRIVATE_DUMMY_RESPONSE_NOT_LOGGED' not in caplog.text
        await client.close()
    asyncio.run(run())


def test_network_timeouts_are_bounded_and_never_masked_by_old_quote(caplog):
    async def run():
        calls=[]
        def handler(req):calls.append(req);raise httpx.ReadTimeout('DUMMY_PRIVATE_TIMEOUT')
        client=Client(clock=lambda:1700000030,transport=httpx.MockTransport(handler))
        with pytest.raises(MarketError,match='UPSTREAM_TIMEOUT'):await client.quote()
        assert len(calls)==2
        logs=[json.loads(r.message) for r in caplog.records]
        assert logs[-1]['event']=='REQUEST_FAILED' and logs[-1]['code']=='UPSTREAM_TIMEOUT'
        assert logs[-1]['attempt']==2 and logs[-1]['http_status'] is None
        assert 'DUMMY_PRIVATE_TIMEOUT' not in caplog.text
        await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('ticker_age', [0,10001])
def test_slow_diagnostic_reads_quote_last_and_still_rejects_actually_stale_quote(ticker_age):
    async def run():
        fixture=PublicFixture();state=None;service=Service(ReadOnlyStore(state),clock=lambda:fixture.now[0])
        transport=diagnostic_transport(fixture);order=[]
        async def handler(req):
            order.append(req.url.path)
            # Three closed-candle requests consume 12 seconds of wall clock.
            if req.url.path==HISTORY:fixture.now[0]+=4
            response=await transport.handle_async_request(req)
            body=response.json()
            if req.url.path==TICKER:body['data'][0]['ts']=str(fixture.now[0]*1000-ticker_age)
            return httpx.Response(200,json=body)
        factory=lambda **kw:Market(clock=kw['clock'],transport=httpx.MockTransport(handler))
        result={}
        with patch('app.active43.diagnostics.Market',side_effect=factory):await service.diagnostics.market_probe(result)
        assert order[-1]==TICKER
        if ticker_age==0:
            assert result['bitget']['status']=='CONNECTED'
            assert result['bitget']['quote_at_ms']==fixture.now[0]*1000
            assert set(result['bitget']['candles'])=={'15m','1h','4h'}
        else:
            assert result['bitget']['status']=='ERROR'
            assert result['bitget']['freshness']['check']=='ticker.ts'
            assert result['bitget']['freshness']['age_ms']==10001
        assert service.store.state is None
        await service.close()
    asyncio.run(run())


def test_real_clock_drift_in_diagnostics_is_not_hidden_by_quote_reordering():
    async def future():
        fixture=PublicFixture();service=Service(ReadOnlyStore(None),clock=lambda:fixture.now[0]-4)
        factory=lambda **kw:Market(clock=kw['clock'],transport=diagnostic_transport(fixture))
        result={}
        with patch('app.active43.diagnostics.Market',side_effect=factory):await service.diagnostics.market_probe(result)
        assert result['bitget']['code']=='UPSTREAM_CLOCK_OR_STALE_RESPONSE'
        assert result['bitget']['freshness']['age_ms']==-4000
        await service.close()
    asyncio.run(future())


@pytest.mark.parametrize('failure', ['stale','timeout','502'])
def test_source_failure_blocks_entries_and_preserves_paper_balance(failure):
    from app.active43.strategies import config
    from tests.test_active43 import MemoryStore
    async def run():
        fixture=PublicFixture();store=MemoryStore(config(),fixture.now[0]);store.state['mode']='ON'
        def handler(req):
            if failure=='timeout':raise httpx.ReadTimeout('DUMMY_PRIVATE')
            if failure=='502':return httpx.Response(502,text='DUMMY_PRIVATE')
            body=fixture.handler(req).json();body['requestTime']-=10001
            return httpx.Response(200,json=body)
        market=Market(clock=lambda:fixture.now[0],transport=httpx.MockTransport(handler))
        service=Service(store,market,clock=lambda:fixture.now[0])
        result=await service.tick()
        assert result['status']=='PAUSED' and result['opened']==result['closed']==0
        assert store.state['balance']=='10000' and store.state['position'] is None
        assert store.state['last_successful_run_at'] is None
        assert not any(e['kind']=='OPEN' for e in store.events)
        await service.close()
    asyncio.run(run())
