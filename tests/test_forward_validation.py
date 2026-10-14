"""All market fixtures and secrets are synthetic; no live collection/trading claim."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import io,json,logging,os,sqlite3,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from app.forward.models import record,verify,realized,frame,ForwardError
from app.forward.storage import SQLiteStore,SupabaseStore
from app.forward.service import Service,configured
from app.forward.api import router
from app.forward.stats import score,aggregate,summarize
from app.intelligence.analogs import AnalogIndex
from app.intelligence.market_context import MarketContext,analyze_window,analyze_with_analogs
from app.lab.models import digest
from tests.test_historical_analogs import pack
from tests.test_market_intelligence import bars

DUMMY_SCHEDULER='dummy-scheduler-secret-unit-tests-only-0000'
DUMMY_KEY='dummy-supabase-key-unit-tests-only-0000'


def market_fixture(forecast=False):
    bs=bars(4160);clock=[bs[-1].time+950];p=pack()
    if forecast:
        row=analyze_window(bs,clock[0])['15m']['state']
        for r in p['states']:
            for key in ('vector','regime','trend_direction','high_leg','low_leg','structure_known_mask','relative_volume'):
                r[key]=deepcopy(row[key])
            r['mtf']=dict(known_mask=row['mtf']['known_mask'],h1=dict(direction=row['vector'][18],closed_at=r['timestamp']//3600*3600),h4=dict(direction=row['vector'][19],closed_at=r['timestamp']//14400*14400))
        p['content_sha256']=digest({k:v for k,v in p.items() if k!='content_sha256'})
    index=AnalogIndex(p);market=MarketContext(None,clock=lambda:clock[0],analog_index=index)
    refresh_fixture(market,bs,clock)
    return market,bs,clock


def refresh_fixture(market,bs,clock):
    market.bars=bs;market.cache=analyze_with_analogs(bs,clock[0],{},market.analog_index,None)
    for v in market.cache.values():v['fetched_at']=clock[0]
    market.at=market.monotonic();market.last_good=deepcopy(market.cache)


class ForwardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.market,self.bs,self.clock=market_fixture()
        self.path=Path(self.folder.name)/'forward-validation.sqlite3'
        self.store=SQLiteStore(self.path,clock=lambda:self.clock[0]);self.svc=Service(self.market,self.store,clock=lambda:self.clock[0])
    async def asyncTearDown(self):
        await self.svc.close();await self.market.close();self.folder.cleanup()

    async def test_capture_before_outcomes_no_trading_and_scheduler_idempotency(self):
        results=await asyncio.gather(self.svc.tick(),self.svc.tick())
        self.assertEqual(results[0],results[1])
        status=await self.store.status();self.assertEqual(status['counts']['PRED'],3)
        replay=await self.svc.tick();self.assertTrue(replay['replayed'])
        self.assertEqual((await self.store.status())['counts']['PRED'],3)
        for r in await self.store.read(mode='recent'):
            if r['kind']=='PRED':
                p=verify(r);self.assertLess(p['created_at_ms'],(p['closed_at']+4*{'15m':900,'1h':3600,'4h':14400}[p['timeframe']])*1000)
                self.assertFalse(p['execution_enabled']);self.assertEqual(p['status'],'ABSTAINED')

    async def test_restart_recovers_and_never_duplicates_same_candle(self):
        await self.svc.tick();new=Service(self.market,SQLiteStore(self.path,clock=lambda:self.clock[0]),clock=lambda:self.clock[0])
        self.assertTrue((await new.tick())['replayed'])
        self.assertEqual((await new.store.status())['counts']['PRED'],3);await new.close()

    async def test_stale_feed_cannot_backfill(self):
        for v in self.market.cache.values():v['status']='STALE'
        result=await self.svc.tick()
        self.assertEqual(result['status'],'DATA_UNAVAILABLE')
        self.assertEqual((await self.store.status())['counts'].get('PRED',0),0)

    async def test_immutable_prediction_corrections_and_no_delete(self):
        await self.svc.tick();rows=await self.store.read(mode='recent');old=next(r for r in rows if r['kind']=='PRED')
        payload=verify(old);payload['fingerprint']='changed-source-fingerprint'
        incoming=record('PRED',old['id'],payload,old['created_ms'],old['cohort'],old['tf'],old['closed_at'])
        result=await self.store.append([incoming]);self.assertEqual(result['corrections'],1)
        result=await self.store.append([incoming]);self.assertEqual(result['corrections'],0)
        with sqlite3.connect(self.path) as conn:
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('delete from forward_records')
            with self.assertRaises(sqlite3.IntegrityError):conn.execute("update forward_records set payload='{}'")
        original=next(r for r in await self.store.read(mode='recent') if r['id']==old['id'])
        self.assertEqual(original['sha256'],old['sha256'])
        self.assertEqual(summarize(await self.store.read(mode='recent'))['corrected_predictions'],1)

    async def test_creation_storage_rejects_future_and_retroactive(self):
        await self.svc.tick();old=next(r for r in await self.store.read(mode='recent') if r['kind']=='PRED');p=verify(old)
        for delta in (-86400,86400):
            bad=deepcopy(p);bad['id']='invalid:'+str(delta);at=old['closed_at']+delta;bad['closed_at']=at
            incoming=record('PRED',bad['id'],bad,old['created_ms'],old['cohort'],old['tf'],at)
            with self.assertRaises(ForwardError):await self.store.append([incoming])
        self.assertEqual((await self.store.status())['counts']['PRED'],3)

    async def test_cohort_changes_are_separate_and_old_predictions_preserved(self):
        await self.svc.tick();old=self.svc.cohort
        self.svc.policy_hash='new-policy-version'
        self.assertNotEqual(old,self.svc.cohort)
        # New policy can capture at a later scheduler slot before the next candle.
        self.clock[0]+=300;refresh_fixture(self.market,self.bs,self.clock)
        await self.svc.tick()
        rows=[r for r in await self.store.read(mode='recent') if r['kind']=='PRED']
        self.assertEqual(len(rows),6);self.assertEqual(len({r['cohort'] for r in rows}),2)

    async def test_end_to_end_forecast_mature_horizons_and_scoring(self):
        market,bs,clock=market_fixture(forecast=True)
        store=SQLiteStore(Path(self.folder.name)/'other'/'forward-validation.sqlite3',clock=lambda:clock[0])
        svc=Service(market,store,clock=lambda:clock[0])
        try:
            await svc.tick();first=next(r for r in await store.read(mode='recent') if r['kind']=='PRED' and r['tf']=='15m')
            self.assertEqual(verify(first)['status'],'FORECAST')
            extended=bars(4192);clock[0]=extended[-1].time+950;refresh_fixture(market,extended[32:],clock)
            result=await svc.tick();self.assertGreaterEqual(result['evaluated_outcomes'],4)
            rows=await store.read(mode='recent');outs=[verify(r) for r in rows if r['kind']=='OUTCOME' and r['ref']==first['id']]
            self.assertEqual({o['horizon'] for o in outs},{4,8,16,32})
            self.assertTrue(all(o['quality']=='COMPLETE' for o in outs))
            stats=summarize(rows);self.assertTrue(any(g['scores']['aura']['count'] for g in stats['groups']))
            self.assertTrue(all(g['confidence_intervals'] is None for g in stats['groups']))
        finally:await svc.close();await market.close()

    async def test_export_cursor_and_hash_integrity(self):
        await self.svc.tick();status=await self.store.status();all_rows=[];cursor=0
        while True:
            batch=await self.store.read(mode='export',after=cursor,limit=2,through=status['max_seq'])
            if not batch:break
            all_rows.extend(batch);cursor=batch[-1]['seq']
        self.assertEqual(len(all_rows),status['total_rows'])
        corrupt=deepcopy(all_rows[0]);corrupt['payload']='{}'
        with self.assertRaises(ForwardError):verify(corrupt)

    async def test_authentication_scheduler_separation_and_no_browser_token(self):
        app=FastAPI();app.include_router(router);app.state.forward_validation=self.svc
        with patch.dict(os.environ,{'AURA_TESTNET_VIEW_PASSWORD':'dummy-owner-password','AURA_FORWARD_SCHEDULER_SECRET':DUMMY_SCHEDULER}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                self.assertEqual((await c.get('/api/intelligence/forward/status')).status_code,401)
                self.assertEqual((await c.post('/api/intelligence/forward/tick',auth=('aura','dummy-owner-password'))).status_code,401)
                headers={'X-Aura-Forward-Token':DUMMY_SCHEDULER}
                self.assertEqual((await c.post('/api/intelligence/forward/tick',headers=dict(headers,Origin='https://evil.invalid'))).status_code,401)
                self.assertEqual((await c.post('/api/intelligence/forward/tick',headers=headers)).status_code,200)
                c.auth=('aura','dummy-owner-password');r=await c.get('/api/intelligence/forward/status')
                self.assertEqual(r.status_code,200);self.assertNotIn(DUMMY_SCHEDULER,r.text)
                self.assertEqual((await c.get('/api/intelligence/forward/export?limit=2')).status_code,200)
                self.assertEqual((await c.get('/api/intelligence/forward/export?format=csv')).status_code,200)

    async def test_concurrent_instances_have_one_immutable_prediction(self):
        other=Service(self.market,SQLiteStore(self.path,clock=lambda:self.clock[0]),clock=lambda:self.clock[0])
        try:
            await asyncio.gather(self.svc.tick(),other.tick())
            self.assertEqual((await self.store.status())['counts']['PRED'],3)
        finally:await other.close()

    async def test_missed_capture_detection_does_not_backfill(self):
        await self.svc.tick();self.clock[0]+=1800
        extended=bars(4162);refresh_fixture(self.market,extended,self.clock)
        await self.svc.tick();status=await self.store.status(self.svc.cohort)
        self.assertEqual(status['counts']['PRED'],4)
        self.assertGreaterEqual(status['missed_closed_candles'],1)
        self.assertGreaterEqual(status['missed_runs'],5)

    async def test_atomic_batch_rolls_back_on_invalid_prediction(self):
        v=await self.market.snapshot('15m');r=self.svc.prediction(v,self.bs,int(self.clock[0]*1000))
        p=verify(r);p['id']='invalid-batch';p['closed_at']+=900
        invalid=record('PRED',p['id'],p,r['created_ms'],r['cohort'],'15m',p['closed_at'])
        with self.assertRaises(ForwardError):await self.store.append([r,invalid])
        self.assertEqual((await self.store.status())['counts'].get('PRED',0),0)

    async def test_premature_outcome_cannot_be_stored(self):
        await self.svc.tick();r=next(x for x in await self.store.read(mode='recent') if x['kind']=='PRED' and x['tf']=='15m')
        p=verify(r);body=dict(prediction_id=r['id'],target_closed_at=p['closed_at']+4*900,fingerprint='dummy-hash')
        premature=record('OUTCOME',r['id']+':4',body,r['created_ms'],r['cohort'],'15m',r['closed_at'],r['id'],4)
        with self.assertRaises(ForwardError):await self.store.append([premature])



class MathTests(unittest.TestCase):
    def test_exact_horizon_future_excluded_mfe_mae(self):
        xs=bars(40);p=dict(id='p',timeframe='15m',closed_at=xs[0].time+900,closed_price=str(xs[0].close))
        target=p['closed_at']+4*900;now=(xs[-1].time+950)*1000
        self.assertIsNone(realized(p,xs,4,target*1000-1))
        r=realized(p,xs,4,now)
        self.assertEqual(D(r['actual_price']),xs[4].close)
        self.assertEqual(r['target_closed_at'],target)
        later=deepcopy(xs);later[20]=replace(later[20],close=D('101'))
        self.assertEqual(r,realized(p,later,4,now))
        self.assertEqual(realized(p,xs[:2]+xs[3:],4,now)['quality'],'MISSING_CANDLES')
        with self.assertRaises(ForwardError):frame(xs+[xs[-1]],'15m',xs[-1].time+900)
        with self.assertRaises(ForwardError):frame(xs,'15m',xs[-1].time+899)

    def test_proper_scores_independent_arithmetic_and_zero_probability(self):
        f=dict(mean_return_pct=1,probabilities=[.2,.1,.7]);s=score(f,2)
        self.assertAlmostEqual(s['brier'],.04+.01+.09)
        self.assertAlmostEqual(s['log_loss'],-__import__('math').log(.7))
        self.assertEqual(s['absolute_error'],1);self.assertEqual(s['squared_error'],1)
        zero=score(dict(mean_return_pct=0,probabilities=[0,1,0]),2)
        result=aggregate([zero]);self.assertIsNone(result['log_loss']);self.assertEqual(result['log_loss_status'],'INFINITY')
        self.assertIsNone(result['balanced_accuracy'])

    def test_storage_scope_isolated_and_empty_stats_not_success(self):
        self.assertEqual(summarize([])['status'],'ПРОВЕРКА ЕЩЁ НЕ ЗАВЕРШЕНА')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ForwardError):SQLiteStore(Path(folder)/'paper.sqlite3')
        source=''.join(p.read_text() for p in Path('app/forward').glob('*.py') if p.name!='api.py')
        for token in ('app.paper','app.bybit','app.testnet','create_order','cancel_order','amend_order'):
            self.assertNotIn(token,source)
        self.assertNotIn('X-Aura-Forward-Token',Path('static/forward_validation.js').read_text())


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    async def test_rpc_allowlist_error_redaction_and_malformed(self):
        calls=[]
        def handler(request):
            calls.append(request);return httpx.Response(403,json={'secret':DUMMY_KEY})
        store=SupabaseStore('https://dummyprojectabcdefgh.supabase.co',DUMMY_KEY,httpx.MockTransport(handler))
        try:
            with self.assertRaises(ForwardError) as error:await store.status()
            self.assertEqual(error.exception.code,'STORAGE_AUTH_ERROR');self.assertNotIn(DUMMY_KEY,str(error.exception))
            self.assertEqual(calls[0].method,'POST');self.assertTrue(calls[0].url.path.endswith('/aura_forward_status'))
            with self.assertRaises(ForwardError):await store.rpc('order',{})
        finally:await store.close()
        def malformed(request):return httpx.Response(200,json=[])
        store=SupabaseStore('https://dummyprojectabcdefgh.supabase.co',DUMMY_KEY,httpx.MockTransport(malformed))
        try:
            with self.assertRaises(ForwardError):await store.status()
        finally:await store.close()

    async def test_timeout_network_rate_and_handler_redaction(self):
        for error,code in [(httpx.ReadTimeout('dummy-only-private-message'),'STORAGE_TIMEOUT'),(httpx.ConnectError('dummy-only-private-message'),'STORAGE_NETWORK_ERROR')]:
            def failed(request):raise error
            store=SupabaseStore('https://dummyprojectabcdefgh.supabase.co',DUMMY_KEY,httpx.MockTransport(failed))
            try:
                with self.assertRaises(ForwardError) as e:await store.status()
                self.assertEqual(e.exception.code,code)
            finally:await store.close()
        stream=io.StringIO();handler=logging.StreamHandler(stream);logging.getLogger().addHandler(handler)
        store=SupabaseStore('https://dummyprojectabcdefgh.supabase.co',DUMMY_KEY,httpx.MockTransport(lambda r:httpx.Response(429)))
        try:
            logging.getLogger('late.forward.transport').warning('dummy key=%s',DUMMY_KEY)
            self.assertNotIn(DUMMY_KEY,stream.getvalue())
            with self.assertRaises(ForwardError) as e:await store.status()
            self.assertEqual(e.exception.code,'STORAGE_RATE_LIMIT')
        finally:await store.close();logging.getLogger().removeHandler(handler)

class ConfigurationTests(unittest.TestCase):
    def test_unconfigured_and_render_ephemeral_storage_rejected(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertIsNone(configured(None).store)
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'RENDER':'true','AURA_FORWARD_SQLITE_PATH':str(Path(folder)/'forward-validation.sqlite3')},clear=True):
            svc=configured(None);self.assertIsNone(svc.store);self.assertEqual(svc.reason,'RENDER_REQUIRES_DURABLE_STORAGE')
        with patch.dict(os.environ,{'AURA_FORWARD_SUPABASE_URL':'https://evil.invalid','AURA_FORWARD_SUPABASE_SERVICE_KEY':DUMMY_KEY},clear=True):
            self.assertEqual(configured(None).reason,'INVALID_STORAGE_CONFIGURATION')

    def test_foreign_database_and_corrupt_storage_cannot_replace_other_ledgers(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'forward-validation.sqlite3'
            with sqlite3.connect(path) as c:c.execute('create table paper_secret_ledger (value text)')
            with self.assertRaises(ForwardError):SQLiteStore(path)
            with sqlite3.connect(path) as c:self.assertIsNotNone(c.execute("select name from sqlite_master where name='paper_secret_ledger'").fetchone())

    def test_storage_schema_closed_rpc_and_disabled_schedule(self):
        sql=Path('scripts/forward_validation_schema.sql').read_text();wf=Path('.github/workflows/aura-forward-validation.yml').read_text()
        self.assertIn('enable row level security',sql);self.assertIn('revoke all on function',sql)
        self.assertIn('pg_advisory_xact_lock',sql);self.assertIn('APPEND_ONLY',sql)
        self.assertIn("vars.AURA_FORWARD_ENABLED == 'true'",wf)
        self.assertIn("parsed.hostname!='terminal.onrender.com'",wf)

    def test_overlapping_scores_never_claim_independent_sample_size(self):
        results=summarize([]);self.assertEqual(results['edge_status'],'NOT_ESTABLISHED')
        src=Path('app/forward/stats.py').read_text()
        self.assertIn('effective_independent_sample_size=None',src);self.assertIn('confidence_intervals=None',src)
