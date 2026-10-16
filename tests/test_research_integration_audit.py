"""Integration audit: isolated files/processes only; known deploy blockers are explicit."""
import asyncio
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch
import httpx
import pytest
from fastapi import FastAPI
from app.lab.models import canonical,digest,LabError,Baseline
from app.research.api import router,instance
from app.research.data import available
from app.research.experiment import frozen_config
from app.research.service import Service
from app.research.storage import Store,MAX_RAW

ROOT=Path(__file__).resolve().parents[1]
AUTH=('aura','DUMMY_INTEGRATION_OWNER')


def report(config):
    r=dict(auditor=dict(status='REJECTED'),research_only=True,activation_available=False,final_test_is_independent=False,config=config,config_hash=digest(config),runs=[],test_only=True)
    return dict(r,checksum=digest(r))


def test_fresh_interpreter_recovers_queue_history_reports_and_spending_without_dispatch(tmp_path):
    store=Store(tmp_path);config=frozen_config('MEAN_REVERSION',available());ident=store.enqueue(config);claim=store.claim(ident);r=report(config)
    store.finish(ident,r,attempt=claim['attempt']);pending=store.enqueue(frozen_config('LIQUIDITY_SWEEP',available()))
    running=store.enqueue(frozen_config('REGIME_SWITCHING',available()));store.claim(running)
    call=store.reserve('openai','DUMMY_NO_HTTP',7,10,10)
    program='''import json,sys
from pathlib import Path
from app.research.storage import Store
s=Store(Path(sys.argv[1]));row=s.get(sys.argv[2]);pending=s.get(sys.argv[3]);running=s.get(sys.argv[4]);calls=s.calls()
print(json.dumps(dict(state=row['state'],checksum=row['report']['checksum'],events=row['events'],pending=pending['state'],running=running['state'],calls=calls)))
'''
    p=subprocess.run([sys.executable,'-c',program,str(tmp_path),ident,pending,running],cwd=ROOT,capture_output=True,text=True,timeout=15)
    assert p.returncode==0;child=json.loads(p.stdout)
    assert child['checksum']==r['checksum'] and child['state']=='REJECTED' and child['pending']=='QUEUED' and child['running']=='RUNNING'
    assert child['events']==store.get(ident)['events'];assert child['calls'][0]['id']==call and child['calls'][0]['reserved']==7
    assert child['calls'][0]['state']=='RESERVED'
    with pytest.raises(LabError):store.reserve('openai','DUMMY_NO_HTTP',4,10,10)


def test_ephemeral_directory_replacement_does_not_preserve_history(tmp_path):
    root=tmp_path/'old';store=Store(root);ident=store.enqueue(frozen_config('MEAN_REVERSION',available()))
    other=Store(tmp_path/'new');assert other.list()==[]
    with pytest.raises(LabError,match='RESEARCH_NOT_FOUND'):other.get(ident)
    assert store.get(ident)['state']=='QUEUED'


