"""Append-only SQLite development store and transactional Supabase RPC adapter."""
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import time
from contextlib import contextmanager
import httpx
from app.async_workers import run_in_slot
from app.lab.models import canonical,digest
from .models import ForwardError,STEPS,verify,record

KINDS=('PRED','OUTCOME','CORRECTION','TICK','COMPLETE','FAILURE')


def validate(row):
    if row.get('kind') not in KINDS or not isinstance(row.get('id'),str) or len(row['id'])>160:
        raise ForwardError('INVALID_RECORD')
    if type(row.get('created_ms')) is not int or row['created_ms']<0 or len(row['payload'].encode())>65536:
        raise ForwardError('INVALID_RECORD')
    body=verify(row)
    if row['kind']=='PRED':
        if (row['tf'] not in STEPS or type(row['closed_at']) is not int or row['closed_at']%STEPS[row['tf']] or
                body.get('exchange')!='Binance' or body.get('market_type')!='SPOT' or body.get('symbol')!='BTCUSDT' or
                body.get('closed_at')!=row['closed_at'] or body.get('id')!=row['id']):raise ForwardError('INVALID_PREDICTION')
    return body


SCHEMA='''
CREATE TABLE IF NOT EXISTS forward_records (
 seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,
 created_ms INTEGER NOT NULL,ingested_ms INTEGER NOT NULL,cohort TEXT NOT NULL,tf TEXT NOT NULL,
 closed_at INTEGER NOT NULL,ref TEXT NOT NULL,horizon INTEGER NOT NULL,
 payload TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS forward_prediction_unique ON forward_records(cohort,tf,closed_at) WHERE kind='PRED';
CREATE UNIQUE INDEX IF NOT EXISTS forward_outcome_unique ON forward_records(ref,horizon) WHERE kind='OUTCOME';
CREATE INDEX IF NOT EXISTS forward_ref_idx ON forward_records(ref);
CREATE INDEX IF NOT EXISTS forward_kind_idx ON forward_records(kind,cohort,seq);
CREATE TRIGGER IF NOT EXISTS forward_no_update BEFORE UPDATE ON forward_records BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS forward_no_delete BEFORE DELETE ON forward_records BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
'''


