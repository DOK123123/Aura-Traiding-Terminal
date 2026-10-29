"""Mandatory read-only database attestation before every ledger RPC.

Only a reviewed, project-bound configuration can construct this client. No
fallback to a local DB, generic Supabase env or production project is supported.
"""
import json
import time
import httpx
from app.manual_paper.supabase_store import SupabaseStore


class PreviewStore(SupabaseStore):
    def __init__(self,config,**kwargs):
        self.project_ref=config.project_ref
        super().__init__(config.url,config.key,**kwargs)

    def verify_scope(self):
        started=time.monotonic()
        try:
            with self.client.stream('POST',self.base+'/rest/v1/rpc/aura_manual_preview_guard',json={}) as response:
                if response.status_code!=200:raise ValueError()
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>4096 or time.monotonic()-started>10:raise ValueError()
                value=json.loads(body)
            if (not isinstance(value,dict) or value.get('scope')!='AURA_MANUAL_PREVIEW_ONLY_V1'
                    or value.get('project_ref')!=self.project_ref or value.get('isolated') is not True
                    or value.get('role')!='service_role'):
                raise ValueError()
            return True
        except (ValueError,TypeError,httpx.HTTPError,ArithmeticError):
            raise ValueError('STORAGE_SCOPE_MISMATCH') from None

    def rpc(self,name,args):
        self.verify_scope()  # Includes commit/initialization, not only a one-off startup probe.
        return super().rpc(name,args)