def test_real_main_router_coexists_with_strategy_lab_and_never_touches_trading_state(tmp_path):
    from app.main import app
    from app.lab.service import Service as LabService
    from app.lab.experiment import execute
    from tests.test_lab import snap
    class Forbidden:
        def __getattr__(self,name):raise AssertionError('TRADING_STATE_ACCESS_FORBIDDEN')
    async def no_page(*args,**kwargs):raise AssertionError('NO_NETWORK_FETCH')
    async def work():
        lab=LabService(tmp_path,no_page);snapshot=snap();config=Baseline(risk_pct='0.5');result=execute(snapshot,config)
        lab_id=lab.store.save(snapshot,config.data(),result);research=Service(tmp_path)
        # Existing isolated sentinel ledgers are never opened by either research UI.
        sentinel=tmp_path/'.data/protected-trading.sqlite3'
        with sqlite3.connect(sentinel) as c:c.execute('create table portfolio(balance text,position text)');c.execute("insert into portfolio values('10000','EXISTING_SENTINEL_POSITION')")
        before=hashlib.sha256(sentinel.read_bytes()).hexdigest();overrides=dict(app.dependency_overrides)
        state_before=dict(app.state._state)
        app.dependency_overrides[instance]=lambda:research;app.state.lab=lab
        for name in ('auto42','paper','forward_validation','testnet','bybit_demo'):setattr(app.state,name,Forbidden())
        original=socket.socket.connect
        def deny(sock,address):
            if sock.family in (socket.AF_INET,socket.AF_INET6):raise AssertionError('NETWORK_FORBIDDEN')
            return original(sock,address)
        try:
            with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=AUTH[1],AURA_RESEARCH_LLM_ENABLED='false',PAPER_DB_PATH=str(sentinel),LAB_DB_PATH=str(lab.store.path)),patch.object(socket.socket,'connect',deny),patch('app.automated.service.Service.__init__',side_effect=AssertionError('AUTO42_SERVICE_FORBIDDEN')),patch('app.automated.storage.SupabaseStore.__init__',side_effect=AssertionError('SUPABASE_FORBIDDEN')),patch('app.paper.service.Service.__init__',side_effect=AssertionError('PAPER_SERVICE_FORBIDDEN')):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid',auth=AUTH) as c:
                    for path in ('/api/health','/api/lab/experiments','/api/lab/experiments/'+lab_id,'/api/lab/adaptive43','/api/lab/profiles43','/api/lab/v2','/api/research','/static/research.html','/'):
                        response=await c.get(path);assert response.status_code==200,path
                    r=await c.post('/api/research/queue',json={'hypothesis':'MEAN_REVERSION'},headers={'X-Aura-Lab':'research-only'});assert r.status_code==200
                    ident=r.json()['id'];assert (await c.get('/api/research/experiments/'+ident)).json()['state']=='QUEUED'
                    assert (await c.get('/api/lab/experiments/'+lab_id)).json()['id']==lab_id
                    assert (await c.get('/api/lab/experiments/'+ident)).status_code==404
                    assert (await c.get('/api/research/experiments/'+lab_id)).status_code==422
            assert lab.store.path!=research.store.path
            assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==before
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(overrides);app.state._state.clear();app.state._state.update(state_before)
    asyncio.run(work())


def test_all_research_endpoints_require_owner_and_mutations_csrf(tmp_path):
    app=FastAPI();app.include_router(router);svc=Service(tmp_path);app.dependency_overrides[instance]=lambda:svc
    ident=svc.store.enqueue(frozen_config('MEAN_REVERSION',available()))
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=AUTH[1],AURA_RESEARCH_LLM_ENABLED='false'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid') as c:
                gets=('/api/research','/api/research/login','/api/research/experiments/'+ident,'/api/research/experiments/'+ident+'/export')
                posts=('/api/research/queue','/api/research/queue/'+ident+'/run','/api/research/queue/'+ident+'/retry','/api/research/ideas','/api/research/recover-interrupted')
                for path in gets:assert (await c.get(path)).status_code==401
                for path in posts:
                    assert (await c.post(path,json={})).status_code==401
                    assert (await c.post(path,json={},auth=AUTH)).status_code==403
                    assert (await c.post(path,json={},auth=AUTH,headers={'X-Aura-Lab':'research-only','Sec-Fetch-Site':'cross-site'})).status_code==403
                r=await c.post('/api/research/ideas',json={},auth=AUTH,headers={'X-Aura-Lab':'research-only'})
                assert r.status_code==503 and r.json()['code']=='AI_NOT_CONFIGURED'
    asyncio.run(work());assert svc.store.get(ident)['state']=='QUEUED' and svc.store.calls()==[]


def test_corrupt_compressed_report_and_sqlite_errors_are_sanitized(tmp_path):
    store=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());ident=store.enqueue(cfg);claim=store.claim(ident);store.finish(ident,report(cfg),attempt=claim['attempt'])
    with store.connect() as c:c.execute('update queue set result=? where id=?',(b'DUMMY_BAD_GZIP_NO_SECRET',ident))
    app=FastAPI();app.include_router(router);app.dependency_overrides[instance]=lambda:Service(tmp_path,store=store)
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=AUTH[1]):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='https://offline.invalid',auth=AUTH) as c:
                r=await c.get('/api/research/experiments/'+ident);assert r.status_code==503 and 'DUMMY_BAD' not in r.text
                assert r.headers['cache-control']=='no-store'
                with patch.object(store,'get',side_effect=sqlite3.OperationalError('DUMMY_SQL_SECRET')):
                    r=await c.get('/api/research/experiments/'+ident);assert r.status_code==503 and 'DUMMY_SQL' not in r.text
    asyncio.run(work())


