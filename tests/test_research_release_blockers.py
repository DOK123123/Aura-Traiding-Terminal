"""Mandatory release regressions: external storage/runner only; no production access."""
from argparse import Namespace
from contextlib import contextmanager
import gzip
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch
import asyncio
import hashlib
import httpx
import pytest
from fastapi import FastAPI
from app.lab.models import LabError,canonical,digest
from app.research.storage import Store,APP_ID,SCHEMA
from app.research.artifacts import COMPACT_LIMIT,CHUNK_LIMIT,streamed_digest
from app.research.persistence import initialize,configured_store,location,ROOT
from app.research.experiment import frozen_config
from app.research.data import available
from app.research.service import Service
from app.research.api import router,instance

@pytest.fixture
def durable():
    with tempfile.TemporaryDirectory(prefix='.research-durable-test-',dir='/workspace') as folder:
        p=Path(folder);initialize(p);yield p


def synthetic_report(config,n=1000):
    r=dict(research_only=True,activation_available=False,final_test_is_independent=False,test_only=True,config=config,config_hash=digest(config),
        auditor=dict(status='REJECTED',reasons=['SYNTHETIC_STORAGE_FIXTURE_ONLY']),runs=[dict(split='train',scale='1',metrics={},decisions=[dict(i=i,reason='X'*250) for i in range(n)],trades=[],equity_curve=[],daily_equity=[])])
    return dict(r,checksum=streamed_digest(r))


def test_chunk_transaction_rollback_then_exact_reconstruction(tmp_path):
    s=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());i=s.enqueue(cfg);claim=s.claim(i);r=synthetic_report(cfg)
    with s.connect() as c:c.execute("create trigger fail_chunk after insert on chunks when new.ordinal=1 begin select raise(ABORT,'DUMMY_FAIL_AFTER_CHUNK');end")
    with pytest.raises(sqlite3.Error):s.finish(i,r,attempt=claim['attempt'])
    with s.connect() as c:
        assert c.execute('select count(*) from chunks').fetchone()[0]==0
        c.execute('drop trigger fail_chunk')
    assert s.get(i)['state']=='RUNNING' and s.get(i)['report'] is None
    s.finish(i,r,attempt=claim['attempt']);m=s.get(i)['report']
    assert len(canonical(m))<=COMPACT_LIMIT and 'decisions' not in m['runs'][0]
    assert len(m['runs'][0]['artifacts']['decisions']['chunks'])>=2
    assert s.materialize(i)==r
    assert s.verify_chunks(i)['status']=='PASS'


def test_pages_are_bounded_and_corrupt_chunk_fails_closed(tmp_path):
    s=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());i=s.enqueue(cfg);claim=s.claim(i);r=synthetic_report(cfg)
    s.finish(i,r,attempt=claim['attempt']);offset=0;rows=[]
    while True:
        page=s.page(i,'0','decisions',offset,100);assert len(canonical(page))<CHUNK_LIMIT+4096
        rows+=page['records']
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert rows==r['runs'][0]['decisions']
    with s.connect() as c:c.execute("update chunks set payload=? where kind='decisions' and ordinal=0",(gzip.compress(b'{}\n'),))
    with pytest.raises(LabError,match='RESEARCH_INTEGRITY'):s.page(i,'0','decisions',0)


@pytest.mark.parametrize('blob',[b'[]',b'null',b'{}',gzip.compress(b'[]'),b'{broken'])
def test_invalid_manifest_types_never_http500(tmp_path,blob):
    s=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());i=s.enqueue(cfg);claim=s.claim(i);s.finish(i,synthetic_report(cfg,1),attempt=claim['attempt'])
    with s.connect() as c:c.execute('update queue set result=? where id=?',(blob,i))
    app=FastAPI();app.include_router(router);app.dependency_overrides[instance]=lambda:Service(tmp_path,store=s)
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_RELEASE'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='https://offline.invalid',auth=('aura','DUMMY_OWNER_RELEASE')) as c:
                response=await c.get('/api/research/experiments/'+i)
                assert response.status_code==503 and response.headers['cache-control']=='no-store'
    asyncio.run(work())


