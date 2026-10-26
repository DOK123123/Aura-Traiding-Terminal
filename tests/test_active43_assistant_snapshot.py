"""Assistant snapshot is owner-only, read-only, non-trading and bounded."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from app.active43.api import router
from tests.test_active43_paper_readiness import prepare

OWNER_PASSWORD = 'DUMMY_ASSISTANT_OWNER_PASSWORD'
SHA = 'e' * 40


def test_assistant_snapshot_owner_only_no_mutations(monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD', OWNER_PASSWORD)
    monkeypatch.setenv('RENDER_GIT_COMMIT', SHA)

    async def run():
        market, now, store, svc = prepare()
        app = FastAPI()
        app.include_router(router)
        app.state.active43 = svc
        before = deepcopy((store.state, store.events, store.revision))
        forbidden = AsyncMock(side_effect=AssertionError('MUTATION_NOT_ALLOWED'))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://test'
        ) as client:
            with patch.object(store, 'peek', forbidden) as peek:
                response = await client.get('/api/active43/assistant-snapshot')
                assert response.status_code == 401
                peek.assert_not_awaited()
            with patch.object(store, 'load', forbidden), patch.object(
                store, 'commit', forbidden
            ), patch.object(svc, 'tick', forbidden), patch.object(
                svc, 'control', forbidden
            ), patch.object(svc, 'snapshot', forbidden):
                response = await client.get(
                    '/api/active43/assistant-snapshot',
                    auth=('aura', OWNER_PASSWORD),
                )
            assert response.status_code == 200, response.text
            assert 'no-store' in response.headers['cache-control']
            data = response.json()
            assert data['status'] == 'PASS', data
            assert data['account']['mode'] == 'OFF'
            assert data['account']['balance'] == '10000'
            assert data['read_only'] and not data['state_changed']
            assert not data['trading_control_available']
            assert not data['market_data_verified']
            assert not data['signal_verified']
            assert not data['production_paper_verified']
            assert data['readiness_scope'] == 'ACCOUNT_AND_SCHEDULE_ONLY'
            assert data['render_commit'] == SHA
            assert not any('ledger_sha256' in str(k) for k in data)
            assert before == (store.state, store.events, store.revision)
            forbidden.assert_not_awaited()
            await svc.readiness_lock.acquire()
            try:
                response = await client.get(
                    '/api/active43/assistant-snapshot',
                    auth=('aura', OWNER_PASSWORD),
                )
                assert response.json()['errors'] == ['READINESS_BUSY']
                assert response.json()['status'] == 'BLOCKED'
            finally:
                svc.readiness_lock.release()
        await svc.close()

    asyncio.run(run())


def test_assistant_snapshot_without_service_blocks(monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD', OWNER_PASSWORD)

    async def run():
        app = FastAPI()
        app.include_router(router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://test'
        ) as client:
            response = await client.get(
                '/api/active43/assistant-snapshot',
                auth=('aura', OWNER_PASSWORD),
            )
            assert response.status_code == 200
            assert response.json()['status'] == 'BLOCKED'
            assert response.json()['errors'] == ['ACTIVE43_NOT_CONFIGURED']
    asyncio.run(run())
