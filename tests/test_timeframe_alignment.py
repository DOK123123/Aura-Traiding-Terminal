"""Offline evidence checks. Synthetic cases never establish market performance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.automated.alignment import capture,present
from app.automated.api import router
from app.automated.engine import DemoError
from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.strategy import strategy,_evaluate
from app.intelligence.market_context import analyze_window
from app.lab.models import Bar
from research.market_intelligence.structure import segment_states
from scripts.replay_auto42_verification import PrefixCache,snapshot
from tests.test_auto42 import fixture,DUMMY_OWNER
from tests import test_auto42 as fixtures
from tests.test_market_context import csv_row
from tests.test_market_intelligence import bars


def enrich(value):
    """Explicit synthetic indicator evidence matching the fixture's directions."""
    state=value['state'];state['trend_indicators']=dict(ema20=102,ema50=100,adx14=30,atr14=1,rsi14=60,sample_count=300)
    value['alignment_inputs']={}
    for tf,key in [('1h','h1'),('4h','h4')]:
        side=state['mtf'][key]['direction']
        value['alignment_inputs'][tf]=dict(trend_indicators=dict(ema20=102 if side==1 else 98,ema50=100,adx14=30,atr14=1,rsi14=60,sample_count=260))
    return value


class AlignmentMath(unittest.TestCase):
    def test_linear_series_independent_ema_adx_atr_oracle(self):
        bs=[Bar(1577836800+i*900,D(100+i),D(101+i),D(99+i),D(100+i),D(10)) for i in range(300)]
        state=segment_states(bs)[-1];values=state['trend_indicators']
        self.assertAlmostEqual(values['ema20'],399-9.5,places=10)
        self.assertAlmostEqual(values['ema50'],399-24.5,places=10)
        self.assertAlmostEqual(values['adx14'],100,places=10)
        self.assertAlmostEqual(values['atr14'],2,places=10)
        self.assertAlmostEqual(values['rsi14'],100,places=10)
        self.assertEqual(state['trend_direction'],1)

    def test_legitimate_disagreement_and_aligned_gate_are_not_trade_commands(self):
        bs,s,now=fixture();enrich(s)
        d=strategy(s,bs,now[0]);self.assertEqual(d['timeframe_alignment']['verdict'],'VALID_ALIGNMENT_PASS')
        self.assertEqual({k:v for k,v in d.items() if k!='timeframe_alignment'},_evaluate(s,bs,now[0]))
        s['state']['mtf']['h1']['direction']=-1;s['state']['mtf']['alignment']=False;enrich(s)
        d=strategy(s,bs,now[0]);evidence=d['timeframe_alignment']
        self.assertEqual(d['reason'],'MTF_NOT_ALIGNED');self.assertIsNone(d['direction'])
        self.assertTrue(evidence['decision_valid']);self.assertEqual(evidence['detail'],'TREND_DISAGREEMENT')
        self.assertEqual(evidence['issues'],[])

    def test_flag_error_is_identified_without_changing_strategy(self):
        bs,s,now=fixture();enrich(s);s['state']['mtf']['alignment']=False
        d=strategy(s,bs,now[0]);self.assertEqual(d['reason'],'MTF_NOT_ALIGNED')
        self.assertFalse(d['timeframe_alignment']['decision_valid'])
        self.assertIn('ALIGNMENT_FLAG_MISMATCH',d['timeframe_alignment']['issues'])

    def test_missing_higher_and_stale_are_distinct_from_conflicting_trends(self):
        bs,s,now=fixture();enrich(s);s['state']['mtf']['h4']=None
        with self.assertRaisesRegex(DemoError,'MTF_UNAVAILABLE') as caught:strategy(s,bs,now[0])
        self.assertFalse(caught.exception.alignment_snapshot['alignment_evaluated'])
        s['freshness']['status']='STALE'
        with self.assertRaisesRegex(DemoError,'STALE_DATA') as caught:strategy(s,bs,now[0])
        self.assertFalse(caught.exception.alignment_snapshot['freshness']['fresh_at_evaluation'])
        self.assertIsNone(caught.exception.alignment_snapshot['decision_valid'])

    def test_no_legacy_snapshot_or_missing_indicators_can_claim_validity(self):
        self.assertEqual(present(None,123)['status'],'NOT_CAPTURED')
        bs,s,now=fixture();self.assertIsNone(strategy(s,bs,now[0])['timeframe_alignment']['decision_valid'])

    def test_capture_copies_inputs_and_does_not_leak_arbitrary_fields(self):
        bs,s,now=fixture();enrich(s);s['secret']='DUMMY_NOT_FOR_OUTPUT'
        d=strategy(s,bs,now[0]);e=d['timeframe_alignment'];old=deepcopy(e)
        s['state']['trend_indicators']['ema20']=999
        self.assertEqual(e,old);self.assertNotIn('DUMMY_NOT_FOR_OUTPUT',json.dumps(e))
        current=present(e,now[0]+900)
        self.assertFalse(current['current_data_fresh']);self.assertTrue(current['decision_valid'])


