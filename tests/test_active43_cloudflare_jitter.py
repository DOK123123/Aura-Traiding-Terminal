"""Cloudflare scheduledTime jitter regression: attribution only, no paper mutations."""
import asyncio
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.active43.api import router
from app.active43.service import Service

TOKEN = 'DUMMY_SCHEDULER_TOKEN_' + 'x' * 40
PATH = '/api/active43/tick'
BASE_MS = 1792876320000  # 2026-10-24 21:12:00 UTC, cron minute 12
INVOCATION = 'a' * 32


def test_cloudflare_scheduled_time_jitter_and_rejections(monkeypatch):
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET', TOKEN)
    async def run():
        service = Service(reason='ACTIVE43_DISABLED')
        app = FastAPI()
        app.include_router(router)
        app.state.active43 = service

        async def fake_tick():
            return {'status': 'COMPLETED', 'mode': 'OFF'}

        # Isolate attribution validation; no engine or database writes.
        with patch.object(service, 'tick', side_effect=fake_tick) as tick:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url='http://test'
            ) as client:
                def headers(ms):
                    return {
                        'X-Aura-Active43-Bitget-Token': TOKEN,
                        'X-Aura-Invocation-Id': INVOCATION,
                        'X-Aura-Scheduled-At': str(ms),
                    }
                # Exact Cloudflare observed jitter (+52.426s) is accepted.
                with patch.object(service, 'clock', return_value=(BASE_MS + 53000) / 1000):
                    response = await client.post(PATH, headers=headers(BASE_MS + 52426))
                    assert response.status_code == 200, response.text
                    # Incorrect cron slot (minute 11) remains rejected.
                    response = await client.post(PATH, headers=headers(BASE_MS - 60000))
                    assert response.status_code == 400
                    assert response.json()['detail'] == 'INVALID_SCHEDULE_ATTRIBUTION'
                # Old scheduled event remains rejected.
                with patch.object(service, 'clock', return_value=(BASE_MS + 400000) / 1000):
                    response = await client.post(PATH, headers=headers(BASE_MS + 52426))
                    assert response.status_code == 400
                assert tick.call_count == 1
        await service.close()
    asyncio.run(run())
