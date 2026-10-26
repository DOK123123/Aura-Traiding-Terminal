"""No exchange orders, credentials or external network. Real SQLite transactions."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.manual_paper.api import router
from app.manual_paper.bitget import fetch_execution_quote
from app.manual_paper.commands import ManualCommands
from app.manual_paper.core import ManualPaper
from app.manual_paper.quotes import QuoteRejected
from app.manual_paper.service import Service, configured
from app.manual_paper.store import ManualStore

STAMP=1793007900000
AUTH=('aura','dummy-manual-test-password')
HEAD={'X-Aura-Paper':'local-only','Origin':'http://testserver'}
BODY=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000')


def quote(bid='80000',ask='80001',stamp=STAMP):
    return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',
                time=stamp,bid=Decimal(bid),ask=Decimal(ask),price=Decimal(bid),bid_size=Decimal('1'),ask_size=Decimal('1'))


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',AUTH[1])
    service=Service(ManualStore(tmp_path/'manual-paper.sqlite3'),clock=lambda:STAMP/1000)
    service.quote=AsyncMock(return_value=quote())
    app=FastAPI();app.include_router(router);app.state.manual_paper=service
    with TestClient(app) as client:
        yield client,service


def post(client,path='/orders',body=None,headers=None):
    return client.post('/api/manual-paper'+path,json=BODY if body is None else body,auth=AUTH,headers=HEAD if headers is None else headers)


@pytest.mark.parametrize('side,bid,ask,stop,target,exit_bid,exit_ask,expected',[
    ('LONG','80000','80001','79500','81000','81000','81001','9.023994'),
    ('SHORT','80000','80001','80500','79000','78999','79000','9.046000'),
])
def test_api_long_short_fees_and_restart(setup,side,bid,ask,stop,target,exit_bid,exit_ask,expected):
    client,svc=setup
    initial=client.get('/api/manual-paper/state',auth=AUTH)
    assert initial.status_code==200 and initial.json()['balance']=='10000'
    svc.quote.return_value=quote(bid,ask)
    body={**BODY,'side':side,'stop':stop,'target':target}
    opened=post(client,body=body)
    assert opened.status_code==200,opened.text
    assert opened.json()['result']['id']==BODY['request_id']
    svc.quote.return_value=quote(exit_bid,exit_ask,STAMP+1000);svc.clock=lambda:(STAMP+1000)/1000
    # Recreate storage + service, as after restart, with no lost balance/position.
    restored=Service(ManualStore(svc.store.path),clock=svc.clock)
    restored.quote=svc.quote;client.app.state.manual_paper=restored
    state=client.get('/api/manual-paper/state',auth=AUTH).json()
    assert state['position']['id']==BODY['request_id']
    assert Decimal(state['position_net_pnl'])==Decimal(expected)
    closed=post(client,'/positions/'+BODY['request_id']+'/close',dict(request_id='b'*32))
    assert closed.status_code==200,closed.text
    assert Decimal(closed.json()['result']['net'])==Decimal(expected)
    restored.quote.side_effect=QuoteRejected('MARKET_UNAVAILABLE')
    assert post(client,body=body).json()==opened.json()
    assert post(client,'/positions/'+BODY['request_id']+'/close',dict(request_id='b'*32)).json()==closed.json()
    history=client.get('/api/manual-paper/state',auth=AUTH).json()
    assert history['position'] is None and history['history_total']==1
    assert history['equity'] is None and history['market_error']=='MARKET_UNAVAILABLE'
    assert Decimal(history['balance'])==Decimal('10000')+Decimal(expected)


@pytest.mark.parametrize('headers',[{}, {'Origin':'http://evil.invalid','X-Aura-Paper':'local-only'},
    {'X-Aura-Paper':'local-only','Sec-Fetch-Site':'cross-site'},
    {'X-Aura-Paper':'local-only','Origin':'https://testserver'}])
def test_csrf(setup,headers):
    client,svc=setup
    assert post(client,headers=headers).status_code==403
    assert svc.store.load()==(None,0)


@pytest.mark.parametrize('path,method',[
    ('/state','get'),('/quote','get'),('/orders','post'),('/positions/'+'a'*32+'/close','post')])
def test_owner_required(setup,path,method):
    client,svc=setup
    assert getattr(client,method)('/api/manual-paper'+path).status_code==401
    assert svc.store.load()==(None,0)


@pytest.mark.parametrize('patch_body',[
    {'quantity':True},{'quantity':'NaN'},{'quantity':'1e1000000'},{'stop':'Infinity'},
    {'side':'BUY'},{'symbol':'ETHUSDT'},{'entry':'1'},{'price':'1'},{'request_id':'bad'},
])
def test_untrusted_body_rejected(setup,patch_body):
    client,svc=setup
    assert post(client,body={**BODY,**patch_body}).status_code==422
    assert svc.store.load()==(None,0)


@pytest.mark.parametrize('patch_body,code',[
    ({'quantity':'0.1'},'POSITION_SIZE_LIMIT'),({'stop':'70000','quantity':'0.02'},'RISK_LIMIT'),
    ({'stop':'81000'},'INVALID_STOPS'),({'quantity':'0'},'INVALID_NUMBER'),
])
def test_risk_atomic_reject(setup,patch_body,code):
    client,svc=setup
    r=post(client,body={**BODY,**patch_body})
    assert r.status_code==409 and r.json()['code']==code
    assert svc.store.load()==(None,0)


def test_replays_ignore_changing_quote_and_close_is_position_scoped(setup):
    client,svc=setup
    first=post(client).json();svc.quote.return_value=quote('80200','80201')
    assert post(client,body={**BODY,'quantity':'0.010'}).json()==first
    assert post(client,body={**BODY,'quantity':'0.02'}).json()['code']=='IDEMPOTENCY_CONFLICT'
    assert post(client,'/positions/'+'c'*32+'/close',{'request_id':'d'*32}).json()['code']=='POSITION_NOT_FOUND'
    assert svc.store.load()[0].position.id==BODY['request_id']


@pytest.mark.parametrize('mutation',[
    lambda q:dict(q,time=STAMP-5001),lambda q:dict(q,time=STAMP+1),
    lambda q:dict(q,source='Bybit'),lambda q:dict(q,product='SPOT')])
def test_bad_quote_never_mutates(setup,mutation):
    client,svc=setup;svc.quote.return_value=mutation(quote())
    r=post(client)
    assert r.status_code==503
    assert svc.store.load()==(None,0)


def test_expired_while_waiting_for_storage_transaction(setup):
    client,svc=setup
    original=svc.store.execute
    def delayed(*args):
        svc.clock=lambda:STAMP/1000+6
        return original(*args)
    svc.store.execute=delayed
    assert post(client).json()['code']=='STALE_QUOTE'
    assert svc.store.load()==(None,0)


@pytest.mark.parametrize('side,bid,ask,stop,target,reason,fill',[
    ('LONG','78000','78001','79500','81000','STOP_LOSS','78000'),
    ('LONG','82000','82001','79500','81000','TAKE_PROFIT','82000'),
    ('SHORT','82000','82001','80500','79000','STOP_LOSS','82001'),
    ('SHORT','78000','78001','80500','79000','TAKE_PROFIT','78001'),
])
def test_protective_exit_observed_price_gap_and_no_double_exit(setup,side,bid,ask,stop,target,reason,fill):
    client,svc=setup
    assert post(client,body={**BODY,'side':side,'stop':stop,'target':target}).status_code==200
    svc.quote.return_value=quote(bid,ask)
    asyncio.run(svc.protect());asyncio.run(svc.protect())
    ledger,_=svc.store.load()
    assert ledger.position is None and len(ledger.trades)==1
    assert ledger.trades[0]['exit']==Decimal(fill) and ledger.trades[0]['reason']==reason


def test_unavailable_protection_preserves_position_and_balance(setup):
    client,svc=setup;post(client)
    before=svc.store.load();svc.quote.side_effect=QuoteRejected('MARKET_UNAVAILABLE')
    with pytest.raises(QuoteRejected):asyncio.run(svc.protect())
    after=svc.store.load()
    assert after[1]==before[1] and after[0].balance==before[0].balance
    assert after[0].position==before[0].position


def test_concurrent_process_like_stores_one_open(tmp_path):
    path=tmp_path/'manual-paper.sqlite3'
    def run(i):
        try:return ManualCommands(ManualStore(path)).open(format(i,'032x'),'LONG','0.01','79500','81000',dict(quote(),price='80000'))
        except ValueError as e:return str(e)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(run,range(1,17)))
    assert sum(isinstance(r,dict) for r in results)==1
    assert set(r for r in results if isinstance(r,str))=={'POSITION_ALREADY_OPEN'}
    assert ManualStore(path).load()[1]==1


def test_same_id_concurrency_and_transaction_rollback(tmp_path):
    store=ManualStore(tmp_path/'manual-paper.sqlite3')
    def run(_):return ManualCommands(store).open('a'*32,'LONG','0.01','79500','81000',dict(quote(),price='80000'))
    with ThreadPoolExecutor(max_workers=8) as pool:receipts=list(pool.map(run,range(16)))
    assert all(r==receipts[0] for r in receipts)
    def fail(ledger):
        ledger.close('81000')
        raise RuntimeError('simulated crash before commit')
    with pytest.raises(RuntimeError):store.execute('b'*32,'CLOSE',{},fail)
    ledger,version=store.load()
    assert version==1 and ledger.position and not ledger.trades
    assert store.lookup('b'*32,'CLOSE',{}) is None


def test_real_process_restart_retains_account_and_receipts(tmp_path):
    path=tmp_path/'manual-paper.sqlite3'
    open_code="""
