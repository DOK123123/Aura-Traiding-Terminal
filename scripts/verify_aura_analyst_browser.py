"""Offline real-Chromium UI verification; synthetic analysis, no trading/API writes."""
import argparse,base64,functools,json,os,subprocess,tempfile,threading,time
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx
from websockets.sync.client import connect


def main():
    if os.getenv('RENDER'):raise ValueError('LOCAL_OFFLINE_ONLY')
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--public-snapshot',type=Path);args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=False);root=Path(__file__).resolve().parents[1]
    fixture=json.loads((root/'tests/fixtures/aura_analyst_synthetic.json').read_text())
    initial='LONG'
    if args.public_snapshot:
        public=json.loads(args.public_snapshot.read_text())['result'];initial=public['state']
        fixture=dict(now=public['generated_at'],LONG=public,SHORT=public,WAIT=public)
    script='window.__fixture='+json.dumps(fixture)+';'+'''
    window.__case='LONG';window.__calls=[];
    const NativeDate=Date;Date=class extends NativeDate{static now(){return window.__fixture.now*1000;}};
    window.fetch=async (url,options={})=>{window.__calls.push({url,method:options.method||'GET'});return String(url)==='/api/analyst'?{ok:true,json:async()=>structuredClone(window.__fixture[window.__case])}:{ok:false,status:503,json:async()=>({detail:'OFFLINE_BROWSER_FIXTURE'})};};
    window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){this.readyState=3;}};
    '''
    with tempfile.TemporaryDirectory(prefix='aura-analyst-browser-') as folder:
        folder=Path(folder);(folder/'static').symlink_to(root/'static',target_is_directory=True)
        (folder/'test.html').write_text((root/'static/index.html').read_text().replace('<head>','<head><script>'+script+'</script>',1))
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
                assert ev("window.__calls.every(c=>c.method==='GET')")
                assert ev("!window.__calls.some(c=>/\\/(control|tick|initialize|reset|strategy)(\\?|$)/.test(c.url))")
                report=dict(status='PASS',scope='RECORDED_PUBLIC_SNAPSHOT_NO_LIVE_REQUESTS' if args.public_snapshot else 'OFFLINE_SYNTHETIC_REAL_CHROMIUM',screenshots=outputs,mobile_viewport=[393,851],desktop_viewport=[1440,1000],states=[initial] if args.public_snapshot else ['LONG','SHORT','WAIT'],timeframes=['5m','15m','1h','4h'],read_only_requests=True,android_device_verified=False,production_changed=False)
                (args.output_dir/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        finally:
            server.shutdown();server.server_close();proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':main()
