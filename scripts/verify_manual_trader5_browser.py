"""Real Chrome + real loopback API/SQLite; synthetic quotes; zero external I/O.

Usage: python scripts/verify_manual_trader5_browser.py --browser /path/to/chrome --output-dir /new/path
"""
import argparse
import base64
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx
from websockets.sync.client import connect

ROOT=Path(__file__).resolve().parents[1]


def main():
    if os.getenv('RENDER'):raise ValueError('LOCAL_TEST_ONLY')
    p=argparse.ArgumentParser();p.add_argument('--browser',required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=False)
    fixture=json.loads((ROOT/'tests/fixtures/aura_analyst_synthetic.json').read_text());stamp=fixture['now']*1000
    with tempfile.TemporaryDirectory(prefix='aura-manual-browser-') as folder:
        folder=Path(folder)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        env={k:v for k,v in os.environ.items() if not k.startswith(('AURA_','BYBIT_','BINANCE_','PAPER_','RENDER'))}
        env['PYTHONPATH']=str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')
        api=subprocess.Popen([sys.executable,'tests/manual_trader5_web_fixture.py','--db',str(folder/'manual-paper.sqlite3'),'--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        chrome=None
        try:
            with httpx.Client(base_url=base,trust_env=False,timeout=3) as client:
                for _ in range(100):
                    if api.poll() is not None:raise AssertionError(api.stderr.read().decode())
                    try:
                        if client.get('/__test/audit').status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.05)
                else:raise AssertionError('fixture startup timeout')
                assert client.get('/api/manual-paper/state').status_code==401
                chrome=subprocess.Popen([a.browser,'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=127.0.0.1;localhost',f'--user-data-dir={folder}/profile','--remote-debugging-port=0','about:blank'],env={'PATH':os.defpath,'LANG':'C.UTF-8'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                active=folder/'profile/DevToolsActivePort'
                for _ in range(100):
                    if active.exists():break
                    if chrome.poll() is not None:raise AssertionError(chrome.stderr.read().decode())
                    time.sleep(.05)
                port2=active.read_text().splitlines()[0]
                pages=httpx.get(f'http://127.0.0.1:{port2}/json/list',trust_env=False).json()
                with connect(pages[0]['webSocketDebuggerUrl'],proxy=None) as ws:
                    seq=0
                    def call(method,params=None):
                        nonlocal seq
                        seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
                        while True:
                            r=json.loads(ws.recv(timeout=15))
                            if r.get('id')==seq:
                                if 'error' in r:raise AssertionError(r['error'])
                                return r.get('result',{})
                    def ev(expression):
                        r=call('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
                        if 'exceptionDetails' in r:raise AssertionError(r['exceptionDetails'])
                        return r['result'].get('value')
                    def wait(expression):
                        for _ in range(200):
                            if ev(expression):return
                            time.sleep(.04)
                        diagnostic=ev("({url:location.href,title:document.title,status:document.getElementById('mp-status')?.textContent,text:document.body?.innerText.slice(0,5000),errors:window.__errors,calls:window.__calls})")
                        (a.output_dir/'failure.json').write_text(json.dumps(diagnostic,indent=2))
                        (a.output_dir/'failure.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',dict(format='png'))['data']))
                        raise AssertionError('Browser timeout: '+expression+'\n'+json.dumps(diagnostic))
                    def click(id,touch=False):
                        ev(f"document.getElementById('{id}').scrollIntoView({{block:'center'}})")
                        r=ev(f"(()=>{{const r=document.getElementById('{id}').getBoundingClientRect();return {{x:r.x+r.width/2,y:r.y+r.height/2}};}})()")
                        if touch:
                            call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[dict(**r,id=1)]));call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]))
                        else:
                            call('Input.dispatchMouseEvent',dict(type='mousePressed',**r,button='left',clickCount=1));call('Input.dispatchMouseEvent',dict(type='mouseReleased',**r,button='left',clickCount=1))
                    def setval(id,value):ev(f"document.getElementById('{id}').value={json.dumps(str(value))};document.getElementById('{id}').dispatchEvent(new Event('input'))")
                    def control(**kw):assert client.post('/__test/control',json=kw).status_code==200
                    def audit():return client.get('/__test/audit').json()
                    def analysis(case):
                        control(case=case,bid=None,stale=False)
                        click('analyst-refresh');wait(f"document.getElementById('analyst-state').textContent==='{case if case in ('LONG','SHORT') else 'WAIT'}'")
                        click('mp-refresh');wait("document.getElementById('mp-refresh').disabled===false")
                    shots=[]
                    def shot(name,selector='#manual-paper-panel'):
                        assert ev('document.documentElement.scrollWidth<=innerWidth')
                        bounds=ev("(()=>{const r=document.querySelector("+json.dumps(selector)+").getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1};})()")
                        raw=call('Page.captureScreenshot',dict(format='png',clip=bounds,captureBeyondViewport=True))['data']
                        (a.output_dir/(name+'.png')).write_bytes(base64.b64decode(raw));shots.append(name+'.png')
                    call('Page.enable');call('Network.enable')
                    call('Network.setExtraHTTPHeaders',dict(headers={'Authorization':'Basic '+base64.b64encode(b'aura:dummy-browser-manual-password').decode()}))
                    call('Page.addScriptToEvaluateOnNewDocument',dict(source=f"window.__clock={stamp};const NativeDate=Date;Date=class extends NativeDate{{static now(){{return window.__clock;}}}};window.__errors=[];addEventListener('error',e=>__errors.push(e.message));window.__calls=[];const nativeFetch=fetch;fetch=(u,o={{}})=>{{__calls.push({{url:String(u),method:o.method||'GET'}});return nativeFetch(u,o);}};"))
                    call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))
                    navigation=call('Page.navigate',dict(url=base+'/'));print('Browser navigation:',json.dumps(navigation),flush=True)
                    wait("document.getElementById('analyst-state')?.textContent==='LONG'&&!document.getElementById('mp-long').disabled")
                    ev("const b=document.createElement('p');b.textContent='СИНТЕТИЧЕСКИЙ ЛОКАЛЬНЫЙ СТЕНД · НЕ PRODUCTION';document.getElementById('manual-paper-panel').prepend(b)")
                    assert ev("document.querySelectorAll('#chart canvas').length>0")
                    shot('desktop-analyst','#aura-analyst')
                    click('mp-copy');setval('mp-quantity','0.01')
                    before=audit()['version'];click('mp-long');wait("document.getElementById('mp-confirm-dialog').open")
                    assert audit()['version']==before
                    shot('desktop-confirm','#mp-confirm-dialog');click('mp-cancel');assert audit()['version']==before
                    click('mp-long');wait("document.getElementById('mp-confirm-dialog').open");click('mp-confirm')
                    # Double click after the dialog closes cannot create another intent.
                    ev("document.getElementById('mp-confirm').click()")
                    wait("document.getElementById('mp-position').textContent.includes('LONG')")
                    ledger=audit()['ledger'];assert ledger['position']['side']=='LONG' and not ledger['trades']
                    call('Page.reload');wait("document.getElementById('mp-position')?.textContent.includes('LONG')")
                    shot('desktop-position')
                    click('mp-close');wait("document.getElementById('mp-confirm-dialog').open");assert audit()['ledger']['position']
                    click('mp-confirm');wait("document.getElementById('mp-position').textContent==='Нет открытой позиции'")
                    trade=audit()['ledger']['trades'][0]
                    entry=Decimal(trade['entry']);exit=Decimal(trade['exit']);qty=Decimal('0.01')
                    assert Decimal(trade['net'])==(exit-entry)*qty-(entry+exit)*qty*Decimal('.0006')
                    # Mobile: actual touch input, copied SHORT, lost committed response,
                    # reload and retry of the same durable intent, then protective SL.
                    call('Emulation.setDeviceMetricsOverride',dict(width=393,height=851,deviceScaleFactor=1,mobile=True))
                    call('Emulation.setTouchEmulationEnabled',dict(enabled=True,maxTouchPoints=1))
                    analysis('SHORT');click('mp-copy',True);setval('mp-quantity','0.01');shot('mobile-plan')
                    control(loss=True);click('mp-short',True);wait("document.getElementById('mp-confirm-dialog').open");shot('mobile-confirm','#mp-confirm-dialog')
                    click('mp-confirm',True);wait("!document.getElementById('mp-retry').hidden&&!document.getElementById('mp-retry').disabled")
                    pending=ev("localStorage.getItem('aura-manual-paper-v1-pending')")
                    assert pending and audit()['ledger']['position']['side']=='SHORT'
                    version=audit()['version'];call('Page.reload');wait("document.getElementById('mp-retry')?.hidden===false")
                    assert audit()['version']==version
                    click('mp-retry',True);wait("document.getElementById('mp-retry').hidden")
                    assert audit()['version']==version and ev("localStorage.getItem('aura-manual-paper-v1-pending')")==None
                    p2=audit()['ledger']['position'];control(bid=str(Decimal(p2['stop'])+10),protect=True)
                    click('mp-refresh',True);wait("document.getElementById('mp-position').textContent==='Нет открытой позиции'")
                    assert audit()['ledger']['trades'][-1]['reason']=='STOP_LOSS'
                    shot('mobile-journal')
                    analysis('LONG');click('mp-copy',True)
                    for case in ['WAIT','RATE_LIMIT','HISTORY_CANDLE_CHANGED']:
                        analysis(case);assert ev("document.getElementById('mp-copy').disabled&&document.getElementById('mp-long').disabled")
                    shot('mobile-wait')
                    click('mp-manual',True);control(stale=True);click('mp-refresh',True)
                    wait("document.getElementById('mp-long').disabled&&document.getElementById('mp-equity').textContent==='—'")
                    control(stale=False,unauthorized=True);click('mp-refresh',True);wait("document.getElementById('mp-status').textContent.includes('владелец')")
                    assert ev("document.getElementById('mp-long').disabled&&document.getElementById('mp-close').disabled")
                    assert ev('window.__errors')==[],ev('window.__errors')
                    calls=ev('window.__calls')
                    assert all(c['url'].startswith('/') for c in calls)
                    writes=[c for c in calls if c['method']=='POST']
                    assert all(c['url'].startswith('/api/manual-paper/') for c in writes)
                    report=dict(status='PASS',scope='SYNTHETIC_LOOPBACK_REAL_CHROME_SQLITE',browser=call('Browser.getVersion'),screenshots=shots,
                        mobile_viewport=[393,851],touch=True,checks=['LONG/SHORT/WAIT','preview no writes','explicit OPEN/CLOSE confirmation','cancel','duplicate clicks','risk/fees/net PnL','reload persistence','lost-response same-ID retry','SL observed gap','429/history mismatch WAIT','stale quotes','owner 401','no external or Active43 writes'],production_changed=False,physical_android_verified=False)
                    (a.output_dir/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        finally:
            for proc in (chrome,api):
                if proc is not None:
                    proc.terminate()
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()


if __name__=='__main__':main()
