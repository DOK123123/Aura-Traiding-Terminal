"""Isolated preview guards. No Render, Supabase or market traffic."""
import base64,json,time
from pathlib import Path
from unittest.mock import AsyncMock
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from app.manual_preview.config import parse,PRODUCTION_REFS
from app.manual_preview.store import PreviewStore
from app.manual_preview.page import page,ASSETS
from app.manual_preview import main
from app.manual_paper.store import ManualStore
from app.manual_paper.service import Service

REF='abcdefghijklmnopqrst'
SECRET='sb_secret_DUMMY_ONLY_PREVIEW_NOT_REAL_KEY_1234'
PASS='DUMMY_ONLY_PREVIEW_PASSWORD_123'
AUTH=('aura',PASS)

def environment():return dict(AURA_PREVIEW_ONLY='true',AURA_PREVIEW_OWNER_PASSWORD=PASS,AURA_PREVIEW_PROJECT_REF=REF,AURA_PREVIEW_SUPABASE_URL='https://'+REF+'.supabase.co',AURA_PREVIEW_SUPABASE_SERVICE_KEY=SECRET)

def jwt(ref):
    enc=lambda obj:base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip('=')
    return enc({'alg':'HS256','typ':'JWT'})+'.'+enc({'role':'service_role','ref':ref,'exp':int(time.time())+3600})+'.DUMMY_TEST_SIGNATURE_ONLY'

@pytest.mark.parametrize('key,value,code',[
 ('AURA_PREVIEW_ONLY','false','PREVIEW_MODE_REQUIRED'),
 ('RENDER_SERVICE_ID','srv-db5tonlckfvc73be2m5g','PREVIEW_PRODUCTION_SERVICE_FORBIDDEN'),
 ('AURA_PREVIEW_PROJECT_REF',next(iter(PRODUCTION_REFS)),'PREVIEW_PROJECT_FORBIDDEN'),
 ('AURA_PREVIEW_SUPABASE_URL','https://uvcbhicbnqpqobxnufph.supabase.co','PREVIEW_PROJECT_URL_MISMATCH'),
 ('AURA_MANUAL_PAPER_SUPABASE_SERVICE_KEY','DUMMY_PROD','PREVIEW_FOREIGN_ENV_FORBIDDEN'),
 ('SUPABASE_URL','https://example.invalid','PREVIEW_FOREIGN_ENV_FORBIDDEN'),
 ('AURA_ACTIVE43_BITGET_ENABLED','false','PREVIEW_FOREIGN_ENV_FORBIDDEN'),
 ('BITGET_SECRET_KEY','DUMMY_NOT_ALLOWED','PREVIEW_FOREIGN_ENV_FORBIDDEN'),
 ('AURA_PREVIEW_OWNER_PASSWORD','short','PREVIEW_OWNER_PASSWORD_REQUIRED'),
 ('AURA_PREVIEW_SUPABASE_SERVICE_KEY',jwt('uvcbhicbnqpqobxnufph'),'PREVIEW_PROJECT_BOUND_KEY_REQUIRED'),
 ('AURA_PREVIEW_SUPABASE_SERVICE_KEY','sb_publishable_DUMMY','PREVIEW_PROJECT_BOUND_KEY_REQUIRED')])
def test_unsafe_config_rejected_before_network(key,value,code):
    env=environment();env[key]=value
    with pytest.raises(ValueError,match=code):parse(env)


def test_dedicated_modern_and_legacy_keys_and_repr_no_secrets():
    c=parse(environment());assert not c.manual_enabled and c.key==SECRET
    assert SECRET not in repr(c) and PASS not in repr(c)
    e=environment();e['AURA_PREVIEW_SUPABASE_SERVICE_KEY']=jwt(REF);assert parse(e).project_ref==REF

