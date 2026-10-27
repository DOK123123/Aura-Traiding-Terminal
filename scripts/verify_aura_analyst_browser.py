"""Offline real-Chromium UI verification; synthetic analysis, no trading/API writes."""
import argparse,base64,functools,json,os,subprocess,tempfile,threading,time
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx
from websockets.sync.client import connect


def main():
    if os.getenv('RENDER'):raise ValueError('LOCAL_OFFLINE_ONLY')
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--public-snapshot',type=Path);parser.add_argument('--workspace',action='store_true');args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=False);root=Path(__file__).resolve().parents[1]
    fixture=json.loads((root/'tests/fixtures/aura_analyst_synthetic.json').read_text())
    initial='LONG'
    if args.public_snapshot:
        public=json.loads(args.public_snapshot.read_text())['result'];initial=public['state']
        fixture=dict(now=public['generated_at'],LONG=public,SHORT=public,WAIT=public)
    market={}
    if args.workspace:
        from dataclasses import asdict
        from tests.test_aura_trader5_scenarios import windows
        from app.indicators import analyze
        for tf,bars in windows().items():
            market[tf]=dict(symbol='BTCUSDT',timeframe=tf,candles=[asdict(b) for b in bars],analysis=analyze(bars),source=fixture['LONG']['source'],last_closed_at=bars[-1].time+{'5m':300,'15m':900,'1h':3600,'4h':14400}[tf],fetched_at='2027-01-15T08:02:30Z',stale=False,note='SYNTHETIC LOCAL FIXTURE')
    script='window.__market='+json.dumps(market)+';window.__pageErrors=[];window.addEventListener("error",e=>window.__pageErrors.push(e.message));window.__fixture='+json.dumps(fixture)+';'+'''
    window.__case='LONG';window.__calls=[];
    const NativeDate=Date;Date=class extends NativeDate{static now(){return window.__fixture.now*1000;}};
    window.fetch=async (url,options={})=>{window.__calls.push({url,method:options.method||'GET'});if(String(url).startsWith('/api/market?')&&Object.keys(window.__market).length){const tf=new URL(String(url),'http://localhost').searchParams.get('timeframe');return {ok:true,json:async()=>structuredClone(window.__market[tf])};}return String(url)==='/api/analyst'?{ok:true,json:async()=>structuredClone(window.__fixture[window.__case])}:{ok:false,status:503,json:async()=>({detail:'OFFLINE_BROWSER_FIXTURE'})};};
    window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){this.readyState=3;}};
    '''
    with tempfile.TemporaryDirectory(prefix='aura-analyst-browser-') as folder:
        folder=Path(folder);(folder/'static').symlink_to(root/'static',target_is_directory=True)
        page=(root/'static/index.html').read_text().replace('<head>','<head><script>'+script+'</script>',1)
        (folder/'test.html').write_text(page)
        if args.workspace:
            failure=page.replace('<script defer src="/static/aura-chart-tools.js"></script>','<script>window.AuraChartTools={attach(){throw Error("SYNTHETIC_OPTIONAL_TOOL_FAILURE");}};</script>')
            (folder/'test-failure.html').write_text(failure)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(folder)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
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
                def ev(expression):
                    r=call('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
                    if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
                    return r['result'].get('value')
                call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))
                call('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/test.html'))
                for _ in range(100):
                    if ev("document.getElementById('analyst-state')?.textContent==='"+initial+"' && document.querySelectorAll('#analyst-frames article').length===4 && document.getElementById('analyst-freshness').textContent.includes('Анализ UTC')"):break
                    time.sleep(.05)
                assert ev("document.getElementById('analyst-state').textContent==='"+initial+"'")
                banner_text='СНИМОК ПУБЛИЧНЫХ ДАННЫХ BITGET · ЛОКАЛЬНО · БЕЗ ТОРГОВЛИ' if args.public_snapshot else 'ЛОКАЛЬНАЯ ПРОВЕРКА · СИНТЕТИЧЕСКИЕ СВЕЧИ · НЕ PRODUCTION'
                ev("const banner=document.createElement('p');banner.textContent="+json.dumps(banner_text)+";banner.style.color='#e4bb78';document.getElementById('aura-analyst').prepend(banner)")
                outputs=[]
                cases=[('desktop-long',1440,1000,False,'LONG'),('mobile-long',393,851,True,'LONG'),('desktop-short',1440,1000,False,'SHORT'),('mobile-wait',393,851,True,'WAIT')]
                if args.public_snapshot:cases=[('desktop-public',1440,1000,False,initial),('mobile-public',393,851,True,initial)]
                for name,width,height,mobile,case in cases:
                    call('Emulation.setDeviceMetricsOverride',dict(width=width,height=height,deviceScaleFactor=1,mobile=mobile))
                    ev("window.__case='"+case+"';document.getElementById('analyst-refresh').click()")
                    time.sleep(.2)
                    assert ev("document.getElementById('analyst-state').textContent") == case
                    assert ev("document.querySelectorAll('#analyst-frames article').length") == 4
                    assert ev("document.getElementById('analyst-plan').hidden") == (case=='WAIT')
                    assert ev('document.documentElement.scrollWidth<=innerWidth')
                    if not mobile:ev("document.querySelector('#aura-analyst details').open=true")
                    bounds=ev("(()=>{const r=document.getElementById('aura-analyst').getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1};})()")
                    screenshot=call('Page.captureScreenshot',dict(format='png',clip=bounds,captureBeyondViewport=True))['data']
                    (args.output_dir/(name+'.png')).write_bytes(base64.b64decode(screenshot));outputs.append(name+'.png')
                if args.workspace:
                    # Real SVG overlays attached to the existing actual LWC chart.
                    call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1100,deviceScaleFactor=1,mobile=False))
                    ev("document.getElementById('chart').scrollIntoView({block:'center'})")
                    time.sleep(.2)
                    assert ev("document.querySelector('#chart svg.manual-overlay')!==null")
                    def click(x,y):
                        call('Input.dispatchMouseEvent',dict(type='mousePressed',x=x,y=y,button='left',clickCount=1))
                        call('Input.dispatchMouseEvent',dict(type='mouseReleased',x=x,y=y,button='left',clickCount=1))
                    rect=ev("(()=>{const r=document.getElementById('chart').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
                    x=rect['x']+rect['w']*.35;y=rect['y']+rect['h']*.35
                    for tool in ['horizontal','trend','zone','fib']:
                        ev("document.getElementById('drawing-tool').value='"+tool+"';document.getElementById('drawing-tool').dispatchEvent(new Event('change'))")
                        click(x,y)
                        if tool!='horizontal':click(x+120,y+70)
                        time.sleep(.05)
                    assert ev("JSON.parse(localStorage.getItem(AuraChartTools.KEY)).frames['15m'].length") == 4
                    ev("document.getElementById('drawing-tool').value='select';document.getElementById('drawing-tool').dispatchEvent(new Event('change'))")
                    time.sleep(.1)
                    handle=ev("(()=>{const r=document.querySelector('.manual-overlay circle[data-handle=\"1\"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
                    before=ev("JSON.parse(localStorage.getItem(AuraChartTools.KEY)).frames['15m'][3].points[1].price")
                    call('Input.dispatchMouseEvent',dict(type='mousePressed',x=handle['x'],y=handle['y'],button='left',clickCount=1))
                    call('Input.dispatchMouseEvent',dict(type='mouseMoved',x=handle['x']+25,y=handle['y']-30,button='left',buttons=1))
                    call('Input.dispatchMouseEvent',dict(type='mouseReleased',x=handle['x']+25,y=handle['y']-30,button='left',clickCount=1))
                    assert ev("JSON.parse(localStorage.getItem(AuraChartTools.KEY)).frames['15m'][3].points[1].price") != before
                    ev("for(const [id,n] of Object.entries({entry:16000,stop:15800,target:16500,quantity:0.01})){document.getElementById('drawing-'+id).value=n;}document.getElementById('drawing-apply').click()")
                    assert ev("document.getElementById('drawing-risk').textContent.includes('Гипотетический риск')")
                    ev("document.getElementById('journal-save').click();document.getElementById('journal-save').click()")
                    for _ in range(100):
                        if ev("AuraScenarioJournal.read(localStorage).length===1"):break
                        time.sleep(.02)
                    assert ev("AuraScenarioJournal.read(localStorage).length") == 1
                    ev("document.querySelector('#journal-list input').value=16500;document.querySelector('#journal-list button').click()")
                    for _ in range(100):
                        if ev("AuraScenarioJournal.read(localStorage)[0].state==='REVIEWED'"):break
                        time.sleep(.02)
                    assert ev("AuraScenarioJournal.read(localStorage)[0].state")=='REVIEWED'
                    assert ev("AuraScenarioJournal.read(localStorage)[0].plan.entry")==16000
                    assert ev("window.__pageErrors") == [], ev("window.__pageErrors")
                    # Restart the page: restore local drawings and hypothetical outcome.
                    call('Page.reload')
                    for _ in range(100):
                        if ev("document.querySelector('#journal-list article')!==null && document.querySelector('#chart svg.manual-overlay g')!==null"):break
                        time.sleep(.05)
                    assert ev("AuraScenarioJournal.read(localStorage)[0].state")=='REVIEWED'
                    assert ev("JSON.parse(localStorage.getItem(AuraChartTools.KEY)).frames['15m'].length")==5
                    ev("for(const selector of ['.chart-panel','#scenario-journal','#aura-analyst']){const b=document.createElement('p');b.textContent='СИНТЕТИЧЕСКИЙ ЛОКАЛЬНЫЙ ТЕСТ · НЕ РЫНОЧНЫЕ РЕЗУЛЬТАТЫ · БЕЗ ОРДЕРОВ';b.style.cssText='color:#e4bb78;padding:12px';document.querySelector(selector).prepend(b);}")
                    call('Emulation.setDeviceMetricsOverride',dict(width=393,height=851,deviceScaleFactor=1,mobile=True))
                    call('Emulation.setTouchEmulationEnabled',dict(enabled=True,maxTouchPoints=1))
                    ev("document.getElementById('chart').scrollIntoView({block:'center'});document.getElementById('drawing-tool').value='horizontal';document.getElementById('drawing-tool').dispatchEvent(new Event('change'))")
                    time.sleep(.1)
                    touch=ev("(()=>{const r=document.getElementById('chart').getBoundingClientRect();return {x:r.x+100,y:r.y+100};})()")
                    call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[dict(x=touch['x'],y=touch['y'],id=1)]))
                    call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]))
                    time.sleep(.1)
                    assert ev("JSON.parse(localStorage.getItem(AuraChartTools.KEY)).frames['15m'].length")==6
                    ev("document.getElementById('drawing-tool').value='select';document.getElementById('drawing-tool').dispatchEvent(new Event('change'))")
                    for name,width,height,mobile,selector in [('workspace-desktop',1440,1100,False,'.chart-panel'),('workspace-mobile',393,851,True,'.chart-panel'),('context-desktop',1440,1100,False,'#aura-analyst'),('journal-mobile',393,851,True,'#scenario-journal')]:
                        call('Emulation.setDeviceMetricsOverride',dict(width=width,height=height,deviceScaleFactor=1,mobile=mobile))
                        time.sleep(.2)
                        assert ev('document.documentElement.scrollWidth<=innerWidth')
                        bounds=ev("(()=>{const r=document.querySelector('"+selector+"').getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1};})()")
                        picture=call('Page.captureScreenshot',dict(format='png',clip=bounds,captureBeyondViewport=True))['data']
                        (args.output_dir/(name+'.png')).write_bytes(base64.b64decode(picture));outputs.append(name+'.png')
                    assert ev("window.__pageErrors") == []
                    ev("document.getElementById('drawing-delete').click()")
                    assert ev("document.getElementById('journal-save').disabled")
                    assert ev("AuraScenarioJournal.read(localStorage)[0].state")=='REVIEWED'
                    # A broken optional tool must not take down the original chart.
                    call('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/test-failure.html'))
                    for _ in range(100):
                        if ev("document.getElementById('chart-overlay')?.hidden===true"):break
                        time.sleep(.03)
                    assert ev("document.getElementById('chart-overlay').hidden")
                    assert ev("document.getElementById('drawing-status').textContent.includes('недоступны')")
                    assert ev("document.querySelectorAll('#chart canvas').length>0")
                    assert ev("window.__pageErrors") == []
                assert ev("window.__calls.every(c=>c.method==='GET')")
                assert ev("!window.__calls.some(c=>/\\/(control|tick|initialize|reset|strategy)(\\?|$)/.test(c.url))")
                report=dict(status='PASS',scope='RECORDED_PUBLIC_SNAPSHOT_NO_LIVE_REQUESTS' if args.public_snapshot else 'OFFLINE_SYNTHETIC_REAL_CHROMIUM',screenshots=outputs,mobile_viewport=[393,851],desktop_viewport=[1440,1000],states=[initial] if args.public_snapshot else ['LONG','SHORT','WAIT'],timeframes=['5m','15m','1h','4h'],read_only_requests=True,android_device_verified=False,production_changed=False,workspace_tested=args.workspace)
                (args.output_dir/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        finally:
            server.shutdown();server.server_close();proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':main()