@pytest.mark.xfail(strict=True,reason='AUDIT-F1: real Volatility Breakout report exceeds Store MAX_RAW; deploy blocked until bounded decision logs replace monolithic result')
def test_known_blocker_volatility_breakout_real_report_can_be_saved(tmp_path):
    r=json.loads(gzip.decompress((ROOT/'docs/AI_RESEARCH_V1/VOLATILITY_BREAKOUT.json.gz').read_bytes()))
    store=Store(tmp_path);ident=store.enqueue(r['config']);claim=store.claim(ident)
    store.finish(ident,r,attempt=claim['attempt'])
    assert store.get(ident)['report']['checksum']==r['checksum']


def test_inventory_documents_which_real_reports_fit_current_store():
    lengths={p.stem.split('.')[0]:len(gzip.decompress(p.read_bytes())) for p in (ROOT/'docs/AI_RESEARCH_V1').glob('*.json.gz')}
    assert {name for name,size in lengths.items() if size>MAX_RAW}=={'VOLATILITY_BREAKOUT'}
    assert lengths['VOLATILITY_BREAKOUT']==36461574 and MAX_RAW==33554432


@pytest.mark.xfail(strict=True,reason='AUDIT-F3: valid JSON with wrong result type escapes TypeError as HTTP500 rather than sanitized no-store503')
def test_known_blocker_wrong_type_saved_report_returns_structured_error(tmp_path):
    store=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());ident=store.enqueue(cfg);claim=store.claim(ident);store.finish(ident,report(cfg),attempt=claim['attempt'])
    with store.connect() as c:c.execute('update queue set result=? where id=?',(gzip.compress(b'[]'),ident))
    app=FastAPI();app.include_router(router);app.dependency_overrides[instance]=lambda:Service(tmp_path,store=store)
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=AUTH[1]):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='https://offline.invalid',auth=AUTH) as c:
                r=await c.get('/api/research/experiments/'+ident)
                assert r.status_code==503 and r.headers.get('cache-control')=='no-store'
    asyncio.run(work())


def test_existing_main_lab_route_functions_and_request_schema_remain_unchanged():
    import ast
    old=ast.parse(subprocess.check_output(['git','show','origin/main:app/lab/api.py'],cwd=ROOT,text=True))
    current=ast.parse((ROOT/'app/lab/api.py').read_text())
    def functions(tree):return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
    expected,actual=functions(old),functions(current)
    for name,node in expected.items():assert actual[name]==node,name
    routes=[]
    from app.main import app
    for route in app.routes:
        for method in getattr(route,'methods',set()):routes.append((method,route.path))
    assert len(routes)==len(set(routes)), 'Duplicate method/path registration'


def test_missing_required_runtime_protocol_prevents_app_startup():
    program='''from pathlib import Path
original=Path.read_text
name='STRATEGY_LAB_V2_PROTOCOL.json'
def read(self,*a,**k):
 if self.name==name:raise FileNotFoundError('AUDIT_MISSING_REQUIRED_PROTOCOL')
 return original(self,*a,**k)
Path.read_text=read
try:import app.main
except FileNotFoundError as e:
 if str(e)!='AUDIT_MISSING_REQUIRED_PROTOCOL':raise
 print('REQUIRED_RUNTIME_PROTOCOL_CONFIRMED')
else:raise AssertionError('EXPECTED_RUNTIME_DEPENDENCY_NOT_REACHED')
'''
    p=subprocess.run([sys.executable,'-c',program],cwd=ROOT,capture_output=True,text=True,timeout=15)
    assert p.returncode==0 and 'REQUIRED_RUNTIME_PROTOCOL_CONFIRMED' in p.stdout
