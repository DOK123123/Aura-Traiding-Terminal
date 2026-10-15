"""Offline START timeout regressions; no production controls or real prices."""
import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import httpx
from fastapi import FastAPI
from app.automated.api import router
from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.market_data import snapshot_for_auto
from app.intelligence.market_context import MarketContext
from tests.test_auto42 import fixture,Market,DUMMY_OWNER,DUMMY_TOKEN

class StartTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_analysis_keeps_off_and_diagnostics_then_valid_start_persists(self):
        bars,snap,now=fixture();market=Market(bars,snap)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'auto-paper-42.sqlite3';store=SQLiteStore(path,clock=lambda:now[0]);svc=Service(market,store,clock=lambda:now[0])
            app=FastAPI();app.state.auto42=svc;app.include_router(router)
            with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER,AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    before=await store.load();market.value['status']='ANALYSIS_TIMEOUT'
                    r=await client.post('/api/auto42/control',auth=('aura',DUMMY_OWNER),headers={'X-Aura-Paper':'local-only'},json={'action':'START','request_id':'a'*32,'confirmation':'START PAPER','expected_revision':before['revision']})
                    self.assertEqual(r.status_code,503);v=r.json()
                    self.assertEqual(v['state']['mode'],'OFF');self.assertEqual(v['state']['balance'],'10000');self.assertFalse(v['fresh'])
                    self.assertEqual(v['diagnostics']['last_saved_at'],before['last_saved_at']);self.assertEqual(v['diagnostics']['owner_mode'],'OFF');self.assertEqual(v['diagnostics']['market']['market_status'],'ANALYSIS_TIMEOUT')
                    self.assertEqual(await store.load(),before)
                    refreshed=(await client.get('/api/auto42/status',auth=('aura',DUMMY_OWNER))).json()
                    self.assertEqual(refreshed['state']['mode'],'OFF');self.assertEqual(refreshed['diagnostics']['activation_error']['code'],'ANALYSIS_TIMEOUT')
                    market.value['status']='OK'
                    r=await client.post('/api/auto42/control',auth=('aura',DUMMY_OWNER),headers={'X-Aura-Paper':'local-only'},json={'action':'START','request_id':'b'*32,'confirmation':'START PAPER','expected_revision':before['revision']})
                    self.assertEqual(r.status_code,200);self.assertEqual(r.json()['state']['mode'],'ON')
                    await svc.tick();self.assertEqual((await svc.dashboard())['state']['mode'],'ON')
                    await svc.close();restart=Service(market,SQLiteStore(path,clock=lambda:now[0]),clock=lambda:now[0])
                    self.assertEqual((await restart.dashboard())['state']['mode'],'ON');self.assertIsNone((await restart.dashboard())['diagnostics']['activation_error']);await restart.close()

    async def test_pending_shared_analysis_is_awaited_once_without_new_refresh(self):
        m=MarketContext(None);release=asyncio.Event()
        async def work():await release.wait()
        m.task=asyncio.create_task(work());m.snapshot=AsyncMock(side_effect=[{'status':'ANALYSIS_TIMEOUT'},{'status':'OK'}])
        asyncio.get_running_loop().call_soon(release.set)
        result=await snapshot_for_auto(m)
        self.assertEqual(result['status'],'OK');self.assertEqual(m.snapshot.await_count,2);await m.close()

    async def test_worker_failure_is_not_retried_or_promoted_to_success(self):
        m=MarketContext(None)
        async def done():pass
        m.task=asyncio.create_task(done());await m.task
        m.snapshot=AsyncMock(return_value={'status':'ANALYSIS_TIMEOUT'})
        result=await snapshot_for_auto(m)
        self.assertEqual(result['status'],'ANALYSIS_TIMEOUT');self.assertEqual(m.snapshot.await_count,1);await m.close()

    async def test_wait_budget_remains_bounded_and_does_not_cancel_shared_task(self):
        m=MarketContext(None)
        async def pending():await asyncio.Event().wait()
        m.task=asyncio.create_task(pending());m.snapshot=AsyncMock(return_value={'status':'ANALYSIS_TIMEOUT'})
        with patch('app.automated.market_data.asyncio.wait_for',side_effect=TimeoutError()):
            result=await snapshot_for_auto(m)
        self.assertEqual(result['status'],'ANALYSIS_TIMEOUT');self.assertFalse(m.task.cancelled());self.assertEqual(m.snapshot.await_count,1);await m.close()
