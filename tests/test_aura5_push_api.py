"""Owner/CSRF/size protections, generated dummy subscription, no live sends."""
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.manual_preview import main
from app.manual_preview.push import PushSender
from tests.test_aura5_push import config, sub


def test_owner_csrf_and_no_secret_config(monkeypatch):
    class Store:
        calls=[]
        def rpc(self,action,data):
            self.calls.append(action);return {'state':'QUEUED_NOT_DELIVERED'}
    db=Store();sender=PushSender(db,config())
    monkeypatch.setattr(main.app.state,'preview_config',SimpleNamespace(owner_password='DUMMY_ONLY_OWNER'),raising=False)
    monkeypatch.setattr(main.app.state,'preview_push',sender,raising=False)
    client=TestClient(main.app)
    assert client.get('/api/preview/push/config').status_code==401
    auth=('aura','DUMMY_ONLY_OWNER')
    response=client.get('/api/preview/push/config',auth=auth)
    assert response.status_code==200 and response.json()['ready']
    assert sender.private not in response.text
    value={'subscription':sub(),'candidate':False}
    assert client.post('/api/preview/push/subscribe',auth=auth,json=value).status_code==403
    headers={'X-Aura-Push':'owner','Origin':'https://attacker.invalid'}
    assert client.post('/api/preview/push/subscribe',auth=auth,json=value,headers=headers).status_code==403
    headers['Origin']='http://testserver'
    assert client.post('/api/preview/push/subscribe',auth=auth,json=value,headers=headers).status_code==200
    assert db.calls==['subscribe']
    assert client.post('/api/preview/push/test',auth=auth,json=value,headers=headers).json()['state']=='QUEUED_NOT_DELIVERED'
    assert client.post('/api/preview/push/test',auth=auth,content='x'*8200,headers={**headers,'Content-Type':'application/json'}).status_code==413
    worker=client.get('/aura5-sw.js',auth=auth)
    assert worker.status_code==200 and worker.headers['service-worker-allowed']=='/'
