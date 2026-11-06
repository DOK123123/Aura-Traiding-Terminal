"""Worker and real encryption tests. No external network or real subscribers."""
import base64
import copy
import json
import os
import unittest
from unittest.mock import patch

from app.manual_preview.lock_runtime import Coordinator
from app.manual_preview.signal_lock import advance
from app.manual_preview.web_push import Sender, generate_vapid
from tests.test_signal_lock import sample, NOW


class MemoryStore:
    def __init__(self):
        self.version, self.value, self.writes = 0, None, 0
    def load(self):
        return self.version, copy.deepcopy(self.value)
    def compare_and_swap(self, version, value):
        if version != self.version:
            return False
        self.version += 1
        self.writes += 1
        self.value = copy.deepcopy(value)
        return True


class RuntimeTest(unittest.TestCase):
    def test_500_updates_checkpoint_without_losing_identity_or_immediate_transition(self):
        c, q = sample()
        store = MemoryStore()
        worker = Coordinator(store)
        for i in range(500):
            now = NOW+i/10
            c['quote_time'] = c['quote_received_at'] = now
            q['1h']['time'] = q['1h']['received_at'] = now
            worker.process([c],q,now,True)
            self.assertEqual(len(worker.snapshot(now)['events']),1)
        self.assertLessEqual(store.writes,3)
        identity=worker.snapshot(now)['events'][0]['id']
        c.update(score=100,state='WATCH',rejection=[])
        for item in c['checks']:item['passed']=True
        worker.process([c],q,now,True)
        self.assertEqual(next(iter(store.value['events'].values()))['status'],'WATCH')
        self.assertEqual(worker.snapshot(now)['events'][0]['id'],identity)
        worker.process([],{},now+6,True)
        self.assertEqual(next(iter(store.value['events'].values()))['status'],'UNKNOWN')
        self.assertIsNone(worker.snapshot(now+6)['events'][0]['plan'])

    def test_persisted_clock_watermark_forbids_recreating_pruned_cohort(self):
        c,q=sample()
        state={'events':{},'notices':{},'cooldowns':{},'watermark':NOW+1000}
        self.assertEqual(advance(state,[c],q,NOW)['events'],{})

    def test_durable_notice_replay_does_not_resend_on_each_tick(self):
        class Push:
            def __init__(self):self.jobs=[];self.ids=set();self.completed=[]
            def call(self,action,data=None):
                if action=='enqueue':
                    key=data['event_id']+data['status']
                    if key not in self.ids:self.jobs.append({'id':key,'payload':data,'target':{}});self.ids.add(key)
                    return {'enqueued':True}
                if action=='claim':return self.jobs.pop(0) if self.jobs else None
                if action=='complete':self.completed.append(data);return {'updated':True}
                return {}
        class SenderFake:
            count=0
            def send(self,target,payload,session):self.count+=1;return 'ACCEPTED_NOT_DEVICE_CONFIRMED'
        class Session:
            def close(self):pass
        c,q=sample();push=Push();sender=SenderFake();worker=Coordinator(MemoryStore(),push,sender)
        worker.process([c],q,NOW,True)
        with patch('app.manual_preview.lock_runtime.no_redirect_session',return_value=Session()),patch('app.manual_preview.lock_runtime.time.time',return_value=NOW):
            for _ in range(500):worker.deliver(NOW)
        self.assertEqual(sender.count,1)
        self.assertEqual(len(push.completed),1)

    def test_real_webpush_encryption_decryption_and_vapid_signature_without_network(self):
        from cryptography.hazmat.primitives.asymmetric import ec,utils
        from cryptography.hazmat.primitives import hashes,serialization
        import http_ece
        import requests
        keys=generate_vapid()
        receiver=ec.generate_private_key(ec.SECP256R1())
        public=receiver.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        auth=os.urandom(16)
        enc=lambda raw:base64.urlsafe_b64encode(raw).decode().rstrip('=')
        decode=lambda raw:base64.urlsafe_b64decode(raw+'='*(-len(raw)%4))
        target={'endpoint':'https://fcm.googleapis.com/fcm/send/DUMMY_CRYPTO_TEST_ONLY',
                'keys':{'p256dh':enc(public),'auth':enc(auth)}}
        captured={}
        class InterceptSession:
            def post(self,url,data=None,headers=None,**kwargs):
                self_outer.assertEqual(url,target['endpoint'])
                captured.update(data=data,headers=headers)
                response=requests.Response();response.status_code=201;response._content=b''
                return response
        self_outer=self
        payload={'status':'TEST','event_id':'a'*64}
        result=Sender(keys['private'],keys['public'],keys['contact']).send(target,payload,InterceptSession())
        self.assertEqual(result,'ACCEPTED_NOT_DEVICE_CONFIRMED')
        plain=http_ece.decrypt(captured['data'],private_key=receiver,auth_secret=auth,version='aes128gcm')
        self.assertEqual(json.loads(plain),payload)
        authorization=next(v for k,v in captured['headers'].items() if k.lower()=='authorization')
        token=authorization.split('t=')[1].split(',')[0]
        header,claims,signature=token.split('.')
        self.assertEqual(json.loads(decode(claims))['aud'],'https://fcm.googleapis.com')
        signature=decode(signature)
        der=utils.encode_dss_signature(int.from_bytes(signature[:32],'big'),int.from_bytes(signature[32:],'big'))
        key=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),decode(keys['public']))
        key.verify(der,(header+'.'+claims).encode(),ec.ECDSA(hashes.SHA256()))


if __name__=='__main__':unittest.main()
