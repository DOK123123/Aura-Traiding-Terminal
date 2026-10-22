"""Read-only owner snapshot: no seed, execution, financial disclosure or writes."""
import asyncio
from copy import deepcopy
from unittest.mock import patch
import httpx
import pytest
from fastapi import FastAPI
from app.active43.api import router
from app.active43.readiness import inspect
from app.active43.service import Service
from app.automated.engine import DemoError, risk_reason
from tests.test_active43_setup import SeedStore, service


async def snapshot(store=None):
    store = store or SeedStore()
    store.exists = True
    svc = service(store)
    before = deepcopy((store.state, store.events, store.revision))
    async def forbidden(*args, **kwargs):
        raise AssertionError('readiness attempted a write or side effect')
    with patch.object(store, 'load', side_effect=forbidden), patch.object(store, 'commit', side_effect=forbidden), patch.object(store, 'history', side_effect=forbidden), patch.object(svc, 'tick', side_effect=forbidden), patch('app.active43.service.scheduler_configured', return_value=True):
        result = await inspect(svc)
    assert (store.state, store.events, store.revision) == before
    assert store.loads == 0
    await svc.close()
    return result


def test_empty_off_pass_and_no_disclosed_financial_or_private_fields():
    r = asyncio.run(snapshot())
    assert r['status'] == 'PASS' and r['read_confirmed']
    assert r['mode'] == 'OFF' and r['open_positions'] == r['pending_operations'] == 0
    assert not r['pending'] and not r['pending_exit'] and not r['data_recovery_armed']
    assert r['risk_guards'] == {'status': 'PASS', 'code': None}
    assert r['last_confirmed_read_at'] == 1800000030
    assert not {'balance', 'state', 'position', 'config', 'sha256', 'token', 'key', 'revision'} & r.keys()


@pytest.mark.parametrize('mode', ['ON', 'PAUSED', 'EMERGENCY'])
def test_other_modes_blocked(mode):
    store = SeedStore();store.state['mode'] = mode
    r = asyncio.run(snapshot(store))
    assert r['mode'] == mode and r['status'] == 'BLOCKED' and 'PAPER_NOT_OFF' in r['errors']


@pytest.mark.parametrize('field', ['pending_exit', 'data_recovery_armed', 'pending', 'position', 'mode'])
def test_missing_fields_never_implied_empty(field):
    store = SeedStore();del store.state[field]
    r = asyncio.run(snapshot(store))
    assert r['status'] == 'BLOCKED' and not r['read_confirmed'] and r['open_positions'] is None


@pytest.mark.parametrize('field,value', [('position', {}), ('position', False), ('pending', {}), ('pending', False), ('pending_exit', ''), ('data_recovery_armed', 0)])
def test_malformed_fields_fail_closed(field, value):
    store = SeedStore();store.state[field] = value
    assert asyncio.run(snapshot(store))['status'] == 'BLOCKED'


@pytest.mark.parametrize('change', [{'data_recovery_armed': True}, {'day_low_equity': '9700'}, {'max_drawdown_pct': '10'}])
def test_recovery_and_exact_saved_production_risk_guard(change):
    store = SeedStore();store.state.update(change)
    r = asyncio.run(snapshot(store))
    assert r['status'] == 'BLOCKED' and r['read_confirmed']
    assert r['risk_guards']['code'] == risk_reason(store.state)


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_pending_open_and_pending_exit_real_engine_state_unchanged(side):
    from tests.test_active43 import setup
    async def run():
        market, now, store, svc = setup(side)
        async def peek():
            return dict(state=deepcopy(store.state), revision=store.revision)
        store.peek = peek
        with patch('app.active43.service.scheduler_configured', return_value=True):
            await svc.control('START', 'a'*32, 1)
            market.add();now[0] += market.step;await svc.tick()
            pending = await inspect(svc)
            assert pending['pending'] and pending['pending_operations'] == 1
            market.add();now[0] += market.step;await svc.tick()
            await svc.control('STOP', 'b'*32)
            store.state['pending_exit'] = store.state['position']['id']
            before = deepcopy((store.state, store.events, store.revision))
            r = await inspect(svc)
        assert r['read_confirmed'] and r['status'] == 'BLOCKED'
        assert r['open_positions'] == 1 and r['pending_exit'] and not r['pending']
        assert (store.state, store.events, store.revision) == before
        await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('error', [DemoError('STORAGE_AUTH'), RuntimeError('PRIVATE_KEY_DO_NOT_LEAK'), TimeoutError()])
def test_read_errors_sanitized_and_no_fallback_write(error):
    async def run():
        store = SeedStore();svc = service(store)
        with patch.object(store, 'peek', side_effect=error):r = await inspect(svc)
        assert r['status'] == 'BLOCKED' and r['mode'] is None and not store.loads
        assert 'PRIVATE_KEY_DO_NOT_LEAK' not in str(r)
        await svc.close()
    asyncio.run(run())


def test_no_account_no_scheduler_disabled_and_concurrent_reads():
    async def run():
        store = SeedStore();svc = service(store)
        assert (await inspect(svc))['errors'] == ['SCHEDULER_ACCOUNT_NOT_INITIALIZED']
        store.exists = True
        with patch('app.active43.service.scheduler_configured', return_value=False):
            r = await inspect(svc)
        assert r['read_confirmed'] and r['status'] == 'BLOCKED'
        with patch('app.active43.service.scheduler_configured', return_value=True), patch.object(svc, 'ready', side_effect=DemoError('ACTIVE43_DISABLED')):
            r = await inspect(svc)
        assert r['mode'] == 'OFF' and r['status'] == 'BLOCKED'
        with patch('app.active43.service.scheduler_configured', return_value=True):
            results = await asyncio.gather(*[inspect(svc) for _ in range(10)])
        assert all(r['status'] == 'PASS' for r in results) and not store.loads and not store.events
        await svc.close()
    asyncio.run(run())


def test_owner_auth_required_before_read_and_no_mutation_methods(monkeypatch):
    password = 'DUMMY_OWNER_PASSWORD_READONLY'
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD', password)
    async def run():
        store = SeedStore();store.exists = True;svc = service(store)
        app = FastAPI();app.include_router(router);app.state.active43 = svc
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            path = '/api/active43/off-only-readiness'
            with patch.object(store, 'peek', wraps=store.peek) as peek:
                for kw in ({}, {'auth': ('aura', 'wrong')}, {'headers': {'X-Aura-Active43-Bitget-Token': 'DUMMY_TOKEN'}}):
                    assert (await c.get(path, **kw)).status_code == 401
                assert peek.call_count == 0
                with patch('app.active43.service.scheduler_configured', return_value=True):
                    r = await c.get(path, auth=('aura', password))
                assert r.status_code == 200 and r.json()['status'] == 'PASS'
                assert 'no-store' in r.headers['cache-control'] and peek.call_count == 1
                assert (await c.post(path, auth=('aura', password))).status_code == 405
            assert not store.loads and not store.events
        await svc.close()
    asyncio.run(run())
