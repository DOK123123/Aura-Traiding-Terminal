"""Native-indicator E2E on isolated Bitget V2-shaped fixtures; never live proof."""
import asyncio
from copy import deepcopy
from unittest.mock import patch

import httpx
import pytest

from app.active43.core import initial,validate,SOURCE,IDENTITY
from app.active43.market import Market,Quotes,quote_checked
from app.active43.service import Service,configured,scheduler_configured as actual_scheduler_configured
from app.automated.engine import DemoError
from scripts.verify_active43 import PublicFixture
from scripts.verify_auto42_execution import check_accounting
from tests.test_active43 import MemoryStore
from app.active43.strategies import config


@pytest.fixture(autouse=True)
def configured_scheduler(monkeypatch):
    monkeypatch.setattr('app.active43.service.scheduler_configured',lambda:True)


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_native_market_indicators_signal_execution_restart_database_and_display(side):
    async def run():
        fixture=PublicFixture(side);clock=lambda:fixture.now[0]
        transport=httpx.MockTransport(fixture.handler);market=Market(clock=clock,transport=transport)
        quotes=Quotes(clock=clock,transport=transport);store=MemoryStore(config(),clock())
        svc=Service(store,market,config(),clock=clock,quotes=quotes)
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        fixture.add('signal');await svc.tick()
        assert store.state['pending']['direction']==side
        assert store.state['last_signal']['reason']=='CLOSED_CANDLE_DONCHIAN'
        fixture.add('fill');await asyncio.gather(svc.tick(),svc.tick())
        p=deepcopy(store.state['position']);assert p and p['market_source']==SOURCE
        other=Service(store,market,config(),clock=clock,quotes=quotes)
        assert (await other.load())['state']['position']==p
        fixture.add('update');await other.tick()
        assert store.state['position']
        quote=await quotes.get();assert quote_checked(quote,clock())['identity']==IDENTITY
        fixture.add('close');await other.tick();await svc.tick()
        closed=[e['payload'] for e in store.events if e['kind']=='CLOSE']
        assert len(closed)==1 and closed[0]['exit_reason']=='TAKE_PROFIT'
        check_accounting(p,closed[0],store.state)
        dashboard=await svc.dashboard()
        assert dashboard['state']['trades']==1 and dashboard['trades'][0]['market_source']==SOURCE
        assert dashboard['chart']['source']==SOURCE and dashboard['scheduler_status']=='FRESH'
        assert not dashboard['production_paper_verified']
        assert all(r.method=='GET' and r.url.path.startswith('/api/v2/') for r in fixture.requests)
        await svc.close()
    asyncio.run(run())


def test_bitget_requires_separate_opt_in_and_never_reads_spot_config(monkeypatch):
    monkeypatch.setenv('AURA_ACTIVE43_ENABLED','true');monkeypatch.delenv('AURA_ACTIVE43_BITGET_ENABLED',raising=False)
    assert configured().reason=='ACTIVE43_BITGET_DISABLED'
    s=initial(1700000000);s['market_source']='Binance · Spot / data-api.binance.vision'
    with pytest.raises(DemoError):validate(s)
    with pytest.raises(DemoError):quote_checked(dict(price='68000',time_ms=1700000000000,source='Binance Spot'),1700000000)


def test_region_failure_is_visible_durable_and_recovers_without_false_trade():
    async def run():
        f=PublicFixture();clock=lambda:f.now[0];market=Market(clock=clock,transport=httpx.MockTransport(f.handler))
        store=MemoryStore(config(),clock());svc=Service(store,market,config(),clock=clock)
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        f.failure=403;f.now[0]+=300;await svc.tick()
        assert store.state['mode']=='PAUSED' and store.state['last_error']=='REGION_OR_ACCESS_RESTRICTED'
        assert store.state['data_recovery_armed'] and store.state['position'] is None
        f.failure=None;f.now[0]+=300;await svc.tick()
        assert store.state['mode']=='ON' and store.state['last_error'] is None
        assert not any(e['kind']=='OPEN' for e in store.events)
        assert (await svc.dashboard())['scheduler_status']=='FRESH'
        f.now[0]+=400;assert (await svc.dashboard())['scheduler_status']=='STALE'
        await svc.close()
    asyncio.run(run())


def test_cached_analysis_is_bound_to_strategy_config_and_clock():
    async def run():
        fixture=PublicFixture();clock=lambda:fixture.now[0]
        market=Market(clock=clock,transport=httpx.MockTransport(fixture.handler))
        first=await market.snapshot(config('DONCHIAN'))
        count=len(fixture.requests)
        other=await market.snapshot(config('TREND_ATR'))
        assert other[1]['config_hash']!=first[1]['config_hash'] and len(fixture.requests)>count
        # Same closed candle but a later server cycle must not reuse a cached
        # response past its short freshness budget, even if monotonic test time
        # has not advanced; an actual regional block remains visible.
        fixture.failure=403;fixture.now[0]+=30
        with pytest.raises(DemoError,match='REGION_OR_ACCESS_RESTRICTED'):await market.snapshot(config('TREND_ATR'))
        await market.close()
    asyncio.run(run())