def test_explicit_external_durable_path_and_no_ephemeral_fallback(durable,tmp_path):
    for path in (tmp_path,ROOT/'.data/research',Path('/dev/shm/research')):
        with pytest.raises(LabError):location(path)
    assert configured_store(env={}) is None
    e=dict(AURA_RESEARCH_STATE_DIR=str(durable),AURA_RESEARCH_STORAGE_MODE='durable')
    ro=configured_store(env=e);assert ro.readonly
    with pytest.raises(sqlite3.Error):ro.enqueue(frozen_config('MEAN_REVERSION',available()))
    with pytest.raises(LabError):configured_store(writable=True,env=dict(e,RENDER='true'))
    with pytest.raises(LabError):configured_store(env=dict(e,AURA_RESEARCH_STORAGE_MODE='ephemeral'))


def test_backup_restore_preserves_manifest_chunks_and_reserved_budget(durable):
    from scripts.research_runner import backup,restore,state_store
    s=state_store(durable);cfg=frozen_config('MEAN_REVERSION',available());i=s.enqueue(cfg);claim=s.claim(i);r=synthetic_report(cfg,300)
    s.finish(i,r,attempt=claim['attempt']);s.reserve('openai','DUMMY_NO_PAID_CALL',7,10,10)
    with tempfile.TemporaryDirectory(prefix='.research-backup-test-',dir='/workspace') as folder:
        backup_dir=Path(folder)/'backup';new_dir=Path(folder)/'restored'
        backup(Namespace(state_dir=durable,dest=backup_dir));restore(Namespace(state_dir=new_dir,backup_dir=backup_dir))
        restored=state_store(new_dir);assert restored.materialize(i)==r and restored.calls()==s.calls()
        assert json.loads((new_dir/'aura-research-storage.json').read_text())==json.loads((durable/'aura-research-storage.json').read_text())
        with pytest.raises(LabError):restored.reserve('openai','DUMMY_NO_PAID_CALL',4,10,10)


def test_legacy_schema_not_automatically_modified(tmp_path):
    p=tmp_path/'.data/ai-research/ai-research-v1.sqlite3';p.parent.mkdir(parents=True)
    with sqlite3.connect(p) as c:c.execute('pragma application_id='+str(APP_ID));c.execute('create table legacy(value text)')
    before=p.read_bytes()
    with pytest.raises(LabError,match='RESEARCH_STORAGE_VERSION'):Store(tmp_path)
    assert p.read_bytes()==before


def test_terminal_default_viewer_cannot_enqueue_or_dispatch(tmp_path):
    from app.main import app
    saved=dict(app.dependency_overrides);app.dependency_overrides[instance]=lambda:Service(ROOT)
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_RELEASE',AURA_RESEARCH_LLM_ENABLED='true',AURA_RESEARCH_ROLE='workbench'),patch('app.research.experiment.execute',side_effect=AssertionError('NO_WEB_EXECUTE')),patch('subprocess.Popen',side_effect=AssertionError('NO_WEB_SPAWN')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid',auth=('aura','DUMMY_OWNER_RELEASE'),headers={'X-Aura-Lab':'research-only'}) as c:
                r=(await c.get('/api/research')).json();assert r['writable'] is False and r['llm']['status']=='AI_NOT_CONFIGURED' and r['queue']==[]
                for url in ('/api/research/queue','/api/research/queue/'+'a'*32+'/run','/api/research/ideas'):
                    response=await c.post(url,json={'hypothesis':'MEAN_REVERSION'} if url.endswith('/queue') else {})
                    assert response.status_code==403
                assert (await c.get('/api/health')).status_code==200
    try:asyncio.run(work())
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(saved)


def test_local_workbench_has_no_trading_routes_and_keeps_owner_auth(durable):
    from app.research.web import app
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_RELEASE',AURA_RESEARCH_STATE_DIR=str(durable),AURA_RESEARCH_STORAGE_MODE='durable',AURA_RESEARCH_LLM_ENABLED='false'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as c:
                assert (await c.get('/api/research')).status_code==401
                assert (await c.get('/api/research',auth=('aura','DUMMY_OWNER_RELEASE'))).json()['writable'] is True
                for path in ('/api/auto42/tick','/api/paper','/api/lab/run'):assert (await c.post(path)).status_code==404
    asyncio.run(work())


def test_render_runner_is_rejected_before_claim(durable):
    from scripts.research_runner import supervise,state_store
    s=state_store(durable);i=s.enqueue(frozen_config('MEAN_REVERSION',available()))
    args=Namespace(state_dir=durable,job_id=i,isolated_host=True,command='run',memory_mib=768,cpu_seconds=120,wall_seconds=180)
    with patch.dict('os.environ',RENDER='true'):
        with pytest.raises(LabError):supervise(args)
    assert s.get(i)['state']=='QUEUED'