@pytest.mark.parametrize('reply',[None,{},dict(scope='AURA_MANUAL_PREVIEW_ONLY_V1',project_ref='other',role='service_role',isolated=True),dict(scope='AURA_MANUAL_PREVIEW_ONLY_V1',project_ref=REF,role='service_role',isolated=False)])
def test_scope_failure_never_sends_any_ledger_rpc(reply):
    calls=[]
    def handler(r):calls.append(r.url.path);return httpx.Response(200,json=reply)
    store=PreviewStore(parse(environment()),transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError,match='STORAGE_SCOPE_MISMATCH'):store.rpc('commit',{})
        assert calls==['/rest/v1/rpc/aura_manual_preview_guard']
    finally:store.close()


def test_foreign_modern_secret_on_pinned_preview_host_fails_read_guard_before_write():
    calls=[]
    def handler(r):
        calls.append((r.url.host,r.url.path));return httpx.Response(401,json={'message':'not exposed'})
    store=PreviewStore(parse(environment()),transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError,match='STORAGE_SCOPE_MISMATCH'):store.rpc('commit',{})
        assert calls==[(REF+'.supabase.co','/rest/v1/rpc/aura_manual_preview_guard')]
    finally:store.close()


def test_guard_rechecked_for_each_rpc_and_can_revoke_writes():
    calls=[];valid=True
    def handler(r):
        calls.append(r.url.path)
        if r.url.path.endswith('aura_manual_preview_guard'):return httpx.Response(200,json=dict(scope='AURA_MANUAL_PREVIEW_ONLY_V1',project_ref=REF,role='service_role',isolated=valid))
        return httpx.Response(200,content=b'null')
    s=PreviewStore(parse(environment()),transport=httpx.MockTransport(handler))
    try:
        s.rpc('load',{'known_version':None});valid=False
        with pytest.raises(ValueError):s.rpc('commit',{})
        assert len(calls)==3 and calls[-1].endswith('guard')
    finally:s.close()

@pytest.fixture
def preview(tmp_path,monkeypatch):
    # No imported production configuration, accounts or credentials.
    for key in list(__import__('os').environ):
        if key.startswith(('AURA_','SUPABASE_','BYBIT_','BINANCE_','BITGET_','CLOUDFLARE_','CF_')) or key in {'DATABASE_URL','PGPASSWORD','PGSERVICE','RENDER_API_KEY','RENDER_DEPLOY_HOOK','GITHUB_TOKEN','GH_TOKEN'}:monkeypatch.delenv(key)
    for key,value in environment().items():monkeypatch.setenv(key,value)
    class ReadGuard:
        def verify_scope(self):return True
        def close(self):pass
    monkeypatch.setattr(main,'PreviewStore',lambda config:ReadGuard())
    monkeypatch.setattr(main,'_preview_probe_history',AsyncMock(return_value=None))
    with TestClient(main.app) as client:
        yield client


def test_preview_health_owner_static_and_no_automatic_routes(preview):
    assert preview.get('/api/health').json()['scope']=='ISOLATED_MANUAL_PREVIEW'
    for path in ['/','/static/manual-paper.js','/api/manual-paper/state','/api/preview/readiness']:
        r=preview.get(path);assert r.status_code==401 and SECRET not in r.text
    p=preview.get('/',auth=AUTH);assert p.status_code==200
    assert 'data-manual-preview="true"' in p.text and 'id="active43-panel"' not in p.text
    assert '/api/active43' not in p.text and 'patterns.js' not in p.text
    for path in ['/api/active43/status','/api/auto42/status','/static/active43.js','/static/active43-historical-trades.json.gz']:
        assert preview.get(path,auth=AUTH).status_code==404
    assert preview.get('/api/manual-paper/state',auth=AUTH).json()['code']=='MANUAL_PAPER_DISABLED'


def test_preview_confirmation_header_in_addition_to_owner_and_csrf(preview):
    body=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000')
    assert preview.post('/api/manual-paper/orders',json=body,auth=AUTH,headers={'X-Aura-Paper':'local-only'}).status_code==403
    head={'X-Aura-Preview-Confirm':'manual-virtual','X-Aura-Paper':'local-only'}
    assert preview.post('/api/manual-paper/orders',json=body,auth=AUTH,headers=head).status_code==503
    assert preview.post('/api/active43/tick',auth=AUTH,headers=head).status_code==403


