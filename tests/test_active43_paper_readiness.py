"""Isolated readiness: actual strategy preview, no production access or writes."""
import asyncio
from copy import deepcopy
from unittest.mock import patch, AsyncMock
import httpx
import pytest
from fastapi import FastAPI
from app.active43 import paper_readiness as pr
from app.active43.api import router
from app.active43.core import event
from app.active43.strategies import config
from app.active43.service import Service
from app.automated.engine import DemoError
from scripts.verify_active43_bounce import BounceMarket
from tests.test_active43 import MemoryStore


def prepare():
    market=BounceMarket('LONG');now=market.now
    store=MemoryStore(config('SR_BOUNCE','5m'),now[0])
    async def peek():return dict(state=deepcopy(store.state),revision=store.revision,last_saved_at=now[0])
    store.peek=peek
    svc=Service(store,cfg=config('SR_BOUNCE','5m'),clock=lambda:now[0])
    for n in (1,0):
        at=now[0]//300*300-300*n+120
        # place current observation beyond the latest scheduled time
        created=at+5
        e=event(store.state,'TICK',created//300,created,dict(scheduled_delivery=dict(
            source='CLOUDFLARE_SCHEDULED_REPORTED',scheduled_at=at,invocation_id=str(n+1)*32,
            status='COMPLETED',mode='OFF',opened=0,closed=0)))
        e['id']=store.state['epoch']+':tick:'+str(created//300);store.events.append(e)
    now[0]=now[0]//300*300+150
    return market,now,store,svc


async def probe(change=None):
    market,now,store,svc=prepare()
    if change:change(market,now,store,svc)
    before=deepcopy((store.state,store.events,store.revision,svc.config,svc.restored))
    async def forbidden(*args,**kw):raise AssertionError('WRITE_OR_LOAD_ATTEMPT')
    with patch.object(pr,'Market',return_value=market),patch.object(pr,'scheduler_configured',return_value=True),patch.object(store,'load',side_effect=forbidden),patch.object(store,'commit',side_effect=forbidden),patch.object(svc,'tick',side_effect=forbidden),patch.object(svc,'control',side_effect=forbidden):
        r=await pr.inspect(svc)
    assert before==deepcopy((store.state,store.events,store.revision,svc.config,svc.restored))
    await svc.close()
    return r


def test_ready_uses_real_bounce_preview_and_never_changes_ledger():
    r=asyncio.run(probe())
    assert r['status']=='READY',r
    assert r['account']['balance']=='10000'
    assert r['market']['bars']==1000 and r['market']['history_complete']
    assert r['signal']['strategy_reason']=='BOUNCE_NO_CONFIRMED_REJECTION'
    assert r['signal']['entry_blocker']=='AUTO_OFF' and r['signal']['preview_only']
    assert len(r['scheduler']['ticks'])==2 and not r['scheduler']['http_delivery_verified']
    assert r['read_only'] and not r['state_changed'] and not r['production_paper_verified']


@pytest.mark.parametrize('change,code',[
    (lambda m,n,s,v:s.state.update(mode='ON'),'PAPER_NOT_OFF'),
    (lambda m,n,s,v:s.state.update(data_recovery_armed=True),'DATA_RECOVERY_ARMED'),
    (lambda m,n,s,v:s.state.update(day_low_equity='9700'),'DAILY_LOSS_LIMIT'),
    (lambda m,n,s,v:s.events.clear(),'TWO_RECENT_AUTOMATIC_OFF_TICKS_NOT_CONFIRMED'),
    (lambda m,n,s,v:s.events[0]['payload'].pop('scheduled_delivery'),'TWO_RECENT_AUTOMATIC_OFF_TICKS_NOT_CONFIRMED'),
    (lambda m,n,s,v:setattr(m,'failure','UPSTREAM_TIMEOUT'),'UPSTREAM_TIMEOUT'),
    (lambda m,n,s,v:setattr(m,'failure','UPSTREAM_CLOCK_OR_STALE_RESPONSE'),'UPSTREAM_CLOCK_OR_STALE_RESPONSE'),
    (lambda m,n,s,v:n.__setitem__(0,n[0]+3600),'STALE_OR_MISMATCHED_DATA'),
])
def test_fail_closed(change,code):
    r=asyncio.run(probe(change));assert r['status']=='BLOCKED' and code in r['errors'],r


@pytest.mark.parametrize('mutation',[
    lambda rows:rows[0]['payload']['scheduled_delivery'].update(source='MANUAL'),
    lambda rows:rows[0]['payload']['scheduled_delivery'].update(invocation_id=rows[1]['payload']['scheduled_delivery']['invocation_id']),
    lambda rows:rows[0]['payload']['scheduled_delivery'].update(opened=True),
    lambda rows:rows[0].update(id=rows[1]['id']),
])
def test_manual_duplicate_or_malformed_receipts_never_ready(mutation):
    r=asyncio.run(probe(lambda m,n,s,v:mutation(s.events)))
    assert r['scheduler']['status']=='BLOCKED' and r['status']=='BLOCKED'


def test_corrupt_storage_and_raw_exception_are_not_exposed():
    async def run():
        m,n,s,v=prepare()
        s.peek=AsyncMock(side_effect=DemoError('DO_NOT_EXPOSE_DUMMY_PRIVATE_VALUE'))
        r=await pr.inspect(v)
        assert r['status']=='BLOCKED' and r['errors']==['READINESS_READ_FAILED']
        assert 'DO_NOT_EXPOSE' not in str(r)
        await v.close()
    asyncio.run(run())


def test_concurrent_state_change_blocks_ready_without_adopting_config():
    async def run():
        m,n,s,v=prepare();original=s.peek;calls=0
        async def changing():
            nonlocal calls
            calls+=1;r=await original()
            if calls>1:r['revision']+=1
            return r
        s.peek=changing
        with patch.object(pr,'Market',return_value=m),patch.object(pr,'scheduler_configured',return_value=True):r=await pr.inspect(v)
        assert r['status']=='BLOCKED' and 'ACCOUNT_CHANGED_DURING_READ' in r['errors']
        await v.close()
    asyncio.run(run())


def test_owner_auth_and_no_cache(monkeypatch):
    async def run():
        monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','DUMMY_READINESS_OWNER_ONLY')
        app=FastAPI();app.include_router(router)
        fake=AsyncMock(return_value={'status':'BLOCKED','read_only':True})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            with patch.object(pr,'inspect',fake):
                from types import SimpleNamespace
                app.state.active43=SimpleNamespace(readiness_lock=asyncio.Lock())
                assert (await c.get('/api/active43/paper-readiness')).status_code==401
                fake.assert_not_awaited()
                r=await c.get('/api/active43/paper-readiness',auth=('aura','DUMMY_READINESS_OWNER_ONLY'))
                assert r.status_code==200 and 'no-store' in r.headers['cache-control']
                fake.assert_awaited_once()
    asyncio.run(run())


def test_authenticated_scheduled_receipt_survives_restart_and_duplicate(monkeypatch):
    async def run():
        from tests.test_active43_tick_delivery import prepare as delivery_prepare,TOKEN
        app,now,store,svc,logs=delivery_prepare(monkeypatch)
        now[0]=now[0]//300*300+130
        headers={'X-Aura-Active43-Bitget-Token':TOKEN,'X-Aura-Invocation-Id':'a'*32,
                 'X-Aura-Scheduled-At':str((now[0]-10)*1000)}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            first=await c.post('/api/active43/tick',headers=headers);assert first.status_code==200
            receipt=deepcopy(store.events[-1]);assert receipt['payload']['scheduled_delivery']['source']=='CLOUDFLARE_SCHEDULED_REPORTED'
            before=deepcopy((store.state,store.events,store.revision))
            again=await c.post('/api/active43/tick',headers=headers)
            assert again.json()['duplicate'] and before==(store.state,store.events,store.revision)
            restarted=Service(store,cfg=svc.config,clock=lambda:now[0]);app.state.active43=restarted
            again=await c.post('/api/active43/tick',headers=headers)
            assert again.json()['tick_id']==first.json()['tick_id'] and before==(store.state,store.events,store.revision)
            # auth and malformed metadata cannot cause a write
            bad=dict(headers);bad['X-Aura-Scheduled-At']='DUMMY_PRIVATE_TOKEN'
            assert (await c.post('/api/active43/tick',headers=bad)).status_code==400
            bad.pop('X-Aura-Active43-Bitget-Token')
            assert (await c.post('/api/active43/tick',headers=bad)).status_code==401
            assert before==(store.state,store.events,store.revision)
            await restarted.close()
        await svc.close()
    asyncio.run(run())


def test_concurrent_owner_probe_is_bounded_and_never_waits_on_trading_lock(monkeypatch):
    async def run():
        from types import SimpleNamespace
        monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','DUMMY_OWNER_BUSY_ONLY')
        app=FastAPI();app.include_router(router)
        lock=asyncio.Lock();await lock.acquire()
        app.state.active43=SimpleNamespace(readiness_lock=lock)
        with patch.object(pr,'inspect',AsyncMock()) as fn:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                r=await c.get('/api/active43/paper-readiness',auth=('aura','DUMMY_OWNER_BUSY_ONLY'))
                assert r.status_code==200 and r.json()['errors']==['READINESS_BUSY']
                fn.assert_not_awaited()
        lock.release()
    asyncio.run(run())


@pytest.mark.parametrize('value', ['bad','1800000000000','9999999999999'])
def test_invalid_or_stale_attribution_does_not_execute(value,monkeypatch):
    async def run():
        from tests.test_active43_tick_delivery import prepare as delivery_prepare,TOKEN
        app,now,store,svc,logs=delivery_prepare(monkeypatch)
        before=deepcopy((store.state,store.events,store.revision))
        with patch.object(svc,'tick',AsyncMock()) as tick:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                r=await c.post('/api/active43/tick',headers={'X-Aura-Active43-Bitget-Token':TOKEN,
                    'X-Aura-Invocation-Id':'a'*32,'X-Aura-Scheduled-At':value})
                assert r.status_code==400
                tick.assert_not_awaited()
        assert before==(store.state,store.events,store.revision)
        await svc.close()
    asyncio.run(run())


def test_incomplete_history_is_not_reported_complete():
    r=asyncio.run(probe(lambda m,n,s,v:m.bars.pop(0)))
    assert r['status']=='BLOCKED' and r['market']['code']=='HISTORY_INCOMPLETE'


def test_signal_and_explicit_off_blocker_are_separate():
    def confirm(m,n,s,v):
        m.add('touch');m.add('confirm')
        n[0]=m.at+150
    r=asyncio.run(probe(confirm))
    assert r['signal']['direction']=='LONG' and r['signal']['entry_blocker']=='AUTO_OFF'
    assert r['signal']['strategy_reason']=='CLOSED_SUPPORT_BOUNCE'


def test_history_permission_error_is_safe_and_distinct():
    async def run():
        m,n,s,v=prepare();s.history=AsyncMock(side_effect=DemoError('STORAGE_PERMISSION_DENIED'))
        with patch.object(pr,'Market',return_value=m),patch.object(pr,'scheduler_configured',return_value=True):r=await pr.inspect(v)
        assert r['status']=='BLOCKED' and r['scheduler']['code']=='STORAGE_PERMISSION_DENIED'
        assert r['market']['status']=='PASS'
        await v.close()
    asyncio.run(run())


def test_old_scheduler_pair_does_not_grant_readiness_even_with_fresh_market():
    market,now,store,svc=prepare()
    rows=deepcopy(store.events)
    assert pr.scheduler_evidence(rows,store.state,now[0]+400)['status']=='BLOCKED'


def test_cloudflare_jittered_receipts_are_accepted_without_weakened_provenance():
    # Real platform scheduledTime observed ~52 seconds after the cron minute.
    market,now,store,svc=prepare()
    rows=deepcopy(store.events)
    for row in rows:
        proof=row['payload']['scheduled_delivery']
        proof['scheduled_at']+=52
        row['created_at']+=52
    now[0]=now[0]//300*300+220
    evidence=pr.scheduler_evidence(rows,store.state,now[0])
    assert evidence['status']=='PASS',evidence
    assert len(evidence['ticks'])==2
    # Wrong cron slot and stale/different invocation must remain blocked.
    bad=deepcopy(rows)
    bad[0]['payload']['scheduled_delivery']['scheduled_at']-=60
    assert pr.scheduler_evidence(bad,store.state,now[0])['status']=='BLOCKED'
    bad=deepcopy(rows)
    bad[0]['payload']['scheduled_delivery']['invocation_id']=bad[1]['payload']['scheduled_delivery']['invocation_id']
    assert pr.scheduler_evidence(bad,store.state,now[0])['status']=='BLOCKED'


@pytest.mark.parametrize('damage',['changed','missing'])
def test_readiness_blocks_saved_anchor_disagreement_without_rebaseline(damage):
    from app.lab.models import digest
    from dataclasses import replace
    from decimal import Decimal
    def change(m,n,s,v):
        anchor=m.bars[-1] if damage=='changed' else replace(m.bars[0],time=m.bars[0].time-300)
        original=replace(anchor,volume=anchor.volume+Decimal(1)) if damage=='changed' else anchor
        s.state.update(watermark=anchor.time+300,last_bar_hash=digest(original.data()),last_anchor_ohlcv=original.data())
    r=asyncio.run(probe(change))
    assert r['status']=='BLOCKED',r
    assert ('HISTORY_CANDLE_CHANGED' if damage=='changed' else 'HISTORY_CANDLE_MISSING') in r['errors']
    assert r['history']['status']=='BLOCKED' and r['history']['requires_owner_review']


def test_readiness_reports_matching_anchor_read_only():
    from app.lab.models import digest
    def change(m,n,s,v):
        anchor=m.bars[-1]
        s.state.update(watermark=anchor.time+300,last_bar_hash=digest(anchor.data()),last_anchor_ohlcv=anchor.data())
    r=asyncio.run(probe(change))
    assert r['status']=='READY' and r['history']['status']=='PASS'
    assert r['history']['anchor_status']=='MATCHED'


def test_readiness_accepts_proven_numeric_equivalence_without_clearing_saved_guard():
    from dataclasses import replace
    from decimal import Decimal
    from app.lab.models import digest
    from app.active43.core import SOURCE
    def change(m,n,s,v):
        anchor=m.bars[-1];old=replace(anchor,volume=Decimal('100.0'))
        s.state.update(watermark=old.time+300,last_bar_hash=digest(old.data()),last_anchor_ohlcv=old.data())
        s.state['history_guard']=dict(code='HISTORY_CANDLE_CHANGED',source=SOURCE,old_ohlcv_hash=s.state['last_bar_hash'])
    r=asyncio.run(probe(change))
    assert r['status']=='READY' and r['history']['saved_guard_present']
    assert r['history']['anchor_status']=='MATCHED'
    assert r['signal']['entry_blocker']=='AUTO_OFF'


def test_original_anchor_restored_is_ready_without_mutating_saved_guard():
    from app.lab.models import digest
    from app.active43.core import SOURCE
    def change(m,n,s,v):
        anchor=m.bars[-1]
        s.state.update(watermark=anchor.time+300,last_bar_hash=digest(anchor.data()),last_anchor_ohlcv=anchor.data())
        s.state['history_guard']=dict(code='HISTORY_CANDLE_CHANGED',source=SOURCE,old_ohlcv_hash=s.state['last_bar_hash'])
    r=asyncio.run(probe(change))
    assert r['status']=='READY' and r['history']['saved_guard_present']
    assert r['history']['anchor_status']=='MATCHED'


def test_probe_restart_and_repeat_preserve_balance_events_and_guard():
    async def run():
        from app.lab.models import digest
        from dataclasses import replace
        from decimal import Decimal
        m,n,s,v=prepare();anchor=replace(m.bars[-1],volume=Decimal('99'))
        s.state.update(watermark=anchor.time+300,last_bar_hash=digest(anchor.data()),last_anchor_ohlcv=anchor.data())
        before=deepcopy((s.state,s.events,s.revision))
        for _ in range(2):
            with patch.object(pr,'Market',return_value=m),patch.object(pr,'scheduler_configured',return_value=True):r=await pr.inspect(v)
            assert r['status']=='BLOCKED' and r['history']['code']=='HISTORY_CANDLE_CHANGED'
            assert (s.state,s.events,s.revision)==before
            await v.close()
            v=Service(s,cfg=config('SR_BOUNCE','5m'),clock=lambda:n[0])
        await v.close()
    asyncio.run(run())