def test_supervisor_wall_timeout_kills_process_and_records_error(durable):
    from scripts.research_runner import supervise,state_store
    real=subprocess.Popen
    def sleeping(cmd,**kwargs):return real([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
    s=state_store(durable);i=s.enqueue(frozen_config('MEAN_REVERSION',available()))
    args=Namespace(state_dir=durable,job_id=i,isolated_host=True,command='run',memory_mib=768,cpu_seconds=120,wall_seconds=1)
    with patch('scripts.research_runner.subprocess.Popen',side_effect=sleeping):r=supervise(args)
    assert r['state']=='ERROR' and r['error']=='WORKER_WALL_LIMIT' and r['elapsed_seconds']<10
    assert s.get(i)['report'] is None


@pytest.mark.parametrize('mode',['memory','cpu'])
def test_actual_linux_child_hard_limits(mode):
    program=r'''
from argparse import Namespace
from scripts import research_runner as w
from app.research import experiment,data
class Store:
 def get(self,*a):return {'state':'RUNNING','attempt':'token','config':{}}
w.state_store=lambda *a,**k:Store()
data.load_dataset=lambda:([],{})
def action(*a):
 if MODE=='memory':return bytearray(512*1024*1024)
 while True:pass
experiment.execute=action
try:w.sandbox_child(Namespace(command='_child',isolated_host=True,memory_mib=128,cpu_seconds=1,wall_seconds=5,state_dir='unused',job_id='test',attempt='token'))
except MemoryError:print('MEMORY_LIMIT_ENFORCED')
'''.replace('MODE',repr(mode))
    p=subprocess.run([sys.executable,'-c',program],cwd=ROOT,capture_output=True,text=True,timeout=10,env={'PATH':os.defpath,'LANG':'C.UTF-8'})
    if mode=='memory':assert p.returncode==0 and 'MEMORY_LIMIT_ENFORCED' in p.stdout
    else:assert p.returncode in (-signal.SIGXCPU,-signal.SIGKILL)


def test_fresh_terminal_import_does_not_load_dataset_or_replay():
    program="import sys; import app.main; assert 'scripts.research_lab_v2' not in sys.modules; assert 'app.research.strategies' not in sys.modules; print('LIGHT_VIEWER_ONLY')"
    r=subprocess.run([sys.executable,'-c',program],cwd=ROOT,capture_output=True,text=True,timeout=10)
    assert r.returncode==0 and 'LIGHT_VIEWER_ONLY' in r.stdout


def test_summary_event_history_is_bounded_and_can_page(tmp_path):
    s=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());i=s.enqueue(cfg)
    with s.connect() as c:
        for n in range(250):c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(i,n,'RESEARCHER','TEST_ONLY'))
    row=s.get(i);assert len(row['events'])==100 and row['event_total']==251
    after=0;all_rows=[]
    while True:
        p=s.events(i,after);all_rows+=p['events']
        if not p['events']:break
        after=p['next_after']
    assert len(all_rows)==251


def test_oversized_corrupt_result_not_loaded_into_web_memory(tmp_path):
    s=Store(tmp_path);cfg=frozen_config('MEAN_REVERSION',available());i=s.enqueue(cfg)
    with s.connect() as c:c.execute('update queue set result=? where id=?',(b'X'*(COMPACT_LIMIT+1),i))
    with pytest.raises(LabError,match='RESEARCH_INTEGRITY'):s.get(i)


def test_supervisor_strips_trading_and_llm_secrets_before_child(durable):
    from scripts.research_runner import supervise,state_store
    s=state_store(durable);i=s.enqueue(frozen_config('MEAN_REVERSION',available()));captured={}
    class Process:
        pid=999999
        def wait(self,timeout):return 1
        def poll(self):return 1
    def spawn(cmd,**kwargs):captured.update(kwargs);return Process()
    args=Namespace(state_dir=durable,job_id=i,isolated_host=True,command='run',memory_mib=768,cpu_seconds=120,wall_seconds=180)
    with patch.dict('os.environ',SUPABASE_SERVICE_ROLE_KEY='DUMMY_DB_SECRET',BYBIT_DEMO_API_KEY='DUMMY_EXCHANGE_SECRET',AURA_RESEARCH_LLM_API_KEY='DUMMY_LLM_SECRET'),patch('scripts.research_runner.subprocess.Popen',side_effect=spawn):r=supervise(args)
    assert r['state']=='ERROR'
    assert set(captured['env'])=={'PATH','LANG','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS'}
    assert 'DUMMY_' not in json.dumps(captured['env'])