def test_protection_snapshot_uses_only_public_fresh_futures_without_analysis():
    async def run():
        fixture=PublicFixture();market=Market(clock=lambda:fixture.now[0],transport=httpx.MockTransport(fixture.handler))
        with patch('app.active43.market.analyze',side_effect=AssertionError('no entry analysis')):
            bars,decision,at=await market.protection_snapshot(config())
        assert len(bars)==12 and bars[-1].time+900==fixture.at
        assert decision['source']==SOURCE and decision.get('direction') is None
        assert all(r.method=='GET' for r in fixture.requests)
        assert any(r.url.path.endswith('/public/time') for r in fixture.requests)
        fixture.failure=502
        with pytest.raises(DemoError):await market.protection_snapshot(config())
        await market.close()
    asyncio.run(run())


def test_unrepresentable_normalized_candle_is_a_controlled_error():
    async def run():
        fixture=PublicFixture()
        def handler(request):
            response=fixture.handler(request)
            if request.url.path.endswith('/history-candles'):
                body=response.json()
                for row in body['data']:row[5]='0.00000000000000000001'
                return httpx.Response(200,json=body)
            return response
        market=Market(clock=lambda:fixture.now[0],transport=httpx.MockTransport(handler))
        with pytest.raises(DemoError,match='INVALID_DATA'):
            await market.snapshot(config())
        await market.close()
    asyncio.run(run())


def test_archived_spot_research_cannot_relabel_data_or_replace_bitget_selection(tmp_path):
    from pathlib import Path
    from scripts.active43_history import download
    from scripts.research_active43 import main,simulate
    from scripts.complete_active43_research import run
    selection=Path('app/active43/selection.json').read_bytes()
    for operation in (lambda:download(tmp_path),lambda:main(tmp_path),lambda:run(tmp_path),lambda:simulate(None,None,config(),0,0)):
        with pytest.raises(ValueError,match='ARCHIVED_SPOT_STUDY'):
            operation()
    assert list(tmp_path.iterdir())==[]
    assert Path('app/active43/selection.json').read_bytes()==selection


@pytest.mark.parametrize('failure',[403,429,'timeout'])
def test_current_quote_failure_is_controlled_and_never_uses_spot(failure):
    async def run():
        fixture=PublicFixture();requests=[]
        def handler(request):
            requests.append(request)
            if failure=='timeout':raise httpx.ReadTimeout('DUMMY_OFFLINE_TIMEOUT')
            return httpx.Response(failure,text='OFFLINE_TEST_ONLY')
        quotes=Quotes(clock=lambda:fixture.now[0],transport=httpx.MockTransport(handler))
        with pytest.raises(DemoError):await quotes.get()
        assert requests and all(r.url.host=='api.bitget.com' and r.method=='GET' for r in requests)
        await quotes.close()
    asyncio.run(run())


def test_bitget_scheduler_header_is_incompatible_with_archived_spot_runtime(monkeypatch):
    from fastapi import FastAPI
    from app.active43.api import router
    from tests.test_active43 import setup
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','DUMMY_BITGET_SCHEDULER_'+'x'*40)
    async def run():
        market,now,store,service=setup();app=FastAPI();app.include_router(router);app.state.active43=service
        token='DUMMY_BITGET_SCHEDULER_'+'x'*40
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post('/api/active43/tick',headers={'X-Aura-Active43-Token':token})).status_code==401
            assert (await client.post('/api/active43/tick',headers={'X-Aura-Active43-Bybit-Token':token})).status_code==401
            response=await client.post('/api/active43/tick',headers={'X-Aura-Active43-Bitget-Token':token})
            assert response.status_code==200
            assert response.json()['market_source']==SOURCE and response.json()['strategy_version']=='AURA_4.3_ACTIVE_PAPER_3'
        await service.close()
    asyncio.run(run())


def test_old_bybit_enablement_cannot_start_v3(monkeypatch):
    monkeypatch.setenv('AURA_ACTIVE43_ENABLED','true')
    monkeypatch.setenv('AURA_ACTIVE43_BYBIT_ENABLED','true')
    monkeypatch.delenv('AURA_ACTIVE43_BITGET_ENABLED',raising=False)
    assert configured().store is None and configured().reason=='ACTIVE43_BITGET_DISABLED'


def test_last_successful_scheduler_run_is_durable_and_not_advanced_by_source_failure():
    async def run():
        f=PublicFixture();clock=lambda:f.now[0];market=Market(clock=clock,transport=httpx.MockTransport(f.handler))
        store=MemoryStore(config(),clock());svc=Service(store,market,config(),clock=clock)
        await svc.tick();assert store.state['mode']=='OFF' and store.state['last_successful_run_at']==clock()
        await svc.control('START','e'*32,store.revision)
        last=store.state['last_successful_run_at'];f.failure=503;f.now[0]+=300
        await svc.tick();assert store.state['last_successful_run_at']==last and store.state['last_error']
        restored=Service(store,market,config(),clock=clock)
        assert (await restored.dashboard())['last_successful_run_at']==last
        await restored.close()
    asyncio.run(run())


def test_scheduler_cannot_reuse_bybit_or_owner_secret(monkeypatch):
    token='DUMMY_BITGET_DISTINCT_TOKEN_'+'x'*40
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',token)
    monkeypatch.setenv('AURA_ACTIVE43_SCHEDULER_SECRET',token)
    assert not actual_scheduler_configured()
    monkeypatch.setenv('AURA_ACTIVE43_SCHEDULER_SECRET','DUMMY_OLD_BYBIT_DIFFERENT_'+'y'*40)
    assert actual_scheduler_configured()
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',token)
    assert not actual_scheduler_configured()
