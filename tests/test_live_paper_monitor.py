"""Offline controller tests. Render/Supabase labels below are SIMULATED ONLY."""
import asyncio
from copy import deepcopy
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.automated.api import router
from app.automated.engine import DemoError
from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.live_monitor import monitor_view,position_view,observe_tick,origin
from app.automated import live_evidence
from app.lab.models import digest,canonical
from tests import test_auto42 as fixtures


class SimulatedSupabase(SQLiteStore):
    """Still TEMPORARY SQLITE. Tests verification predicates; never a live proof."""
    backend='SUPABASE_POSTGRES';durable=True


class MonitorController(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.StoreServiceTests.asyncSetUp
    asyncTearDown=fixtures.StoreServiceTests.asyncTearDown
    auth=fixtures.StoreServiceTests.auth
    add_bar=fixtures.StoreServiceTests.add_bar

    async def start(self,production_labels=False):
        if production_labels:
            self.store.backend='SUPABASE_POSTGRES';self.store.durable=True
        with self.auth():await self.svc.control('START','a'*32)

    async def open(self):
        await self.start();self.add_bar();await self.svc.tick();self.add_bar();await self.svc.tick()
        self.assertIsNotNone((await self.store.load())['state']['position'])

    async def close_position(self,kind='TP'):
        s=(await self.store.load())['state'];p=s['position'];self.add_bar();self.market.value['state']['retest']=None
        b=self.bs[-1]
        self.bs[-1]=fixtures.bar(b.time,high=str(D(p['take_profit'])+1) if kind=='TP' else '101',
            low=str(D(p['stop_loss'])-1) if kind=='SL' else '99')
        self.market.value['history']['source_sha256']=digest([b.data() for b in self.bs])
        await self.svc.tick()

    async def test_offline_cycle_never_verifies_live_and_captures_signal_open_close(self):
        await self.open();await self.close_position();result=await self.svc.live_monitor()
        self.assertEqual(result['status'],'WAITING_FOR_REAL_SIGNAL');self.assertFalse(result['live_cycle_verified'])
        self.assertEqual(result['last_close']['event_type'],'CLOSE_TP')
        self.assertEqual(result['last_open']['position_id'],result['last_close']['position_id'])
        self.assertEqual(result['last_open']['signal']['event_type'],'SIGNAL')
        for e in result['events']:
            for key in ('utc_timestamp','position_id','scheduler_run_id','candle_id','reason','source'):self.assertIn(key,e)
            self.assertTrue(e['scheduler_run_id']);self.assertTrue(e['candle_id']);self.assertNotIn('TEST_PASS',e['event_type'])
        self.assertLess(len(canonical((await self.store.load())['state'])),65536)

    async def test_simulated_production_requires_complete_matching_signal_open_close(self):
        with patch.dict('os.environ',RENDER='true',RENDER_GIT_COMMIT='a'*40):
            await self.start(production_labels=True);self.add_bar();await self.svc.tick()
            self.assertFalse((await self.svc.live_monitor())['live_cycle_verified'])
            self.add_bar();await self.svc.tick()
            self.assertEqual((await self.svc.live_monitor())['reason'],'WAITING_FOR_CLOSE')
            await self.close_position();result=await self.svc.live_monitor()
        self.assertEqual(result['status'],'VERIFIED')  # Simulated evidence predicate only.
        self.assertEqual(result['verified_cycle']['open']['position_id'],result['verified_cycle']['close']['position_id'])

    async def test_legacy_trade_counts_and_legacy_open_cannot_verify(self):
        await self.open();env=await self.store.load();s=env['state'];s.pop('live_paper_monitor',None)
        event=fixtures.bar  # No production calls; remove only temporary test telemetry.
        from app.automated.engine import event as make_event
        row=make_event(s,'TEST_ONLY_LEGACY',1,self.now[0],dict(reason='TEST_ONLY'))
        await self.store.commit(env['revision'],s,[row],row['id'])
        self.store.backend='SUPABASE_POSTGRES';self.store.durable=True
        with patch.dict('os.environ',RENDER='true',RENDER_GIT_COMMIT='a'*40):await self.close_position()
        self.assertEqual((await self.svc.live_monitor())['status'],'WAITING_FOR_REAL_SIGNAL')

    async def test_duplicate_and_concurrent_ticks_never_duplicate_monitor_open(self):
        await self.start();self.add_bar();await self.svc.tick();self.add_bar()
        other=Service(self.market,SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0])
        try:await asyncio.gather(self.svc.tick(),other.tick(),self.svc.tick())
        finally:await other.close()
        rows=await self.store.history(limit=200)
        self.assertEqual(sum(e['kind']=='OPEN' for e in rows),1)
        self.assertEqual(sum(e['kind']=='LIVE_MONITOR' and e['payload']['event_type']=='OPEN' for e in rows),1)

    async def test_restart_recovers_position_and_monitor_then_sl_closes_once(self):
        await self.open();before=await self.svc.live_monitor();await self.svc.close()
        self.store=SQLiteStore(self.path,clock=lambda:self.now[0]);self.svc=Service(self.market,self.store,clock=lambda:self.now[0])
        self.assertEqual((await self.svc.live_monitor())['last_open'],before['last_open'])
        self.assertEqual((await self.svc.live_monitor())['position'],before['position'])
        await self.close_position('SL');await self.svc.tick();result=await self.svc.live_monitor()
        self.assertEqual(result['last_close']['event_type'],'CLOSE_SL');self.assertIsNone(result['position'])
        self.assertEqual(sum(e['kind']=='CLOSE' for e in await self.store.history(limit=200)),1)

    async def test_reads_with_open_position_and_crossed_target_cannot_close_trade(self):
        await self.open();self.add_bar();p=(await self.store.load())['state']['position']
        self.bs[-1]=fixtures.bar(self.bs[-1].time,high=str(D(p['take_profit'])+1))
        before=await self.store.load();history=await self.store.history(limit=200)
        def forbidden(*a,**k):raise AssertionError('Diagnostic tried execution')
        with patch.object(self.svc,'snapshot',side_effect=forbidden),patch.object(self.svc,'tick',side_effect=forbidden),patch.object(self.store,'commit',side_effect=forbidden):
            await asyncio.gather(*[self.svc.live_monitor() for _ in range(5)])
        self.assertEqual(before,await self.store.load());self.assertEqual(history,await self.store.history(limit=200))

    async def test_stale_data_error_persisted_and_never_mislabelled_waiting(self):
        await self.start();self.market.value['freshness']['status']='STALE';self.now[0]+=300
        await self.svc.tick();result=await self.svc.live_monitor()
        self.assertEqual(result['status'],'FAILED');self.assertEqual(result['last_error'],'STALE_DATA')
        self.assertTrue(any(e['event_type']=='ERROR' for e in result['events']))
        self.assertEqual(result['balance'],'10000')

    async def test_capture_failure_does_not_block_actual_open_and_reports_failed_monitor(self):
        await self.start();self.add_bar();await self.svc.tick();self.add_bar()
        with patch('app.automated.live_monitor.observe_tick',side_effect=RuntimeError('DUMMY_PRIVATE_ERROR_NOT_FOR_OUTPUT')):
            await self.svc.tick()
        result=await self.svc.live_monitor();self.assertIsNotNone(result['position'])
        self.assertEqual(result['status'],'FAILED');self.assertEqual(result['reason'],'MONITOR_CAPTURE_FAILED')
        self.assertNotIn('DUMMY_PRIVATE_ERROR_NOT_FOR_OUTPUT',json.dumps(result))

    async def test_failed_commit_has_no_partial_monitor_events_or_financial_changes(self):
        await self.start();self.add_bar();before=await self.store.load();rows=await self.store.history(limit=200)
        with patch.object(self.store,'commit',side_effect=DemoError('STORAGE_TIMEOUT')):
            with self.assertRaisesRegex(DemoError,'STORAGE_TIMEOUT'):await self.svc.tick()
        self.assertEqual(before,await self.store.load());self.assertEqual(rows,await self.store.history(limit=200))
        result=await self.svc.live_monitor();self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['storage']['last_write_error_in_this_process'],'STORAGE_TIMEOUT')

    async def test_liquidation_pnl_has_entry_fee_and_stale_marks_are_hidden(self):
        await self.open();s=(await self.store.load())['state'];result=await self.svc.live_monitor()
        expected=D(s['equity'])-D(s['balance'])-D(s['position']['entry_fee'])
        self.assertEqual(D(result['position']['net_pnl_including_entry_fee']),expected)
        self.now[0]+=901;stale=await self.svc.live_monitor()
        self.assertIsNone(stale['position']['net_pnl_including_entry_fee']);self.assertIsNotNone(stale['position']['last_known_net_pnl'])

    async def test_owner_auth_and_cursor_history_read_only(self):
        await self.start();self.add_bar();await self.svc.tick();before=await self.store.load()
        app=FastAPI();app.state.auto42=self.svc;app.include_router(router)
        with self.auth():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                for url in ('/api/auto42/live-monitor','/api/auto42/live-monitor/events'):
                    self.assertEqual((await c.get(url)).status_code,401)
                    r=await c.get(url,auth=('aura',fixtures.DUMMY_OWNER));self.assertEqual(r.status_code,200)
                    self.assertIn('no-store',r.headers['cache-control'])
                r=await c.get('/api/auto42/live-monitor/events?limit=1',auth=('aura',fixtures.DUMMY_OWNER))
                self.assertTrue(r.json()['page_may_have_more']);self.assertGreater(r.json()['next_cursor'],0)
                self.assertEqual((await c.get('/api/auto42/live-monitor/events?limit=201',auth=('aura',fixtures.DUMMY_OWNER))).status_code,422)
        self.assertEqual(before,await self.store.load())


class TechnicalEvidence(unittest.TestCase):
    def test_missing_tampered_and_wrong_code_artifacts_never_live_verify(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'proof.json'
            with patch.object(live_evidence,'REPORT',p):
                self.assertEqual(live_evidence.evidence()['status'],'NOT_TESTED')
                value=dict(status='PASS',test_only=True,code_hashes=live_evidence.code_hashes())
                value['checksum']=digest(value);p.write_bytes(canonical(value))
                self.assertEqual(live_evidence.evidence()['status'],'PASS');self.assertFalse(live_evidence.evidence()['proves_live_autonomy'])
                value['status']='FAIL';p.write_bytes(canonical(value));self.assertEqual(live_evidence.evidence()['status'],'NOT_TESTED')
                value['code_hashes']['app/automated/service.py']='wrong';value.pop('checksum');value['checksum']=digest(value);p.write_bytes(canonical(value))
                self.assertEqual(live_evidence.evidence()['status'],'NOT_TESTED')
