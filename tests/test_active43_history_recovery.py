"""Synthetic isolated regression scenarios; reused with actual SQL by CLI."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
import pytest
from app.active43.service import Service
from app.active43.core import SOURCE
from app.active43.recovery import paper_status,revision_quarantine
from app.automated.engine import DemoError
from scripts.verify_active43 import FixtureMarket
from tests.test_active43 import setup


async def history_scenario(market, now, store, svc, side, damage, has_position, restart=None):
    """Works against MemoryStore or the real PostgreSQL Store, no math mocks."""
    if has_position:
        market.add();now[0]+=market.step;await svc.tick()
        market.add();now[0]+=market.step;await svc.tick()
        assert (await svc.load())['state']['position']
    market.signal=False
    before=(await svc.load())['state'];anchor=market.bars[-1]
    if damage=='changed':market.bars[-1]=replace(anchor,volume=anchor.volume+Decimal(1))
    else:market.bars.pop()
    market.add() if damage=='changed' else market.bars.append(replace(anchor,time=anchor.time+market.step))
    now[0]+=market.step
    first=await svc.tick();paused=(await svc.load())['state']
    expected='HISTORY_CANDLE_CHANGED' if damage=='changed' else 'HISTORY_CANDLE_MISSING'
    assert first['decision']==expected and first['mode']=='PAUSED'
    assert first['opened']==first['closed']==0 and paused['data_recovery_armed']
    assert paused['history_guard']['old_ohlcv_hash']==before['last_bar_hash']
    assert paused['history_guard']['source']==SOURCE
    assert paused['history_guard']['candle_timestamp']==anchor.time
    assert bool(paused['position'])==has_position
    await svc.close()
    if restart:store=restart()
    svc=Service(store,market,svc.config,clock=lambda:now[0])
    assert (await svc.load())['state']==paused
    # Ongoing discrepancy cannot be blessed by retry or service restart.
    market.add();now[0]+=market.step;await svc.tick()
    assert (await svc.load())['state']['mode']=='PAUSED'
    other=None
    if has_position:
        market.add(high='105',low='95');now[0]+=market.step
        other=Service(restart() if restart else store,market,svc.config,clock=lambda:now[0])
        await asyncio.gather(svc.tick(),other.tick())
        await svc.tick()
        closed=await store.history(kind='CLOSE')
        assert len(closed)==1 and closed[0]['payload']['exit_reason']=='STOP_LOSS_AMBIGUOUS'
        assert (await svc.load())['state']['position'] is None
    # Restore the ORIGINAL bar, not a new accepted hash; all gaps closed.
    market.bars=[b for b in market.bars if b.time!=anchor.time]+[anchor]
    market.bars.sort(key=lambda b:b.time)
    market.add();now[0]+=market.step
    recovered=await svc.tick();final=(await svc.load())['state']
    assert recovered['mode']=='ON' and final['last_error'] is None
    assert final.get('history_guard') is None and not final['pending']
    assert recovered['opened']==0
    assert len(await store.history(kind='OPEN'))==int(has_position)
    transitions=[e for e in await store.history(limit=200) if e['kind']=='STATE_TRANSITION']
    assert any(e['payload']['status']=='PAPER_PAUSED_HISTORY' for e in transitions)
    assert any(e['payload']['status']=='PAPER_ON' for e in transitions)
    await svc.close()
    if other:await other.close()
    return dict(side=side,damage=damage,position=has_position,status='PASS',
                opened=int(has_position),closed=int(has_position),restart_restored=True)


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('tf',['5m','15m'])
@pytest.mark.parametrize('damage',['changed','missing'])
@pytest.mark.parametrize('has_position',[False,True])
def test_history_pause_protection_restart_and_recovery(side,tf,damage,has_position):
    async def run():
        market,now,store,svc=setup(side,tf=tf,name='SR_BOUNCE' if tf=='5m' else 'DONCHIAN')
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        await history_scenario(market,now,store,svc,side,damage,has_position)
    asyncio.run(run())


def test_off_never_auto_resumes_and_error_logs_are_safe(caplog):
    async def run():
        market,now,store,svc=setup()
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.bars[-1]=replace(market.bars[-1],volume=Decimal(123));market.add();now[0]+=900;await svc.tick()
        assert store.state['mode']=='PAUSED'
        await svc.control('STOP','b'*32)
        revision=store.revision;now[0]+=300;await svc.tick()
        assert store.state['mode']=='OFF' and not store.state['data_recovery_armed']
        assert store.revision==revision+1 and not store.state['position']
        assert all(x in caplog.text for x in ('HISTORY_CANDLE_CHANGED','candle_timestamp','old_ohlcv_hash','new_ohlcv_hash','scheduler_run_id'))
        assert 'DUMMY' not in caplog.text
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('fresh',[False,True])
def test_source_outage_uses_only_separate_verified_protection(fresh):
    async def run():
        market,now,store,svc=setup()
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.add();now[0]+=900;await svc.tick();market.add();now[0]+=900;await svc.tick()
        market.add(high='105');now[0]+=900
        async def protection(cfg):
            if not fresh:raise DemoError('STALE_DATA')
            return await FixtureMarket.snapshot(market,cfg)
        async def outage(cfg):raise DemoError('UPSTREAM_TIMEOUT')
        market.protection_snapshot=protection
        with patch.object(market,'snapshot',side_effect=outage):await svc.tick()
        assert store.state['last_error']=='HISTORY_SOURCE_UNAVAILABLE'
        assert bool(store.state['position']) is not fresh
        assert store.state['protection_status']==('FRESH_PROTECTION' if fresh else 'EMERGENCY_UNTRUSTED_DATA')
        assert len(await store.history(kind='CLOSE'))==int(fresh)
        await svc.close()
    asyncio.run(run())


def test_incomplete_history_blocks_entries_but_protects_fresh_suffix():
    async def run():
        market,now,store,svc=setup()
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.bars.pop(100);market.add();now[0]+=900;await svc.tick()
        assert store.state['last_error']=='HISTORY_INCOMPLETE' and store.state['mode']=='PAUSED'
        assert store.state['pending'] is None
        await svc.close()
    asyncio.run(run())


def test_same_closed_candle_recovery_has_explicit_transition_reason():
    async def run():
        market,now,store,svc=setup();market.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        anchor=market.bars[-1];market.bars[-1]=replace(anchor,volume=Decimal(111))
        now[0]+=300;await svc.tick();assert store.state['mode']=='PAUSED'
        market.bars[-1]=anchor;now[0]+=300;await svc.tick()
        assert store.state['mode']=='ON' and store.state['last_error'] is None
        assert store.state['last_status_transition']['reason']=='FRESH_DATA_RECOVERED'
        assert store.state['pending'] is None
        await svc.close()
    asyncio.run(run())


def test_unobserved_protection_interval_is_disclosed_not_invented():
    async def run():
        market,now,store,svc=setup()
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        market.add();now[0]+=900;await svc.tick();market.add();now[0]+=900;await svc.tick()
        for _ in range(20):market.add()
        now[0]+=20*900
        async def unavailable(cfg):raise DemoError('INCOMPLETE_HISTORY')
        async def fresh(cfg):
            bars,d,at=await FixtureMarket.snapshot(market,cfg)
            from app.lab.models import digest
            bars=bars[-12:];d['source_sha256']=digest([b.data() for b in bars]);return bars,d,at
        market.protection_snapshot=fresh
        with patch.object(market,'snapshot',side_effect=unavailable):await svc.tick()
        assert store.state['protection_gap']['reason']=='UNOBSERVED_PROTECTION_INTERVAL'
        assert store.state['protection_status']=='FRESH_PROTECTION_GAP'
        assert store.state['position'] and store.state['mode']=='PAUSED'
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('tf',['5m','15m'])
def test_stable_numeric_revision_rebaselines_only_flat_never_traded_after_three_slots(tf):
    async def run():
        market,now,store,svc=setup(tf=tf,name='SR_BOUNCE' if tf=='5m' else 'DONCHIAN')
        market.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):
            await svc.control('START','c'*32,1)
        original=market.bars[-1]
        market.bars[-1]=replace(original,volume=original.volume+Decimal('1'))
        for expected in (1,2):
            market.add();now[0]+=market.step
            result=await svc.tick()
            assert result['mode']=='PAUSED'
            assert store.state['history_guard']['revision_observations']==expected
            assert store.state['pending'] is None
            assert not store.state['position'] and store.state['trades']==0
        market.add();now[0]+=market.step
        recovered=await svc.tick()
        assert recovered['mode']=='ON'
        assert store.state['history_guard'] is None
        assert store.state['last_decision']=='STABLE_CORRECTION_REBASELINE_WAIT_NEXT_CANDLE'
        assert store.state['watermark']==market.bars[-1].time+market.step
        assert store.state['last_anchor_ohlcv']==market.bars[-1].data()
        audit=await store.history(kind='HISTORY_REBASELINE')
        assert len(audit)==1
        assert audit[0]['payload']['distinct_observations']==3
        assert audit[0]['payload']['no_retroactive_entries'] is True
        assert not await store.history(kind='OPEN')
        assert not await store.history(kind='CLOSE')
        assert store.state['balance']=='10000'
        await svc.close()
    asyncio.run(run())


def test_numeric_revision_changing_during_quarantine_resets_confirmation_count():
    async def run():
        market,now,store,svc=setup()
        market.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):
            await svc.control('START','c'*32,1)
        original=market.bars[-1]
        market.bars[-1]=replace(original,volume=original.volume+Decimal('1'))
        market.add();now[0]+=market.step;await svc.tick()
        assert store.state['history_guard']['revision_observations']==1
        market.bars[-2]=replace(market.bars[-2],volume=original.volume+Decimal('2'))
        market.add();now[0]+=market.step;await svc.tick()
        assert store.state['mode']=='PAUSED'
        assert store.state['history_guard']['revision_observations']==1
        market.add();now[0]+=market.step;await svc.tick()
        assert store.state['mode']=='PAUSED'
        assert store.state['history_guard']['revision_observations']==2
        await svc.close()
    asyncio.run(run())


def test_stable_revision_never_resumes_after_explicit_owner_stop():
    async def run():
        market,now,store,svc=setup()
        market.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):
            await svc.control('START','c'*32,1)
        original=market.bars[-1]
        market.bars[-1]=replace(original,volume=original.volume+Decimal('1'))
        market.add();now[0]+=market.step;await svc.tick()
        assert store.state['mode']=='PAUSED'
        await svc.control('STOP','d'*32)
        for _ in range(5):
            market.add();now[0]+=market.step;await svc.tick()
        assert store.state['mode']=='OFF'
        assert not await store.history(kind='HISTORY_REBASELINE')
        assert not await store.history(kind='OPEN')
        await svc.close()
    asyncio.run(run())


def test_quarantine_counts_distinct_slots_and_rejects_unsafe_state():
    market,now,store,_=setup()
    original=store.state
    step=market.step
    mark=now[0]//step*step
    original.update(mode='PAUSED',data_recovery_armed=True,
                    last_error='HISTORY_CANDLE_CHANGED',watermark=mark)
    incident=dict(code='HISTORY_CANDLE_CHANGED',
                  change_classification='NUMERIC_VALUES_CHANGED',
                  numeric_changed_fields=['close'],
                  old_ohlcv_hash='old',new_ohlcv_hash='new',
                  anchor_timestamp=mark-step)
    first,ok=revision_quarantine(original,dict(incident),now[0])
    assert not ok and first['revision_observations']==1
    original['history_guard']=first
    repeat,ok=revision_quarantine(original,dict(incident),now[0]+1)
    assert not ok and repeat['revision_observations']==1
    original['history_guard']=repeat
    second,ok=revision_quarantine(original,dict(incident),now[0]+step)
    assert not ok and second['revision_observations']==2
    original['history_guard']=second
    third,ok=revision_quarantine(original,dict(incident),now[0]+2*step)
    assert ok and third['revision_observations']==3
    for restriction in ('trades','position','pending','pending_exit','off'):
        unsafe=deepcopy(original)
        if restriction=='trades':unsafe['trades']=1
        elif restriction=='position':unsafe['position']={'id':'test'}
        elif restriction=='pending':unsafe['pending']={'direction':'LONG'}
        elif restriction=='pending_exit':unsafe['pending_exit']='test'
        else:unsafe['mode']='OFF'
        candidate,eligible=revision_quarantine(unsafe,dict(incident),now[0]+2*step)
        assert not eligible
