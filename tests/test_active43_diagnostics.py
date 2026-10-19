"""Read-only probes cannot reach load/commit/tick/control, even with Paper ON."""
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from app.active43.api import router
from app.active43.core import initial
from app.active43.diagnostics import configuration
from app.active43.market import Market
from app.active43.service import Service, configured
from app.active43.storage import Store
from app.active43.strategies import config
from app.automated.engine import DemoError
from app.automated.storage import packed
from scripts.verify_active43 import PublicFixture


def diagnostic_transport(fixture):
    def handler(request):
        if request.url.path.endswith('/history-candles') and request.url.params['granularity'] in ('1H','4H'):
            step=3600 if request.url.params['granularity']=='1H' else 14400
            start=int(request.url.params['startTime'])//1000
            end=int(request.url.params['endTime'])//1000
            rows=[[str(at*1000),'68000','68100','67900','68000','100','6800000'] for at in range(start,end,step)]
            return httpx.Response(200,json=dict(code='00000',requestTime=fixture.now[0]*1000,data=rows))
        return fixture.handler(request)
    return httpx.MockTransport(handler)


class ReadOnlyStore:
    def __init__(self, state):
        self.state=state
        self.reads=0
    async def history(self, **kwargs):
        assert kwargs=={'limit':1}
        self.reads+=1
        return []
    async def peek(self):
        self.reads+=1
        return None if self.state is None else {'state':deepcopy(self.state)}
    async def load(self, *args):raise AssertionError('diagnostics must not initialize')
    async def commit(self, *args):raise AssertionError('diagnostics must not commit')
    async def close(self):pass


def test_dedicated_flag_replaces_absent_legacy_gate_but_explicit_stop_is_preserved(monkeypatch):
    monkeypatch.delenv('AURA_ACTIVE43_ENABLED',raising=False)
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_ENABLED','true')
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SUPABASE_URL','https://abcdefghijkl.supabase.co')
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY','DUMMY_DIAGNOSTIC_KEY_'+'x'*40)
    async def run():
        svc=configured()
        assert svc.store is not None and svc.reason is None
        await svc.close()
    asyncio.run(run())
    assert configuration()['server_enabled'] is True
    monkeypatch.setenv('AURA_ACTIVE43_ENABLED','false')
    assert configured().reason=='ACTIVE43_DISABLED'
    assert configuration()['explicit_global_stop'] and not configuration()['server_enabled']
    monkeypatch.delenv('AURA_ACTIVE43_ENABLED')
    monkeypatch.delenv('AURA_ACTIVE43_BITGET_ENABLED')
    assert configured().reason=='ACTIVE43_BITGET_DISABLED'


@pytest.mark.parametrize('mode',['OFF','ON','PAUSED','EMERGENCY'])
def test_probe_off_and_on_never_calls_execution_or_writes_and_is_single_flight(mode,monkeypatch):
    async def run():
        fixture=PublicFixture()
        state=initial(fixture.now[0],config());state['mode']=mode
        state['last_run_at']=state['last_successful_run_at']=fixture.now[0]-10
        store=ReadOnlyStore(state);before=deepcopy(state)
        service=Service(store,reason='ACTIVE43_DISABLED',clock=lambda:fixture.now[0])
        factory=lambda **kw:Market(clock=kw['clock'],transport=diagnostic_transport(fixture))
        with patch('app.active43.diagnostics.Market',side_effect=factory),patch('app.active43.service.scheduler_configured',return_value=True):
            reports=await asyncio.gather(*[service.diagnostics.run() for _ in range(8)])
            assert store.reads==2
            report=reports[0]
            assert report['bitget']['status']=='CONNECTED'
            assert set(report['bitget']['candles'])=={'15m','1h','4h'}
            assert report['supabase']['status']=='CONNECTED'
            assert report['scheduler']['status']=='ACTIVE'
            assert report['virtual_balance']=='10000' and report['mode']==mode
            assert report['state_changed'] is False and report['production_paper_verified'] is False
            assert store.state==before
            # Authenticated diagnostic delivery must not become a real trading tick.
            report=await service.diagnostics.run(scheduler_delivery=True)
            assert report['scheduler']['diagnostic_delivery_confirmed']
            assert store.reads==2 and state==before
        await service.close()
    asyncio.run(run())


def test_missing_account_is_not_initialized_and_delivery_does_not_invent_tick():
    async def run():
        service=Service(ReadOnlyStore(None))
        async def skip_market(report):report['bitget']={'status':'ERROR','code':'REGION_OR_ACCESS_RESTRICTED'}
        with patch.object(service.diagnostics,'market_probe',side_effect=skip_market):
            report=await service.diagnostics.run(scheduler_delivery=True)
        assert report['supabase']['status']=='CONNECTED'
        assert report['supabase']['account_status']=='NOT_INITIALIZED'
        assert report['virtual_balance'] is None and report['mode'] is None
        assert report['scheduler']['status']=='ERROR' and report['status']=='BLOCKED'
        assert report['scheduler']['last_successful_tick'] is None
        await service.close()
    asyncio.run(run())


@pytest.mark.parametrize('status,code',[(403,'STORAGE_AUTH'),(404,'STORAGE_SCHEMA_MISSING'),(500,'STORAGE_HTTP_ERROR')])
def test_peek_is_bounded_read_only_fixed_table_and_sanitizes_failures(status,code):
    async def run():
        requests=[]
        def handler(req):
            requests.append(req)
            return httpx.Response(status,json={'code':'PGRST205' if status==404 else 'UNKNOWN','message':'SECRET_MUST_NEVER_APPEAR'})
        store=Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,config(),httpx.MockTransport(handler))
        with pytest.raises(DemoError) as exc:await store.peek()
        assert exc.value.code==code
        assert len(requests)==1 and requests[0].method=='GET'
        assert requests[0].url.path=='/rest/v1/aura_active43_bitget_account'
        assert requests[0].url.params['limit']=='1'
        assert 'SECRET' not in str(exc.value)
        await store.close()
    asyncio.run(run())