class SQLiteStore:
    backend='SQLITE_LOCAL_NOT_RENDER_DURABLE'
    def __init__(self,path,clock=time.time):
        self.path=Path(path);self.clock=clock;self.slots=asyncio.Semaphore(2)
        if self.path.name!='forward-validation.sqlite3':raise ForwardError('STORAGE_SCOPE_MISMATCH')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
            if tables-{'forward_records','sqlite_sequence'}:raise ForwardError('STORAGE_SCOPE_MISMATCH')
            c.execute('PRAGMA journal_mode=WAL');c.executescript(SCHEMA)
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=5);c.row_factory=sqlite3.Row
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:c.close()
    async def call(self,fn,*args):
        try:return await run_in_slot(self.slots,fn,*args)
        except (sqlite3.Error,OSError):raise ForwardError('STORAGE_UNAVAILABLE') from None
    async def close(self):pass
    async def append(self,rows):return await self.call(self._append,rows)
    def _append(self,rows):
        if len(rows)>100:raise ForwardError('WRITE_LIMIT')
        inserted=duplicates=corrections=0;now_ms=int(self.clock()*1000)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in rows:
                body=validate(row)
                old=c.execute('select * from forward_records where id=?',(row['id'],)).fetchone()
                if old:
                    previous=verify(dict(old));duplicates+=1
                    if row['kind'] in ('PRED','OUTCOME') and previous['fingerprint']!=body['fingerprint']:
                        reference=row['id'] if row['kind']=='PRED' else row['ref']
                        payload=dict(prediction_id=reference,reference_id=row['id'],old_sha256=old['sha256'],
                            proposed_record=body,reason='IMMUTABLE_SOURCE_CORRECTION',fingerprint=body['fingerprint'])
                        correction=record('CORRECTION','correction:'+digest([row['id'],body['fingerprint']]),payload,
                            now_ms,row['cohort'],row['tf'],row['closed_at'],reference)
                        result=self._insert(c,correction,now_ms);corrections+=result
                    continue
                if row['kind']=='PRED':
                    step=STEPS[row['tf']]
                    if (now_ms<row['closed_at']*1000 or not row['closed_at']*1000<=row['created_ms']<(row['closed_at']+step)*1000 or
                            abs(row['created_ms']-now_ms)>120000 or now_ms>=(row['closed_at']+step)*1000):
                        raise ForwardError('RETROACTIVE_PREDICTION')
                if row['kind']=='OUTCOME':
                    pred=c.execute("select * from forward_records where id=? and kind='PRED'",(row['ref'],)).fetchone()
                    if not pred or body['prediction_id']!=row['ref'] or row['horizon'] not in (4,8,16,32) or body['target_closed_at']!=pred['closed_at']+row['horizon']*STEPS[pred['tf']] or now_ms<body['target_closed_at']*1000:
                        raise ForwardError('PREMATURE_OUTCOME')
                inserted+=self._insert(c,row,now_ms)
        return dict(inserted=inserted,duplicates=duplicates,corrections=corrections)
    def _insert(self,c,row,now_ms):
        return c.execute('insert or ignore into forward_records(id,kind,created_ms,ingested_ms,cohort,tf,closed_at,ref,horizon,payload,sha256) values(?,?,?,?,?,?,?,?,?,?,?)',
            (row['id'],row['kind'],row['created_ms'],now_ms,row['cohort'],row['tf'],row['closed_at'],row['ref'],row['horizon'],row['payload'],row['sha256'])).rowcount
    async def read(self,mode='recent',after=0,limit=100,through=None,cohort=None,now=None):
        return await self.call(self._read,mode,after,limit,through,cohort,now)
    def _read(self,mode,after,limit,through,cohort,now):
        if mode not in ('recent','export','pending','run') or not 1<=limit<=200:raise ForwardError('READ_LIMIT')
        with self.connect() as c:
            if mode=='run':
                rows=c.execute('select * from forward_records where id=?',('tick:'+str(after)+':complete',)).fetchall()
            elif mode=='pending':
                query="""select * from forward_records p where p.kind='PRED' and exists(
                    select 1 from (select 4 h union all select 8 union all select 16 union all select 32) hs
                    where p.closed_at+hs.h*(case p.tf when '15m' then 900 when '1h' then 3600 else 14400 end)<=?
                    and not exists(select 1 from forward_records o where o.kind='OUTCOME' and o.ref=p.id and o.horizon=hs.h)) order by p.seq limit ?"""
                rows=c.execute(query,(int(now if now is not None else self.clock()),limit)).fetchall()
            elif mode=='recent':
                preds=c.execute("select id from forward_records where kind='PRED' and (? is null or cohort=?) order by seq desc limit ?",(cohort,cohort,limit)).fetchall()
                ids=[r[0] for r in preds]
                if not ids:return []
                places=','.join('?' for _ in ids)
                rows=c.execute(f'select * from forward_records where id in ({places}) or ref in ({places}) order by seq',ids+ids).fetchall()
            else:
                rows=c.execute('select * from forward_records where seq>? and (? is null or seq<=?) order by seq limit ?',
                    (after,through,through,limit)).fetchall()
            result=[dict(r) for r in rows]
            if len(result)>2000:raise ForwardError('READ_LIMIT')
            for r in result:verify(r)
            return result
    async def status(self,cohort=None):return await self.call(self._status,cohort)
    def _status(self,cohort):
        with self.connect() as c:
            counts=dict(c.execute('select kind,count(*) from forward_records group by kind').fetchall())
            last=dict(c.execute('select kind,max(created_ms) from forward_records group by kind').fetchall())
            bounds=c.execute('select count(*),coalesce(max(seq),0) from forward_records').fetchone()
            pairs=c.execute("select tf,closed_at from forward_records where kind='PRED' and (? is null or cohort=?) order by tf,closed_at",(cohort,cohort)).fetchall()
            ticks=[r[0]//300000 for r in c.execute("select created_ms from forward_records where kind='TICK' order by created_ms")]
            misses=0;previous={};now=int(self.clock())
            for tf,at in pairs:
                if tf in previous:misses+=max(0,(at-previous[tf])//STEPS[tf]-1)
                previous[tf]=at
            misses+=sum(max(0,(now//STEPS[tf]*STEPS[tf]-at)//STEPS[tf]) for tf,at in previous.items())
            missed_runs=sum(max(0,b-a-1) for a,b in zip(ticks,ticks[1:]))+(max(0,now//300-ticks[-1]) if ticks else 0)
            cohorts=[dict(cohort=r[0],predictions=r[1]) for r in c.execute("select cohort,count(*) from forward_records where kind='PRED' group by cohort order by max(seq) desc limit 100")]
            last_eval=c.execute("select max(created_ms) from forward_records where kind='OUTCOME' and json_extract(payload,'$.quality')='COMPLETE'").fetchone()[0]
            evaluated=c.execute("select count(distinct ref) from forward_records where kind='OUTCOME' and json_extract(payload,'$.quality')='COMPLETE'").fetchone()[0]
            invalid=c.execute("select count(*) from forward_records where kind='OUTCOME' and json_extract(payload,'$.quality')<>'COMPLETE'").fetchone()[0]
            return dict(evaluated_predictions=evaluated,invalid_outcomes=invalid,last_successful_evaluation_ms=last_eval,counts=counts,last=last,total_rows=bounds[0],max_seq=bounds[1],missed_closed_candles=misses,
                missed_runs=missed_runs,monitoring_scope='Since first recorded capture/tick only',cohorts=cohorts)


class SecretFilter(logging.Filter):
    def __init__(self,secret):super().__init__();self.secret=secret
    def filter(self,r):
        try:r.msg=r.getMessage().replace(self.secret,'[REDACTED]');r.args=()
        except Exception:r.msg='[REDACTED LOG]';r.args=()
        if r.exc_info:
            import traceback
            r.exc_text=''.join(traceback.format_exception(*r.exc_info)).replace(self.secret,'[REDACTED]');r.exc_info=None
        return True


class SupabaseStore:
    backend='SUPABASE_POSTGRES'
    def __init__(self,url,key,transport=None):
        if not re.fullmatch(r'https://[a-z0-9]{12,40}\.supabase\.co',url) or not 32<=len(key)<=8192 or not key.isascii() or not key.isprintable():
            raise ForwardError('INVALID_STORAGE_CONFIGURATION')
        self.base=url;self.filter=SecretFilter(key);self.slots=asyncio.Semaphore(2)
        handlers={*logging.getLogger().handlers}
        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger,logging.Logger):handlers.update(logger.handlers)
        if logging.lastResort:handlers.add(logging.lastResort)
        self.handlers=handlers
        for h in handlers:h.addFilter(self.filter)
        self.client=httpx.AsyncClient(timeout=10,follow_redirects=False,transport=transport,
            headers={'apikey':key,'Authorization':'Bearer '+key})
    async def close(self):
        await self.client.aclose()
        for h in self.handlers:h.removeFilter(self.filter)
    async def rpc(self,name,args):
        if name not in ('aura_forward_append','aura_forward_read','aura_forward_status'):
            raise ForwardError('STORAGE_METHOD_FORBIDDEN')
        try:
            async with asyncio.timeout(12):
                return await self._request(name,args)
        except (httpx.TimeoutException,TimeoutError):raise ForwardError('STORAGE_TIMEOUT') from None
        except httpx.HTTPError:raise ForwardError('STORAGE_NETWORK_ERROR') from None
        except (ValueError,TypeError):raise ForwardError('STORAGE_INVALID_RESPONSE') from None
    async def _request(self,name,args):
        async with self.slots:
            async with self.client.stream('POST',self.base+'/rest/v1/rpc/'+name,json=args) as response:
                if response.status_code==429:raise ForwardError('STORAGE_RATE_LIMIT')
                if response.status_code in (401,403):raise ForwardError('STORAGE_AUTH_ERROR')
                if response.status_code>=400:raise ForwardError('STORAGE_HTTP_ERROR')
                raw=bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw)+len(chunk)>2*1024*1024:raise ForwardError('STORAGE_RESPONSE_LIMIT')
                    raw.extend(chunk)
                return json.loads(raw)
    async def append(self,rows):
        if len(rows)>100:raise ForwardError('WRITE_LIMIT')
        for r in rows:validate(r)
        result=await self.rpc('aura_forward_append',{'p_records':rows})
        if not isinstance(result,dict) or any(type(result.get(k)) is not int or not 0<=result[k]<=100 for k in ('inserted','duplicates','corrections')):raise ForwardError('STORAGE_INVALID_RESPONSE')
        return result
    async def read(self,mode='recent',after=0,limit=100,through=None,cohort=None,now=None):
        result=await self.rpc('aura_forward_read',{'p_mode':mode,'p_after':after,'p_limit':limit,'p_through':through,'p_cohort':cohort})
        if not isinstance(result,list) or len(result)>2000:raise ForwardError('STORAGE_INVALID_RESPONSE')
        for row in result:verify(row)
        return result
    async def status(self,cohort=None):
        result=await self.rpc('aura_forward_status',{'p_cohort':cohort})
        if not isinstance(result,dict) or not isinstance(result.get('counts'),dict) or not isinstance(result.get('last'),dict) or any(type(result.get(k)) is not int or result[k]<0 for k in ('total_rows','max_seq','missed_closed_candles','missed_runs')):
            raise ForwardError('STORAGE_INVALID_RESPONSE')
        return result
