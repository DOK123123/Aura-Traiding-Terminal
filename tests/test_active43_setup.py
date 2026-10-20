"""Isolated account setup and OFF heartbeat; no production credentials/data."""
import asyncio,json
from copy import deepcopy
from unittest.mock import patch

import httpx,pytest
from fastapi import FastAPI
from app.active43.api import router
from app.active43.service import Service
from app.active43.core import initial
from app.active43.strategies import config
from app.automated.engine import DemoError
from tests.test_active43 import MemoryStore

class SeedStore(MemoryStore):
    def __init__(self):
        super().__init__(config(),1800000030)
        self.exists=False;self.loads=0;self.fail_load=False
    async def peek(self):
        return await super().load(1800000030) if self.exists else None
    async def load(self,now):
        self.loads+=1
        if self.fail_load:raise DemoError('STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN')
        if not self.exists:
            async with self.lock:
                if not self.exists:self.state=initial(now,config());self.exists=True
        return await super().load(now)


def service(store):return Service(store,clock=lambda:1800000030)
async def connected():return {'bitget':{'status':'CONNECTED'},'supabase':{'status':'CONNECTED'}}


def test_concurrent_setup_restart_and_repetition_preserve_single_off_account():
    async def run():
        store=SeedStore();a=service(store);b=service(store)
        with patch.object(a.diagnostics,'run',side_effect=connected),patch.object(b.diagnostics,'run',side_effect=connected):
            reports=await asyncio.gather(a.initialize(),b.initialize())
        assert all(r['account_available'] and r['readback_verified'] and r['mode']=='OFF' for r in reports)
        assert store.state['balance']=='10000' and store.state['position'] is None and store.events==[]
        before=await store.peek();loads=store.loads
        await a.close();restored=service(store)
        assert (await restored.initialize())['balance']=='10000'
        assert await store.peek()==before and store.loads==loads
        await restored.close();await b.close()
    asyncio.run(run())


def test_existing_changed_balance_and_on_mode_are_never_reset():
    async def run():
        store=SeedStore();store.exists=True;store.state.update(balance='9876',equity='9876',realized_pnl='-124',gross_realized_pnl='-124',mode='ON')
        before=deepcopy(store.state);svc=service(store)
        result=await svc.initialize()
        assert result['mode']=='ON' and result['balance']=='9876' and not result['initialization_attempted']
        assert store.state==before and not store.loads
        with pytest.raises(DemoError,match='OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'):await svc.verify_off_tick()
        assert store.state==before and store.events==[]
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('component',['bitget','supabase'])
def test_setup_preflight_failure_does_not_create_account(component):
    async def run():
        store=SeedStore();svc=service(store);probe=await connected();probe[component]['status']='ERROR'
        with patch.object(svc.diagnostics,'run',return_value=probe):
            with pytest.raises(DemoError):await svc.initialize()
        assert not store.exists and not store.loads and not store.events
        await svc.close()
    asyncio.run(run())


def test_database_failure_no_false_success_and_safe_recovery():
    async def run():
        store=SeedStore();svc=service(store);store.fail_load=True
        with patch.object(svc.diagnostics,'run',side_effect=connected):
            with pytest.raises(DemoError):await svc.initialize()
            assert not store.exists
            store.fail_load=False;result=await svc.initialize()
        assert result['readback_verified'] and store.state['balance']=='10000' and store.events==[]
        await svc.close()
    asyncio.run(run())


def test_off_heartbeat_reuses_tick_without_market_or_execution_and_deduplicates():
    async def run():
        store=SeedStore();svc=service(store)
        with pytest.raises(DemoError,match='SCHEDULER_ACCOUNT_NOT_INITIALIZED'):await svc.verify_off_tick()
        with patch.object(svc.diagnostics,'run',side_effect=connected):await svc.initialize()
        async def forbidden():raise AssertionError('No market snapshot or execution in OFF heartbeat')
        with patch.object(svc,'snapshot',side_effect=forbidden),patch('app.active43.service.advance',side_effect=AssertionError('No trading')):
            results=await asyncio.gather(svc.verify_off_tick(),svc.verify_off_tick())
            duplicate=await svc.verify_off_tick()
        assert all(r['mode']=='OFF' and r['opened']==r['closed']==0 and r['verification_only'] for r in results)
        assert duplicate['duplicate'] and [e['kind'] for e in store.events]==['TICK']
        assert store.state['balance']=='10000' and store.state['last_successful_run_at']==1800000030
        await svc.close()
    asyncio.run(run())


def test_concurrent_owner_start_cas_retry_cannot_turn_off_verification_into_trading():
    async def run():
        store=SeedStore();svc=service(store)
        with patch.object(svc.diagnostics,'run',side_effect=connected):await svc.initialize()
        async def owner_wins(*args):
            store.state['mode']='ON';store.revision+=1
            raise DemoError('CONCURRENT_UPDATE')
        with patch.object(store,'commit',side_effect=owner_wins),patch('app.active43.service.advance',side_effect=AssertionError('No trading')):
            with pytest.raises(DemoError,match='OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'):await svc.verify_off_tick()
        assert store.state['mode']=='ON' and store.state['balance']=='10000' and store.events==[]
        await svc.close()
    asyncio.run(run())