def test_peek_validates_hash_scope_and_returns_no_fabricated_balance():
    async def run():
        state=initial(1800000000,config())
        row=dict(revision=1,**packed(state),saved_at=datetime.fromtimestamp(1800000000,timezone.utc).isoformat())
        rows=[]
        store=Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,config(),httpx.MockTransport(lambda _:httpx.Response(200,json=rows)))
        assert await store.peek() is None
        rows.append(row)
        assert (await store.peek())['state']['balance']=='10000'
        row['sha256']='0'*64
        with pytest.raises(DemoError):await store.peek()
        await store.close()
    asyncio.run(run())


def test_diagnostic_auth_csrf_scheduler_separation_and_off_mode(monkeypatch):
    password='dummy-diagnostic-owner'
    token='DUMMY_DIAGNOSTIC_SCHEDULER_'+'x'*40
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',password)
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',token)
    async def run():
        service=Service(reason='ACTIVE43_DISABLED')
        async def probe(scheduler_delivery=False):
            return dict(paper_only=True,exchange_execution=False,read_only=True,state_changed=False,scheduler_delivery=scheduler_delivery)
        app=FastAPI();app.include_router(router);app.state.active43=service
        with patch.object(service.diagnostics,'run',side_effect=probe) as called:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                path='/api/active43/diagnostics'
                assert (await client.post(path)).status_code==401
                assert (await client.post(path,auth=('aura',password))).status_code==403
                hdr={'X-Aura-Paper':'local-only','Origin':'https://evil.invalid'}
                assert (await client.post(path,auth=('aura',password),headers=hdr)).status_code==403
                hdr.pop('Origin')
                assert (await client.post(path,auth=('aura',password),headers=hdr)).status_code==200
                assert (await client.post(path+'/scheduler',auth=('aura',password))).status_code==401
                assert (await client.post(path+'/scheduler',headers={'X-Aura-Active43-Token':token})).status_code==401
                response=await client.post(path+'/scheduler',headers={'X-Aura-Active43-Bitget-Token':token})
                assert response.status_code==200 and response.json()['scheduler_delivery'] is True
                assert response.headers['cache-control']=='no-store'
                assert (await client.get(path,auth=('aura',password))).status_code==405
            assert called.call_count==2
        await service.close()
    asyncio.run(run())


def test_bitget_failure_and_database_failure_remain_independent_and_sanitized():
    async def run():
        fixture=PublicFixture();fixture.failure=403
        store=ReadOnlyStore(None)
        service=Service(store,clock=lambda:fixture.now[0])
        factory=lambda **kw:Market(clock=kw['clock'],transport=diagnostic_transport(fixture))
        with patch('app.active43.diagnostics.Market',side_effect=factory):
            report=await service.diagnostics.run()
        assert report['bitget']['status']=='ERROR' and report['bitget']['code']=='REGION_OR_ACCESS_RESTRICTED'
        assert report['supabase']['status']=='CONNECTED'
        await service.close()
        class FailedStore(ReadOnlyStore):
            async def history(self,**kwargs):raise DemoError('STORAGE_SCHEMA_MISSING')
        service=Service(FailedStore(None),clock=lambda:fixture.now[0]);fixture.failure=None
        with patch('app.active43.diagnostics.Market',side_effect=factory):
            report=await service.diagnostics.run()
        assert report['bitget']['status']=='CONNECTED'
        assert report['supabase']['status']=='ERROR' and report['supabase']['code']=='STORAGE_SCHEMA_MISSING'
        assert 'https://' not in json.dumps(report['supabase'])
        await service.close()
    asyncio.run(run())


@pytest.mark.parametrize('body',[[1],[{'saved_at':12}],{'error':'SECRET_MUST_NOT_LEAK'},[{},{}]])
def test_corrupt_account_response_is_controlled_not_http_500(body):
    async def run():
        store=Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,config(),httpx.MockTransport(lambda _:httpx.Response(200,json=body)))
        with pytest.raises(DemoError):await store.peek()
        await store.close()
    asyncio.run(run())


def test_oversized_account_response_is_rejected_before_parsing():
    async def run():
        store=Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,config(),httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*131073)))
        with pytest.raises(DemoError) as exc:await store.peek()
        assert exc.value.code=='STORAGE_RESPONSE_LIMIT'
        await store.close()
    asyncio.run(run())


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_diagnostic_reads_actual_open_position_without_changing_it(side):
    from tests.test_active43 import setup
    async def run():
        market,now,store,engine=setup(side)
        with patch('app.active43.service.scheduler_configured',return_value=True):
            await engine.control('START','a'*32,1)
        for _ in range(2):
            market.add();now[0]+=market.step;await engine.tick()
        before=deepcopy(store.state)
        reader=Service(ReadOnlyStore(before),clock=lambda:now[0])
        async def skip_market(report):report['bitget']={'status':'ERROR','code':'OFFLINE_TEST_ONLY'}
        with patch.object(reader.diagnostics,'market_probe',side_effect=skip_market):
            result=await reader.diagnostics.run()
        position=result['current_position']
        assert position['direction']==side and position['active_stop']==before['position']['active_stop']
        assert result['virtual_balance']==before['balance']
        assert store.state==before==reader.store.state and reader.store.reads==2
        await reader.close();await engine.close()
    asyncio.run(run())
