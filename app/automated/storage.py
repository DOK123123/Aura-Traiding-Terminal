"""Isolated transactional ledger; durable Supabase or explicitly local development."""
import asyncio
from contextlib import contextmanager
import hashlib,json,sqlite3,time
from pathlib import Path
from app.async_workers import run_in_slot
from app.lab.models import canonical
from app.forward.storage import SupabaseStore as SafeTransport
from app.forward.models import ForwardError
from .engine import DemoError,initial,validate


def packed(value):
    raw=canonical(value).decode();return dict(payload=raw,sha256=hashlib.sha256(raw.encode()).hexdigest())


def unpack(row):
    try:
        raw=row['payload']
        if hashlib.sha256(raw.encode()).hexdigest()!=row['sha256']:raise ValueError()
        return json.loads(raw)
    except (KeyError,TypeError,ValueError,ArithmeticError):raise DemoError('CORRUPT_PORTFOLIO') from None


def verify_envelope(result):
    try:
        if type(result['revision']) is not int or result['revision']<1:raise ValueError()
        state=unpack(result);validate(state)
        return dict(state=state,revision=result['revision'])
    except (KeyError,TypeError,ValueError,ArithmeticError):raise DemoError('CORRUPT_PORTFOLIO') from None


def validate_commit(state,events,key):
    validate(state)
    if not 1<=len(events)<=100:raise DemoError('WRITE_LIMIT')
    if len(canonical(state))>65536:raise DemoError('WRITE_LIMIT')
    if key not in {e.get('id') for e in events}:raise DemoError('INVALID_EVENT')
    ids=set()
    for e in events:
        if (not isinstance(e['id'],str) or len(e['id'])>200 or e['id'] in ids or len(canonical(e))>65536 or
            e['epoch']!=state['epoch'] or type(e['created_at']) is not int or
            e['payload'].get('execution_mode')!='PAPER_ONLY' or e['payload'].get('real_money_execution')!='DISABLED'):raise DemoError('INVALID_EVENT')
        ids.add(e['id'])


SCHEMA='''
CREATE TABLE IF NOT EXISTS auto42_account (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auto42_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,epoch TEXT NOT NULL,kind TEXT NOT NULL,created_at INTEGER NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS auto42_epoch ON auto42_events(epoch,seq);
CREATE TRIGGER IF NOT EXISTS auto42_no_update BEFORE UPDATE ON auto42_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS auto42_no_delete BEFORE DELETE ON auto42_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
'''


class SQLiteStore:
    backend='SQLITE_DEVELOPMENT_ONLY';durable=False
    def __init__(self,path,clock=time.time):
        self.path=Path(path);self.clock=clock;self.slots=asyncio.Semaphore(2)
        if self.path.name!='auto-paper-42.sqlite3':raise DemoError('STORAGE_SCOPE_MISMATCH')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
            if tables-{'auto42_account','auto42_events','sqlite_sequence'}:raise DemoError('STORAGE_SCOPE_MISMATCH')
            c.execute('PRAGMA journal_mode=WAL');c.executescript(SCHEMA)
            p=packed(initial(int(clock())))
            c.execute('insert or ignore into auto42_account values(1,1,?,?)',(p['payload'],p['sha256']))
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=5);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
    async def call(self,fn,*args):
        try:return await run_in_slot(self.slots,fn,*args)
        except (sqlite3.Error,OSError):raise DemoError('STORAGE_UNAVAILABLE') from None
    async def close(self):pass
    async def load(self):return await self.call(self._load)
    def _load(self):
        with self.connect() as c:return verify_envelope(dict(c.execute('select * from auto42_account where id=1').fetchone()))
    async def commit(self,revision,state,events,key):return await self.call(self._commit,revision,state,events,key)
    def _commit(self,revision,state,events,key):
        validate_commit(state,events,key)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=dict(c.execute('select * from auto42_account where id=1').fetchone())
            if c.execute('select 1 from auto42_events where id=?',(key,)).fetchone():return dict(verify_envelope(old),duplicate=True)
            if old['revision']!=revision:raise DemoError('CONCURRENT_UPDATE')
            for e in events:
                p=packed(e);c.execute('insert into auto42_events(id,epoch,kind,created_at,payload,sha256) values(?,?,?,?,?,?)',
                    (e['id'],e['epoch'],e['kind'],e['created_at'],p['payload'],p['sha256']))
            p=packed(state);c.execute('update auto42_account set revision=revision+1,payload=?,sha256=? where id=1',(p['payload'],p['sha256']))
            return dict(state=state,revision=revision+1,duplicate=False)
    async def lookup(self,key):
        return await self.call(self._lookup,key)
    def _lookup(self,key):
        with self.connect() as c:
            r=c.execute('select * from auto42_events where id=?',(key,)).fetchone()
            return unpack(dict(r)) if r else None
    async def history(self,epoch=None,after=None,limit=50):return await self.call(self._history,epoch,after,limit)
    def _history(self,epoch,after,limit):
        if not 1<=limit<=200:raise DemoError('READ_LIMIT')
        with self.connect() as c:
            if after is None:rows=c.execute('select * from auto42_events where (? is null or epoch=?) order by seq desc limit ?',(epoch,epoch,limit)).fetchall()
            else:rows=c.execute('select * from auto42_events where seq>? order by seq limit ?',(after,limit)).fetchall()
            return [dict(unpack(dict(r)),seq=r['seq']) for r in rows]


