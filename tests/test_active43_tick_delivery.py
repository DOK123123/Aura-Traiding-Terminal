"""Receipt/logging regressions; isolated memory/ASGI only, never production."""
import asyncio
from copy import deepcopy
import json
import pytest
import httpx
from fastapi import FastAPI
from app.active43.api import router
from app.active43 import delivery
from tests.test_active43 import setup

TOKEN='DUMMY_TICK_DELIVERY_SCHEDULER_'+'x'*40
COMMIT='d'*40


def prepare(monkeypatch):
    market,now,store,svc=setup()
    async def peek():return await store.load(now[0])
    store.peek=peek
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',TOKEN)
    monkeypatch.setenv('RENDER_GIT_COMMIT',COMMIT)
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','ТЕСТОВЫЙ_ПАРОЛЬ_НЕ_СЕКРЕТ')
    logs=[];monkeypatch.setattr(delivery.logger,'info',lambda fmt,raw:logs.append(json.loads(raw)))
    app=FastAPI();app.include_router(router);app.state.active43=svc
    return app,now,store,svc,logs


@pytest.mark.parametrize('path',['tick','verify-off-tick'])
def test_receipt_is_actual_readback_and_repeated_delivery_does_not_write(path,monkeypatch):
    async def run():
        app,now,store,svc,logs=prepare(monkeypatch);before=deepcopy(store.state)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            args={'headers':{'X-Aura-Active43-Bitget-Token':TOKEN,'X-Aura-Invocation-Id':'a'*32}}
            if path=='verify-off-tick':args['json']={'confirmation':'INITIALIZE ISOLATED PAPER ACCOUNT'}
            first=await c.post('/api/active43/'+path,**args);assert first.status_code==200
            body=first.json();receipt=next(e for e in store.events if e['kind']=='TICK')
            assert body['tick_id']==receipt['id']
            assert body['tick_created_at']==receipt['created_at']==now[0]
            assert body['tick_slot_start']==now[0]//300*300 and body['tick_receipt_verified']
            assert body['render_commit']==body['tick_render_commit']==COMMIT
            revision=store.revision
            again=await c.post('/api/active43/'+path,**args)
            assert again.json()['duplicate'] and again.json()['tick_id']==body['tick_id']
            assert again.json()['tick_created_at']==body['tick_created_at'] and store.revision==revision
            assert len([e for e in store.events if e['kind']=='TICK'])==1
            for key in ('balance','equity','mode','position','pending','pending_exit','trades','fees','realized_pnl'):
                assert store.state[key]==before[key]
            assert all(e['event']=='TICK_SAVED' and e['invocation_id']=='a'*32 and e['http_status']==200 and e['duration_ms']>=0 for e in logs)
            assert TOKEN not in json.dumps(logs)
        await svc.close()
    asyncio.run(run())


def test_auth_and_bad_correlation_never_execute_or_expose_secrets(monkeypatch):
    async def run():
        app,now,store,svc,logs=prepare(monkeypatch)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            assert (await c.post('/api/active43/tick')).status_code==401
            for cid in ('DUMMY_PRIVATE_DO_NOT_LOG','c'*300):
                r=await c.post('/api/active43/tick',headers={'X-Aura-Active43-Bitget-Token':TOKEN,'X-Aura-Invocation-Id':cid})
                assert r.status_code==400 and cid not in r.text
            assert not store.events and not logs
        await svc.close()
    asyncio.run(run())


def test_unknown_commit_or_logging_error_never_creates_false_extra_tick(monkeypatch):
    async def run():
        app,now,store,svc,logs=prepare(monkeypatch)
        store.fail=True
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            headers={'X-Aura-Active43-Bitget-Token':TOKEN,'X-Aura-Invocation-Id':'e'*32}
            failed=await c.post('/api/active43/tick',headers=headers)
            assert failed.status_code==503 and not store.events
            assert logs[-1]['event']=='TICK_FAILED' and logs[-1]['tick_id'] is None
            store.fail=False
            def broken_logger(*args):raise RuntimeError('DUMMY_LOGGER_FAILURE')
            monkeypatch.setattr(delivery.logger,'info',broken_logger)
            ok=await c.post('/api/active43/tick',headers=headers)
            assert ok.status_code==200 and ok.json()['tick_receipt_verified']
            assert (await c.post('/api/active43/tick',headers=headers)).json()['duplicate']
            assert len(store.events)==1
        await svc.close()
    asyncio.run(run())


def test_missing_readback_receipt_does_not_claim_saved(monkeypatch):
    async def run():
        app,now,store,svc,logs=prepare(monkeypatch)
        actual=store.lookup;reads=[0]
        async def missing(key):
            reads[0]+=1
            if reads[0]>2:return None
            return await actual(key)
        monkeypatch.setattr(store,'lookup',missing)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            r=await c.post('/api/active43/tick',headers={'X-Aura-Active43-Bitget-Token':TOKEN})
            assert r.status_code==503 and r.json()['code']=='STORAGE_READBACK_OUTCOME_UNKNOWN'
            assert logs[-1]['event']=='TICK_FAILED' and logs[-1]['tick_id'] is None
            assert len(store.events)==1
        monkeypatch.setattr(store,'lookup',actual)
        assert (await svc.tick())['duplicate']
        await svc.close()
    asyncio.run(run())
