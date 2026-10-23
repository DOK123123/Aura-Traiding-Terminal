"""Experimental strategy and owner selection; synthetic isolated inputs only."""
import asyncio,json
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import httpx,pytest
from fastapi import FastAPI
from app.active43.api import router
from app.active43.core import validate
from app.active43.service import Service,selected
from app.active43.strategies import config,signals
from app.automated.engine import DemoError
from app.lab.models import digest
from scripts.verify_active43_bounce import BounceMarket,cycle
from tests.test_active43 import MemoryStore


class SelectStore(MemoryStore):
    async def peek(self):return await self.load(1700000030)
    async def select_strategy(self,revision,state,ev,key):return await self.commit(revision,state,[ev],key)


def test_default_donchian_protocol_and_selection_unchanged():
    assert selected()==json.loads(Path('app/active43/selection.json').read_text())['config']==config()
    assert config()['protocol_hash']=='f2bf45afdd0e7fc324afd1c4977376aacd804d02fc6f9494212fc05e45b61e69'
    with pytest.raises(ValueError):config('SR_BOUNCE','15m')


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_confirmed_closed_bounce_and_prefix_causality(side):
    f=BounceMarket(side)
    assert signals(f.bars,'SR_BOUNCE')[-1].direction is None
    f.add('touch');assert signals(f.bars,'SR_BOUNCE')[-1].direction is None
    f.add('confirm');decision=signals(f.bars,'SR_BOUNCE')[-1]
    assert decision.direction==side and decision.target_distance==decision.stop_distance*D('1.5')
    prefix=signals(f.bars,'SR_BOUNCE');f.add('TP')
    assert signals(f.bars,'SR_BOUNCE')[:-1]==prefix
    assert all(signals(f.bars[:end],'SR_BOUNCE')==signals(f.bars,'SR_BOUNCE')[:end] for end in (20,49,1000,1001))


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('kind',['TP','SL','BOTH'])
def test_actual_signal_execution_risk_costs_restart_duplicates_and_exit(side,kind):
    r=asyncio.run(cycle(side,kind));p=r['open'];t=r['close']
    assert r['open_count']==r['close_count']==1 and r['independent_accounting']
    assert D(p['notional'])<=2000 and D(p['risk_usdt'])<=50
    assert D(p['entry_fee'])>0 and D(t['fees'])>D(p['entry_fee'])
    distance=abs(D(p['entry_price'])-D(p['stop_loss']))
    assert abs(abs(D(p['take_profit'])-D(p['entry_price']))-distance*D('1.5'))<D('.1')
    assert t['exit_reason']==('TAKE_PROFIT' if kind=='TP' else 'STOP_LOSS_AMBIGUOUS' if kind=='BOTH' else 'STOP_LOSS')


def test_selection_off_persists_and_restarts_without_resetting_financials():
    async def run():
        store=SelectStore(config(),1700000030);svc=Service(store,clock=lambda:1700000030)
        before=deepcopy(store.state);r=await svc.select_strategy('BOUNCE_5M','a'*32,1)
        assert r['state_saved'] and store.state['config']==config('SR_BOUNCE','5m') and svc.config==store.state['config']
        for k in ('balance','equity','fees','day_start_equity','day_low_equity','max_drawdown_pct','epoch','trades'):
            assert store.state[k]==before[k]
        assert store.state['mode']=='OFF' and store.state['watermark'] is None and len(store.events)==1
        assert (await svc.select_strategy('BOUNCE_5M','a'*32,1))['duplicate']
        other=Service(store,clock=lambda:1700000030)
        assert (await other.load())['state']['config']==config('SR_BOUNCE','5m') and other.config==svc.config
        assert (await other.dashboard())['strategy_switch_allowed']
        await other.select_strategy('DONCHIAN_15M','b'*32,store.revision)
        await svc.load();assert svc.config==config() and len(store.events)==2
        await svc.close();await other.close()
    asyncio.run(run())


@pytest.mark.parametrize('field,value',[('mode','ON'),('mode','PAUSED'),('mode','EMERGENCY'),('pending',{}),('pending_exit','x'),('data_recovery_armed',True),('emergency',True),('day_low_equity','9700')])
def test_selection_blocked_for_nonempty_or_armed_state(field,value):
    async def run():
        store=SelectStore(config(),1700000030);svc=Service(store,clock=lambda:1700000030)
        store.state[field]=value;before=deepcopy(store.state)
        with pytest.raises(DemoError):await svc.select_strategy('BOUNCE_5M','a'*32,1)
        assert store.state==before and not store.events
        await svc.close()
    asyncio.run(run())


def test_database_failure_and_racing_revision_never_acknowledge_or_reset_selection():
    async def run():
        store=SelectStore(config(),1700000030);svc=Service(store,clock=lambda:1700000030);before=deepcopy(store.state)
        with patch.object(store,'select_strategy',side_effect=DemoError('STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN')):
            with pytest.raises(DemoError):await svc.select_strategy('BOUNCE_5M','a'*32,1)
        assert store.state==before and svc.config==config()
        with pytest.raises(DemoError,match='CONCURRENT_UPDATE'):await svc.select_strategy('BOUNCE_5M','b'*32,2)
        assert store.state==before and not store.events
        await svc.close()
    asyncio.run(run())


def test_unauthorized_config_change_not_adopted_without_immutable_receipt():
    async def run():
        store=SelectStore(config(),1700000030);store.state['config']=config('SR_BOUNCE','5m');store.state['config_hash']=digest(store.state['config'])
        svc=Service(store)
        with pytest.raises(DemoError,match='CONFIG_CHANGED'):await svc.load()
        store.state['strategy_change_id']='active43:bitget:strategy:'+'c'*32
        with pytest.raises(DemoError,match='CONFIG_CHANGED'):await svc.load()
        await svc.close()
    asyncio.run(run())