class SupabaseStore:
    backend='SUPABASE_POSTGRES';durable=True
    def __init__(self,url,key,transport=None):
        try:self.transport=SafeTransport(url,key,transport)
        except ForwardError as exc:raise DemoError(exc.code) from None
    async def close(self):await self.transport.close()
    async def rpc(self,name,args):
        if name not in ('aura_auto42_load','aura_auto42_commit','aura_auto42_history'):raise DemoError('INVALID_STORAGE_ACTION')
        import httpx
        try:
            async with asyncio.timeout(12):
                async with self.transport.slots:
                    async with self.transport.client.stream('POST',self.transport.base+'/rest/v1/rpc/'+name,json=args) as response:
                        if response.status_code!=200:
                            code='STORAGE_AUTH' if response.status_code in (401,403) else 'STORAGE_RATE_LIMIT' if response.status_code==429 else 'STORAGE_HTTP_ERROR'
                            raise DemoError(code)
                        raw=bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw)+len(chunk)>2*1024*1024:raise DemoError('STORAGE_RESPONSE_LIMIT')
                            raw.extend(chunk)
                        value=json.loads(raw)
                        if isinstance(value,dict) and value.get('error'):
                            allowed={'CONCURRENT_UPDATE','CORRUPT_PORTFOLIO','INVALID_EVENT','WRITE_LIMIT'}
                            raise DemoError(value['error'] if value['error'] in allowed else 'STORAGE_UNAVAILABLE')
                        return value
        except (TimeoutError,httpx.TimeoutException):raise DemoError('STORAGE_TIMEOUT') from None
        except httpx.HTTPError:raise DemoError('STORAGE_NETWORK') from None
        except (ValueError,TypeError):raise DemoError('STORAGE_INVALID_RESPONSE') from None
    async def load(self):
        seed=packed(initial(int(time.time())))
        return verify_envelope(await self.rpc('aura_auto42_load',dict(seed=seed)))
    async def commit(self,revision,state,events,key):
        validate_commit(state,events,key)
        value=await self.rpc('aura_auto42_commit',dict(expected_revision=revision,new_state=packed(state),new_events=[dict(e,**packed(e)) for e in events],operation_key=key))
        result=verify_envelope(value)
        if type(value.get('duplicate')) is not bool:raise DemoError('STORAGE_INVALID_RESPONSE')
        return dict(result,duplicate=value['duplicate'])
    async def lookup(self,key):
        value=await self.rpc('aura_auto42_history',dict(selected_epoch=None,after_seq=None,row_limit=1,event_id=key))
        if not isinstance(value,list) or len(value)>1:raise DemoError('STORAGE_INVALID_RESPONSE')
        return unpack(value[0]) if value else None
    async def history(self,epoch=None,after=None,limit=50):
        value=await self.rpc('aura_auto42_history',dict(selected_epoch=epoch,after_seq=after,row_limit=limit))
        if not isinstance(value,list) or len(value)>200:raise DemoError('STORAGE_INVALID_RESPONSE')
        return [dict(unpack(r),seq=r['seq']) for r in value]
