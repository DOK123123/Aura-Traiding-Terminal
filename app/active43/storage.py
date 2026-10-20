"""Dedicated Supabase namespace; no method can address another portfolio."""
import asyncio,json,re
from datetime import datetime
import httpx
from app.forward.storage import SupabaseStore as SafeTransport
from app.forward.models import ForwardError
from app.automated.storage import packed,unpack,verify_envelope,validate_commit
from app.automated.diagnostics import http_error
from app.automated.engine import DemoError
from .core import initial,validate,SCOPE

URL_VARIABLE='AURA_ACTIVE43_BITGET_SUPABASE_URL'
KEY_VARIABLE='AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY'


def storage_configuration(url: str,key: str) -> dict:
    """Safe metadata only. Never expose URLs, credentials, length or fingerprints."""
    normalized_url=url.strip().rstrip('/')
    normalized_key=key.strip()
    code=None
    if not normalized_url:code='STORAGE_URL_MISSING'
    elif not re.fullmatch(r'https://[a-z0-9]{12,40}\.supabase\.co',normalized_url):code='STORAGE_URL_INVALID'
    elif not normalized_key:code='STORAGE_KEY_MISSING'
    elif not (32<=len(normalized_key)<=8192 and normalized_key.isascii() and normalized_key.isprintable()):code='STORAGE_KEY_INVALID'
    return dict(code=code,url_variable=URL_VARIABLE,key_variable=KEY_VARIABLE,
        url_present=bool(normalized_url),key_present=bool(normalized_key),
        url_format_valid=bool(re.fullmatch(r'https://[a-z0-9]{12,40}\.supabase\.co',normalized_url)),
        key_format_valid=32<=len(normalized_key)<=8192 and normalized_key.isascii() and normalized_key.isprintable(),
        url_padding_normalized=url!=normalized_url,key_padding_normalized=key!=normalized_key)


class Store:
    backend='SUPABASE_ACTIVE43_BITGET';durable=True
    def __init__(self,url,key,config,transport=None):
        self.config=config;self.status='UNKNOWN'
        metadata=storage_configuration(url,key)
        if metadata['code']:raise DemoError(metadata['code'])
        try:self.transport=SafeTransport(url.strip().rstrip('/'),key.strip(),transport)
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
    async def peek(self):
        """GET only the dedicated singleton; unlike load(), never seeds an account."""
        try:
            async with asyncio.timeout(12):
                async with self.transport.slots:
                    async with self.transport.client.stream('GET',self.transport.base+'/rest/v1/aura_active43_bitget_account',
                            params={'id':'eq.1','select':'revision,payload,sha256,saved_at','limit':'1'}) as response:
                        raw=bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw)+len(chunk)>131072:raise DemoError('STORAGE_RESPONSE_LIMIT')
                            raw.extend(chunk)
                        try:value=json.loads(raw)
                        except ValueError:raise DemoError('STORAGE_INVALID_RESPONSE') from None
                        if response.status_code!=200:raise DemoError(http_error(response.status_code,value)[0])
                        if not isinstance(value,list) or len(value)>1:raise DemoError('STORAGE_INVALID_RESPONSE')
                        if not value:return None
                        row=value[0]
                        saved=datetime.fromisoformat(row['saved_at'].replace('Z','+00:00'))
                        if saved.tzinfo is None:raise DemoError('STORAGE_INVALID_RESPONSE')
                        return self.envelope(dict(row,last_saved_at=int(saved.timestamp())))
        except (TimeoutError,httpx.TimeoutException):raise DemoError('STORAGE_READ_TIMEOUT') from None
        except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError,OverflowError):raise DemoError('STORAGE_INVALID_RESPONSE') from None

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
