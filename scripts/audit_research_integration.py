"""Offline integration/resource audit. Temporary research DB; no production lifespan.

No Render, Supabase, external market request or LLM call. Fixed bundled real data.
"""
import argparse
import asyncio
from contextlib import ExitStack
import gzip
import json
from pathlib import Path
import resource
import socket
import tempfile
import threading
import time
from unittest.mock import patch
import httpx
from app.lab.models import canonical
from app.research.service import Service
from app.research.llm import Advisor
from app.research.api import instance
from app.main import app

ROOT=Path(__file__).resolve().parents[1]

def rss_mib():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])/1024
    raise RuntimeError('LINUX_RSS_UNAVAILABLE')

async def run(name:str):
    before=rss_mib();cpu0=resource.getrusage(resource.RUSAGE_SELF);rss=[];phase=['manual_http_run'];done=threading.Event()
    def sampler():
        while not done.wait(.02):rss.append((phase[0],rss_mib()))
    monitor=threading.Thread(target=sampler,daemon=True);monitor.start()
    health=[];loop_gaps=[];start=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='aura-integration-bench-') as folder:
            svc=Service(Path(folder),advisor=None);app.dependency_overrides[instance]=lambda:svc
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid',auth=('aura','DUMMY_OWNER_ONLY'),headers={'X-Aura-Lab':'research-only'}) as client:
                ident=(await client.post('/api/research/queue',json={'hypothesis':name})).json()['id']
                task=asyncio.create_task(client.post('/api/research/queue/'+ident+'/run',json={}))
                async def probe():
                    last=time.perf_counter()
                    while not task.done():
                        await asyncio.sleep(.02);now=time.perf_counter();loop_gaps.append(now-last);last=now
                        t=time.perf_counter();response=await client.get('/api/health');health.append(time.perf_counter()-t)
                        if response.status_code!=200:raise AssertionError('HEALTH_FAILURE')
                await probe();response=await task
                if response.status_code!=200:raise AssertionError('RESEARCH_HTTP_FAILURE')
                summary=response.json();phase[0]='owner_full_export'
                t=time.perf_counter();export=await client.get('/api/research/experiments/'+ident+'/export');export_elapsed=time.perf_counter()-t
                if export.status_code!=200:raise AssertionError('EXPORT_FAILURE')
                db_bytes=svc.store.path.stat().st_size
                statuses={r['split']+':'+r['scale']:r['status'] for r in summary['report']['audits']}
                elapsed=time.perf_counter()-start;cpu=resource.getrusage(resource.RUSAGE_SELF)
                peak=max([value for _,value in rss]+[rss_mib(),cpu.ru_maxrss/1024])
                phase_peaks={key:max((value for label,value in rss if label==key),default=before) for key in ('manual_http_run','owner_full_export')}
                done.set();monitor.join(timeout=1)
                # Verify historical identity only AFTER resource profiling to avoid counting
                # an extra decoded reference artifact as normal server memory.
                expected=json.loads(gzip.decompress((ROOT/'docs/AI_RESEARCH_V1'/(name+'.json.gz')).read_bytes()))
                if summary['report']['checksum']!=expected['checksum']:raise AssertionError('REAL_REPRODUCIBILITY_FAILURE')
            return dict(scope='OFFLINE_CURRENT_BRANCH_NO_PRODUCTION_LIFESPAN',hypothesis=name,status=summary['state'],
                real_replay_identical=True,source_sha256=summary['report']['source']['sha256'],checksum=summary['report']['checksum'],audits=statuses,
                baseline_import_rss_mib=before,peak_rss_mib=peak,phase_peak_rss_mib=phase_peaks,
                elapsed_seconds=elapsed,cpu_user_seconds=cpu.ru_utime-cpu0.ru_utime,
                cpu_system_seconds=cpu.ru_stime-cpu0.ru_stime,
                health_probes=len(health),health_max_seconds=max(health,default=0),health_mean_seconds=sum(health)/max(len(health),1),
                event_loop_probe_max_gap_seconds=max(loop_gaps,default=0),full_export_seconds=export_elapsed,full_export_bytes=len(export.content),
                temporary_research_database_bytes=db_bytes,render_plan='UNKNOWN_NOT_ACCESSED',render_memory='UNKNOWN',render_restart='NOT_TESTED',
                production_supabase='NOT_ACCESSED',llm='DISABLED_NOT_CALLED',render_sizing_guarantee=False)
    finally:
        app.dependency_overrides.pop(instance,None);done.set();monitor.join(timeout=1)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--hypothesis',choices=['MEAN_REVERSION','LIQUIDITY_SWEEP','VOLATILITY_BREAKOUT','REGIME_SWITCHING'],default='REGIME_SWITCHING');p.add_argument('--sandbox-poll',action='store_true');a=p.parse_args(argv)
    if a.sandbox_poll:
        from scripts.replay_aura_csv import enable_sandbox_poll
        enable_sandbox_poll()
    def deny(*args,**kwargs):raise AssertionError('OFFLINE_AUDIT_NETWORK_OR_LLM_FORBIDDEN')
    original=socket.socket.connect
    def connect(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):return deny()
        return original(sock,address)
    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket,'connect',connect));stack.enter_context(patch.object(Advisor,'propose',deny))
        stack.enter_context(patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_ONLY',AURA_RESEARCH_LLM_ENABLED='false'))
        result=asyncio.run(run(a.hypothesis))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as f:f.write(canonical(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('audits','checksum')}))

if __name__=='__main__':main()
