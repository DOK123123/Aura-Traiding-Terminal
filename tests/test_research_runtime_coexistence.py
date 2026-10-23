"""Temporary-only Auto Paper cycle alongside read-only Research requests."""
import asyncio
from unittest.mock import patch
import unittest
import httpx
from app.research.service import Service as ResearchService
from tests import test_live_paper_monitor as monitor_fixtures


class ResearchCoexistence(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=monitor_fixtures.MonitorController.asyncSetUp
    asyncTearDown=monitor_fixtures.MonitorController.asyncTearDown
    auth=monitor_fixtures.MonitorController.auth
    add_bar=monitor_fixtures.MonitorController.add_bar
    start=monitor_fixtures.MonitorController.start
    open=monitor_fixtures.MonitorController.open
    close_position=monitor_fixtures.MonitorController.close_position
    async def test_research_viewer_does_not_mutate_or_block_paper_cycle(self):
        from app.main import app
        from app.research.api import instance
        before=dict(app.dependency_overrides)
        app.dependency_overrides[instance]=lambda:ResearchService(None)
        async def read_viewer():
            with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=monitor_fixtures.fixtures.DUMMY_OWNER):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid',auth=('aura',monitor_fixtures.fixtures.DUMMY_OWNER)) as c:
                    for _ in range(12):
                        assert (await c.get('/api/research')).status_code==200
                        assert (await c.get('/api/health')).status_code==200
                        await asyncio.sleep(0)
        async def paper_cycle():
            await self.open(); position=(await self.store.load())['state']['position'];assert position is not None
            await self.close_position(); monitor=await self.svc.live_monitor()
            assert monitor['last_close']['event_type']=='CLOSE_TP'
            assert monitor['status']=='WAITING_FOR_REAL_SIGNAL'
            assert not monitor['live_cycle_verified']
        try:
            with patch('app.research.experiment.execute',side_effect=AssertionError('RESEARCH_WEB_EXECUTE_FORBIDDEN')):
                await asyncio.wait_for(asyncio.gather(read_viewer(),paper_cycle()),timeout=15)
        finally:app.dependency_overrides.clear();app.dependency_overrides.update(before)
