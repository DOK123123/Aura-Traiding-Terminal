"""Offline wire/backend tests. Actual SQL is separately tested in disposable PG."""
import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import io
import json
import logging
import os
import threading
import time
from unittest.mock import AsyncMock,patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.manual_paper.api import router
from app.manual_paper.commands import ManualCommands
from app.manual_paper.core import ManualPaper
from app.manual_paper.service import Service,configured
from app.manual_paper.store import ManualStore
from app.manual_paper.supabase_store import SupabaseStore,PREFIX

URL='https://abcdefghijklmnopqrst.supabase.co'
KEY='DUMMY_ONLY_SUPABASE_SERVICE_KEY_1234567890'


class WireFixture:
    """Only the HTTP transport is mocked here. Not evidence of SQL correctness."""
    def __init__(self):
        self.lock=threading.Lock();self.payload=None;self.version=0;self.receipts={};self.calls=[]
        self.lose_reply=False;self.conflict=False
    def __call__(self,req):
        assert req.method=='POST' and req.url.host=='abcdefghijklmnopqrst.supabase.co'
        name=req.url.path.removeprefix('/rest/v1/rpc/'+PREFIX)
        assert name in ('load','lookup','commit')
        assert req.headers['apikey']==KEY and 'authorization' not in req.headers
        a=json.loads(req.content);self.calls.append((name,a))
        with self.lock:
            if name=='load':
                if self.payload is None:return httpx.Response(200,content=b'null',headers={'content-type':'application/json'})
                value=dict(scope='AURA_MANUAL_PAPER_V1',version=self.version,sha256=hashlib.sha256(self.payload.encode()).hexdigest())
                if a['p_known_version']==self.version:value['unchanged']=True
                else:value['payload']=self.payload
                return httpx.Response(200,json=value) if value is not None else httpx.Response(200,content=b'null')
            if name=='lookup':
                previous=self.receipts.get(a['p_request_id'])
                value=({'error':'IDEMPOTENCY_CONFLICT'} if previous[0]!=a['p_intent_hash'] else previous[1]) if previous else None
                return httpx.Response(200,json=value) if value is not None else httpx.Response(200,content=b'null')
            old=self.receipts.get(a['p_request_id'])
            if old:
                return httpx.Response(200,json=old[1] if old[0]==a['p_intent_hash'] else {'error':'IDEMPOTENCY_CONFLICT'})
            if self.conflict:
                self.conflict=False;return httpx.Response(200,json={'error':'CONCURRENT_UPDATE'})
            if a['p_expected_version']!=self.version:return httpx.Response(200,json={'error':'CONCURRENT_UPDATE'})
            if a['p_request_id'] is not None and (a['p_quote_ms'] is None or not 0<=time.time()*1000-a['p_quote_ms']<=5000):
                return httpx.Response(200,json={'error':'STALE_QUOTE'})
            self.payload=a['p_new_payload'];self.version+=1
            result=a['p_new_receipt'] or {'version':1}
            if a['p_request_id']:self.receipts[a['p_request_id']]=(a['p_intent_hash'],result)
            if self.lose_reply:
                self.lose_reply=False;raise httpx.ReadTimeout('DUMMY_ONLY_SECRET_MUST_NOT_LEAK',request=req)
            return httpx.Response(200,json=result)


def quote(price='80000'):
    return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',
                time=int(time.time()*1000)-5,price=Decimal(price),bid=Decimal(price),ask=Decimal(price),
                bid_size=Decimal('1'),ask_size=Decimal('1'))


def test_supabase_api_persistence_close_restart_and_lost_reply(monkeypatch):
    wire=WireFixture()
    store=SupabaseStore(URL,KEY,transport=httpx.MockTransport(wire))
    svc=Service(store,durable=True);svc.quote=AsyncMock(return_value=quote())
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','DUMMY_ONLY_OWNER_PASSWORD')
    app=FastAPI();app.include_router(router);app.state.manual_paper=svc
    auth=('aura','DUMMY_ONLY_OWNER_PASSWORD');headers={'X-Aura-Paper':'local-only'}
    body=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000')
    with TestClient(app) as client:
        wire.lose_reply=True
        r=client.post('/api/manual-paper/orders',json=body,auth=auth,headers=headers)
        assert r.status_code==503 and r.json()['code']=='STORAGE_UNAVAILABLE'
        assert wire.version==1
        r=client.post('/api/manual-paper/orders',json=body,auth=auth,headers=headers)
        assert r.status_code==200 and wire.version==1
        # New service/client/process-like instance reads the SAME remote account.
        restored=SupabaseStore(URL,KEY,transport=httpx.MockTransport(wire))
        restored_svc=Service(restored,durable=True);restored_svc.quote=AsyncMock(return_value=quote('81000'))
        app.state.manual_paper=restored_svc
        state=client.get('/api/manual-paper/state',auth=auth).json()
        assert state['storage_backend']=='SUPABASE_MANUAL_PAPER_V1'
        assert state['position']['id']=='a'*32 and Decimal(state['balance'])==Decimal('9999.52')
        r=client.post('/api/manual-paper/positions/'+'a'*32+'/close',json={'request_id':'b'*32},auth=auth,headers=headers)
        assert r.status_code==200 and Decimal(r.json()['balance'])==Decimal('10009.034')
        history=client.get('/api/manual-paper/state',auth=auth).json()
        assert history['history_total']==1 and history['position'] is None
        store.close();restored.close()


