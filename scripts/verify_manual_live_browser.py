"""Offline Chromium desktop/mobile rehearsal. No production traffic or orders.

Requires installed Chromium and repository Python dependencies. Mobile viewport
and touch emulation are not a test on physical Android Chrome.
"""
import argparse
import asyncio
import base64
import functools
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import AsyncMock
from decimal import Decimal
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from websockets.sync.client import connect
from app.manual_paper.api import router
from app.manual_paper.store import ManualStore
from app.manual_paper.service import Service

ROOT=Path(__file__).resolve().parents[1]

def main():
    if os.getenv('RENDER'):raise ValueError('LOCAL_OFFLINE_ONLY')
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=False)
    fixture=json.loads((ROOT/'tests/fixtures/manual_live_synthetic.json').read_text());now=fixture['now']
    closed=json.loads((ROOT/'tests/fixtures/aura_analyst_synthetic.json').read_text())['LONG']
    bootstrap='window.__fixture='+json.dumps(fixture)+';window.__closed='+json.dumps(closed)+';'+r'''
    const nativeNow=Date.now,boot=nativeNow();Date.now=()=>window.__fixture.now*1000+nativeNow()-boot;window.__sockets=[];window.__historyCalls=0;
    const nativeFetch=window.fetch.bind(window);window.__posts=0;
    window.fetch=async(url,options={})=>{
      if(String(url).startsWith('https://api.bitget.com/api/v2/mix/market/candles?')){
        window.__historyCalls++;const g=new URL(url).searchParams.get('granularity'),tf=({'1H':'1h','4H':'4h'})[g]||g;
        return {ok:true,json:async()=>({code:'00000',requestTime:Date.now(),data:__fixture.snapshots.LONG.windows[tf].bars.map(b=>[String(b.time*1000),b.open,b.high,b.low,b.close,b.volume,'0'])})};
      }
      if(String(url).startsWith('/api/manual-paper/')){if(options.method==='POST')window.__posts++;return nativeFetch(url,{...options,headers:{...options.headers,Authorization:'Basic '+btoa('aura:DUMMY_ONLY_BROWSER_OWNER_PASSWORD')}});}
      if(url==='/api/analyst')return {ok:true,json:async()=>__closed};
      return {ok:false,status:503,json:async()=>({code:'OFFLINE_FIXTURE_ONLY'})};
    };
    window.WebSocket=class{
      constructor(url){if(url!=='wss://ws.bitget.com/v2/ws/public')throw Error('NON_PUBLIC_WS');this.readyState=1;window.__sockets.push(this);setTimeout(()=>this.onopen?.(),20);}
      send(raw){if(raw==='ping')return;const args=JSON.parse(raw).args;
        for(const arg of args){const tf=({'candle1m':'1m','candle5m':'5m','candle15m':'15m','candle1H':'1h','candle4H':'4h'})[arg.channel];let data;
          if(tf){const b=__fixture.snapshots.LONG.windows[tf].bars.at(-1);data=[[String(b.time*1000),b.open,b.high,b.low,b.close,b.volume,'0']];}
          else{const q=__fixture.snapshots.LONG.quote;data=[{instId:'BTCUSDT',bidPr:q.bid,askPr:q.ask,lastPr:q.last,ts:Date.now()}];}
          this.onmessage?.({data:JSON.stringify({arg,action:'snapshot',ts:Date.now(),data})});
        }
        if(!this.timer)this.timer=setInterval(()=>{if(this.readyState!==1)return;const arg={instType:'USDT-FUTURES',instId:'BTCUSDT',channel:'ticker'},q=__fixture.snapshots.LONG.quote;this.onmessage?.({data:JSON.stringify({arg,action:'update',ts:Date.now(),data:[{bidPr:q.bid,askPr:q.ask,lastPr:q.last,ts:Date.now()}]})});},1000);
      }
      close(){clearInterval(this.timer);this.readyState=3;this.onclose?.();}
    };
    document.addEventListener('DOMContentLoaded',()=>{const badge=document.createElement('p');badge.textContent='SYNTHETIC OFFLINE TEST · виртуальные тестовые данные · не production';badge.style='position:fixed;bottom:0;left:0;right:0;background:#523700;color:white;font-size:12px;padding:4px;z-index:10000';document.body.append(badge);});
    window.confirm=message=>{window.__confirmation=message;return true;};
    '''
    password='DUMMY_ONLY_BROWSER_OWNER_PASSWORD';previous=os.environ.get('AURA_TESTNET_VIEW_PASSWORD');os.environ['AURA_TESTNET_VIEW_PASSWORD']=password
    try:
      with tempfile.TemporaryDirectory(prefix='aura-manual-browser-') as raw:
        folder=Path(raw);boot=time.monotonic();svc=Service(ManualStore(folder/'manual-paper.sqlite3'),clock=lambda:now+time.monotonic()-boot)
        def quote():return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',time=int(svc.clock()*1000)-1000,bid=Decimal('14712.15'),ask=Decimal('14712.35'),price=Decimal('14712.25'),bid_size=Decimal('1'),ask_size=Decimal('1'))
        svc.quote=AsyncMock(side_effect=quote);api=FastAPI();api.include_router(router);api.state.manual_paper=svc
        (folder/'static').symlink_to(ROOT/'static',target_is_directory=True)
        (folder/'index.html').write_text((ROOT/'static/index.html').read_text().replace('<head>','<head><script>'+bootstrap+'</script>',1))
        with TestClient(api) as client:
          class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path.startswith('/api/'):
                    r=client.get(self.path,headers=dict(self.headers));self.send_response(r.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(r.content)
                else:super().do_GET()
            def do_POST(self):
                if not self.path.startswith('/api/manual-paper/'):self.send_error(403);return
                size=int(self.headers.get('content-length','0'))
                if size>4096:self.send_error(413);return
                headers=dict(self.headers);headers.pop('Origin',None);headers.pop('origin',None)
                r=client.post(self.path,content=self.rfile.read(size),headers=headers);self.send_response(r.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(r.content)
          server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(folder)));threading.Thread(target=server.serve_forever,daemon=True).start()
          proc=subprocess.Popen(['/usr/bin/chromium','--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--proxy-server=http://127.0.0.1:9',f'--user-data-dir={folder}/profile','--remote-debugging-port=0','about:blank'],env={'PATH':os.defpath,'LANG':'C.UTF-8'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
          try:
            active=folder/'profile/DevToolsActivePort'
            for _ in range(100):
                if active.exists():break
                time.sleep(.1)
            port=active.read_text().splitlines()[0];page=httpx.get(f'http://127.0.0.1:{port}/json/list',trust_env=False).json()[0]
            with connect(page['webSocketDebuggerUrl'],proxy=None) as ws:
              seq=0
              def call(method,params=None):
                nonlocal seq
                seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
                while True:
                    r=json.loads(ws.recv(timeout=10))
                    if r.get('id')==seq:
                        if 'error' in r:raise ValueError(r['error'])
                        return r.get('result',{})
              def evaluate(expression):
                r=call('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
                if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
                return r['result'].get('value')
              def wait(expression):
                for _ in range(100):
                    if evaluate(expression):return
                    time.sleep(.05)
                raise AssertionError(evaluate("JSON.stringify({state:document.getElementById('ml-state')?.textContent,status:document.getElementById('ml-status')?.textContent,explanation:document.getElementById('ml-explanation')?.textContent,mp:document.getElementById('mp-status')?.textContent,position:document.getElementById('mp-position')?.textContent,closeDisabled:document.getElementById('mp-close')?.disabled,tf:timeframe,chartClose:currentData?.candles?.at(-1)?.close,hubClose:window.AuraManualLiveHub?.windows?.['15m']?.bars?.at(-1)?.close,posts:window.__posts,quote:window.AuraManualLiveHub?.quote,now:Date.now()/1000})"))
              for name,width,height,mobile in [('desktop',1440,1000,False),('mobile',393,851,True)]:
                call('Emulation.setDeviceMetricsOverride',dict(width=width,height=height,deviceScaleFactor=1,mobile=mobile));call('Emulation.setTouchEmulationEnabled',dict(enabled=mobile))
                boot=time.monotonic()
                call('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/'))
                wait("document.getElementById('ml-state')?.textContent==='LONG'&&document.querySelectorAll('canvas').length>0")
                assert evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert evaluate('window.__posts')==0
                # Realtime price/candle update without navigation or refresh.
                before=evaluate("document.getElementById('headline-price').textContent")
                evaluate("(()=>{__fixture.snapshots.LONG.quote={...__fixture.snapshots.LONG.quote,bid:14712.2,ask:14712.4,last:14712.3};const w=AuraManualLiveHub.ws,arg={instType:'USDT-FUTURES',instId:'BTCUSDT',channel:'ticker'};w.onmessage({data:JSON.stringify({arg,action:'update',ts:Date.now(),data:[{bidPr:14712.2,askPr:14712.4,lastPr:14712.3,ts:Date.now()}]})});})()")
                wait("document.getElementById('headline-price').textContent!=="+json.dumps(before))
                previous_close=evaluate('currentData.candles.at(-1).close')
                evaluate("(()=>{const b=__fixture.snapshots.LONG.windows['15m'].bars.at(-1);b.close+=.25;b.high+=1;b.volume+=1;AuraManualLiveHub.ws.onmessage({data:JSON.stringify({arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel:'candle15m'},action:'update',ts:Date.now(),data:[[String(b.time*1000),b.open,b.high,b.low,b.close,b.volume,'0']]})});})()")
                wait('currentData.candles.at(-1).close>'+str(previous_close))
                evaluate("document.getElementById('aura-live-analyst').scrollIntoView()")
                (args.output_dir/(name+'.png')).write_bytes(base64.b64decode(call('Page.captureScreenshot',dict(format='png'))['data']))
                # Test chart touches: horizontal drawing via actual touch protocol on mobile.
                if mobile:
                    evaluate("document.getElementById('chart').scrollIntoView();document.getElementById('drawing-tool').value='horizontal';document.getElementById('drawing-tool').dispatchEvent(new Event('change'))")
                    rect=evaluate("(()=>{const r=document.getElementById('chart').getBoundingClientRect();return {x:r.x+100,y:r.y+120};})()")
                    call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[rect]));call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]))
                    wait("document.querySelectorAll('.manual-overlay line').length>0")
                wait("!document.getElementById('ml-copy').disabled");evaluate("document.getElementById('ml-copy').click();document.getElementById('mp-quantity').value='0.01'")
                wait("!document.getElementById('mp-long').disabled")
                assert evaluate('window.__posts')==0
                evaluate("document.getElementById('mp-long').click();document.getElementById('mp-long').click()")
                wait("document.getElementById('mp-position').textContent.includes('LONG')")
                assert evaluate('window.__posts')==1
                assert svc.store.load()[0].position is not None
                wait("!document.getElementById('mp-close').disabled");evaluate("document.getElementById('mp-close').click()")
                wait("document.getElementById('mp-position').textContent==='Нет открытой позиции'")
                assert evaluate('window.__posts')==2
                assert len(svc.store.load()[0].trades)==(1 if name=='desktop' else 2)
                # Actual form response, fees and history are rendered after server save.
                assert 'комиссии' in evaluate("document.getElementById('mp-history').textContent")
                evaluate("document.getElementById('manual-paper-panel').scrollIntoView()")
                (args.output_dir/(name+'-paper.png')).write_bytes(base64.b64decode(call('Page.captureScreenshot',dict(format='png'))['data']))
                calls=evaluate('window.__historyCalls');evaluate("Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'))")
                assert evaluate("document.getElementById('ml-state').textContent")=='WAIT'
                evaluate("Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'))")
                wait("document.getElementById('ml-status').textContent==='LIVE'")
                assert evaluate('window.__historyCalls')>=calls+5
              report=dict(status='PASS',desktop=True,mobile_touch_emulation=True,physical_android_chrome=False,background_resnapshot=True,user_only_open_close=True,double_click_deduplicated=True,committed_virtual_trades=[t['id'] for t in svc.store.load()[0].trades],production_changed=False)
              (args.output_dir/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
          finally:
            server.shutdown();server.server_close();proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    finally:
        if previous is None:os.environ.pop('AURA_TESTNET_VIEW_PASSWORD',None)
        else:os.environ['AURA_TESTNET_VIEW_PASSWORD']=previous

if __name__=='__main__':main()
