"""Local Render-like acceptance, NEVER a Render deployment or production runner.

Uses a sanitized subprocess, real uvicorn TCP/lifespan, Git-archived checkout,
public frozen report, temporary databases and loopback-only network guards.
"""
import argparse
import asyncio
import base64
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
OWNER='DUMMY_LOCAL_STAGING_OWNER_ONLY'
AUTH=('aura',OWNER)


def require(value,message):
    if not value:raise AssertionError(message)


def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


def process_usage(pid):
    try:
        status=Path(f'/proc/{pid}/status').read_text();stats=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()
        rss=next(int(x.split()[1])/1024 for x in status.splitlines() if x.startswith('VmRSS:'))
        hwm=next(int(x.split()[1])/1024 for x in status.splitlines() if x.startswith('VmHWM:'))
        virtual=next(int(x.split()[1])/1024 for x in status.splitlines() if x.startswith('VmSize:'))
        return dict(rss_mib=rss,high_water_rss_mib=hwm,virtual_mib=virtual,cpu_seconds=(int(stats[11])+int(stats[12]))/os.sysconf('SC_CLK_TCK'))
    except (OSError,StopIteration):return dict(rss_mib=0,cpu_seconds=0)


def env_for(checkout,port,render=True,poll=False):
    sandbox=checkout.parent
    return dict(PATH=os.defpath,LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
        PORT=str(port),AURA_TESTNET_VIEW_PASSWORD=OWNER,RENDER='true' if render else '',AURA_RESEARCH_LLM_ENABLED='false',
        PAPER_DB_PATH=str(sandbox/'paper.sqlite3'),LAB_DB_PATH=str(sandbox/'lab.sqlite3'),
        AURA_AUTO42_SQLITE_PATH='' if render else str(sandbox/'auto-paper-42.sqlite3'),
        AURA_STAGING_AS_MIB='1536',AURA_STAGING_SANDBOX=str(sandbox),AURA_STAGING_SANDBOX_POLL='true' if poll else 'false')


@contextmanager
def server(checkout,render=True,poll=False):
    port=free_port();url=f'http://127.0.0.1:{port}';log=checkout.parent/'web.log'
    with log.open('ab') as f:
        p=subprocess.Popen([sys.executable,str(ROOT/'scripts/staging/web_child.py'),str(checkout)],cwd=checkout,env=env_for(checkout,port,render,poll),stdout=f,stderr=f,start_new_session=True)
        try:
            deadline=time.monotonic()+30
            with httpx.Client(trust_env=False,timeout=1) as c:
                while True:
                    require(p.poll() is None,'WEB_PROCESS_EXITED_BEFORE_READY')
                    try:
                        if c.get(url+'/api/health').status_code==200:break
                    except httpx.HTTPError:pass
                    require(time.monotonic()<deadline,'WEB_STARTUP_TIMEOUT');time.sleep(.05)
            yield url,p
        except BaseException:
            shutil.copyfile(log,Path('/tmp/aura-staging-failure-web.log'))
            raise
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()