import sys
from app.manual_paper.store import ManualStore
from app.manual_paper.commands import ManualCommands
ManualCommands(ManualStore(sys.argv[1])).open('a'*32,'LONG','0.01','79500','81000',{'source':'Bitget USDT-M Futures','time':1793007900000,'price':'80000'})
"""
    subprocess.run([sys.executable,'-c',open_code,str(path)],check=True,capture_output=True)
    close_code="""
import sys,json
from app.manual_paper.store import ManualStore
from app.manual_paper.commands import ManualCommands
s=ManualStore(sys.argv[1]); l,v=s.load(); assert l.position.id=='a'*32 and str(l.balance)=='9999.520000'
r=ManualCommands(s).close('b'*32,{'source':'Bitget USDT-M Futures','time':1793007901000,'price':'81000'},'a'*32)
print(json.dumps(r))
"""
    r=subprocess.run([sys.executable,'-c',close_code,str(path)],check=True,capture_output=True,text=True)
    assert Decimal(json.loads(r.stdout)['balance'])==Decimal('10009.034')
    ledger,version=ManualStore(path).load()
    assert version==2 and ledger.position is None and len(ledger.trades)==1


def test_corruption_never_resets_balance(setup):
    client,svc=setup;post(client)
    with sqlite3.connect(svc.store.path) as db:
        raw=json.loads(db.execute('select data from state').fetchone()[0]);raw['balance']='10000'
        db.execute('update state set data=?',(json.dumps(raw),))
    r=client.get('/api/manual-paper/state',auth=AUTH)
    assert r.status_code==503 and r.json()['code']=='CORRUPT_JOURNAL'


@pytest.mark.parametrize('mode,render',[('development','true'),('persistent-disk','true'),('','')])
def test_ephemeral_render_storage_rejected(tmp_path,monkeypatch,mode,render):
    monkeypatch.setenv('AURA_MANUAL_PAPER_ENABLED','true');monkeypatch.setenv('AURA_MANUAL_PAPER_STORAGE',mode)
    monkeypatch.setenv('AURA_MANUAL_PAPER_DB',str(tmp_path/'manual-paper.sqlite3'))
    monkeypatch.setenv('AURA_MANUAL_PAPER_MOUNT',str(tmp_path))
    if render:monkeypatch.setenv('RENDER',render)
    else:monkeypatch.delenv('RENDER',raising=False)
    svc=configured(object());assert svc.store is None and svc.error
    assert not (tmp_path/'manual-paper.sqlite3').exists()


def test_persistent_mount_configuration_only(tmp_path,monkeypatch):
    monkeypatch.setenv('AURA_MANUAL_PAPER_ENABLED','true');monkeypatch.setenv('AURA_MANUAL_PAPER_STORAGE','persistent-disk')
    monkeypatch.setenv('AURA_MANUAL_PAPER_DB',str(tmp_path/'manual-paper.sqlite3'))
    monkeypatch.setenv('AURA_MANUAL_PAPER_MOUNT',str(tmp_path))
    monkeypatch.setattr(os.path,'ismount',lambda p:p==tmp_path)
    svc=configured(object());assert svc.store and svc.durable


def ticker_payload(**changes):
    return dict(code='00000',requestTime=STAMP,data=[dict(symbol='BTCUSDT',ts=str(STAMP),
        bidPr='80000',askPr='80001',lastPr='80000.5',bidSz='1',askSz='1',**changes)])


def test_bitget_fixed_get_allowlist_and_exact_bid_ask():
    calls=[]
    def handler(req):
        calls.append(req)
        assert req.method=='GET' and req.url.host=='api.bitget.com'
        if req.url.path=='/api/v2/public/time':return httpx.Response(200,json=dict(code='00000',data={'serverTime':str(STAMP)}))
        assert req.url.path=='/api/v2/mix/market/ticker'
        assert dict(req.url.params)==dict(symbol='BTCUSDT',productType='USDT-FUTURES')
        return httpx.Response(200,json=ticker_payload())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_execution_quote(client,clock=lambda:STAMP/1000)
    q=asyncio.run(run())
    assert q['bid']==Decimal('80000') and q['ask']==Decimal('80001') and len(calls)==2


@pytest.mark.parametrize('field,value',[
    ('symbol','ETHUSDT'),('bidPr','NaN'),('askPr','0'),('bidPr','82000'),('askPr','90000'),
    ('ts',str(STAMP-5001)),('ts',str(STAMP+1)),('bidSz','0'),('lastPr','90000')])
def test_bad_bitget_response_fails_closed(field,value):
    def handler(req):
        if req.url.path.endswith('/time'):return httpx.Response(200,json=dict(code='00000',data={'serverTime':str(STAMP)}))
        data=ticker_payload();data['data'][0][field]=value
        return httpx.Response(200,json=data)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            await fetch_execution_quote(c,clock=lambda:STAMP/1000)
    with pytest.raises(QuoteRejected):asyncio.run(run())


@pytest.mark.parametrize('status',[302,403,429,500])
def test_market_http_failures_redacted(status):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(status,json={'secret':'dummy-never-expose'}))) as c:
            await fetch_execution_quote(c,clock=lambda:STAMP/1000)
    with pytest.raises(QuoteRejected,match='^MARKET_UNAVAILABLE$'):asyncio.run(run())


def test_http_service_restart_preserves_account_and_idempotency(tmp_path):
    """Actually stop and restart Uvicorn; no TestClient or in-memory persistence."""
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.startswith(('AURA_','BYBIT_','BINANCE_','PAPER_','RENDER'))}
    env.update(AURA_MANUAL_PAPER_ENABLED='true',AURA_MANUAL_PAPER_STORAGE='development',
               AURA_MANUAL_PAPER_DB=str(tmp_path/'manual-paper.sqlite3'),AURA_TESTNET_VIEW_PASSWORD=AUTH[1],
               AURA_ACTIVE43_BITGET_ENABLED='false',MANUAL_TEST_PORT=str(port),PYTHONPATH=os.getcwd()+os.pathsep+os.environ.get('PYTHONPATH',''))
    url=f'http://127.0.0.1:{port}'
    headers={'X-Aura-Paper':'local-only','Origin':url}
    def start():
        proc=subprocess.Popen([sys.executable,'tests/manual_paper_web_fixture.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if proc.poll() is not None:raise AssertionError('fixture failed to start')
            try:
                if httpx.get(url+'/api/health',trust_env=False,timeout=.2).status_code==200:return proc
            except httpx.HTTPError:pass
            time.sleep(.05)
        proc.terminate();proc.wait(timeout=5);raise AssertionError('fixture startup timeout')
    def stop(proc):
        proc.terminate();proc.wait(timeout=10)
    with httpx.Client(base_url=url,trust_env=False,auth=AUTH,headers=headers,timeout=10) as client:
        proc=start()
        try:
            r=client.post('/api/manual-paper/orders',json=BODY);assert r.status_code==200,r.text
            receipt=r.json()
            assert client.get('/api/manual-paper/state').json()['position']['id']==BODY['request_id']
        finally:stop(proc)
        env['MANUAL_TEST_BID']='80500'
        proc=start()
        try:
            restored=client.get('/api/manual-paper/state').json()
            assert restored['position']['id']==BODY['request_id']
            assert Decimal(restored['balance'])==Decimal('9999.519994')
            assert client.post('/api/manual-paper/orders',json=BODY).json()==receipt
            r=client.post('/api/manual-paper/positions/'+BODY['request_id']+'/close',json={'request_id':'b'*32})
            assert r.status_code==200,r.text
            final=client.get('/api/manual-paper/state').json()
            assert final['history_total']==1 and final['position'] is None
            assert Decimal(final['balance'])==Decimal('10004.026994')
        finally:stop(proc)
        proc=start()
        try:
            final_again=client.get('/api/manual-paper/state').json()
            assert final_again['balance']==final['balance'] and final_again['trades']==final['trades']
        finally:stop(proc)


def test_commit_succeeds_but_reply_lost_replay_does_not_mutate(setup):
    client,svc=setup
    original=svc.store.execute
    def lost(*args):
        original(*args)
        raise OSError('dummy simulated connection loss after durable commit')
    svc.store.execute=lost
    r=post(client)
    assert r.status_code==503 and r.json()['code']=='STORAGE_UNAVAILABLE'
    svc.store.execute=original;svc.quote.side_effect=QuoteRejected('MARKET_UNAVAILABLE')
    r=post(client)
    assert r.status_code==200 and svc.store.load()[1]==1
    assert svc.store.load()[0].position.id==BODY['request_id']


def test_missing_state_and_foreign_database_never_reseed(tmp_path):
    path=tmp_path/'manual-paper.sqlite3';store=ManualStore(path)
    ManualCommands(store).open('a'*32,'LONG','0.01','79500','81000',dict(quote(),price='80000'))
    with sqlite3.connect(path) as db:db.execute('delete from state')
    with pytest.raises(ValueError,match='CORRUPT_JOURNAL'):store.load()
    foreign=tmp_path/'foreign.sqlite3'
    with sqlite3.connect(foreign) as db:db.execute('create table active43(dummy text)')
    with pytest.raises(ValueError,match='STORAGE_SCOPE_MISMATCH'):ManualStore(foreign).load()


def test_permanent_receipts_are_append_only(setup):
    client,svc=setup;post(client)
    with sqlite3.connect(svc.store.path) as db:
        with pytest.raises(sqlite3.IntegrityError,match='APPEND_ONLY'):db.execute('delete from requests')
        with pytest.raises(sqlite3.IntegrityError,match='APPEND_ONLY'):db.execute("update requests set result='{}'")


def test_drawdown_gate_preserves_losses(tmp_path):
    store=ManualStore(tmp_path/'manual-paper.sqlite3');cmd=ManualCommands(store)
    cmd.open('a'*32,'SHORT','0.025','80500','79000',dict(quote(),price='80000'))
    cmd.close('b'*32,dict(quote(),price='150000'),'a'*32)
    before=store.load()
    assert before[0].balance<Decimal('9000')
    with pytest.raises(ValueError,match='DRAWDOWN_LIMIT'):
        cmd.open('c'*32,'LONG','0.01','79500','81000',dict(quote(),price='80000'))
    assert store.load()[1]==before[1]


@pytest.mark.parametrize('kind',['timeout','clock','request_time','large','invalid_json','rows'])
def test_market_transport_clock_and_shape_failures(kind):
    def handler(req):
        if kind=='timeout':raise httpx.ReadTimeout('dummy redacted timeout',request=req)
        if req.url.path.endswith('/time'):
            stamp=STAMP-5000 if kind=='clock' else STAMP
            return httpx.Response(200,json=dict(code='00000',data={'serverTime':str(stamp)}))
        if kind=='large':return httpx.Response(200,content=b'x'*32769)
        if kind=='invalid_json':return httpx.Response(200,content=b'not json')
        data=ticker_payload()
        if kind=='request_time':data['requestTime']=STAMP-5001
        if kind=='rows':data['data']*=2
        return httpx.Response(200,json=data)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            await fetch_execution_quote(c,clock=lambda:STAMP/1000)
    with pytest.raises(QuoteRejected):asyncio.run(run())
