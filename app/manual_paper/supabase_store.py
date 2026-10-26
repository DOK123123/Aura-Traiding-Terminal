"""Dedicated Supabase RPC backend. No exchange/Active43 access or local fallback.

The synchronous interface matches ManualStore; Service runs all I/O in threads.
Each mutation is a server-validated optimistic CAS, atomically committed with its
permanent receipt by PostgreSQL. SQL checks quote freshness after acquiring lock.
"""
import hashlib
import json
import re
import threading
import time

import httpx

from app.forward.storage import SecretFilter
from .core import ManualPaper
from .store import ManualStore

PREFIX='aura_manual_paper_v1_'
MAX_PAYLOAD=1048576
ERRORS={'CONCURRENT_UPDATE','IDEMPOTENCY_CONFLICT','CORRUPT_JOURNAL','STALE_QUOTE',
        'WRITE_LIMIT','INVALID_REQUEST_ID','STORAGE_SCOPE_MISMATCH'}


class SupabaseStore:
    backend='SUPABASE_MANUAL_PAPER_V1'
    durable=True

    def __init__(self,url,key,*,transport=None):
        import logging
        url=url.strip().rstrip('/');key=key.strip()
        if (not re.fullmatch(r'https://[a-z0-9]{12,40}\.supabase\.co',url)
                or not 32<=len(key)<=8192 or not key.isascii() or not key.isprintable()):
            raise ValueError('INVALID_STORAGE_CONFIGURATION')
        self.base=url
        self.slots=threading.BoundedSemaphore(2)
        self.cache_lock=threading.Lock()
        self.cached=None
        headers={'apikey':key}
        # New secret keys are API keys, not JWTs. Only legacy JWT keys go in Bearer.
        if key.startswith('eyJ'):headers['Authorization']='Bearer '+key
        self.client=httpx.Client(timeout=5,follow_redirects=False,transport=transport,
                                 headers=headers,limits=httpx.Limits(max_connections=2))
        self.log_filter=SecretFilter(key)
        self.handlers={*logging.getLogger().handlers}
        for log in logging.Logger.manager.loggerDict.values():
            if isinstance(log,logging.Logger):self.handlers.update(log.handlers)
        if logging.lastResort:self.handlers.add(logging.lastResort)
        for handler in self.handlers:handler.addFilter(self.log_filter)

    def close(self):
        self.client.close()
        for handler in self.handlers:handler.removeFilter(self.log_filter)

    def rpc(self,name,args):
        if name not in ('load','lookup','commit'):
            raise ValueError('STORAGE_SCOPE_MISMATCH')
        started=time.monotonic()
        try:
            with self.slots:
                with self.client.stream('POST',self.base+'/rest/v1/rpc/'+PREFIX+name,json={'p_'+k:v for k,v in args.items()}) as r:
                    if r.status_code!=200:
                        raise ValueError('STORAGE_UNAVAILABLE')
                    raw=bytearray()
                    for chunk in r.iter_bytes():
                        if time.monotonic()-started>10:raise ValueError('STORAGE_UNAVAILABLE')
                        raw.extend(chunk)
                        if len(raw)>2*MAX_PAYLOAD:raise ValueError('STORAGE_RESPONSE_LIMIT')
                    value=json.loads(raw)
                    if isinstance(value,dict) and value.get('error'):
                        raise ValueError(value['error'] if value['error'] in ERRORS else 'STORAGE_UNAVAILABLE')
                    return value
        except httpx.HTTPError:
            # Includes unknown mutation outcome. Never retry with a new request ID.
            raise ValueError('STORAGE_UNAVAILABLE') from None
        except (TypeError,ArithmeticError,json.JSONDecodeError):
            raise ValueError('CORRUPT_JOURNAL') from None

    @staticmethod
    def _digest(payload):
        return hashlib.sha256(payload.encode()).hexdigest()

    def load(self):
        with self.cache_lock:cached=self.cached
        value=self.rpc('load',{'known_version':cached['version'] if cached else None})
        if value is None:
            # An existing account disappearing cannot become an automatic reset.
            if cached is not None:raise ValueError('CORRUPT_JOURNAL')
            return None,0
        try:
            if not isinstance(value,dict):raise ValueError()
            if value.get('scope')!='AURA_MANUAL_PAPER_V1':raise ValueError()
            version=value['version']
            if type(version) is not int or version<1:raise ValueError()
            if value.get('unchanged') is True:
                if cached is None or version!=cached['version'] or value['sha256']!=cached['sha256']:
                    raise ValueError()
                value=cached
            elif (not isinstance(value.get('payload'),str) or not isinstance(value.get('sha256'),str)
                  or self._digest(value['payload'])!=value['sha256']):
                raise ValueError()
            ledger=ManualStore.decode(value['payload'])
            with self.cache_lock:
                if self.cached is None or self.cached['version']<=version:
                    self.cached=dict(payload=value['payload'],sha256=value['sha256'],version=version)
            return ledger,version
        except (KeyError,TypeError,ValueError):
            raise ValueError('CORRUPT_JOURNAL') from None

    def lookup(self,request_id,command,arguments):
        if not re.fullmatch(r'[a-f0-9]{32}',request_id):raise ValueError('INVALID_REQUEST_ID')
        value=self.rpc('lookup',{'request_id':request_id,'intent_hash':ManualStore.fingerprint(command,arguments)})
        if value is not None:
            self.receipt(value,request_id,command)
        return value

    @staticmethod
    def receipt(value,request_id,command):
        if (not isinstance(value,dict) or value.get('request_id')!=request_id or value.get('command')!=command
                or type(value.get('version')) is not int or value['version']<1
                or not isinstance(value.get('balance'),str) or not isinstance(value.get('result'),dict)):
            raise ValueError('CORRUPT_JOURNAL')

    def _commit(self,version,ledger,request_id,intent_hash,receipt,quote_ms):
        ledger.validate()
        payload=ManualStore.encode(ledger)
        if len(payload.encode())>MAX_PAYLOAD:raise ValueError('WRITE_LIMIT')
        return self.rpc('commit',dict(expected_version=version,new_payload=payload,
            new_sha256=self._digest(payload),request_id=request_id,intent_hash=intent_hash,
            new_receipt=receipt,quote_ms=quote_ms))

    def save(self,ledger,expected_version):
        # Only first empty-account creation is supported; never overwrite a live ledger.
        if expected_version!=0 or ManualStore.encode(ledger)!=ManualStore.encode(ManualPaper()):
            raise ValueError('STORAGE_SCOPE_MISMATCH')
        value=self._commit(0,ledger,None,None,None,None)
        if value!={'version':1}:raise ValueError('CORRUPT_JOURNAL')
        return 1

    def execute(self,request_id,command,arguments,apply_command,*,quote_ms=None):
        previous=self.lookup(request_id,command,arguments)
        if previous is not None:return previous
        for _ in range(3):
            ledger,version=self.load()
            ledger=ledger if ledger is not None else ManualPaper()
            try:
                # Reserve room for the eventual close before another open.
                if command=='OPEN' and len(ManualStore.encode(ledger).encode())>MAX_PAYLOAD-8192:
                    raise ValueError('WRITE_LIMIT')
                result=apply_command(ledger)
            except ValueError:
                # A duplicate can commit BETWEEN lookup and load. Its resulting
                # position/stale quote must not turn a successful retry into an
                # error. The permanent receipt remains authoritative.
                previous=self.lookup(request_id,command,arguments)
                if previous is not None:return previous
                raise
            receipt=dict(request_id=request_id,command=command,version=version+1,
                         balance=str(ledger.balance),result=result)
            try:
                value=self._commit(version,ledger,request_id,
                    ManualStore.fingerprint(command,arguments),receipt,quote_ms)
                self.receipt(value,request_id,command)
                return value
            except ValueError as exc:
                if str(exc)!='CONCURRENT_UPDATE':raise
                # Another process may have committed this exact intent meanwhile.
                previous=self.lookup(request_id,command,arguments)
                if previous is not None:return previous
        raise ValueError('CONCURRENT_UPDATE')
