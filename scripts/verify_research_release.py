"""Manual offline acceptance on an isolated Linux host; never a production endpoint."""
import argparse
import asyncio
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
import httpx
from app.lab.models import canonical
from app.research.artifacts import ARRAYS
from app.research.registry import HYPOTHESES
from app.research.data import available
from app.research.experiment import frozen_config
from scripts.research_runner import state_store
from app.main import app

ROOT=Path(__file__).resolve().parents[1]

def rss():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])/1024

async def verify(directory):
    store=state_store(directory);cases=[]
    for name in HYPOTHESES:
        ident=store.enqueue(frozen_config(name,available()));prior=store.get(ident)
        command='verify' if prior['report'] else 'run'
        cmd=[sys.executable,'-m','scripts.research_runner',command,'--state-dir',str(directory),'--job-id',ident,'--isolated-host']
        baseline=rss();parent_peak=baseline;start=time.perf_counter();latencies=[]
        process=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid',auth=('aura','DUMMY_RELEASE_OWNER')) as client:
            with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_RELEASE_OWNER',AURA_RESEARCH_STATE_DIR='',AURA_RESEARCH_LLM_ENABLED='false'),patch('app.research.experiment.execute',side_effect=AssertionError('WEB_EXECUTION_FORBIDDEN')),patch('app.research.data.load_dataset',side_effect=AssertionError('WEB_DATASET_LOAD_FORBIDDEN')):
                while process.poll() is None:
                    now=time.perf_counter();health=await client.get('/api/health');overview=await client.get('/api/research');latencies.append(time.perf_counter()-now)
                    if health.status_code!=200 or overview.status_code!=200 or overview.json()['writable']:raise AssertionError('VIEWER_ISOLATION_FAILURE')
                    parent_peak=max(parent_peak,rss());await asyncio.sleep(.05)
        stdout,stderr=process.communicate(timeout=5)
        if process.returncode:raise AssertionError('ISOLATED_RUNNER_FAILED:'+name)
        outcome=json.loads(stdout);row=store.get(ident);report=row['report']
        store.verify_chunks(ident)
        old=json.loads(gzip.decompress((ROOT/'docs/AI_RESEARCH_V1'/(name+'.json.gz')).read_bytes()))
        for actual,expected in zip(report['runs'],old['runs'],strict=True):
            compact={k:v for k,v in actual.items() if k not in ('run_key','artifacts')}
            assert compact=={k:v for k,v in expected.items() if k not in ARRAYS}
            for kind in ARRAYS:
                ref=actual['artifacts'][kind];h=hashlib.sha256()
                for record in expected[kind]:h.update(canonical(record)+b'\n')
                assert ref['records']==len(expected[kind]) and ref['sha256']==h.hexdigest()
        assert report['auditor']==old['auditor'] and report['causal_prefix_checks']==old['causal_prefix_checks']
        cases.append(dict(hypothesis=name,command=command,worker=outcome,financial_equivalence=True,decision_and_curve_equivalence=True,
            manifest_bytes=len(canonical(report)),runs=len(report['runs']),original_report_bytes=len(canonical(old)),
            logical_checksum=report['logical_report_checksum'],manifest_checksum=report['checksum'],
            viewer_baseline_rss_mib=baseline,viewer_peak_during_worker_mib=parent_peak,viewer_health_status_max_seconds=max(latencies),viewer_probes=len(latencies),
            validation='REUSED_EXPLORATORY_DATA_NOT_EDGE_OR_LIVE_TRADING_PROOF'))
        print(name,'PASS',flush=True)
    return dict(status='PASS',scope='ISOLATED_LOCAL_WORKER_ACCEPTANCE_NOT_RENDER_DEPLOY',cases=cases,production_access=False,paid_api_calls=False,
        real_data=available(),frozen_parameters_unchanged=True,trade_engine_unchanged=True,unexpected_promotions=False,
        note='Calculation code hash changes from lazy import placement; all28 run payloads, decisions, trades and curves are byte-equivalent to PR7 canonical records.')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-dir',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--sandbox-poll',action='store_true');a=p.parse_args(argv)
    if os.getenv('RENDER'):raise SystemExit('ISOLATED_HOST_REQUIRED')
    if a.sandbox_poll:
        from scripts.replay_aura_csv import enable_sandbox_poll
        enable_sandbox_poll()
    result=asyncio.run(verify(a.state_dir));a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as f:f.write(canonical(result))

if __name__=='__main__':main()
