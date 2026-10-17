"""Separate Supabase RPC namespace; reuses existing safe transport, not Auto account."""
import asyncio
import json
from app.forward.storage import SupabaseStore as Transport
from app.forward.models import ForwardError
from app.automated.storage import packed,unpack
from app.automated.engine import DemoError
from .core import seed,checked,SCOPE

class Store:
    backend='SUPABASE_PRACTICE_ONLY'
    def __init__(self,url,key,transport=None):
        try:self.transport=Transport(url,key,transport)
        except ForwardError as e:raise DemoError(e.code) from None
    async def close(self):await self.transport.close()
    async def rpc(self,name,args):
        if name not in ('aura_practice_load','aura_practice_commit','aura_practice_history'):raise DemoError('STORAGE_METHOD_FORBIDDEN')
        try:
            async with asyncio.timeout(12):
                async with self.transport.slots:
                    async with self.transport.client.stream('POST',self.transport.base+'/rest/v1/rpc/'+name,json=args) as r:
                        if r.status_code!=200:raise DemoError('STORAGE_UNAVAILABLE')
                        raw=bytearray()
                        async for b in r.aiter_bytes():
                            raw.extend(b)
                            if len(raw)>2*1024**2:raise DemoError('STORAGE_RESPONSE_LIMIT')
                        value=json.loads(raw)
                        if type(value) is dict and value.get('error'):
                            code=value['error'];raise DemoError(code if code in ('CONCURRENT_UPDATE','IDEMPOTENCY_CONFLICT','CORRUPT_PORTFOLIO','WRITE_LIMIT','INVALID_EVENT','STALE_QUOTE_AT_COMMIT') else 'STORAGE_UNAVAILABLE')
                        return value
        except (TimeoutError,):raise DemoError('STORAGE_TIMEOUT_OUTCOME_UNKNOWN') from None
        except DemoError:raise
        except Exception:raise DemoError('STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN') from None
    @staticmethod
    def envelope(value):
        try:
            if type(value['revision']) is not int or value['revision']<1:raise ValueError()
            state=checked(unpack(value))
            if type(value.get('last_saved_at')) is not int or value['last_saved_at']<0 or type(value.get('duplicate',False)) is not bool:raise ValueError()
            return dict(state=state,revision=value['revision'],last_saved_at=value['last_saved_at'],duplicate=value.get('duplicate',False))
        except (KeyError,TypeError,ValueError):raise DemoError('CORRUPT_PORTFOLIO') from None
    async def load(self,now):return self.envelope(await self.rpc('aura_practice_load',dict(seed=packed(seed(now)))))
    async def commit(self,revision,state,event,key):
        checked(state)
        result=await self.rpc('aura_practice_commit',dict(expected_revision=revision,new_state=packed(state),new_events=[dict(event,**packed(event))],operation_key=key))
        return self.envelope(result)
    async def history(self,after=None,limit=100,key=None):
        rows=await self.rpc('aura_practice_history',dict(selected_epoch=None,after_seq=after,row_limit=limit,event_id=key))
        if type(rows) is not list or len(rows)>limit:raise DemoError('STORAGE_INVALID_RESPONSE')
        try:
            result=[dict(unpack(r),seq=r['seq']) for r in rows]
            for e in result:
                if (e.get('kind') not in ('OPEN','UPDATE','CLOSE') or not str(e.get('id','')).startswith('practice:') or type(e.get('seq')) is not int or e['seq']<1
                    or e.get('payload',{}).get('practice_scope')!=SCOPE or e['payload'].get('execution_mode')!='PAPER_ONLY' or e['payload'].get('real_money_execution')!='DISABLED'):raise DemoError('STORAGE_INVALID_RESPONSE')
            return result
        except (KeyError,TypeError):raise DemoError('STORAGE_INVALID_RESPONSE') from None
