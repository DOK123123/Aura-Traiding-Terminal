"""Explicit OFFLINE test: fake public quotes + SQLite-backed mock Supabase RPC.

Real Chromium/HTTP/API/engine, never Render or a Supabase live-execution proof.
No test-quote endpoint is added to the application.
"""
import argparse
import asyncio
import base64
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
PASSWORD='DUMMY_OFFLINE_PRACTICE_OWNER'

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def child(folder,listen):
    if os.getenv('AURA_PRACTICE_OFFLINE_TEST_ONLY')!='true' or os.getenv('RENDER'):raise SystemExit('OFFLINE_GUARD')
    import httpx
    import uvicorn
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from tests.test_practice import RPC
    from app.practice.storage import Store
    from app.practice.service import Service
    from app.practice.api import router
    from app.practice.core import SOURCE
    class FakeQuotes:
        async def get(self):
            return dict(price=(folder/'price').read_text(),time_ms=int(time.time()*1000),trade_id=time.time_ns(),source=SOURCE)
        async def close(self):pass
    rpc=RPC(folder/'mock-rpc.sqlite3')
    svc=Service(Store('https://abcdefghijkl.supabase.co','DUMMY_KEY_'+'x'*40,httpx.MockTransport(rpc)),FakeQuotes())
    @asynccontextmanager
    async def lifespan(app):
        app.state.practice=svc;svc.start()
        try:yield
        finally:await svc.close()
    app=FastAPI(lifespan=lifespan);app.include_router(router);app.mount('/static',StaticFiles(directory=ROOT/'static'))
    uvicorn.run(app,host='127.0.0.1',port=listen,access_log=False)


def run(output):
    if os.getenv('RENDER'):raise SystemExit('OFFLINE_ONLY')
    import httpx
    from websockets.sync.client import connect
    if output.exists():raise ValueError('Output must be new')
    chrome=shutil.which('chromium')
    if not chrome:raise RuntimeError('Chromium not installed; NOT RUN')
    with tempfile.TemporaryDirectory(prefix='aura-practice-offline-') as temp:
        folder=Path(temp);(folder/'price').write_text('100');listen=port();debug=port();base=f'http://127.0.0.1:{listen}'
        env=dict(PATH=os.defpath,LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',AURA_TESTNET_VIEW_PASSWORD=PASSWORD,AURA_PRACTICE_OFFLINE_TEST_ONLY='true')
        procs=[]
        with (folder/'logs').open('wb') as log:
            def launch_web():
                p=subprocess.Popen([sys.executable,'-m','scripts.verify_practice_offline','--child',str(folder),'--port',str(listen)],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);procs.append(p)
                for _ in range(150):
                    if p.poll() is not None:raise RuntimeError('Offline server exited')
                    try:
                        if httpx.get(base+'/api/practice/state',auth=('aura',PASSWORD),trust_env=False,timeout=1).status_code==200:return p
                    except httpx.HTTPError:pass
                    time.sleep(.05)
                raise RuntimeError('Offline server timeout')
            def stop(p):
                if p.poll() is None:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            try:
                web=launch_web();p=subprocess.Popen([chrome,'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--proxy-server=http://127.0.0.1:9',f'--user-data-dir={folder}/browser',f'--remote-debugging-port={debug}','about:blank'],env={'PATH':os.defpath,'LANG':'C.UTF-8'},stdout=log,stderr=log,start_new_session=True);procs.append(p)
                for _ in range(150):
                    try:pages=httpx.get(f'http://127.0.0.1:{debug}/json/list',trust_env=False,timeout=1).json();break
                    except (httpx.HTTPError,ValueError):time.sleep(.05)
                else:raise RuntimeError('Offline Chromium timeout')
                with connect(pages[0]['webSocketDebuggerUrl'],proxy=None) as ws:
                    sequence=0
                    def call(method,params=None):
                        nonlocal sequence
                        sequence+=1;i=sequence;ws.send(json.dumps(dict(id=i,method=method,params=params or {})))
                        while True:
                            m=json.loads(ws.recv(timeout=15))
                            if m.get('id')==i:
                                if 'error' in m:raise RuntimeError('CDP error')
                                return m.get('result',{})
                    def evaluate(js):
                        r=call('Runtime.evaluate',dict(expression=js,returnByValue=True,awaitPromise=True))
                        if 'exceptionDetails' in r:raise RuntimeError('Browser JS error')
                        return r['result'].get('value')
                    def wait(js):
                        for _ in range(150):
                            if evaluate(js):return
                            time.sleep(.1)
                        raise RuntimeError('Offline UI timeout: '+js+'; '+str(evaluate("['status','quote','position','storage'].map(k=>document.getElementById(k)?.textContent).join(' | ')")))
                    call('Network.enable');call('Network.setExtraHTTPHeaders',dict(headers={'Authorization':'Basic '+base64.b64encode(('aura:'+PASSWORD).encode()).decode()}))
                    call('Page.navigate',dict(url=base+'/static/practice.html'))
                    wait("document.readyState==='complete' && !!document.getElementById('connect')")
                    evaluate("document.getElementById('connect').click()")
                    wait("!document.getElementById('long').disabled")
                    wait("!!document.querySelector('#chart canvas')")
                    evaluate("document.getElementById('sl').value='98';document.getElementById('tp').value='104';document.getElementById('long').click()")
                    wait("!document.getElementById('close').disabled && document.getElementById('status').textContent.includes('подтверждено')")
                    (folder/'price').write_text('101')
                    wait("document.getElementById('events').textContent.includes('UPDATE')")
                    evaluate("document.getElementById('close').click()")
                    wait("document.getElementById('events').textContent.includes('CLOSE') && !document.getElementById('long').disabled")
                    with httpx.Client(base_url=base,auth=('aura',PASSWORD),trust_env=False) as client:
                        before=client.get('/api/practice/state').json();assert before['state']['position'] is None
                        kinds=[e['kind'] for e in before['events']];assert kinds.count('OPEN')==1 and kinds.count('CLOSE')==1 and 'UPDATE' in kinds
                        stop(web);launch_web();after=client.get('/api/practice/state').json();assert before['state']==after['state']
                    result=dict(status='PASS',scope='OFFLINE_FAKE_QUOTES_MOCK_SUPABASE_ONLY',real_chromium=True,real_http_api=True,existing_execution_engine=True,open_update_manual_close=True,confirmed_receipt_displayed=True,chart_position=True,open_count=1,close_count=1,persisted_balance=after['state']['balance'],restart_same_state=True,real_render_verified=False,real_supabase_verified=False,paid_api=False,production_access=False)
                    output.parent.mkdir(parents=True,exist_ok=True)
                    with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
                    print(json.dumps(result))
            finally:
                for p in reversed(procs):stop(p)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--child',type=Path);parser.add_argument('--port',type=int);parser.add_argument('--output',type=Path);a=parser.parse_args()
    if a.child:child(a.child,a.port)
    elif a.output:run(a.output)
    else:parser.error('--output required')
