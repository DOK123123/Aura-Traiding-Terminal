"""Only generated dummy keys and stubbed send transports. No provider traffic."""
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import pytest
from app.manual_preview.push import PushSender, subscription, NAMES, VerifiedSession


def b64(value):return base64.urlsafe_b64encode(value).decode().rstrip('=')

def config():
    key=ec.generate_private_key(ec.SECP256R1())
    return dict(zip(NAMES,[b64(key.private_numbers().private_value.to_bytes(32,'big')),
        b64(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)),
        'mailto:dummy-owner@example.invalid']))

def sub():
    return {'endpoint':'https://fcm.googleapis.com/fcm/send/DUMMY_ONLY_ENDPOINT',
            'keys':{'auth':b64(b'0123456789abcdef'), 'p256dh':config()[NAMES[1]]}}


class Store:
    def __init__(self):self.calls=[];self.job={'id':'dummy-event','scenario_id':'a'*64,'kind':'WATCH','subscription':sub()}
    def rpc(self,action,data=None):
        self.calls.append((action,data));return self.job if action=='claim' else None


def test_missing_vapid_never_claims_or_exposes_private():
    db=Store();sender=PushSender(db,{})
    sender.once();assert not db.calls and not sender.ready
    assert 'private_key' not in sender.config()


def test_provider_acceptance_is_not_delivery():
    db=Store();env=config();seen=[]
    def send(**kw):seen.append(kw);return type('Reply',(),{'status_code':201})()
    sender=PushSender(db,env,send=send);assert sender.ready
    sender.once();assert db.calls[-1][1]['state']=='ACCEPTED_BY_PUSH_SERVICE'
    assert sender.config()['delivery_confirmed'] is False
    assert env[NAMES[0]] not in str(sender.config())
    assert seen[0]['timeout']==8 and seen[0]['ttl']==60


def test_uncertain_outcome_never_claims_delivery():
    def send(**kw):raise TimeoutError('DUMMY_ONLY')
    db=Store();sender=PushSender(db,config(),send=send);sender.once()
    assert db.calls[-1][1]['state']=='UNKNOWN_SEND_OUTCOME'


@pytest.mark.parametrize('endpoint',['http://fcm.googleapis.com/fcm/send/foo','https://127.0.0.1/x',
 'https://fcm.googleapis.com.evil.invalid/fcm/send/foo','https://fcm.googleapis.com:443/fcm/send/foo',
 'https://owner@fcm.googleapis.com/fcm/send/foo','https://fcm.googleapis.com/fcm/send/foo?key=secret'])
def test_endpoint_ssrf_rejected(endpoint):
    value=sub();value['endpoint']=endpoint
    with pytest.raises(ValueError):subscription(value)


def test_keys_and_pair_validation():
    value=sub();value['keys']['auth']='invalid'
    with pytest.raises(ValueError):subscription(value)
    env=config();env[NAMES[1]]=config()[NAMES[1]]
    assert not PushSender(Store(),env).ready


def test_transport_keeps_tls_and_disables_redirects(monkeypatch):
    import requests
    seen={}
    def request(self,method,url,**kwargs):seen.update(kwargs);return object()
    monkeypatch.setattr(requests.Session,'request',request)
    with VerifiedSession() as session:
        session.post('https://fcm.googleapis.com/fcm/send/DUMMY_ONLY',allow_redirects=True,verify=False)
    assert seen['allow_redirects'] is False and seen['verify'] is True