def test_setup_endpoints_require_scheduler_auth_explicit_confirmation_and_no_overrides(monkeypatch):
    token='DUMMY_SETUP_SCHEDULER_'+'x'*40
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',token)
    async def run():
        store=SeedStore();svc=service(store);app=FastAPI();app.include_router(router);app.state.active43=svc
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            path='/api/active43/initialize';body={'confirmation':'INITIALIZE ISOLATED PAPER ACCOUNT'};hdr={'X-Aura-Active43-Bitget-Token':token}
            assert (await c.post(path,json=body)).status_code==401
            assert (await c.post(path,json={},headers=hdr)).status_code==422
            assert (await c.post(path,json=dict(body,balance='99999'),headers=hdr)).status_code==422
            assert not store.exists
            with patch.object(svc.diagnostics,'run',side_effect=connected):r=await c.post(path,json=body,headers=hdr)
            assert r.status_code==200 and r.json()['mode']=='OFF'
            assert (await c.post('/api/active43/verify-off-tick',json=body,headers=hdr)).status_code==200
            assert store.state['balance']=='10000' and store.state['mode']=='OFF'
            assert all(e['kind']=='TICK' for e in store.events)
        await svc.close()
    asyncio.run(run())


def test_prepare_client_uses_only_explicit_setup_and_guarded_off_endpoint():
    from scripts.active43_scheduler import prepare,INITIALIZE_URL,OFF_TICK_URL,DIAGNOSTIC_URL,URL
    from tests.test_active43_scheduler import Response
    class Client:
        def __init__(self):self.urls=[]
        def open(self,req,timeout):
            self.urls.append(req.full_url)
            if req.full_url==DIAGNOSTIC_URL:
                after=len(self.urls)>1
                return Response(dict(scope='AURA43_ACTIVE_PAPER',market_source='Bitget · USDT-M Futures / api.bitget.com',
                    strategy_version='AURA_4.3_ACTIVE_PAPER_3',paper_only=True,exchange_execution=False,read_only=True,state_changed=False,
                    production_paper_verified=False,status='PASS' if after else 'BLOCKED',mode='OFF',configuration={'server_enabled':True},
                    bitget={'status':'CONNECTED'},supabase={'status':'CONNECTED'},scheduler={'status':'ACTIVE' if after else 'ERROR','diagnostic_delivery_confirmed':True}))
            assert json.loads(req.data)=={'confirmation':'INITIALIZE ISOLATED PAPER ACCOUNT'}
            if req.full_url==INITIALIZE_URL:
                return Response(dict(operation='INITIALIZE_PAPER_ACCOUNT',status='ACCOUNT_AVAILABLE',scope='AURA43_ACTIVE_PAPER',market_source='Bitget · USDT-M Futures / api.bitget.com',
                    strategy_version='AURA_4.3_ACTIVE_PAPER_3',paper_only=True,account_available=True,state_saved=True,readback_verified=True,
                    existing_account_preserved=True,exchange_execution=False,mode_changed_by_operation=False,trade_execution_performed=False,
                    production_paper_verified=False,mode='OFF',position_present=False,initial_balance_matches=True))
            assert req.full_url==OFF_TICK_URL
            return Response(dict(status='COMPLETED',scope='AURA43_ACTIVE_PAPER',market_source='Bitget · USDT-M Futures / api.bitget.com',
                strategy_version='AURA_4.3_ACTIVE_PAPER_3',paper_only=True,exchange_execution=False,state_saved=True,mode='OFF',
                processed=False,duplicate=False,opened=0,closed=0,last_processed_closed_at=None,verification_only=True))
    client=Client();logs=[];token='DUMMY_PREPARE_TOKEN_'+'x'*40
    assert prepare({'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET':token},opener=client,emit=logs.append)==0
    assert client.urls==[DIAGNOSTIC_URL,INITIALIZE_URL,OFF_TICK_URL,DIAGNOSTIC_URL]
    assert URL not in client.urls and token not in '\n'.join(logs)
    assert 'PREPARATION_VERIFIED' in logs[-1] and '"production_paper_verified": false' in logs[-1]


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_setup_preserves_existing_position_and_refuses_heartbeat(side):
    from tests.test_active43 import setup
    async def run():
        market,now,store,svc=setup(side)
        with patch('app.active43.service.scheduler_configured',return_value=True):await svc.control('START','a'*32,1)
        for _ in range(2):market.add();now[0]+=market.step;await svc.tick()
        await svc.control('STOP','b'*32)
        async def peek():return await store.load(now[0])
        store.peek=peek;before=deepcopy(store.state);events=deepcopy(store.events)
        assert before['position'] and before['mode']=='OFF'
        result=await svc.initialize()
        assert result['position_present'] and result['balance']==before['balance']
        with pytest.raises(DemoError,match='OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT'):await svc.verify_off_tick()
        assert store.state==before and store.events==events
        await svc.close()
    asyncio.run(run())


def test_off_heartbeat_preserves_emergency_block():
    async def run():
        store=SeedStore();store.exists=True;store.state['emergency']=True;svc=service(store)
        before=deepcopy(store.state)
        with pytest.raises(DemoError,match='OFF_TICK_ACCOUNT_RISK_BLOCKED'):await svc.verify_off_tick()
        assert store.state==before and store.events==[]
        await svc.close()
    asyncio.run(run())
