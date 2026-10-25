"""Offline Chromium mobile-viewport rehearsal. Not an Android hardware test."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import functools
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import httpx
from websockets.sync.client import connect


def main():
    if os.getenv('RENDER'):raise ValueError('LOCAL_OFFLINE_ONLY')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    fixture="""
    window.__calls=0; window.__sockets=[];
    const row=(t,c=101,v=10)=>[String(t*1000),'100','105','95',String(c),String(v),'1000'];
    window.fetch=async url=>{window.__calls++;const s=url.includes('granularity=1m')?60:300,t=Math.floor(Date.now()/1000/s)*s;return {ok:true,json:async()=>({code:'00000',requestTime:String(Date.now()),data:Array.from({length:200},(_,i)=>row(t-(199-i)*s))})};};
    window.WebSocket=class{constructor(url){this.url=url;this.readyState=1;window.__sockets.push(this);setTimeout(()=>this.onopen?.(),10);}send(raw){if(raw==='ping')return;const arg=JSON.parse(raw).args[0],s=arg.channel==='candle1m'?60:300,t=Math.floor(Date.now()/1000/s)*s;this.onmessage?.({data:JSON.stringify({action:'update',arg,ts:Date.now(),data:[row(t,104,20)]})});}close(){this.readyState=3;this.onclose?.();}};
    """
    with tempfile.TemporaryDirectory(prefix='a43-live-browser-') as folder:
        folder=Path(folder)
        html=folder/'test.html'
        html.write_text('<meta name="viewport" content="width=device-width,initial-scale=1"><body style="margin:8px"><details id="active43-panel" open><summary>BITGET FUTURES LIVE</summary><select id="a43-live-timeframe"><option>1m</option><option selected>5m</option></select><p id="a43-live-status"></p><p id="a43-live-price"></p><div id="a43-live-chart" style="height:300px"></div></details><script>'+fixture+'</script><script src="'+(root/'static/vendor/lightweight-charts.standalone.production.js').as_uri()+'"></script><script src="'+(root/'static/active43-live.js').as_uri()+'"></script>')
        (folder/'vendor.js').write_bytes((root/'static/vendor/lightweight-charts.standalone.production.js').read_bytes())
        (folder/'live.js').write_bytes((root/'static/active43-live.js').read_bytes())
        html.write_text(html.read_text().replace((root/'static/vendor/lightweight-charts.standalone.production.js').as_uri(),'/vendor.js').replace((root/'static/active43-live.js').as_uri(),'/live.js'))
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(SimpleHTTPRequestHandler,directory=str(folder)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        proc=subprocess.Popen(['/usr/bin/chromium','--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--proxy-server=http://127.0.0.1:9',f'--user-data-dir={folder}/profile','--remote-debugging-port=0','about:blank'],env={'PATH':os.defpath,'LANG':'C.UTF-8'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            active=folder/'profile/DevToolsActivePort'
            for _ in range(100):
                if active.exists():break
                time.sleep(.1)
            port=active.read_text().splitlines()[0]
            pages=httpx.get(f'http://127.0.0.1:{port}/json/list',trust_env=False).json()
            with connect(pages[0]['webSocketDebuggerUrl'],proxy=None) as ws:
                seq=0
                def call(method,params=None):
                    nonlocal seq
                    seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
                    while True:
                        response=json.loads(ws.recv(timeout=10))
                        if response.get('id')==seq:
                            if 'error' in response:raise ValueError(response['error'])
                            return response.get('result',{})
                def evaluate(expression):
                    r=call('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
                    if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
                    return r['result'].get('value')
                call('Emulation.setDeviceMetricsOverride',dict(width=393,height=851,deviceScaleFactor=2,mobile=True))
                call('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/test.html'))
                for _ in range(100):
                    state=evaluate("document.getElementById('a43-live-status')?.textContent")
                    if state and state.startswith('LIVE'):break
                    time.sleep(.05)
                assert state and state.startswith('LIVE'),evaluate('JSON.stringify({href:location.href,body:document.body?.innerText,html:document.documentElement.outerHTML.slice(0,700)})')
                assert evaluate("document.querySelectorAll('canvas').length")>0
                assert evaluate("document.documentElement.scrollWidth<=innerWidth")
                assert '104' in evaluate("document.getElementById('a43-live-price').textContent")
                before=evaluate('window.__calls')
                evaluate("Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'))")
                assert evaluate('window.__sockets.at(-1).readyState')==3
                assert evaluate('window.__calls')==before
                evaluate("Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'))")
                time.sleep(.1)
                assert evaluate('window.__calls')==before+1
                evaluate("document.getElementById('a43-live-timeframe').value='1m';document.getElementById('a43-live-timeframe').dispatchEvent(new Event('change'))")
                time.sleep(.1)
                assert evaluate("document.getElementById('a43-live-status').textContent.startsWith('LIVE')")
                screenshot=call('Page.captureScreenshot',dict(format='png'))['data']
                (args.output_dir/'mobile.png').write_bytes(base64.b64decode(screenshot))
                # Actual main HTML/scripts: closed server feed plus provisional public WS.
                from app.live import snapshot
                from app.models import Candle
                at=int(time.time())//900*900
                closed=[Candle(at-(200-i)*900,100,105,95,101,10) for i in range(200)]
                market=snapshot(closed,'BTCUSDT','15m','Bitget · USDT-M Futures / api.bitget.com','polling')
                market.update(fetched_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),note='TEST_ONLY CLOSED',stale=False)
                main_fixture="window.__market="+json.dumps(market)+";"+fixture
                main_fixture += """
                const previousFetch=window.fetch;
                window.fetch=async url=>String(url).startsWith('/api/market?')?{ok:true,json:async()=>window.__market}:String(url).startsWith('https://api.bitget.com')?previousFetch(url.replace('granularity=15m','granularity=5m')):{ok:false,status:401,json:async()=>({detail:'TEST_ONLY UNAUTHORIZED'})};
                const PublicSocket=window.WebSocket;
                window.WebSocket=class extends PublicSocket{constructor(url){super(url);if(!url.includes('ws.bitget.com'))setTimeout(()=>this.onmessage?.({data:JSON.stringify(window.__market)}),40);}send(raw){if(raw==='ping')return;const arg=JSON.parse(raw).args[0],s=arg.channel==='candle15m'?900:300,t=Math.floor(Date.now()/1000/s)*s;this.onmessage?.({data:JSON.stringify({action:'update',arg,ts:Date.now(),data:[row(t,104,20)]})});}};
                """
                # REST must reflect the selected 15m interval, not the owner fixture's 5m.
                main_fixture += """
                const displayFetch=window.fetch;
                window.fetch=async url=>String(url).includes('granularity=15m')?{ok:true,json:async()=>({code:'00000',requestTime:Date.now(),data:Array.from({length:200},(_,i)=>row(Math.floor(Date.now()/1000/900)*900-(199-i)*900))})}:displayFetch(url);
                """
                (folder/'static').symlink_to(root/'static',target_is_directory=True)
                (folder/'main.html').write_text((root/'static/index.html').read_text().replace('<head>','<head><script>'+main_fixture+'</script>',1))
                call('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/main.html'))
                for _ in range(100):
                    ready=evaluate("parseFloat(document.getElementById('headline-price')?.textContent)===104 && document.getElementById('feed-state')?.textContent.startsWith('LIVE')")
                    if ready:break
                    time.sleep(.05)
                assert ready,evaluate("JSON.stringify({price:document.getElementById('headline-price')?.textContent,feed:document.getElementById('feed-state')?.textContent,status:document.getElementById('status')?.textContent})")
                assert evaluate("currentData.candles.at(-1).time < Math.floor(Date.now()/1000/900)*900")
                assert evaluate("currentData.analysis.price===101")
                assert evaluate("document.documentElement.scrollWidth<=innerWidth")
                (args.output_dir/'main-mobile.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',dict(format='png'))['data']))
                report=dict(status='PASS',scope='OFFLINE_CHROMIUM_MOBILE_EMULATION',viewport=[393,851],live_price_and_canvas=True,background_socket_closed=True,resume_rest_snapshot=True,timeframe_switch=True,actual_main_chart=True,main_closed_analytics_preserved=True,android_device_verified=False,production_changed=False)
                (args.output_dir/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        finally:
            server.shutdown();server.server_close()
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':main()