def test_preview_readiness_does_not_seed_or_trade(preview,monkeypatch):
    q=AsyncMock(return_value={});monkeypatch.setattr(main,'fetch_execution_quote',q)
    r=preview.get('/api/preview/readiness',auth=AUTH)
    assert r.status_code==200 and r.json()['state_changed'] is False
    assert r.json()['ready'] is True and r.json()['manual_enabled'] is False
    assert preview.app.state.manual_paper.store is None


def test_blueprint_policy_and_generated_sql_current():
    from scripts.build_manual_preview_sql import rendered
    cfg=json.loads(Path('deploy/manual-preview/render.yaml').read_text());assert len(cfg['services'])==1 and set(cfg)=={'services'}
    s=cfg['services'][0];assert s['plan']=='free' and s['autoDeployTrigger']=='off'
    assert s['startCommand'].startswith('python -m uvicorn app.manual_preview.main:app')
    assert 'disk' not in s and 'preDeployCommand' not in s and 'fromGroup' not in json.dumps(cfg)
    env={v['key']:v for v in s['envVars']};assert env['AURA_PREVIEW_MANUAL_ENABLED']['value']=='false'
    for key in ['AURA_PREVIEW_OWNER_PASSWORD','AURA_PREVIEW_SUPABASE_SERVICE_KEY']:assert env[key]=={'key':key,'sync':False}
    assert Path('deploy/manual-preview/schema.sql').read_text()==rendered()
    assert 'PREVIEW_EMPTY_PROJECT_REQUIRED' in rendered() and 'REPLACE_PREVIEW_PROJECT_REF' in rendered()

@pytest.mark.parametrize('side,stop,target,exit_bid,exit_ask,reason',[
 ('LONG','79500','81000','81000','81001','TAKE_PROFIT'),
 ('LONG','79500','81000','79000','79001','STOP_LOSS'),
 ('SHORT','80500','79000','78999','79000','TAKE_PROFIT'),
 ('SHORT','80500','79000','80999','81000','STOP_LOSS')])
def test_preview_owner_full_cycle_restart_and_protective_exit(preview,tmp_path,side,stop,target,exit_bid,exit_ask,reason):
    import asyncio
    from dataclasses import replace
    stamp=int(time.time()*1000);clock=lambda:stamp/1000
    def quote(bid='80000',ask='80001'):
        return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',time=stamp,
                    bid=Decimal(bid),ask=Decimal(ask),price=Decimal(bid),bid_size=Decimal('1'),ask_size=Decimal('1'))
    store=ManualStore(tmp_path/'manual-paper.sqlite3');svc=Service(store,clock=clock);svc.quote=AsyncMock(return_value=quote())
    preview.app.state.preview_config=replace(preview.app.state.preview_config,manual_enabled=True)
    preview.app.state.manual_paper=svc
    from types import SimpleNamespace
    preview.app.state.preview_protection_task=SimpleNamespace(done=lambda:False)
    body=dict(request_id='a'*32,side=side,quantity='0.01',stop=stop,target=target)
    h={'X-Aura-Preview-Confirm':'manual-virtual','X-Aura-Paper':'local-only'}
    opened=preview.post('/api/manual-paper/orders',json=body,auth=AUTH,headers=h);assert opened.status_code==200,opened.text
    saved=opened.json();assert preview.post('/api/manual-paper/orders',json=body,auth=AUTH,headers=h).json()==saved
    # Destroy service/store objects: a new isolated instance restores the account.
    restored=Service(ManualStore(store.path),clock=clock);restored.quote=AsyncMock(return_value=quote(exit_bid,exit_ask));preview.app.state.manual_paper=restored
    state=preview.get('/api/manual-paper/state',auth=AUTH).json();assert state['position']['id']=='a'*32
    asyncio.run(restored.protect());asyncio.run(restored.protect())
    ledger,_=restored.store.load();assert len(ledger.trades)==1 and ledger.position is None
    assert ledger.trades[0]['reason']==reason
    assert ledger.balance==Decimal('10000')+ledger.trades[0]['net']
    assert preview.post('/api/manual-paper/orders',json=body,auth=AUTH,headers=h).json()==saved