def test_owner_auth_csrf_strict_body_and_scheduler_cannot_switch(monkeypatch):
    password='DUMMY_BOUNCE_OWNER_PASSWORD';monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',password)
    async def run():
        store=SelectStore(config(),1700000030);svc=Service(store,clock=lambda:1700000030)
        app=FastAPI();app.include_router(router);app.state.active43=svc
        body=dict(choice='BOUNCE_5M',request_id='a'*32,expected_revision=1,confirmation='CHANGE PAPER STRATEGY WHILE OFF')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            assert (await c.post('/api/active43/strategy',json=body)).status_code==401
            assert (await c.post('/api/active43/strategy',json=body,headers={'X-Aura-Active43-Bitget-Token':'DUMMY_TOKEN'})).status_code==401
            assert (await c.post('/api/active43/strategy',json=body,auth=('aura',password))).status_code==403
            headers={'X-Aura-Paper':'local-only'}
            assert (await c.post('/api/active43/strategy',json=dict(body,balance='100000'),auth=('aura',password),headers=headers)).status_code==422
            for invalid in (dict(body,confirmation='START'),dict(body,choice='LIVE'),dict(body,expected_revision=True)):
                assert (await c.post('/api/active43/strategy',json=invalid,auth=('aura',password),headers=headers)).status_code==422
            assert not store.events
            r=await c.post('/api/active43/strategy',json=body,auth=('aura',password),headers=headers)
            assert r.status_code==200 and r.json()['state_saved'] and store.state['mode']=='OFF'
        await svc.close()
    asyncio.run(run())


def test_valid_pending_and_stale_data_block_switch_or_entry():
    from app.active43.core import SOURCE
    from scripts.verify_active43_bounce import BounceMarket
    async def run():
        store=SelectStore(config(),1700000030);store.state['watermark']=1700000000//900*900
        store.state['pending']=dict(direction='LONG',signal_at=store.state['watermark'],stop_loss='67800',take_profit='68600',source=SOURCE)
        validate(store.state);svc=Service(store)
        with pytest.raises(DemoError,match='OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'):await svc.select_strategy('BOUNCE_5M','a'*32,1)
        assert not store.events;await svc.close()
        f=BounceMarket('LONG');st=MemoryStore(config('SR_BOUNCE','5m'),f.now[0]);st.state['mode']='ON'
        f.failure='STALE_DATA';engine=Service(st,f,config('SR_BOUNCE','5m'),clock=lambda:f.now[0])
        result=await engine.tick();assert result['opened']==0 and st.state['position'] is None and st.state['balance']=='10000'
        await engine.close()
    asyncio.run(run())


def test_tick_racing_selection_does_not_commit_old_configuration_or_open():
    async def run():
        store=SelectStore(config(),1700000030);a=Service(store,clock=lambda:1700000030);b=Service(store,clock=lambda:1700000030)
        commit=store.commit;switched=False
        async def race(revision,state,events,key):
            nonlocal switched
            if not switched and events[0]['kind']=='TICK':
                switched=True
                await b.select_strategy('BOUNCE_5M','d'*32,revision)
                raise DemoError('CONCURRENT_UPDATE')
            return await commit(revision,state,events,key)
        with patch.object(store,'commit',side_effect=race):
            with pytest.raises(DemoError,match='CONFIG_CHANGED'):await a.tick()
        assert store.state['mode']=='OFF' and store.state['balance']=='10000' and len(store.events)==1
        assert (await a.tick())['opened']==0 and a.config==config('SR_BOUNCE','5m')
        await a.close();await b.close()
    asyncio.run(run())


def test_simulation_has_no_network_and_refuses_render(tmp_path,monkeypatch):
    from scripts.verify_active43_bounce import run
    monkeypatch.delenv('RENDER',raising=False)
    def forbidden(*a,**kw):raise AssertionError('Simulation must never construct a network client')
    monkeypatch.setattr(httpx,'AsyncClient',forbidden)
    report=run(tmp_path/'isolated.json')
    assert len(report['cases'])==6 and not report['production_paper_verified'] and not report['production_writes']
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(ValueError,match='LOCAL_OFFLINE_ONLY'):run(tmp_path/'blocked.json')
    assert not (tmp_path/'blocked.json').exists()


def test_read_only_scan_rejects_render_future_or_existing_output_before_network(tmp_path,monkeypatch):
    from scripts.scan_active43_bounce import run
    monkeypatch.delenv('RENDER',raising=False)
    def forbidden(*a,**kw):raise AssertionError('No HTTP on invalid scan request')
    monkeypatch.setattr(httpx,'AsyncClient',forbidden)
    for end in (True,1,900000000000):
        with pytest.raises(ValueError):run(tmp_path/'invalid.json',end)
    existing=tmp_path/'existing.json';existing.write_text('UNCHANGED')
    with pytest.raises(ValueError):run(existing)
    assert existing.read_text()=='UNCHANGED'
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(ValueError):run(tmp_path/'blocked.json')


def test_selection_does_not_seed_missing_account():
    async def run():
        store=SelectStore(config(),1700000030);svc=Service(store)
        with patch.object(store,'peek',return_value=None),patch.object(store,'load',side_effect=AssertionError('No seed/load')):
            with pytest.raises(DemoError,match='SCHEDULER_ACCOUNT_NOT_INITIALIZED'):await svc.select_strategy('BOUNCE_5M','a'*32,1)
        assert not store.events and svc.config==config()
        await svc.close()
    asyncio.run(run())