async def load_test(url,pid,ident,requests=240,concurrency=12):
    paths=['/api/health','/api/research',f'/api/research/experiments/{ident}/records?run_key=0&kind=decisions&limit=100','/api/paper/state']
    samples=[];rss=[];semaphore=asyncio.Semaphore(concurrency);before=process_usage(pid);start=time.perf_counter()
    async with httpx.AsyncClient(base_url=url,auth=AUTH,trust_env=False,timeout=20) as c:
        async def one(i):
            async with semaphore:
                t=time.perf_counter();r=await c.get(paths[i%len(paths)]);duration=time.perf_counter()-t
                require(r.status_code==200,'LOAD_HTTP_STATUS_'+str(r.status_code)+'_ROUTE_'+paths[i%len(paths)]);samples.append((paths[i%len(paths)],duration));rss.append(process_usage(pid)['rss_mib'])
        await asyncio.gather(*(one(i) for i in range(requests)))
    elapsed=time.perf_counter()-start;after=process_usage(pid);cpu=after['cpu_seconds']-before['cpu_seconds']
    def metrics(values):
        v=sorted(values);return dict(requests=len(v),p50_ms=v[len(v)//2]*1000,p95_ms=v[min(len(v)-1,int(len(v)*.95))]*1000,max_ms=max(v)*1000)
    return dict(**metrics([v for _,v in samples]),concurrency=concurrency,elapsed_seconds=elapsed,cpu_seconds=cpu,mean_one_core_cpu_percent=100*cpu/elapsed,baseline_rss_mib=before['rss_mib'],peak_sampled_rss_mib=max(rss),end_rss_mib=after['rss_mib'],process_high_water_rss_mib=after['high_water_rss_mib'],end_virtual_mib=after['virtual_mib'],per_route={path:metrics([v for p,v in samples if p==path]) for path in paths},http_errors=0)


def browser_check(url,sandbox):
    """Real Chromium DOM and JS; no paid browser service or package install."""
    from websockets.sync.client import connect
    binary=shutil.which('chromium')
    require(binary,'CHROMIUM_NOT_AVAILABLE');port=free_port()
    cmd=[binary,'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--no-first-run','--no-default-browser-check',
        '--proxy-server=http://127.0.0.1:9',f'--user-data-dir={sandbox}/browser-profile',f'--remote-debugging-port={port}','--remote-debugging-address=127.0.0.1','about:blank']
    with (sandbox/'browser.log').open('wb') as log:
        p=subprocess.Popen(cmd,env={'PATH':os.defpath,'LANG':'C.UTF-8'},stdout=log,stderr=log,start_new_session=True)
        try:
            with httpx.Client(trust_env=False,timeout=1) as c:
                deadline=time.monotonic()+15
                while True:
                    try:pages=c.get(f'http://127.0.0.1:{port}/json/list').json();break
                    except (httpx.HTTPError,ValueError):
                        require(time.monotonic()<deadline,'BROWSER_STARTUP_TIMEOUT');time.sleep(.1)
            with connect(pages[0]['webSocketDebuggerUrl'],proxy=None,open_timeout=5) as ws:
                sequence=0
                def call(method,params=None):
                    nonlocal sequence
                    sequence+=1;ident=sequence;ws.send(json.dumps(dict(id=ident,method=method,params=params or {})))
                    while True:
                        message=json.loads(ws.recv(timeout=20))
                        if message.get('id')==ident:
                            require('error' not in message,'BROWSER_CDP_ERROR');return message.get('result',{})
                def evaluate(expression):
                    r=call('Runtime.evaluate',dict(expression=expression,awaitPromise=True,returnByValue=True));require('exceptionDetails' not in r,'BROWSER_JS_EXCEPTION');return r['result'].get('value')
                call('Network.enable');call('Network.setExtraHTTPHeaders',dict(headers={'Authorization':'Basic '+base64.b64encode(('aura:'+OWNER).encode()).decode()}))
                call('Page.navigate',dict(url=url+'/static/research.html'))
                def wait(expression):
                    deadline=time.monotonic()+20
                    while not evaluate(expression):
                        require(time.monotonic()<deadline,'BROWSER_DOM_TIMEOUT');time.sleep(.1)
                wait("!!document.getElementById('research-refresh')")
                evaluate("document.getElementById('research-refresh').click()")
                wait("document.getElementById('research-queue').children.length===1 && !document.getElementById('research-refresh').disabled")
                require(evaluate("document.getElementById('research-ai').textContent.includes('AI_NOT_CONFIGURED')"),'BROWSER_FALSE_AI_STATUS')
                evaluate("document.getElementById('research-queue').querySelector('button').click()")
                wait("document.getElementById('research-metrics').children.length===7 && !document.getElementById('research-refresh').disabled")
                require(evaluate("document.getElementById('research-audit').textContent.includes('REJECTED')"),'BROWSER_AUDITOR_MISSING')
                evaluate("document.getElementById('research-kind').value='decisions';document.getElementById('research-load-records').click()")
                wait("document.getElementById('research-records').textContent.length>100 && !document.getElementById('research-refresh').disabled")
                require(evaluate("['enqueue','recover','idea'].every(k=>document.getElementById('research-'+k).disabled)"),'BROWSER_MUTATION_ENABLED')
                return dict(status='PASS',engine='ACTUAL_LOCAL_CHROMIUM_HEADLESS',research_page=True,authenticated_refresh=True,experiment_history=True,seven_run_metrics=True,auditor_rejected=True,large_records_page=True,mutations_disabled=True,llm_status='AI_NOT_CONFIGURED',sandbox_note='Disposable browser profile; Chromium --no-sandbox required by container; not a browser security certification')
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()



def git_snapshot_roundtrip(approved, sandbox):
    """Local Git only: commit/checkout public fixture, no remote, no source repo writes."""
    repository=sandbox/'snapshot-source';target=repository/'docs/research-snapshot';target.parent.mkdir(parents=True)
    shutil.copytree(approved,target)
    env=dict(PATH=os.defpath,LANG='C.UTF-8',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
    def git(*args):
        return subprocess.check_output(['git','-C',str(repository),'-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',*args],env=env,text=True).strip()
    git('init','-q');git('add','docs/research-snapshot')
    git('-c','user.name=Aura Local Staging','-c','user.email=staging@example.invalid','commit','-qm','Public snapshot local restart fixture')
    commit=git('rev-parse','HEAD');archive=sandbox/'snapshot.tar'
    git('archive','--output',str(archive),'HEAD')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in approved.iterdir()}
    shutil.rmtree(approved)
    with tarfile.open(archive) as t:t.extractall(approved.parents[1],filter='data')
    require(before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in approved.iterdir()},'GIT_SNAPSHOT_ROUNDTRIP_MISMATCH')
    require(not git('remote'),'UNEXPECTED_SNAPSHOT_REMOTE')
    return dict(status='PASS',local_commit=commit,files=len(before),hashes_equal=True,remote_configured=False,remote_publication=False)


def verify(scratch_parent,output,poll=False):
    from app.research.storage import Store
    from app.research.snapshot import export_snapshot,SnapshotStore
    from app.research.persistence import initialize
    from scripts.research_runner import backup,restore,state_store
    from types import SimpleNamespace
    require(not os.getenv('RENDER'),'LOCAL_ONLY_NOT_RENDER')
    require(not output.exists(),'OUTPUT_MUST_BE_NEW')
    source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='.aura-staging-',dir=scratch_parent) as folder:
        sandbox=Path(folder);checkout=sandbox/'checkout';checkout.mkdir();archive=sandbox/'source.tar'
        subprocess.run(['git','archive','--output',str(archive),'HEAD'],cwd=ROOT,check=True)
        with tarfile.open(archive) as t:t.extractall(checkout,filter='data')
        archive.unlink()
        state=sandbox/'research-state';initialize(state);store=state_store(state)
        report=json.loads(gzip.decompress((checkout/'docs/AI_RESEARCH_V1/VOLATILITY_BREAKOUT.json.gz').read_bytes()))
        ident=store.enqueue(report['config']);claim=store.claim(ident);store.finish(ident,report,attempt=claim['attempt'])
        require(store.materialize(ident)==report,'SOURCE_REPORT_RECONSTRUCTION_MISMATCH')
        approved=checkout/'docs/research-snapshot';exported=export_snapshot(store,ident,approved)
        git_transfer=git_snapshot_roundtrip(approved,sandbox)
        require(SnapshotStore(approved).verify()['checksum']==exported['checksum'],'GIT_CHECKED_OUT_SNAPSHOT_INVALID')
        backup_dir=sandbox/'backup';restore_dir=sandbox/'restored'
        backup(SimpleNamespace(state_dir=state,dest=backup_dir));restore(SimpleNamespace(backup_dir=backup_dir,state_dir=restore_dir))
        require(state_store(restore_dir,readonly=True).materialize(ident)==report,'BACKUP_RESTORE_MISMATCH')
        try:export_snapshot(store,ident,approved)
        except Exception as e:require(getattr(e,'code',None)=='RESEARCH_ALREADY_PROCESSED','DUPLICATE_NOT_CONTROLLED')
        else:raise AssertionError('DUPLICATE_EXPORT_ALLOWED')
        with server(checkout,poll=poll) as (url,proc):
            with httpx.Client(base_url=url,trust_env=False,timeout=20) as c:
                require(c.get('/api/research').status_code==401,'ANONYMOUS_ALLOWED');require(c.get('/api/research',auth=('aura','DUMMY_WRONG')).status_code==401,'WRONG_PASSWORD_ALLOWED')
                c.auth=AUTH
                overview=c.get('/api/research');require(overview.status_code==200,'OVERVIEW_FAILED');data=overview.json();require(not data['writable'] and data['llm']['status']=='AI_NOT_CONFIGURED','RESEARCH_NOT_READONLY')
                require(c.get(f'/api/research/experiments/{ident}').json()['report']['logical_report_checksum']==report['checksum'],'HTTP_REPORT_MISMATCH')
                paper_before=c.get('/api/paper/state').json()
                lab=c.get('/api/lab/v2');require(lab.status_code==200,'STRATEGY_LAB_INCOMPATIBLE')
                monitor=c.get('/api/auto42/live-monitor');require(monitor.status_code==503 and monitor.json()['live_cycle_verified'] is False,'UNCONFIGURED_MONITOR_NOT_FAIL_CLOSED')
                for path in ('/api/research/queue',f'/api/research/queue/{ident}/run','/api/research/ideas','/api/research/recover-interrupted'):
                    r=c.post(path,headers={'X-Aura-Lab':'research-only'},json={'hypothesis':'MEAN_REVERSION'} if path.endswith('/queue') else {})
                    require(r.status_code==403,'RESEARCH_MUTATION_ALLOWED')
                require(c.post('/api/research/import').status_code in (404,405),'HTTP_IMPORT_EXISTS')
                ui=browser_check(url,sandbox)
                performance=asyncio.run(load_test(url,proc.pid,ident))
                chunk=approved/'chunk-0-decisions-0.gz';original=chunk.read_bytes();chunk.write_bytes(b'corrupted-staging-only')
                r=c.get(f'/api/research/experiments/{ident}/records?run_key=0&kind=decisions');require(r.status_code==503,'CORRUPT_CHUNK_NOT_CONTROLLED_'+str(r.status_code));require(c.get('/api/health').status_code==200,'CORRUPT_CHUNK_KILLS_HEALTH')
                chunk.write_bytes(original);require(c.get(f'/api/research/experiments/{ident}/records?run_key=0&kind=decisions').status_code==200,'CHUNK_RECOVERY_FAILED')
                require(c.get('/api/paper/state').json()==paper_before,'PAPER_STATE_CHANGED')
        # Fresh process loads the identical immutable artifact and persisted local ledger.
        with server(checkout,poll=poll) as (url,proc):
            with httpx.Client(base_url=url,trust_env=False,timeout=20,auth=AUTH) as c:
                require(c.get(f'/api/research/experiments/{ident}').json()['report']['logical_report_checksum']==report['checksum'],'RESTART_LOST_REPORT')
                require(c.get('/api/paper/state').json()==paper_before,'RESTART_CHANGED_PAPER_STATE')
        index=approved/'index.json';original_index=index.read_bytes();index.write_bytes(b'[]')
        with server(checkout,poll=poll) as (url,proc):
            with httpx.Client(base_url=url,trust_env=False,timeout=20,auth=AUTH) as c:
                require(c.get('/api/research').status_code==503,'CORRUPT_INDEX_NOT_CONTROLLED');require(c.get('/api/health').status_code==200,'CORRUPT_INDEX_KILLS_TERMINAL')
        index.write_bytes(original_index)
        # Secondary local-SQLite profile: real monitor routes, default OFF, no ticks/orders.
        with server(checkout,render=False,poll=poll) as (url,proc):
            with httpx.Client(base_url=url,trust_env=False,timeout=20,auth=AUTH) as c:
                m=c.get('/api/auto42/live-monitor');require(m.status_code==200 and not m.json()['live_cycle_verified'],'LOCAL_MONITOR_INCOMPATIBLE_'+str(m.status_code)+'_'+str(m.json().get('reason')))
                require(c.get('/api/research').status_code==200,'RECOVERY_FAILED')
                monitor_status=m.json()['status']
        result=dict(status='PASS',release_ready=False,render_staging_verified=False,location='LOCAL_LINUX_SANDBOX_NOT_RENDER',source_head=source_head,
            actual_start_web=True,actual_lifespan=True,actual_tcp_http=True,render_environment_simulated=True,main_profile_auto42='FAIL_CLOSED_NO_SUPABASE_CONFIGURED',secondary_profile_monitor=monitor_status,
            environment_allowlisted=True,production_supabase_access=False,trading_api_credentials=False,external_network_denied=True,web_address_space_cap_mib=1536,
            browser=ui,performance=performance,git_transfer=git_transfer,storage=dict(source_report_bytes=len(json.dumps(report,separators=(',',':'),ensure_ascii=False).encode()),snapshot_checksum=exported['checksum'],restart=True,backup_restore=True,duplicate_rejected=True,corrupt_chunk_503=True,corrupt_index_503=True,error_recovery=True,git_snapshot_checked_out=True,actual_git_publication=False,private_data_published=False,physical_disk_durability_attested=False),
            paper_state_unchanged=True,research_http_mutations_forbidden=True,no_http_import=True,paid_resources_created=False,paid_api=False,
            limitations=['Local VM is not Render hardware/plan, TLS/proxy or persistent-disk verification; address-space cap is not RSS/cgroup RAM','External market/Supabase unavailable by design; configured production autonomous flow not exercised','No full browser penetration test; disposable Chromium container mode','Bounded local load is not a sustained production capacity guarantee','Git checkout snapshot remains durable only when reviewed source/backup is retained'])
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scratch-parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sandbox-poll',action='store_true');a=p.parse_args()
    try:result=verify(a.scratch_parent,a.output,a.sandbox_poll);print(json.dumps(dict(status=result['status'],release_ready=False,render_staging_verified=False)));return 0
    except Exception as e:print(json.dumps(dict(status='FAIL',error_type=type(e).__name__,message=str(e) if isinstance(e,AssertionError) else 'STAGING_VERIFICATION_FAILED')));return 1

if __name__=='__main__':raise SystemExit(main())
