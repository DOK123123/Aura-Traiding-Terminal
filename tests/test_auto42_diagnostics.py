"""Diagnostics use dummy credentials and mocked services, never production writes."""
import asyncio,io,json,logging,socket,ssl,unittest
from pathlib import Path
from unittest.mock import patch
from uvicorn.logging import AccessFormatter
from app.forward.storage import SecretFilter

DUMMY_KEY='dummy-storage-key-for-diagnostics-tests-only'


class AccessLogTests(unittest.TestCase):
    def test_uvicorn_five_argument_record_survives_secret_filter(self):
        record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',
            ('127.0.0.1:1000','GET','/api/health','1.1',200),None)
        f=SecretFilter(DUMMY_KEY);f.filter(record)
        self.assertEqual(len(record.args),5);self.assertIs(type(record.args[-1]),int)
        out=AccessFormatter('%(client_addr)s - %(request_line)s %(status_code)s',use_colors=False).format(record)
        self.assertIn('GET /api/health HTTP/1.1',out);self.assertIn('200',out)
    def test_access_secret_redaction_keeps_both_handler_formats_valid(self):
        record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',
            ('127.0.0.1:1000','GET','/dummy?canary='+DUMMY_KEY,'1.1',200),None)
        SecretFilter(DUMMY_KEY).filter(record)
        for f in (AccessFormatter('%(request_line)s %(status_code)s',use_colors=False),logging.Formatter('%(message)s')):
            self.assertNotIn(DUMMY_KEY,f.format(record))
        self.assertEqual(len(record.args),5)
    def test_http_status_enum_and_numeric_args_keep_formatter_types(self):
        from http import HTTPStatus
        from decimal import Decimal
        f=SecretFilter(DUMMY_KEY)
        r=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',('client','GET','/api/health','1.1',HTTPStatus.OK),None)
        f.filter(r);self.assertIs(r.args[-1],HTTPStatus.OK)
        self.assertIn('200',AccessFormatter('%(status_code)s',use_colors=False).format(r))
        r=logging.LogRecord('app',logging.INFO,'',0,'amount %.2f',(Decimal('12.50'),),None);f.filter(r)
        self.assertEqual(r.getMessage(),'amount 12.50')
    def test_mapping_args_bytes_traceback_and_stack_redacted(self):
        f=SecretFilter(DUMMY_KEY)
        record=logging.LogRecord('app',logging.WARNING,'',0,'value %(value)s',({'value':DUMMY_KEY},),None)
        record.stack_info='canary '+DUMMY_KEY;f.filter(record)
        self.assertNotIn(DUMMY_KEY,logging.Formatter().format(record));self.assertIsInstance(record.args,dict)
        self.assertEqual(f.redact((DUMMY_KEY.encode(),403)),(b'[REDACTED]',403))
        try:raise RuntimeError('dummy canary '+DUMMY_KEY)
        except RuntimeError:
            import sys
            record=logging.LogRecord('app',logging.ERROR,'',0,'failed %s',(DUMMY_KEY,),sys.exc_info())
        f.filter(record);self.assertNotIn(DUMMY_KEY,logging.Formatter().format(record))


class StorageDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_network_categories_no_raw_exception_text(self):
        import httpx
        from app.automated.storage import SupabaseStore
        from app.automated.engine import DemoError
        for kind,cause in [('DNS',socket.gaierror(-2,DUMMY_KEY)),('TLS',ssl.SSLError(DUMMY_KEY)),('CONNECT',ConnectionRefusedError(DUMMY_KEY))]:
            def handle(request):raise httpx.ConnectError(DUMMY_KEY) from cause
            store=SupabaseStore('https://abcdefghijklmnopqrst.supabase.co',DUMMY_KEY,httpx.MockTransport(handle))
            with self.assertRaisesRegex(DemoError,'STORAGE_'+kind):await store.load()
            self.assertEqual(store.diagnostics['network_error'],kind)
            self.assertNotIn(DUMMY_KEY,json.dumps(store.diagnostics));await store.close()
    async def test_http_auth_schema_permission_rate_and_database_categories(self):
        import httpx
        from app.automated.storage import SupabaseStore
        from app.automated.engine import DemoError
        cases=[(401,{},'STORAGE_AUTH'),(403,{'code':'42501'},'STORAGE_PERMISSION_DENIED'),
            (404,{'code':'PGRST202'},'STORAGE_SCHEMA_MISSING'),(404,{'code':'42P01'},'STORAGE_SCHEMA_MISSING'),
            (503,{'code':'PGRST000'},'STORAGE_DATABASE_UNAVAILABLE'),(429,{},'STORAGE_RATE_LIMIT')]
        for status,body,code in cases:
            body=dict(body,message=DUMMY_KEY,details=DUMMY_KEY)
            store=SupabaseStore('https://abcdefghijklmnopqrst.supabase.co',DUMMY_KEY,httpx.MockTransport(lambda r:httpx.Response(status,json=body)))
            with self.assertRaisesRegex(DemoError,code):await store.load()
            self.assertEqual(store.diagnostics['http_status'],status);self.assertNotIn(DUMMY_KEY,json.dumps(store.diagnostics));await store.close()
    async def test_config_diagnostics_exposes_only_variable_names(self):
        from app.automated.diagnostics import configuration
        with patch.dict('os.environ',{'AURA_AUTO42_SUPABASE_URL':'postgres://'+DUMMY_KEY,'AURA_AUTO42_SUPABASE_SERVICE_KEY':'bad'},clear=True):
            data=configuration();self.assertEqual(set(data['invalid_variables']),{'AURA_AUTO42_SUPABASE_URL','AURA_AUTO42_SUPABASE_SERVICE_KEY'})
            self.assertNotIn(DUMMY_KEY,json.dumps(data))
        with patch.dict('os.environ',{},clear=True):self.assertIn('AURA_AUTO42_SUPABASE_URL',configuration()['missing_variables'])
    async def test_last_save_is_confirmed_and_survives_restart_and_duplicates(self):
        import tempfile
        from app.automated.storage import SQLiteStore
        from app.automated.service import Service
        with tempfile.TemporaryDirectory() as folder:
            clock=[1700000010];path=Path(folder)/'auto-paper-42.sqlite3';store=SQLiteStore(path,clock=lambda:clock[0]);svc=Service(None,store,clock=lambda:clock[0])
            before=await store.load();clock[0]+=1;await svc.tick();after=await store.load()
            self.assertGreater(after['last_saved_at'],before['last_saved_at']);saved=after['last_saved_at'];await svc.tick()
            self.assertEqual((await store.load())['last_saved_at'],saved)
            restart=SQLiteStore(path,clock=lambda:clock[0]);self.assertEqual((await restart.load())['last_saved_at'],saved);await svc.close()
    async def test_additive_sqlite_migration_preserves_original_payload_and_no_fake_timestamp(self):
        import sqlite3,tempfile
        from app.automated.storage import SQLiteStore,packed
        from app.automated.engine import initial
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'auto-paper-42.sqlite3';original=packed(initial(1700000000))
            with sqlite3.connect(path) as c:
                c.execute('create table auto42_account(id INTEGER PRIMARY KEY,revision INTEGER,payload TEXT,sha256 TEXT)')
                c.execute('insert into auto42_account values(1,3,?,?)',(original['payload'],original['sha256']))
            store=SQLiteStore(path);loaded=await store.load();self.assertEqual(loaded['revision'],3);self.assertIsNone(loaded['last_saved_at'])
            with sqlite3.connect(path) as c:self.assertEqual(c.execute('select payload,sha256 from auto42_account').fetchone(),(original['payload'],original['sha256']))
            await store.close()
    async def test_owner_http_error_carries_safe_diagnostics_and_not_false_server_offline(self):
        import httpx
        from fastapi import FastAPI
        from app.automated.storage import SupabaseStore
        from app.automated.service import Service
        from app.automated.api import router
        from tests.test_auto42 import DUMMY_OWNER
        def handle(r):raise httpx.ConnectError(DUMMY_KEY) from socket.gaierror(-2,DUMMY_KEY)
        store=SupabaseStore('https://abcdefghijklmnopqrst.supabase.co',DUMMY_KEY,httpx.MockTransport(handle));svc=Service(None,store)
        app=FastAPI();app.state.auto42=svc;app.include_router(router)
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                r=await client.get('/api/auto42/status',auth=('aura',DUMMY_OWNER));self.assertEqual(r.status_code,503)
                d=r.json()['diagnostics'];self.assertEqual(d['render_api'],'ONLINE');self.assertEqual(d['storage']['status'],'ERROR');self.assertEqual(d['protection'],'BLOCKED')
                self.assertNotIn(DUMMY_KEY,r.text)
        await svc.close()
    async def test_no_credentials_needed_to_instantiate_and_missing_storage_is_explicit(self):
        from app.automated.service import configured
        with patch.dict('os.environ',{},clear=True):
            d=(await configured(None).dashboard())['diagnostics'];self.assertEqual(d['render_api'],'ONLINE')
            self.assertEqual(d['storage']['status'],'ERROR');self.assertIn('AURA_AUTO42_SUPABASE_SERVICE_KEY',d['configuration']['missing_variables'])


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import tempfile
        from tests.test_auto42 import fixture,Market
        from app.automated.storage import SQLiteStore
        from app.automated.service import Service
        self.folder=tempfile.TemporaryDirectory();self.bs,self.snap,self.now=fixture();self.market=Market(self.bs,self.snap)
        self.path=Path(self.folder.name)/'auto-paper-42.sqlite3';self.store=SQLiteStore(self.path,clock=lambda:self.now[0]);self.svc=Service(self.market,self.store,clock=lambda:self.now[0])
    async def asyncTearDown(self):await self.svc.close();self.folder.cleanup()
    async def start_and_fail(self):
        from tests.test_auto42 import DUMMY_TOKEN,DUMMY_OWNER
        with patch.dict('os.environ',AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN,AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):await self.svc.control('START','a'*32)
        self.market.value['status']='STALE';r=await self.svc.tick();self.assertEqual(r['status'],'PAUSED')
        s=(await self.store.load())['state'];self.assertTrue(s['data_recovery_armed']);self.assertEqual(s['mode'],'PAUSED');return s
    async def test_transient_error_recovery_survives_restart_without_old_entry(self):
        from app.automated.service import Service
        from app.automated.storage import SQLiteStore
        before=await self.start_and_fail();self.now[0]+=300;self.market.value['status']='OK'
        fresh=Service(self.market,SQLiteStore(self.path,clock=lambda:self.now[0]),clock=lambda:self.now[0]);result=await fresh.tick()
        after=(await self.store.load())['state'];self.assertEqual(after['mode'],'ON');self.assertFalse(after['data_recovery_armed'])
        self.assertEqual(after['watermark'],before['watermark']);self.assertIsNone(after['position']);self.assertIsNone(after['pending']);self.assertFalse(result['processed_this_run'])
        self.assertTrue((await fresh.tick())['duplicate']);await fresh.close()
    async def test_stop_and_emergency_cancel_recovery_authority(self):
        await self.start_and_fail();await self.svc.control('STOP','b'*32);self.now[0]+=300;self.market.value['status']='OK';r=await self.svc.tick()
        after=(await self.store.load())['state'];self.assertEqual(after['mode'],'OFF');self.assertFalse(after['data_recovery_armed']);self.assertEqual(r['tick_outcome'],'HEARTBEAT_OFF')
        await self.svc.control('EMERGENCY','c'*32);self.now[0]+=300;await self.svc.tick();self.assertEqual((await self.store.load())['state']['mode'],'EMERGENCY')
    async def test_hard_gap_pause_does_not_gain_recovery_authority(self):
        from app.automated.engine import event
        loaded=await self.store.load();s=loaded['state'];s.update(mode='PAUSED',last_error='MISSING_CANDLES',last_decision='MISSING_CANDLES')
        e=event(s,'ERROR','unit-hard-gap',self.now[0],dict(reason='MISSING_CANDLES'));await self.store.commit(loaded['revision'],s,[e],e['id'])
        await self.svc.tick();after=(await self.store.load())['state'];self.assertEqual(after['mode'],'PAUSED');self.assertFalse(after['data_recovery_armed'])
        self.assertEqual(self.market.reads,0)
    async def test_wait_and_candle_processing_are_distinct_from_heartbeat(self):
        from tests.test_auto42 import DUMMY_TOKEN,DUMMY_OWNER,bar
        from app.lab.models import digest
        with patch.dict('os.environ',AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN,AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):await self.svc.control('START','a'*32)
        self.bs.append(bar(self.bs[-1].time+900));self.now[0]+=900;at=self.bs[-1].time+900
        self.market.value['last_closed_at']=at;self.market.value['state']['timestamp']=at;self.market.value['state']['retest']=None
        self.market.value['history']['source_sha256']=digest([b.data() for b in self.bs])
        for key,step in [('h1',3600),('h4',14400)]:self.market.value['state']['mtf'][key]['closed_at']=at//step*step
        r=await self.svc.tick();self.assertTrue(r['processed_this_run']);self.assertTrue(r['state_saved'])
        self.assertEqual(r['tick_outcome'],'CANDLE_PROCESSED');self.assertEqual(r['decision'],'NO_CONFIRMED_SETUP');self.assertEqual(r['opened_positions'],0)
        replay=await self.svc.tick();self.assertFalse(replay['processed_this_run']);self.assertEqual(replay['tick_outcome'],'NO_NEW_WORK')
    async def test_risk_pause_never_auto_rearms(self):
        from app.automated.engine import event
        loaded=await self.store.load();s=loaded['state'];s.update(balance='9800',equity='9800',day_low_equity='9800',realized_pnl='-200',gross_loss='200',trades=1,losses=1,mode='PAUSED',last_decision='DAILY_LOSS_LIMIT')
        e=event(s,'TEST','unit-risk',self.now[0],dict(reason='DAILY_LOSS_LIMIT'));await self.store.commit(loaded['revision'],s,[e],e['id'])
        await self.svc.tick();s=(await self.store.load())['state'];self.assertEqual(s['mode'],'PAUSED');self.assertFalse(s['data_recovery_armed']);self.assertEqual(self.market.reads,0)