@pytest.mark.skipif(__import__('os').getenv('AURA_MANUAL_PAPER_VERIFY_POSTGRES')!='true',reason='Disposable local PostgreSQL opt-in')
def test_preview_real_postgresql_isolation_and_restart():
    from scripts.verify_manual_preview_postgres import run
    result=run();assert result['status']=='PASS' and len(result['checks'])==7
    assert result['production_changed'] is False and result['hosted_supabase_verified'] is False


def test_dead_protection_worker_blocks_new_open(preview):
    from dataclasses import replace
    preview.app.state.preview_config=replace(preview.app.state.preview_config,manual_enabled=True)
    body=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000')
    h={'X-Aura-Preview-Confirm':'manual-virtual','X-Aura-Paper':'local-only'}
    preview.app.state.preview_protection_task=None
    response=preview.post('/api/manual-paper/orders',json=body,auth=AUTH,headers=h)
    assert response.status_code==503 and response.json()['code']=='PREVIEW_PROTECTION_UNAVAILABLE'


def test_preview_import_never_loads_main_or_auto_controllers():
    import subprocess,sys
    result=subprocess.check_output([sys.executable,'-c',"import sys,json;import app.manual_preview.main;print(json.dumps([x for x in ['app.main','app.active43.service','app.automated.service'] if x in sys.modules]))"],text=True)
    assert json.loads(result)==[]


