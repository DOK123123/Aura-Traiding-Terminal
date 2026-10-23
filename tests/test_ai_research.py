"""Offline fixtures test invariants; only bundled Binance data is performance evidence."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from app.lab.models import LabError,digest
from app.research.registry import HYPOTHESES,PROTOCOL,registry
from app.research.strategies import HypothesisDecisions
from app.research.data import available,load_dataset
from app.research.experiment import frozen_config,execute
from app.research.auditor import audit_run,conclusion
from app.research.storage import Store
from app.research.service import Service
from app.research.llm import Advisor
from tests.test_market_intelligence import bars


def env(**changes):
    value=dict(AURA_RESEARCH_LLM_ENABLED='true',AURA_RESEARCH_LLM_PROVIDER='openai',AURA_RESEARCH_LLM_MODEL='DUMMY_MODEL',AURA_RESEARCH_LLM_API_KEY='DUMMY_KEY_NOT_REAL',
      AURA_RESEARCH_LLM_INPUT_USD_PER_M='1',AURA_RESEARCH_LLM_OUTPUT_USD_PER_M='2',AURA_RESEARCH_LLM_DAILY_USD='0.1',AURA_RESEARCH_LLM_TOTAL_USD='0.2')
    return dict(value,**changes)

class Determinism(unittest.TestCase):
    def test_real_dataset_integrity_and_contamination_truth(self):
        bs,source=load_dataset();self.assertEqual(len(bs),39200);self.assertEqual(source['sha256'],available()['sha256'])
        self.assertFalse(available()['independent_test_available']);self.assertFalse(PROTOCOL['candidate_for_paper_enabled'])
        for b in bs:self.assertLessEqual(b.time+900,PROTOCOL['end_exclusive'])
        self.assertEqual(set(registry()),set(HYPOTHESES))

    def test_all_hypotheses_causal_under_future_mutation_and_prefix(self):
        bs=bars(1400);i=1199;cut=bs[i].time+900
        changed=[b if b.time<cut else replace(b,open=b.open*3,high=b.high*3,low=b.low*3,close=b.close*3) for b in bs]
        a,b,c=HypothesisDecisions(bs),HypothesisDecisions(changed),HypothesisDecisions(bs[:i+1])
        for name in HYPOTHESES:
            self.assertEqual(a.decision(i,name),b.decision(i,name));self.assertEqual(a.decision(i,name),c.decision(i,name))
            d=a.decision(i,name)
            if 'context_closed_at' in d:self.assertLessEqual(d['context_closed_at'],cut)
        self.assertEqual(list(a.rows('MEAN_REVERSION',cut,cut+900))[0]['closed_at'],cut+900)

    def test_sweep_long_short_uses_prior_range_and_reclaim(self):
        bs=bars(400);index=399
        prior=bs[index-20:index];lo=min(b.low for b in prior);hi=max(b.high for b in prior)
        for side in ('LONG','SHORT'):
            data=HypothesisDecisions(bs);b=bs[index]
            data.data['atr'][index]=1.;data.data['adx'][index]=15.
            data.data['bars']=list(bs)
            data.data['bars'][index]=replace(b,open=lo if side=='LONG' else hi,low=lo-1,high=hi+1,close=lo+D('.5') if side=='LONG' else hi-D('.5'),volume=sum(x.volume for x in prior))
            d=data.decision(index,'LIQUIDITY_SWEEP');self.assertEqual(d['direction'],side)
            self.assertLess(D(d['stop_loss']),D(d['take_profit'])) if side=='LONG' else self.assertGreater(D(d['stop_loss']),D(d['take_profit']))

    def test_experiment_reproducible_three_ledgers_no_test_sensitivity_or_selection(self):
        bs=bars(1800);source=dict(available(),sha256='SYNTHETIC_TEST_ONLY')
        with patch.dict(PROTOCOL,start=bs[1200].time,end_exclusive=bs[-1].time+900):
            config=frozen_config('LIQUIDITY_SWEEP',source);a=execute(config,bs,source);b=execute(config,bs,source)
        self.assertEqual(digest(a),digest(b));self.assertEqual(len(a['runs']),7)
        self.assertEqual([r['scale'] for r in a['runs'] if r['split']=='test'],['1'])
        self.assertTrue(all(s['fresh_ledger'] for s in a['splits']));self.assertFalse(a['auditor']['promotion_allowed'])
        for r in a['runs']:self.assertEqual(r['equity_curve'][0]['equity'],'10000')

    def test_independent_oracle_rejects_corrupted_metrics_and_ledger(self):
        from scripts.research_lab_v2 import replay
        from scripts.verify_auto42_execution import TestMarket
        m=TestMarket('LONG');bs=list(m.bars);start=bs[-2].time
        # Queue at close then execute next candle and hit target in that candle.
        bs[-1]=replace(bs[-1],high=D(106))
        decision=dict(direction='LONG',reason='AI_LAB_TEST',source=__import__('app.lab.models',fromlist=['SOURCE']).SOURCE,stop_loss='97.5',take_profit='105',signal_at=start+900,original_signal_at=start+900,strategy_timeframe='15m')
        rows=[dict(closed_at=start+900,decision=decision),dict(closed_at=start+1800,decision=dict(direction=None,reason='NO_SIGNAL'))]
        run=replay(bs,rows,start,start+1800,'AI_TEST','train');self.assertEqual(run['metrics']['trades'],1)
        self.assertEqual(audit_run(run,bs)['status'],'PASS')
        for key in ('net_profit','fees','max_drawdown_pct','profit_factor','expectancy'):
            bad=deepcopy(run);bad['metrics'][key]='999'
            with self.assertRaises((AssertionError,ValueError)):audit_run(bad,bs)
        bad=deepcopy(run);bad['trades'][0]['entry_price']='999'
        with self.assertRaises(ValueError):audit_run(bad,bs)

    def test_new_modules_have_no_trading_service_or_scheduler_authority(self):
        import ast
        root=Path(__file__).resolve().parents[1]
        for p in (root/'app/research').glob('*.py'):
            tree=ast.parse(p.read_bytes())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    self.assertNotIn(node.module,('app.automated.service','app.automated.storage','app.paper.service','scripts.auto42_scheduler'))

class Persistence(unittest.TestCase):
    def setUp(self):self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.store=Store(self.root)
    def tearDown(self):self.folder.cleanup()
    def config(self):return frozen_config('MEAN_REVERSION',available())

    def test_frozen_queue_dedup_restart_no_automatic_execution(self):
        config=self.config();ident=self.store.enqueue(config);self.assertEqual(self.store.enqueue(config),ident)
        store=Store(self.root);self.assertEqual(store.get(ident)['state'],'QUEUED');claim=store.claim(ident);self.assertEqual(claim['config'],config)
        with self.assertRaises(LabError):store.claim(ident)
        store.finish(ident,None,'TEST_INJECTED_FAILURE',attempt=claim['attempt']);self.assertEqual(store.get(ident)['state'],'ERROR')
        self.assertIsNone(store.get(ident)['report'])

    def test_concurrent_claims_and_budget_atomic_across_instances(self):
        from concurrent.futures import ThreadPoolExecutor
        ident=self.store.enqueue(self.config())
        def claim(_):
            try:Store(self.root).claim(ident);return 'ONE'
            except LabError:return 'DENIED'
        with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(claim,range(2))),['DENIED','ONE'])
        def reserve(_):
            try:Store(self.root).reserve('openai','DUMMY_MODEL',7,10,10);return 'ONE'
            except LabError:return 'DENIED'
        with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(reserve,range(2))),['DENIED','ONE'])
        self.assertEqual(sum(c['reserved'] for c in self.store.calls()),7)

    def test_wrong_database_symlink_hardlink_and_storage_failure_fail_closed(self):
        self.store.path.unlink();self.store.path.write_bytes(b'not a database')
        with self.assertRaises((LabError,sqlite3.Error)):Store(self.root)
        self.store.path.unlink();target=self.root/'protected.sqlite3';target.write_text('PRESERVE')
        self.store.path.symlink_to(target)
        with self.assertRaises(LabError):Store(self.root)
        self.assertEqual(target.read_text(),'PRESERVE');self.store.path.unlink()
        import os
        os.link(target,self.store.path)
        with self.assertRaises(LabError):Store(self.root)
        self.assertEqual(target.read_text(),'PRESERVE')

    def test_interrupted_jobs_only_recovered_manually_after_lease_not_rerun(self):
        now=[10000];store=Store(self.root,clock=lambda:now[0]);ident=store.enqueue(self.config());store.claim(ident)
        now[0]+=500;self.assertEqual(store.interrupt_stale(),0);now[0]+=101;self.assertEqual(store.interrupt_stale(),1)
        self.assertEqual(store.get(ident)['error'],'INTERRUPTED_MANUAL_RECOVERY')
        with self.assertRaises(LabError):store.claim(ident)

class LLM(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.folder=tempfile.TemporaryDirectory();self.store=Store(Path(self.folder.name))
    async def asyncTearDown(self):self.folder.cleanup()

    async def test_unconfigured_no_call_no_budget_spend_backtester_still_available(self):
        a=Advisor(self.store,env={});self.assertEqual(a.status()['status'],'AI_NOT_CONFIGURED')
        with self.assertRaisesRegex(LabError,'AI_NOT_CONFIGURED'):await a.propose()
        self.assertEqual(self.store.calls(),[])
        s=Service(Path(self.folder.name),store=self.store,advisor=a);r=await s.overview()
        self.assertEqual(len(r['agents']),3);self.assertEqual(r['agents'][1]['state'],'IDLE');self.assertFalse(r['activation_available'])

    async def test_real_adapter_mock_valid_response_no_keys_in_outputs_or_log(self):
        def respond(req):
            self.assertEqual(str(req.url),'https://api.openai.com/v1/chat/completions')
            payload=json.loads(req.content);self.assertNotIn('tools',payload);self.assertEqual(payload['max_tokens'],512)
            idea=dict(title='TEST proposal',rationale='unverified',source_ids=['JEG1990'],risks=['insufficient sample'])
            return httpx.Response(200,json=dict(usage=dict(prompt_tokens=1000,completion_tokens=100),choices=[dict(message=dict(content=json.dumps(idea)))]))
        a=Advisor(self.store,env=env(),transport=httpx.MockTransport(respond));result=await a.propose()
        self.assertFalse(result['can_execute']);self.assertFalse(result['queued']);self.assertNotIn('DUMMY_KEY',json.dumps(result)+json.dumps(self.store.calls()))
        self.assertEqual(self.store.calls()[0]['state'],'COMPLETE');self.assertGreater(self.store.calls()[0]['reserved'],0)

    async def test_errors_unknown_usage_keep_reservation_and_sanitize(self):
        for response in (httpx.Response(429,text='DUMMY_KEY_NOT_REAL RAW_SECRET'),httpx.Response(200,json={'usage':{}})):
            a=Advisor(self.store,env=env(),transport=httpx.MockTransport(lambda req:response))
            with self.assertRaisesRegex(LabError,'LLM_CALL_FAILED'):await a.propose()
        self.assertEqual(len(self.store.calls()),2);self.assertTrue(all(c['state']=='FAILED_RESERVATION_RETAINED' for c in self.store.calls()))
        self.assertNotIn('RAW_SECRET',json.dumps(self.store.calls()))

    async def test_spending_token_invalid_provider_and_prices_fail_before_network(self):
        a=Advisor(self.store,env=env(AURA_RESEARCH_LLM_DAILY_USD='0.000000001'))
        with self.assertRaisesRegex(LabError,'LLM_BUDGET_EXCEEDED'):await a.propose()
        self.assertEqual(self.store.calls(),[])
        a=Advisor(self.store,env=env(AURA_RESEARCH_LLM_MAX_INPUT_TOKENS='2048'))
        with self.assertRaisesRegex(LabError,'LLM_TOKEN_LIMIT'):await a.propose()
        for changes in (dict(AURA_RESEARCH_LLM_PROVIDER='https://localhost'),dict(AURA_RESEARCH_LLM_INPUT_USD_PER_M='NaN')):
            a=Advisor(self.store,env=env(**changes));self.assertIn(a.status()['status'],('AI_NOT_CONFIGURED','AI_CONFIG_INVALID'))

class API(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.research.api import router,instance
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.s=Service(self.root,store=Store(self.root),writable=True)
        self.app=FastAPI();self.app.include_router(router);self.app.dependency_overrides[instance]=lambda:self.s
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://aura.invalid')
        self.auth=patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_PASSWORD',AURA_RESEARCH_LLM_ENABLED='false');self.auth.start()
        self.headers={'X-Aura-Lab':'research-only','Origin':'https://aura.invalid'}
    async def asyncTearDown(self):await self.client.aclose();self.auth.stop();self.folder.cleanup()

    async def test_owner_csrf_schema_no_store_and_unconfigured_ai(self):
        self.assertEqual((await self.client.get('/api/research')).status_code,401)
        args=dict(auth=('aura','DUMMY_OWNER_PASSWORD'))
        r=await self.client.get('/api/research',**args);self.assertEqual(r.status_code,200);self.assertEqual(r.headers['cache-control'],'no-store');self.assertEqual(r.json()['llm']['status'],'AI_NOT_CONFIGURED')
        body={'hypothesis':'MEAN_REVERSION'}
        self.assertEqual((await self.client.post('/api/research/queue',json=body,**args)).status_code,403)
        self.assertEqual((await self.client.post('/api/research/queue',json=body,headers=dict(self.headers,Origin='https://evil.invalid'),**args)).status_code,403)
        r=await self.client.post('/api/research/queue',json=dict(body,parameters={'risk':99}),headers=self.headers,**args);self.assertEqual(r.status_code,422)
        r=await self.client.post('/api/research/queue',json=body,headers=self.headers,**args);self.assertEqual(r.status_code,200)
        ident=r.json()['id'];self.assertEqual((await self.client.get('/api/research/experiments/'+ident,**args)).json()['state'],'QUEUED')
        r=await self.client.post('/api/research/ideas',json={},headers=self.headers,**args);self.assertEqual(r.status_code,503);self.assertEqual(r.json()['code'],'AI_NOT_CONFIGURED')
        self.assertEqual((await self.client.post('/api/research/queue/not-id/run',headers=self.headers,**args)).status_code,422)
        for forbidden in ('/activate','/orders','/deploy','/scheduler'):self.assertEqual((await self.client.post('/api/research'+forbidden,**args)).status_code,404)

    async def test_http_never_executes_or_spawns_worker(self):
        ident=(await self.s.enqueue('MEAN_REVERSION'))['id']
        with patch('app.research.experiment.execute',side_effect=AssertionError('HTTP_EXECUTION_FORBIDDEN')) as execute_mock,patch('subprocess.Popen',side_effect=AssertionError('HTTP_SPAWN_FORBIDDEN')) as spawn:
            result=await self.s.run(ident)
        self.assertFalse(result['executed']);self.assertEqual(result['status'],'EXTERNAL_RUNNER_REQUIRED')
        execute_mock.assert_not_called();spawn.assert_not_called()
        self.assertEqual((await self.s.get(ident))['state'],'QUEUED')

class AdditionalSafety(unittest.TestCase):
    def test_configured_paper_or_lab_path_conflict_prevents_creation(self):
        for key in ('PAPER_DB_PATH','LAB_DB_PATH'):
            with tempfile.TemporaryDirectory() as folder:
                target=Path(folder)/'.data/ai-research/ai-research-v1.sqlite3'
                with patch.dict('os.environ',**{key:str(target)}):
                    with self.assertRaisesRegex(LabError,'RESEARCH_STORAGE_CONFLICT'):Store(Path(folder))
                self.assertFalse(target.exists())

    def test_explicit_retry_preserves_config_and_error_event_completed_cannot_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));cfg=frozen_config('MEAN_REVERSION',available());ident=store.enqueue(cfg);claim=store.claim(ident);store.finish(ident,None,'TEST_FAILURE',attempt=claim['attempt'])
            store.retry(ident);self.assertEqual(store.get(ident)['config'],cfg);self.assertEqual(store.get(ident)['state'],'QUEUED');self.assertEqual(len(store.get(ident)['events']),4)
            self.assertEqual(store.claim(ident)['config'],cfg)
            with self.assertRaises(LabError):store.retry(ident)

    def test_render_llm_requires_explicit_persistent_storage_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Advisor(Store(Path(folder)),env=env(RENDER='true'))
            self.assertEqual(a.status()['status'],'AI_CONFIG_INVALID')

    def test_published_summary_checksum_and_boundaries(self):
        from app.research.published import summary
        s=summary();self.assertFalse(s['candidate_for_paper_enabled']);self.assertEqual(len(s['experiments']),4)
        for e in s['experiments']:self.assertEqual(e['status'],'REJECTED')

class AnonymousConstruction(unittest.IsolatedAsyncioTestCase):
    async def test_no_storage_factory_access_on_unauthenticated_read_or_mutation(self):
        from app.research.api import router
        app=FastAPI();app.include_router(router)
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_PASSWORD'),patch('app.research.api.service') as factory:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://aura.invalid') as c:
                self.assertEqual((await c.get('/api/research')).status_code,401)
                self.assertEqual((await c.post('/api/research/queue',json={'hypothesis':'MEAN_REVERSION'})).status_code,401)
            factory.assert_not_called()

class SuccessfulManualCycle(unittest.IsolatedAsyncioTestCase):
    async def test_http_enqueues_and_reads_only_external_result_pages(self):
        from app.research.api import router,instance
        bs=bars(1500);source=dict(available(),sha256='SYNTHETIC_SUCCESS_TEST_ONLY')
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));svc=Service(Path(folder),store=store,writable=True);app=FastAPI();app.include_router(router);app.dependency_overrides[instance]=lambda:svc
            with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_PASSWORD'),patch.dict(PROTOCOL,start=bs[1200].time,end_exclusive=bs[-1].time+900),patch('app.research.service.available',return_value=source):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://aura.invalid',auth=('aura','DUMMY_OWNER_PASSWORD'),headers={'X-Aura-Lab':'research-only'}) as c:
                    ident=(await c.post('/api/research/queue',json={'hypothesis':'MEAN_REVERSION'})).json()['id']
                    response=await c.post('/api/research/queue/'+ident+'/run',json={});self.assertEqual(response.status_code,200);self.assertFalse(response.json()['executed'])
                    self.assertEqual(store.get(ident)['state'],'QUEUED')
                    # Test-only simulation of an external caller; HTTP did not execute it.
                    claim=store.claim(ident);r=execute(claim['config'],bs,source);store.finish(ident,r,attempt=claim['attempt'])
                    self.assertEqual((await c.post('/api/research/queue/'+ident+'/run',json={})).status_code,409)
                    self.assertEqual((await c.post('/api/research/queue/'+ident+'/retry',json={})).status_code,409)
                    export=(await c.get('/api/research/experiments/'+ident+'/export')).json();self.assertNotIn('decisions',export['report']['runs'][0]);self.assertIn('artifacts',export['report']['runs'][0])
                    page=await c.get('/api/research/experiments/'+ident+'/records?run_key=0&kind=decisions');self.assertEqual(page.status_code,200)
                    self.assertEqual(Store(Path(folder)).get(ident)['report']['checksum'],export['report']['checksum'])

class LLMUnknownOutcome(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_reservation_survives_restart_and_credential_echo_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder))
            def timeout(req):raise httpx.ReadTimeout('DUMMY_SECRET_ERROR')
            with self.assertRaisesRegex(LabError,'LLM_CALL_FAILED'):await Advisor(store,env=env(),transport=httpx.MockTransport(timeout)).propose()
            before=Store(Path(folder)).calls();self.assertEqual(len(before),1);self.assertGreater(before[0]['reserved'],0)
            idea=dict(title='DUMMY_KEY_NOT_REAL',rationale='test',source_ids=['JEG1990'],risks=['test'])
            response=httpx.Response(200,json=dict(usage=dict(prompt_tokens=1000,completion_tokens=10),choices=[dict(message=dict(content=json.dumps(idea)))]))
            with self.assertRaisesRegex(LabError,'LLM_CALL_FAILED'):await Advisor(store,env=env(),transport=httpx.MockTransport(lambda req:response)).propose()
            self.assertNotIn('DUMMY_KEY',json.dumps(store.calls()));self.assertNotIn('DUMMY_SECRET_ERROR',json.dumps(store.calls()))


class AttemptFencing(unittest.TestCase):
    def test_old_worker_cannot_finish_new_attempt_after_manual_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            now=[10000];store=Store(Path(folder),clock=lambda:now[0]);ident=store.enqueue(frozen_config('MEAN_REVERSION',available()))
            old=store.claim(ident);now[0]+=601;self.assertEqual(store.interrupt_stale(),1);store.retry(ident);new=store.claim(ident)
            self.assertNotEqual(old['attempt'],new['attempt'])
            with self.assertRaises(LabError):store.finish(ident,None,'LATE_OLD_WORKER',attempt=old['attempt'])
            self.assertEqual(store.get(ident)['state'],'RUNNING')
            store.finish(ident,None,'CURRENT_ATTEMPT_ERROR',attempt=new['attempt']);self.assertEqual(store.get(ident)['error'],'CURRENT_ATTEMPT_ERROR')
