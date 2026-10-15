import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from app import execution_verification as ev
from app.lab.models import digest
from scripts.replay_auto42_verification import code_hashes

class EvidencePanel(unittest.IsolatedAsyncioTestCase):
    def report(self):
        v=dict(code_hashes=code_hashes(),isolated=dict(status='PASS',test_only=True),historical=dict(status='PASS'),live=dict(status='PASS'))
        return dict(v,checksum=digest(v))
    async def test_owner_only_read_no_live_state_access_and_live_never_pass(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'proof.json';path.write_text(json.dumps(self.report()));app=FastAPI();app.include_router(ev.router)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                with patch.dict('os.environ',{'AURA_TESTNET_VIEW_PASSWORD':'DUMMY_OWNER_VERIFICATION_ONLY'}),patch.object(ev,'REPORT',path):
                    self.assertEqual((await c.get('/api/auto42-verification')).status_code,401)
                    r=await c.get('/api/auto42-verification',auth=('aura','DUMMY_OWNER_VERIFICATION_ONLY'))
                    self.assertEqual(r.status_code,200);self.assertEqual(r.json()['isolated']['status'],'PASS');self.assertEqual(r.json()['live']['status'],'NOT_TESTED')
                    self.assertFalse(hasattr(app.state,'auto42'))
    def test_missing_tampered_or_outdated_evidence_never_pass(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'proof.json'
            with patch.object(ev,'REPORT',path):
                self.assertEqual(ev.evidence()['isolated']['status'],'NOT_TESTED')
                v=self.report();v['isolated']['status']='FAIL';path.write_text(json.dumps(v))
                self.assertEqual(ev.evidence()['isolated']['status'],'NOT_TESTED')
                v=self.report();v['code_hashes']['app/automated/engine.py']='bad';v.pop('checksum');v['checksum']=digest(v);path.write_text(json.dumps(v))
                self.assertFalse(ev.evidence()['code_matches']);self.assertEqual(ev.evidence()['isolated']['status'],'NOT_TESTED')
    def test_no_arbitrary_artifact_paths(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'proof.json';v=self.report();v['code_hashes']['/tmp/untrusted']='x';v.pop('checksum');v['checksum']=digest(v);path.write_text(json.dumps(v))
            with patch.object(ev,'REPORT',path):self.assertEqual(ev.evidence()['isolated']['status'],'NOT_TESTED')
