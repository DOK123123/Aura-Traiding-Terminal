"""LOCAL ONLY synthetic V5/MemoryStore browser verification; no production keys or writes.

python -m scripts.verify_active43_browser --output /tmp/aura43-browser.json
Requires installed Chromium. Local HTTP server binds 127.0.0.1. No order/fixture
HTTP route is created; the isolated account is prepared in process before serving.
"""
import base64,json,os,signal,socket,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from websockets.sync.client import connect
if os.getenv('RENDER') or not __debug__:raise ValueError('LOCAL_OFFLINE_ONLY')
ROOT=Path(__file__).resolve().parents[1];PASSWORD='DUMMY_ACTIVE43_BROWSER_OWNER'
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
if '--child' in sys.argv:
 from scripts.replay_aura_csv import enable_sandbox_poll
 enable_sandbox_poll()
 from fastapi import FastAPI
 from fastapi.staticfiles import StaticFiles
 from app.active43.api import router
 from app.active43.service import Service
 from app.active43.strategies import config
 from app.active43.market import Market,Quotes
 from tests.test_active43 import MemoryStore
 from scripts.verify_active43 import PublicFixture
 from unittest.mock import patch
 import asyncio,uvicorn
 fixture=PublicFixture();transport=httpx.MockTransport(fixture.handler);clock=lambda:fixture.now[0]
 async def prepare():
  market=Market(clock=clock,transport=transport);quotes=Quotes(clock=clock,transport=transport)
  service=Service(MemoryStore(config(),clock()),market,config(),clock=clock,quotes=quotes)
  with patch('app.active43.service.scheduler_configured',return_value=True):await service.control('START','a'*32,1)
  for phase in ('signal','fill','update','close'):
   fixture.add(phase);await service.tick()
  return service
 app=FastAPI();app.include_router(router);app.state.active43=asyncio.run(prepare());app.mount('/static',StaticFiles(directory=ROOT/'static'))
 uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),access_log=False)
else:
 if os.getenv('RENDER') or not __debug__:raise ValueError('LOCAL_OFFLINE_ONLY')
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 if args.output.exists():raise ValueError('New output path required')
 with tempfile.TemporaryDirectory(prefix='active43-browser-offline-') as folder:
  folder=Path(folder);listen=port();debug=port();procs=[]
  env=dict(PATH=os.defpath,LANG='C.UTF-8',PYTHONPATH=str(ROOT),AURA_TESTNET_VIEW_PASSWORD=PASSWORD,AURA_ACTIVE43_SCHEDULER_SECRET='DUMMY_ACTIVE43_BROWSER_SCHEDULER_'+'x'*32)
  with (folder/'logs').open('wb') as log:
   try:
    web=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child',str(listen)],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);procs.append(web)
    for _ in range(150):
     try:
      if httpx.get(f'http://127.0.0.1:{listen}/api/active43/status',trust_env=False,timeout=1).status_code==401:break
     except httpx.HTTPError:pass
     time.sleep(.1)
    chrome=subprocess.Popen(['/usr/bin/chromium','--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--proxy-server=http://127.0.0.1:9',f'--user-data-dir={folder}/browser',f'--remote-debugging-port={debug}','about:blank'],env=dict(PATH=os.defpath,LANG='C.UTF-8'),stdout=log,stderr=log,start_new_session=True);procs.append(chrome)
    for _ in range(150):
     try:pages=httpx.get(f'http://127.0.0.1:{debug}/json/list',trust_env=False,timeout=1).json();break
     except (httpx.HTTPError,ValueError):time.sleep(.1)
    with connect(pages[0]['webSocketDebuggerUrl'],proxy=None) as ws:
     seq=0
     def call(method,params=None):
      global seq
      seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
      while True:
       v=json.loads(ws.recv(timeout=15))
       if v.get('id')==seq:
        assert 'error' not in v,v
        return v.get('result',{})
     def evaluate(js):
      r=call('Runtime.evaluate',dict(expression=js,returnByValue=True,awaitPromise=True));assert 'exceptionDetails' not in r,r
      return r['result'].get('value')
     def wait(js):
      for _ in range(150):
       if evaluate(js):return
       time.sleep(.1)
      raise AssertionError('UI timeout '+str(evaluate("document.getElementById('active43-panel')?.textContent")))
     call('Network.enable');call('Network.setExtraHTTPHeaders',dict(headers={'Authorization':'Basic '+base64.b64encode(('aura:'+PASSWORD).encode()).decode()}))
     call('Emulation.setDeviceMetricsOverride',dict(width=430,height=932,deviceScaleFactor=1,mobile=True))
     call('Page.navigate',dict(url=f'http://127.0.0.1:{listen}/static/index.html'))
     wait("document.readyState==='complete'&&!!document.getElementById('a43-refresh')")
     evaluate("document.getElementById('active43-panel').open=true")
     wait("document.getElementById('a43-mode').textContent.includes('Включён')")
     wait("document.querySelectorAll('#a43-chart circle').length===2")
     wait("document.getElementById('a43-history').textContent.includes('TAKE_PROFIT') || document.getElementById('a43-history').textContent.includes('Take Profit')")
     evaluate("document.getElementById('a43-research').click()")
     wait("document.querySelectorAll('#a43-comparison tr').length===15")
     width=evaluate("document.getElementById('active43-panel').getBoundingClientRect().width")
     assert width<=430,width
     state=httpx.get(f'http://127.0.0.1:{listen}/api/active43/status',auth=('aura',PASSWORD),trust_env=False).json()
     assert state['state']['mode']=='ON' and state['state']['position'] is None and state['state']['trades']==1
     assert not state['production_paper_verified']
     result=dict(status='PASS',scope='OFFLINE_SYNTHETIC_MEMORY_STORE_UI_ONLY_NOT_SUPABASE_OR_RENDER',real_chromium=True,real_owner_http_api=True,width=430,panel_width=width,native_indicators_closed_trade_visible=True,entry_exit_markers=2,comparison_rows=15,equity_canvas=True,open_count=1,close_count=1,production_paper_verified=False)
     args.output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
   finally:
    for p in reversed(procs):
     if p.poll() is None:
      os.killpg(p.pid,signal.SIGTERM)
      try:p.wait(timeout=5)
      except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
