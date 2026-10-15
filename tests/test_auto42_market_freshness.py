"""Synthetic fixtures verify safety, never historical performance."""
import unittest
from unittest.mock import patch
from copy import deepcopy
from app.intelligence.market_context import MarketContext,unavailable,STEPS
from app.automated.service import Service
from app.automated.market_data import snapshot_for_auto
from app.automated.engine import DemoError
from tests.test_auto42 import fixture,Market

class FreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_upstream_and_analysis_errors_are_not_masked_as_stale(self):
        bars,snap,now=fixture();market=Market(bars,snap);svc=Service(market,clock=lambda:now[0])
        for code in ('UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','NETWORK_ERROR','RATE_LIMIT','INVALID_CLOSE_TIME'):
            market.value['status']=code
            with self.assertRaises(DemoError) as raised:await svc.snapshot()
            self.assertEqual(raised.exception.code,code)
            self.assertEqual(svc.market_diagnostics['market_status'],code)
            self.assertEqual(svc.market_diagnostics['expected_closed_at'],now[0]//900*900)
            self.assertEqual(svc.market_diagnostics['last_closed_at'],snap['last_closed_at'])

    async def test_stale_stays_blocked(self):
        bars,snap,now=fixture();market=Market(bars,snap);market.value['status']='STALE'
        svc=Service(market,clock=lambda:now[0])
        with self.assertRaises(DemoError) as raised:await svc.snapshot()
        self.assertEqual(raised.exception.code,'STALE_DATA')
        self.assertEqual(svc.market_diagnostics['error_source'],'FRESHNESS')

    async def test_new_close_invalidates_young_cache_once_not_every_request(self):
        bars,_,_=fixture();boundary=bars[-1].time+900;clock=[boundary-1];mono=[0]
        svc=MarketContext(None,clock=lambda:clock[0],monotonic=lambda:mono[0])
        def analyze(bs,now,*args):
            values={}
            for tf,step in STEPS.items():
                v=unavailable();v.update(status='OK',last_closed_at=(int(now)//step)*step,
                    history={'window_end_exclusive':int(now)//900*900})
                values[tf]=v
            return values
        with patch('app.intelligence.market_context.fetch_window',return_value=(bars[:-1],{})) as fetch,patch('app.intelligence.market_context.analyze_with_analogs',side_effect=analyze):
            before=await snapshot_for_auto(svc);self.assertEqual(fetch.call_count,1)
            clock[0]=boundary+1;mono[0]=2;fetch.return_value=(bars,{})
            after=await snapshot_for_auto(svc)
            self.assertEqual(fetch.call_count,2);self.assertEqual(after['last_closed_at'],boundary)
            self.assertEqual(after['freshness']['status'],'FRESH')
            await snapshot_for_auto(svc);self.assertEqual(fetch.call_count,2)
        await svc.close()

    async def test_boundary_failure_honors_cooldown_and_retry_ttl(self):
        bars,_,_=fixture();boundary=bars[-1].time+900;clock=[boundary+1];mono=[2]
        svc=MarketContext(None,clock=lambda:clock[0],monotonic=lambda:mono[0]);svc.at=0;svc.cache={'15m':dict(unavailable(),status='OK',last_closed_at=boundary-900)}
        with patch('app.intelligence.market_context.fetch_window',side_effect=TimeoutError()) as fetch:
            v=await snapshot_for_auto(svc);self.assertEqual(v['status'],'UPSTREAM_TIMEOUT')
            await snapshot_for_auto(svc);self.assertEqual(fetch.call_count,1)
            mono[0]=33;await snapshot_for_auto(svc);self.assertEqual(fetch.call_count,2)
            svc.cooldown_until=100;clock[0]+=900;mono[0]=34
            await snapshot_for_auto(svc);self.assertEqual(fetch.call_count,2)
        await svc.close()

    async def test_timeout_diagnostics_persist_and_restart_recovers_without_duplicate_entry(self):
        import tempfile
        from pathlib import Path
        from app.automated.storage import SQLiteStore
        from tests.test_auto42 import DUMMY_TOKEN,DUMMY_OWNER
        bars,snap,now=fixture();market=Market(bars,snap)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'auto-paper-42.sqlite3';store=SQLiteStore(path,clock=lambda:now[0]);svc=Service(market,store,clock=lambda:now[0])
            with patch.dict('os.environ',AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN,AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
                await svc.control('START','a'*32)
            before=(await store.load())['state'];market.value['status']='UPSTREAM_TIMEOUT'
            result=await svc.tick();self.assertEqual(result['decision'],'UPSTREAM_TIMEOUT')
            failed=(await store.load())['state'];self.assertEqual(failed['watermark'],before['watermark']);self.assertTrue(failed['data_recovery_armed'])
            errors=[e for e in await store.history() if e['kind']=='ERROR']
            self.assertEqual(errors[0]['payload']['market']['error_source'],'UPSTREAM')
            self.assertEqual(errors[0]['payload']['market']['expected_closed_at'],now[0]//900*900)
            self.assertTrue((await svc.tick())['duplicate']);self.assertIsNone(failed['position'])
            await svc.close();now[0]+=300;market.value['status']='OK'
            restart=Service(market,SQLiteStore(path,clock=lambda:now[0]),clock=lambda:now[0])
            recovered=await restart.tick();self.assertEqual(recovered['mode'],'ON');self.assertEqual(recovered['opened_positions'],0)
            self.assertTrue((await restart.tick())['duplicate']);await restart.close()

    async def test_scheduler_preserves_safe_market_failure_code(self):
        from scripts.auto42_scheduler import safe_code
        for code in ('UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','NETWORK_ERROR','INVALID_CLOSE_TIME','RATE_LIMIT'):
            self.assertEqual(safe_code(code),code)
        self.assertEqual(safe_code('dummy-sensitive-message'),'UNCLASSIFIED_SERVER_ERROR')