class AlignmentWindows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.bs=bars(4175)

    def test_every_boundary_uses_latest_complete_utc_block_and_no_future(self):
        cache=PrefixCache(self.bs)
        with cache.installed():
            for n in range(4160,4176):
                at=self.bs[n-1].time+900;s=snapshot(self.bs[:n],at)
                d=strategy(s,self.bs[:n],at+30)['timeframe_alignment']
                for tf,step in [('15m',900),('1h',3600),('4h',14400)]:
                    self.assertEqual(d['frames'][tf]['closed_at'],at//step*step)
                    self.assertLessEqual(d['frames'][tf]['closed_at'],at)
        with self.assertRaises(DemoError):strategy(snapshot(self.bs[:4160],self.bs[4159].time+900),self.bs[:4161],self.bs[4159].time+930)

    def test_native_replay_prefix_equivalence_and_future_perturbation(self):
        cache=PrefixCache(self.bs);at=self.bs[4160].time+900
        direct=snapshot(self.bs[:4161],at)
        with cache.installed():self.assertEqual(snapshot(self.bs[:4161],at),direct)
        altered=self.bs[:4161]+[replace(b,open=b.open*2,close=b.close*2,low=b.low*2,high=b.high*2) for b in self.bs[4161:]]
        with PrefixCache(altered).installed():self.assertEqual(snapshot(altered[:4161],at),direct)

    def test_gap_resets_warmup_and_never_creates_alignment(self):
        bs=self.bs[:4000]+self.bs[4001:];values=analyze_window(bs,bs[-1].time+930)
        self.assertEqual(values['15m']['status'],'INSUFFICIENT_HISTORY')
        self.assertIsNone(values['15m']['state'])

    def test_provider_excludes_forming_candle_and_close_at_exact_cutoff(self):
        from app.intelligence.market_context import fetch_window
        end=self.bs[-1].time+900
        async def page(q):
            xs=[b for b in self.bs if q['startTime']<=b.time*1000<=q['endTime']]
            result=[csv_row(b) for b in xs[:q['limit']]]
            return result
        got,info=asyncio.run(fetch_window(page,end+30))
        self.assertEqual(got[-1].time+900,end);self.assertTrue(info['complete'])


class AlignmentStorage(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.StoreServiceTests.asyncSetUp
    asyncTearDown=fixtures.StoreServiceTests.asyncTearDown
    auth=fixtures.StoreServiceTests.auth
    add_bar=fixtures.StoreServiceTests.add_bar
    async def test_saved_decision_read_only_restart_duplicate_and_no_orders(self):
        self.market.value['state']['mtf']['h1']['direction']=-1
        self.market.value['state']['mtf']['alignment']=False;enrich(self.market.value)
        with self.auth():await self.svc.control('START','a'*32)
        self.add_bar();await self.svc.tick();before=await self.store.load();journal=await self.store.history()
        evidence=await self.svc.alignment_dashboard()
        self.assertEqual(evidence['snapshot']['strategy_reason'],'MTF_NOT_ALIGNED')
        self.assertEqual(evidence['snapshot']['evaluated_closed_at'],before['state']['watermark'])
        for _ in range(3):await self.svc.alignment_dashboard()
        self.assertEqual(before,await self.store.load());self.assertEqual(journal,await self.store.history())
        fresh=Service(None,SQLiteStore(self.path),clock=lambda:self.now[0])
        self.assertEqual((await fresh.alignment_dashboard())['snapshot'],evidence['snapshot'])
        await fresh.close();await asyncio.gather(self.svc.tick(),self.svc.tick())
        self.assertEqual(before,await self.store.load())
        self.assertEqual(sum(e['kind'] in ('OPEN','CLOSE') for e in journal),0)
        self.assertEqual(before['state']['balance'],'10000');self.assertIsNone(before['state']['pending'])

    async def test_endpoint_owner_auth_no_market_or_writes_and_no_csrf_needed_for_get(self):
        app=FastAPI();app.state.auto42=self.svc;app.include_router(router)
        before=await self.store.load();self.market.snapshot=lambda _:self.fail('Diagnostic fetched market')
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                self.assertEqual((await c.get('/api/auto42/alignment')).status_code,401)
                r=await c.get('/api/auto42/alignment',auth=('aura',DUMMY_OWNER))
                self.assertEqual(r.status_code,200);self.assertEqual(r.json()['status'],'NOT_CAPTURED')
                self.assertIn('no-store',r.headers['cache-control'])
        self.assertEqual(before,await self.store.load());self.assertEqual(self.market.reads,0)
