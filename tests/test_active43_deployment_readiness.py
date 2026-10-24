import asyncio
from copy import deepcopy
from unittest.mock import patch,AsyncMock
import httpx
import pytest
from fastapi import FastAPI
from app.active43.api import router
from app.active43.deployment_readiness import inspect
from tests.test_active43_paper_readiness import prepare

SHA='d'*40


def test_owner_gate_reads_full_actual_ledger_never_loads_writes_or_runs_market(monkeypatch):
    async def run():
        m,n,s,v=prepare();before=deepcopy((s.state,s.events,s.revision,v.config));monkeypatch.setenv('RENDER_GIT_COMMIT',SHA)
        forbidden=AsyncMock(side_effect=AssertionError('NO_WRITE_OR_MARKET'))
        with patch.object(s,'load',forbidden),patch.object(s,'commit',forbidden),patch.object(v,'tick',forbidden),patch.object(v,'snapshot',forbidden):
            r=await inspect(v)
        assert r['status']=='PASS' and r['render_commit']==SHA
        assert r['account']['mode']=='OFF' and r['account']['balance']=='10000' and len(r['account']['ledger_sha256'])==64
        assert before==(s.state,s.events,s.revision,v.config);forbidden.assert_not_awaited()
        # Heartbeat counters/times cannot masquerade as changes to financial history.
        s.state['last_run_at']=n[0]
        assert (await inspect(v))['account']['ledger_sha256']==r['account']['ledger_sha256']
        await v.close()
    asyncio.run(run())


def test_corrupt_or_missing_history_and_db_errors_block(monkeypatch):
    async def run():
        m,n,s,v=prepare();monkeypatch.setenv('RENDER_GIT_COMMIT',SHA)
        s.history=AsyncMock(side_effect=ValueError('DUMMY_PRIVATE_DETAIL'))
        r=await inspect(v)
        assert r['status']=='BLOCKED' and r['account'] is None and 'DUMMY_PRIVATE_DETAIL' not in str(r)
        await v.close()
    asyncio.run(run())


@pytest.mark.parametrize('mode',['ON','PAUSED','EMERGENCY'])
def test_not_off_never_passes(mode,monkeypatch):
    async def run():
        m,n,s,v=prepare();monkeypatch.setenv('RENDER_GIT_COMMIT',SHA);s.state['mode']=mode
        r=await inspect(v);assert r['status']=='BLOCKED'
        await v.close()
    asyncio.run(run())


def test_missing_sha_and_concurrent_revision_block(monkeypatch):
    async def run():
        m,n,s,v=prepare();monkeypatch.delenv('RENDER_GIT_COMMIT',raising=False)
        assert (await inspect(v))['status']=='BLOCKED'
        original=s.peek;counter=0
        async def changing():
            nonlocal counter
            counter+=1;r=await original()
            if counter>1:r['revision']+=1
            return r
        s.peek=changing;monkeypatch.setenv('RENDER_GIT_COMMIT',SHA)
        assert (await inspect(v))['account'] is None
        await v.close()
    asyncio.run(run())


def test_owner_authorization_precedes_any_reads_and_response_not_cached(monkeypatch):
    async def run():
        monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','DUMMY_DEPLOYMENT_OWNER');monkeypatch.setenv('RENDER_GIT_COMMIT',SHA)
        m,n,s,v=prepare();app=FastAPI();app.include_router(router);app.state.active43=v
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            with patch.object(s,'peek',AsyncMock(side_effect=AssertionError('NO_UNAUTH_READ'))) as peek:
                assert (await c.get('/api/active43/deployment-readiness')).status_code==401;peek.assert_not_awaited()
            r=await c.get('/api/active43/deployment-readiness',auth=('aura','DUMMY_DEPLOYMENT_OWNER'))
            assert r.status_code==200 and r.json()['status']=='PASS' and 'no-store' in r.headers['cache-control']
        await v.close()
    asyncio.run(run())
