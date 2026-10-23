"""Actual owner-independent scheduler HTTP response -> Worker, entirely offline."""
import asyncio
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from app.active43.api import router
from app.active43.core import initial
from app.active43.market import Market
from app.active43.service import Service
from app.active43.strategies import config
from scripts.verify_active43 import PublicFixture
from tests.test_active43_diagnostics import ReadOnlyStore, diagnostic_transport


@pytest.mark.parametrize('account', ['fresh', 'stale', 'missing'])
def test_worker_accepts_actual_server_diagnostics_without_hiding_blocked(account, monkeypatch):
    token = 'DUMMY_CF_SERVER_CONTRACT_' + 'x'*40
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET', token)
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_ENABLED', 'true')
    monkeypatch.setenv('AURA_ACTIVE43_ENABLED', 'true')

    async def response():
        fixture = PublicFixture()
        state = initial(fixture.now[0], config()) if account != 'missing' else None
        if state is not None:
            state['last_successful_run_at'] = fixture.now[0] - (10 if account == 'fresh' else 1000)
        store = ReadOnlyStore(state)
        before = deepcopy(state)
        service = Service(store, clock=lambda:fixture.now[0])
        app = FastAPI();app.include_router(router);app.state.active43 = service
        factory = lambda **kw:Market(clock=kw['clock'], transport=diagnostic_transport(fixture))
        with patch('app.active43.diagnostics.Market', side_effect=factory):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                r = await client.post('/api/active43/diagnostics/scheduler', headers={'X-Aura-Active43-Bitget-Token':token})
        assert r.status_code == 200
        assert store.state == before and store.reads == 2
        await service.close()
        return r.json()

    body = asyncio.run(response())
    expected = 'PASS' if account == 'fresh' else 'BLOCKED'
    assert body['status'] == expected
    # Dummy env + captured actual response through stdin, no remote network.
    script = """
import {run} from './deploy/active43-free-worker/worker.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;
const {body,token}=JSON.parse(input),logs=[];
const result=await run({AURA_ACTIVE43_CRON_ENABLED:'true',AURA_ACTIVE43_OPERATION:'diagnostics',AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:token},
 {emit:b=>logs.push(b),fetcher:async()=>Response.json(body)});
console.log(JSON.stringify({result,logs}));
"""
    out = subprocess.run(['node','--input-type=module','-e',script],
        input=json.dumps(dict(body=body,token=token)),text=True,capture_output=True,
        cwd=Path(__file__).resolve().parents[1],timeout=10,check=True)
    result = json.loads(out.stdout)
    assert result['result']['status'] == expected
    assert [e['event'] for e in result['logs']] == ['REQUEST_STARTED','RENDER_REACHED','DIAGNOSTICS_RECEIVED'] + (['DIAGNOSTICS_BLOCKED'] if expected == 'BLOCKED' else [])
    assert token not in out.stdout and 'virtual_balance' not in out.stdout and 'current_position' not in out.stdout


def test_saved_mode_off_heartbeat_does_not_require_bitget_or_open_positions(monkeypatch):
    from tests.test_active43_setup import SeedStore
    token='DUMMY_SAVED_MODE_FRESHNESS_'+'x'*40
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',token)
    async def response():
        store=SeedStore();store.exists=True
        svc=Service(store,clock=lambda:1800000030)
        app=FastAPI();app.include_router(router);app.state.active43=svc
        with patch.object(svc,'snapshot',side_effect=AssertionError('OFF must not request market data')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                responses=[await c.post('/api/active43/tick',headers={'X-Aura-Active43-Bitget-Token':token}) for _ in range(2)]
        assert all(r.status_code==200 for r in responses)
        assert [r.json()['duplicate'] for r in responses]==[False,True]
        assert store.state['mode']=='OFF' and store.state['balance']=='10000'
        assert store.state['position'] is None and [e['kind'] for e in store.events]==['TICK']
        await svc.close()
        return [r.json() for r in responses]
    bodies=asyncio.run(response())
    script="""
import {run} from './deploy/active43-free-worker/worker.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const {bodies,token}=JSON.parse(raw),logs=[];
for(const body of bodies)await run({AURA_ACTIVE43_CRON_ENABLED:'true',AURA_ACTIVE43_OPERATION:'saved_mode',AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:token},
 {emit:b=>logs.push(b),fetcher:async(url)=>{if(!url.endsWith('/tick'))throw Error('WRONG_PATH');return Response.json(body);}});
console.log(JSON.stringify(logs));
"""
    out=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(dict(bodies=bodies,token=token)),
        text=True,capture_output=True,timeout=10,check=True,cwd=Path(__file__).resolve().parents[1])
    logs=json.loads(out.stdout);saves=[r for r in logs if r['event']=='TICK_SAVED']
    assert len(saves)==2 and all(r['status']=='COMPLETED' and r['mode']=='OFF' and r['opened']==r['closed']==0 and r['state_saved'] for r in saves)
    assert token not in out.stdout