def test_actual_preview_uvicorn_restart_keeps_account(tmp_path):
    import os,socket,subprocess,sys
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env={'PATH':os.environ['PATH'],'PYTHONPATH':os.getcwd(),**environment(),
         'AURA_PREVIEW_MANUAL_ENABLED':'true','MANUAL_PREVIEW_TEST_ONLY':'1',
         'MANUAL_PREVIEW_TEST_DB':str(tmp_path/'manual-paper.sqlite3'),'MANUAL_PREVIEW_TEST_PORT':str(port)}
    def start():
        proc=subprocess.Popen([sys.executable,'tests/manual_preview_web_fixture.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if proc.poll() is not None:raise AssertionError('PREVIEW_FIXTURE_START_FAILED')
            try:
                if httpx.get(f'http://127.0.0.1:{port}/api/health',trust_env=False,timeout=.2).status_code==200:return proc
            except httpx.HTTPError:pass
            time.sleep(.05)
        proc.terminate();proc.wait(timeout=5);raise AssertionError('PREVIEW_FIXTURE_TIMEOUT')
    body=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000')
    headers={'X-Aura-Paper':'local-only','X-Aura-Preview-Confirm':'manual-virtual'}
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',auth=AUTH,headers=headers,trust_env=False,timeout=10) as client:
        p=start()
        try:
            receipt=client.post('/api/manual-paper/orders',json=body);assert receipt.status_code==200,receipt.text
            before=client.get('/api/manual-paper/state').json();assert before['position']['id']=='a'*32
            assert client.get('/api/active43/status').status_code==404
        finally:p.terminate();p.wait(timeout=10)
        env['MANUAL_PREVIEW_TEST_BID']='80500';p=start()
        try:
            state=client.get('/api/manual-paper/state').json();assert state['balance']==before['balance'] and state['position']==before['position']
            assert client.post('/api/manual-paper/orders',json=body).json()==receipt.json()
            closed=client.post('/api/manual-paper/positions/'+'a'*32+'/close',json={'request_id':'b'*32});assert closed.status_code==200,closed.text
            state=client.get('/api/manual-paper/state').json();assert state['position'] is None and state['history_total']==1
            assert Decimal(state['balance'])==Decimal('10000')+Decimal(state['trades'][0]['net'])
        finally:p.terminate();p.wait(timeout=10)


def test_preview_chart_bridge_scope_and_auth(preview):
    # No private exchange API, no production access, no writable preview market route.
    assert preview.get('/api/preview/bitget/candles').status_code == 401
    assert preview.get('/api/preview/bitget/candles',auth=AUTH).status_code == 400
    assert preview.get('/api/preview/bitget/candles?symbol=ETHUSDT&productType=USDT-FUTURES&granularity=1m&limit=201',auth=AUTH).status_code == 400
    assert preview.post('/api/preview/bitget/candles',auth=AUTH).status_code == 403
    page_response=preview.get('/',auth=AUTH)
    assert 'name="aura-preview-ws-token"' in page_response.text
    assert main.app.state.preview_ws_token in page_response.text
    assert main.app.state.preview_ws_token not in preview.get('/api/health').text


def test_preview_fixed_public_candles_relay(preview):
    # Mocked public-only Bitget transport. Never contact real market during CI.
    calls=[]
    def handler(req):
        calls.append((req.method,str(req.url)))
        now=time.time();current=int(now//60)*60
        bars=[[str((current-200*60+i*60)*1000),'100','101','99','100','1','2'] for i in range(201)]
        return httpx.Response(200,json={'code':'00000','requestTime':int(now*1000),'data':bars})
    main.app.state.preview_public_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response=preview.get('/api/preview/bitget/candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=1m&limit=201',auth=AUTH)
    assert response.status_code == 200
    assert response.json()['code']=='00000'
    assert len(calls)==1
    assert calls[0][0]=='GET'
    assert calls[0][1]=='https://api.bitget.com/api/v2/mix/market/candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=1m&limit=201'


def test_preview_history_integrity_diagnostics():
    step=60
    at=1760000000//step*step+25
    base=at//step*step-200*step
    bars=[[str((base+i*step)*1000),'100','101','99','100','1','2'] for i in range(201)]
    body={'code':'00000','requestTime':at*1000,'data':bars}
    assert main._preview_history_quality(body,'1m',at)=='PASS'
    assert main._preview_history_quality(body,'1m',at+11)=='STALE_REQUEST_TIME'
    bad={**body,'data':bars[:-3]+bars[-2:]}
    assert main._preview_history_quality(bad,'1m',at)=='HISTORY_GAP'
    unaligned={**body,'data':[[str(int(r[0])+25000),*r[1:]] for r in bars]}
    assert main._preview_history_quality(unaligned,'1m',at)=='INVALID_ROW_VALUES_OR_TIME'


def test_preview_preserves_chart_dom_and_dependency_order():
    """The reduced page must keep every shared-chart DOM target, including footer."""
    import re
    from html.parser import HTMLParser
    class Elements(HTMLParser):
        def __init__(self):super().__init__();self.ids=[]
        def handle_starttag(self,tag,attrs):
            self.ids.extend(value for name,value in attrs if name=='id')
    html=page()
    elements=Elements();elements.feed(html)
    source=(Path(__file__).parents[1]/'static/app.js').read_text()
    targets=set(re.findall(r'''\$\(['"]([^'"]+)['"]\)''',source))
    assert targets<=set(elements.ids)
    assert elements.ids.count('last-updated')==1
    assert html.index('manual-live-analysis.js')<html.index('manual-live-feed.js')<html.index('/static/app.js')<html.index('manual-live-ui.js')


def test_preview_rejects_unverified_public_history(preview):
    def handler(req):
        return httpx.Response(200,json={'code':'00000','requestTime':int(time.time()*1000),'data':[]})
    main.app.state.preview_public_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response=preview.get('/api/preview/bitget/candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=1m&limit=201',auth=AUTH)
    assert response.status_code==503
    assert response.json()['code']=='PUBLIC_MARKET_UNAVAILABLE'
