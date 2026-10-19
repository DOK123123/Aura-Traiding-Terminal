"""Dedicated Supabase namespace; no method can address another portfolio."""
import asyncio,json
import httpx
from app.forward.storage import SupabaseStore as SafeTransport
from app.forward.models import ForwardError
from app.automated.storage import packed,unpack,verify_envelope,validate_commit
from app.automated.diagnostics import http_error
from app.automated.engine import DemoError
from .core import initial,validate,SCOPE

class Store:
    backend='SUPABASE_ACTIVE43_BITGET';durable=True
    def __init__(self,url,key,config,transport=None):
        self.config=config;self.status='UNKNOWN'
        try:self.transport=SafeTransport(url,key,transport)
        except ForwardError as exc:raise DemoError(exc.code) from None
    async def close(self):await self.transport.close()
    async def rpc(self,name,args):
        if name not in ('aura_active43_bitget_load','aura_active43_bitget_commit','aura_active43_bitget_history'):raise DemoError('STORAGE_METHOD_FORBIDDEN')
        try:
            async with asyncio.timeout(12):
                async with self.transport.slots:
                    async with self.transport.client.stream('POST',self.transport.base+'/rest/v1/rpc/'+name,json=args) as r:
                        if r.status_code!=200:
                            raw=bytearray()
                            async for chunk in r.aiter_bytes():
                                raw.extend(chunk[:max(0,65536-len(raw))])
                                if len(raw)>=65536:break
                            try:body=json.loads(raw)
                            except ValueError:body={}
                            raise DemoError(http_error(r.status_code,body)[0])
                        raw=bytearray()
                        async for chunk in r.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw)>2*1024*1024:raise DemoError('STORAGE_RESPONSE_LIMIT')
                        value=json.loads(raw)
                        if isinstance(value,dict) and value.get('error'):
                            code=value['error'];allowed={'CONCURRENT_UPDATE','CORRUPT_PORTFOLIO','INVALID_EVENT','WRITE_LIMIT','CONFIG_CHANGED','STALE_EXECUTION_AT_COMMIT'}
                            raise DemoError(code if code in allowed else 'STORAGE_UNAVAILABLE')
                        self.status='CONNECTED';return value
        except (TimeoutError,httpx.TimeoutException):self.status='ERROR';raise DemoError('STORAGE_TIMEOUT_OUTCOME_UNKNOWN') from None
        except DemoError:self.status='ERROR';raise
        except (httpx.HTTPError,ValueError,TypeError):self.status='ERROR';raise DemoError('STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN') from None
    @staticmethod
    def envelope(value):
        env=verify_envelope(value);validate(env['state'])
        if type(value.get('duplicate',False)) is not bool:raise DemoError('STORAGE_INVALID_RESPONSE')
        return dict(env,duplicate=value.get('duplicate',False))
    async def load(self,now):return self.envelope(await self.rpc('aura_active43_bitget_load',dict(seed=packed(initial(now,self.config)))))
    async def commit(self,revision,state,events,key):
        validate(state);validate_commit(state,events,key)
        return self.envelope(await self.rpc('aura_active43_bitget_commit',dict(expected_revision=revision,new_state=packed(state),new_events=[dict(e,**packed(e)) for e in events],operation_key=key)))
    async def history(self,epoch=None,after=None,limit=50,key=None,kind=None,before=None):
        if not 1<=limit<=200 or kind not in (None,'CLOSE','OPEN','SIGNAL','ERROR'):raise DemoError('READ_LIMIT')
        value=await self.rpc('aura_active43_bitget_history',dict(selected_epoch=epoch,after_seq=after,row_limit=limit,event_id=key,kind_filter=kind,before_seq=before))
        if not isinstance(value,list) or len(value)>limit:raise DemoError('STORAGE_INVALID_RESPONSE')
        try:
            rows=[dict(unpack(r),seq=r['seq']) for r in value]
            if any(e['payload'].get('scope')!=SCOPE or not e['epoch'].startswith('ACTIVE43_BITGET_') or (epoch and e['epoch']!=epoch) for e in rows):raise DemoError('STORAGE_SCOPE_MISMATCH')
            return rows
        except (KeyError,TypeError):raise DemoError('STORAGE_INVALID_RESPONSE') from None
    async def lookup(self,key):
        rows=await self.history(key=key,limit=1);return rows[0] if rows else None
