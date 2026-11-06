"""Owner/CSRF/subscription boundaries; all storage is an offline test double."""
import base64
import json
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.manual_preview import main
from app.manual_preview.config import parse
from app.manual_preview.lock_runtime import Coordinator
from tests.test_signal_lock_runtime import MemoryStore
from tests.test_manual_preview import environment, AUTH, PASS


class Push:
    def __init__(self):self.rows={};self.calls=[]
    def call(self,action,data=None):
        data=data or {};self.calls.append(action)
        if action=='subscribe':
            self.rows[data['id']]={'id':data['id'],'candidate':data['candidate'],'watch':data['watch'],'last_status':None}
            return self.rows[data['id']]
        if action=='diagnostics':return {'subscription':self.rows.get(data.get('id')),'subscriber_count':len(self.rows),'pending':0}
        if action=='preferences':self.rows[data['id']].update(candidate=data['candidate'],watch=data['watch']);return {'updated':True}
        if action=='unsubscribe':self.rows.pop(data['id'],None);return {'removed':True}
        if action=='test':return {'enqueued':True}
        raise ValueError('UNEXPECTED_PRIVATE_RPC')


@pytest.fixture
def client(monkeypatch):
    env=environment();env.update(AURA_PREVIEW_SIGNALS_ENABLED='true',AURA_PREVIEW_SIGNAL_LOCK_ENABLED='true',AURA_PREVIEW_PUSH_ENABLED='true')
    push=Push();worker=Coordinator(MemoryStore(),push,SimpleNamespace(public_key='B'*87))
    worker.error=None;worker.updated_at=time.time()
    values={'preview_config':parse(env),'preview_ws_token':'DUMMY_PUSH_CSRF_TOKEN_ONLY_123456789',
            'signal_lock':worker,'signal_lock_enabled':True,'signal_lock_task':SimpleNamespace(done=lambda:False),
            'preview_signals_task':SimpleNamespace(done=lambda:False),'preview_signals':SimpleNamespace(last_cycle_at=time.time())}
    for k,v in values.items():monkeypatch.setattr(main.app.state,k,v,raising=False)
    c=TestClient(main.app,auth=AUTH)
    try:
        # Do not enter the real application's lifespan or touch hosted services.
        yield c,push
    finally:c.close()


def headers():return {'Origin':'http://testserver','X-Aura-Preview-Push':'DUMMY_PUSH_CSRF_TOKEN_ONLY_123456789','Content-Type':'application/json'}


def target():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    enc=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
    return {'endpoint':'https://fcm.googleapis.com/fcm/send/DUMMY_API_SUBSCRIPTION_ONLY',
            'keys':{'p256dh':enc(public),'auth':enc(bytes(16))}}


def test_push_writes_require_owner_same_origin_token_and_never_authorize_orders(client):
    c,push=client;payload={'subscription':target(),'candidate':False,'watch':True}
    for h in [{},{**headers(),'Origin':'https://evil.invalid'}, {**headers(),'X-Aura-Preview-Push':'wrong'},
              {**headers(),'Sec-Fetch-Site':'cross-site'}, {**headers(),'Content-Type':'text/plain'}]:
        assert c.post('/api/preview/push/subscribe',content=json.dumps(payload),headers=h).status_code==403
    assert c.post('/api/manual-paper/orders',json={},headers=headers()).status_code==403
    assert not push.calls
    assert c.post('/api/preview/push/subscribe',json=payload,headers=headers(),auth=('aura','wrong')).status_code==401


def test_subscribe_preferences_test_diagnostics_and_unsubscribe_hide_targets(client):
    c,push=client
    response=c.post('/api/preview/push/subscribe',json={'subscription':target(),'candidate':False,'watch':True},headers=headers())
    assert response.status_code==200
    sid=response.json()['id']
    assert c.post('/api/preview/push/preferences',json={'id':sid,'candidate':True,'watch':False},headers=headers()).json()['updated']
    response=c.get('/api/preview/push/status',params={'subscription_id':sid})
    assert response.json()['configured'] and response.json()['real_android_delivery']=='UNKNOWN'
    assert response.json()['diagnostics']['subscription']['candidate'] is True
    assert 'endpoint' not in response.text and 'p256dh' not in response.text and PASS not in response.text
    result=c.post('/api/preview/push/test',json={'id':sid},headers=headers())
    assert result.json()['device_delivery']=='NOT_CONFIRMED'
    assert c.post('/api/preview/push/unsubscribe',json={'id':sid},headers=headers()).json()['removed']
    assert not push.rows
    assert not {'config','bootstrap','claim','complete'} & set(push.calls)


def test_invalid_subscriptions_limits_and_static_worker_have_no_secrets(client):
    c,push=client
    payload={'subscription':target(),'candidate':False,'watch':True};payload['subscription']['endpoint']='https://api.bitget.com/api/v2/mix/order/place-order'
    assert c.post('/api/preview/push/subscribe',json=payload,headers=headers()).status_code==400
    assert c.post('/api/preview/push/test',content='x'*8193,headers=headers()).status_code==413
    assert c.post('/api/preview/push/preferences',json={'id':'a'*64,'candidate':'true','watch':True},headers=headers()).status_code==400
    assert not push.calls
    response=c.get('/signal-lock-sw.js')
    assert response.status_code==200 and response.headers['Service-Worker-Allowed']=='/'
    assert PASS not in response.text and 'DUMMY_PUSH_CSRF_TOKEN_ONLY' not in response.text


def test_actual_owner_page_wires_signal_lock_without_removing_manual_analytics(client):
    c,_=client
    html=c.get('/').text
    for value in ['id="aura-signal-lock"','data-signal-lock="true"','/static/push-client.js','id="aura-explainable"','id="aura-confidence"']:
        assert value in html
    assert 'aura-mobile-shell.js' in html and 'manual-paper.js' in html