def test_metadata_cache_revalidation_and_concurrent_cas_retry():
    wire=WireFixture();s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(wire))
    s.save(ManualPaper(),0)
    s.load();s.load()
    assert wire.calls[-1]==('load',{'p_known_version':1})
    wire.conflict=True
    result=ManualCommands(s).open('a'*32,'SHORT','0.01','80500','79000',quote())
    assert result['version']==2 and s.load()[0].position.side=='SHORT'
    with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):
        ManualCommands(s).open('a'*32,'LONG','0.01','79500','81000',quote())
    s.close()


def test_database_stale_gate_and_no_reset_or_fallback():
    wire=WireFixture();s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(wire))
    with pytest.raises(ValueError,match='STALE_QUOTE'):
        ManualCommands(s).open('a'*32,'LONG','0.01','79500','81000',dict(quote(),time=int(time.time()*1000)-6000))
    assert wire.payload is None
    s.save(ManualPaper(),0);s.load();wire.payload=None
    with pytest.raises(ValueError,match='CORRUPT_JOURNAL'):s.load()
    with pytest.raises(ValueError,match='STORAGE_SCOPE_MISMATCH'):s.rpc('aura_active43_bitget_commit',{})
    s.close()


@pytest.mark.parametrize('status',[302,401,403,429,500])
def test_transport_fails_closed_and_redacts(status):
    s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(lambda req:httpx.Response(status,json={'secret':KEY})))
    with pytest.raises(ValueError,match='^STORAGE_UNAVAILABLE$'):s.load()
    s.close()


@pytest.mark.parametrize('value',[
    {'version':1,'payload':'{}','sha256':'bad','scope':'AURA_MANUAL_PAPER_V1'},
    {'version':True,'payload':'{}','sha256':'bad'},[],{},
    {'error':'DUMMY_ONLY_UNKNOWN_SECRET'},
    {'scope':'AURA_MANUAL_PAPER_V1','version':1,'payload':123,'sha256':'bad'},
])
def test_corrupt_storage_response_is_not_account_reset(value):
    s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(lambda req:httpx.Response(200,json=value)))
    with pytest.raises(ValueError):s.load()
    s.close()


def test_configuration_uses_only_dedicated_env_and_no_disk(tmp_path,monkeypatch):
    monkeypatch.setenv('RENDER','true');monkeypatch.setenv('AURA_MANUAL_PAPER_ENABLED','true')
    monkeypatch.setenv('AURA_MANUAL_PAPER_STORAGE','supabase')
    monkeypatch.setenv('AURA_MANUAL_PAPER_SUPABASE_URL',URL)
    monkeypatch.setenv('AURA_MANUAL_PAPER_SUPABASE_SERVICE_KEY',KEY)
    svc=configured(object())
    assert isinstance(svc.store,SupabaseStore) and svc.durable
    asyncio.run(svc.close())
    monkeypatch.delenv('AURA_MANUAL_PAPER_SUPABASE_SERVICE_KEY')
    # Existing Active43 secrets must never be an implicit storage fallback.
    monkeypatch.setenv('AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY',KEY)
    svc=configured(object())
    assert svc.store is None and svc.error=='PERSISTENT_STORAGE_NOT_READY'
    assert not list(tmp_path.iterdir())


def test_log_filter_and_legacy_jwt_header():
    stream=io.StringIO();handler=logging.StreamHandler(stream);logging.getLogger().addHandler(handler)
    try:
        s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(lambda req:httpx.Response(500)))
        logging.getLogger('httpcore.manual_test').warning('key=%s',KEY)
        assert KEY not in stream.getvalue();s.close()
        jwt='eyJ'+'DUMMY_ONLY_LEGACY_JWT_KEY_1234567890'
        def handler_fn(req):
            assert req.headers['authorization']=='Bearer '+jwt
            return httpx.Response(200,content=b'null',headers={'content-type':'application/json'})
        s=SupabaseStore(URL,jwt,transport=httpx.MockTransport(handler_fn));assert s.load()==(None,0);s.close()
    finally:logging.getLogger().removeHandler(handler)


def test_payload_limit_reserves_close_and_never_mutates(monkeypatch):
    import app.manual_paper.supabase_store as backend
    wire=WireFixture();s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(wire))
    cmd=ManualCommands(s)
    cmd.open('a'*32,'LONG','0.01','79500','81000',quote())
    # Simulate a nearly full ledger with an existing open position. A close fits
    # the absolute cap even when the reserve prevents opening another position.
    monkeypatch.setattr(backend,'MAX_PAYLOAD',len(ManualStore.encode(s.load()[0]).encode())+7000)
    with pytest.raises(ValueError,match='WRITE_LIMIT'):
        cmd.open('c'*32,'LONG','0.01','79500','81000',quote())
    assert wire.version==1 and 'c'*32 not in wire.receipts
    result=cmd.close('b'*32,quote('81000'),'a'*32)
    assert Decimal(result['balance'])==Decimal('10009.034')
    version=wire.version
    monkeypatch.setattr(backend,'MAX_PAYLOAD',10)
    with pytest.raises(ValueError,match='WRITE_LIMIT'):
        s._commit(version,ManualPaper(),None,None,None,None)
    assert wire.version==version
    s.close()


def test_duplicate_committed_between_lookup_and_load_returns_receipt():
    wire=WireFixture();other=SupabaseStore(URL,KEY,transport=httpx.MockTransport(wire))
    armed=True;committed=None
    def concurrent_transport(req):
        nonlocal armed,committed
        if req.url.path.endswith('_load') and armed:
            armed=False
            committed=ManualCommands(other).open('a'*32,'LONG','0.01','79500','81000',quote())
        return wire(req)
    s=SupabaseStore(URL,KEY,transport=httpx.MockTransport(concurrent_transport))
    result=ManualCommands(s).open('a'*32,'LONG','0.01','79500','81000',quote())
    assert result==committed and wire.version==1 and len(wire.receipts)==1
    s.close();other.close()
