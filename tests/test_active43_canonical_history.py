"""Exact numeric identity and narrow, durable, volume-only recovery."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal,localcontext
from unittest.mock import patch
import pytest
from app.active43.candle_integrity import decimal_text,candle_hash,anchor_matches
from app.active43.recovery import history_issue
from app.active43.service import Service
from app.lab.models import digest
from tests.test_active43 import setup


def test_normalization_does_not_round_with_small_decimal_context():
    with localcontext() as ctx:
        ctx.prec=3
        assert decimal_text(Decimal('12345678901234567890123456789.123456789000'))=='12345678901234567890123456789.123456789'
        assert decimal_text(Decimal('100000'))=='100000'
        assert decimal_text(Decimal('-0.000'))=='0'
    for value in ('NaN','Infinity','1E+99999999','1E-99999999'):
        with pytest.raises(ValueError):decimal_text(Decimal(value))


def test_legacy_format_equivalence_requires_a_provable_original_value():
    m,n,s,v=setup();bar=replace(m.bars[-1],volume=Decimal('100.000'))
    saved=deepcopy(s.state);saved.update(watermark=bar.time+m.step,last_bar_hash=digest(bar.data()),last_anchor_ohlcv=bar.data())
    equivalent=replace(bar,volume=Decimal('100'))
    assert anchor_matches(saved,equivalent)
    assert candle_hash(bar)==candle_hash(equivalent)
    assert not anchor_matches(saved,replace(equivalent,close=equivalent.close+Decimal('.000000000001')))
    saved.pop('last_anchor_ohlcv');assert not anchor_matches(saved,equivalent)


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('tf',['5m','15m'])
def test_format_change_same_slot_migrates_once_without_trade_or_pause(side,tf):
    async def run():
        m,n,store,svc=setup(side,tf=tf,name='SR_BOUNCE' if tf=='5m' else 'DONCHIAN');m.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        old=replace(m.bars[-1],volume=Decimal('100.000'))
        store.state.update(last_bar_hash=digest(old.data()),last_anchor_ohlcv=old.data())
        m.bars[-1]=replace(old,volume=Decimal('100'))
        r=await svc.tick();assert r['mode']=='ON' and not r['opened'] and not r['closed']
        assert store.state['last_bar_hash']==candle_hash(m.bars[-1])
        first=deepcopy((store.state,store.events,store.revision))
        await svc.close();svc=Service(store,m,store.state['config'],clock=lambda:n[0])
        again=await svc.tick();assert again['duplicate'] and first==(store.state,store.events,store.revision)
        assert len([e for e in store.events if e['kind']=='HISTORY_NORMALIZED'])==1
        assert store.state['balance']=='10000'
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('tf',['5m','15m'])
def test_small_volume_revision_requires_three_slots_and_survives_restart(side,tf):
    async def run():
        m,n,store,svc=setup(side,tf=tf,name='SR_BOUNCE' if tf=='5m' else 'DONCHIAN');m.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        anchor=m.bars[-1];m.bars[-1]=replace(anchor,volume=anchor.volume+Decimal('.01'))
        for count in (1,2,3):
            m.add();n[0]+=m.step;r=await svc.tick()
            assert r['mode']==('ON' if count==3 else 'PAUSED')
            before=deepcopy((store.state,store.events,store.revision))
            assert (await svc.tick())['duplicate'] and before==(store.state,store.events,store.revision)
            if count==1:
                await svc.close();svc=Service(store,m,store.state['config'],clock=lambda:n[0])
                # Source may reformat the same revised volume; evidence stays numeric.
                m.bars[-2]=replace(m.bars[-2],volume=Decimal('100.0100'))
        audit=[e for e in store.events if e['kind']=='HISTORY_REBASELINE']
        assert len(audit)==1 and audit[0]['payload']['accepted_numeric_fields']==['volume']
        assert store.state['position'] is None and store.state['pending'] is None
        assert store.state['balance']=='10000' and store.state['trades']==0
        assert not [e for e in store.events if e['kind'] in ('OPEN','CLOSE')]
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('change',['close','high','low','open','volume_drop','volume_large','missing'])
def test_price_revisions_and_unacceptable_volume_never_auto_recover(change):
    async def run():
        m,n,store,svc=setup(tf='5m',name='SR_BOUNCE');m.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        anchor=m.bars[-1]
        changed={'close':{'close':Decimal('100.1')},'open':{'open':Decimal('100.1')},'high':{'high':Decimal('102')},'low':{'low':Decimal('98')},'volume_drop':{'volume':Decimal('99.99')},'volume_large':{'volume':Decimal('101')}}
        if change!='missing':m.bars[-1]=replace(anchor,**changed[change])
        for i in range(5):
            m.add();n[0]+=m.step
            if change=='missing' and i==0:m.bars=[b for b in m.bars if b.time!=anchor.time]
            await svc.tick()
            assert store.state['mode']=='PAUSED'
            assert store.state['last_bar_hash']==candle_hash(anchor)
        assert not [e for e in store.events if e['kind'] in ('HISTORY_REBASELINE','OPEN','CLOSE')]
        await svc.close()
    asyncio.run(run())


def test_source_failure_resets_volume_confirmation_chain():
    async def run():
        m,n,store,svc=setup(tf='5m',name='SR_BOUNCE');m.signal=False
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        anchor=m.bars[-1];m.bars[-1]=replace(anchor,volume=Decimal('100.01'))
        for _ in range(2):m.add();n[0]+=m.step;await svc.tick()
        assert store.state['history_guard']['revision_observations']==2
        m.failure='UPSTREAM_TIMEOUT';m.add();n[0]+=m.step;await svc.tick()
        assert 'revision_observations' not in store.state['history_guard']
        m.failure=None
        for count in (1,2,3):
            m.add();n[0]+=m.step;result=await svc.tick()
            assert result['mode']==('ON' if count==3 else 'PAUSED')
            if count<3:assert store.state['history_guard']['revision_observations']==count
        await svc.close()
    asyncio.run(run())


def test_volume_bound_is_exact_even_beyond_decimal_context_precision():
    from app.active43.recovery import revision_quarantine
    m,n,store,_=setup(tf='5m',name='SR_BOUNCE')
    original=replace(m.bars[-1],volume=Decimal('1'))
    saved=deepcopy(store.state);saved.update(mode='ON',watermark=original.time+300,last_bar_hash=digest(original.data()),last_anchor_ohlcv=original.data())
    too_much=replace(original,volume=Decimal('1.001'+'0'*65+'1'))
    issue=history_issue(saved,[too_much],n[0])
    candidate,eligible=revision_quarantine(saved,issue,n[0])
    assert not eligible and 'revision_observations' not in candidate
