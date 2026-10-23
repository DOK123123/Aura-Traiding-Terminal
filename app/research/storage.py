"""Dedicated bounded local queue/history and conservative LLM reservations."""
from contextlib import contextmanager
import gzip
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from app.lab.models import LabError,canonical,digest
from .artifacts import COMPACT_LIMIT,CHUNK_LIMIT,split_report,decode,checked_manifest,unpack_chunk,bad,ARRAYS

APP_ID=0x41524c31
MAX_RAW=COMPACT_LIMIT
DB_LIMIT=256*1024*1024
SCHEMA=2

class Store:
    def __init__(self,root:Path,clock=time.time,*,directory=None,readonly=False):
        self.root=Path(root).resolve();self.directory=Path(directory) if directory is not None else self.root/'.data/ai-research'
        self.path=self.directory/'ai-research-v1.sqlite3';self.clock=clock;self.readonly=readonly
        self._safe_path()
        if readonly and not self.path.exists():raise LabError('RESEARCH_STORAGE_NOT_CONFIGURED')
        if not readonly:self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            from contextlib import closing
            from urllib.parse import quote
            with closing(sqlite3.connect('file:'+quote(str(self.path.resolve()))+'?mode=ro',uri=True)) as c:
                if c.execute('pragma application_id').fetchone()[0]!=APP_ID:raise LabError('RESEARCH_STORAGE_CONFLICT')
                if c.execute('pragma user_version').fetchone()[0]!=SCHEMA:raise LabError('RESEARCH_STORAGE_VERSION')
        else:
            # Exclusive creation prevents adopting an unrelated database in a race.
            try:
                with self.path.open('xb'):pass
            except FileExistsError:raise LabError('RESEARCH_STORAGE_CONFLICT') from None
            with sqlite3.connect(self.path) as c:
                c.execute(f'pragma application_id={APP_ID}');c.execute(f'pragma user_version={SCHEMA}')
                c.execute('pragma max_page_count=65536')
                c.executescript('''
                 create table queue(id text primary key, fingerprint text unique not null, hypothesis text not null, state text not null, created integer not null, updated integer not null, config text not null, result blob, error text, attempt text);
                 create table events(seq integer primary key, job_id text not null, at integer not null, role text not null, state text not null);
                 create table chunks(job_id text not null,attempt text not null,run_key text not null,kind text not null,ordinal integer not null,payload blob not null,primary key(job_id,attempt,run_key,kind,ordinal));
                 create index events_job_seq on events(job_id,seq);
                 create table llm_calls(id text primary key, at integer not null, provider text not null, model text not null, reserved integer not null, state text not null, usage text);
                ''')

    def _safe_path(self):
        forbidden=(Path(os.getenv('PAPER_DB_PATH',str(self.root/'.data/paper.sqlite3'))),
            Path(os.getenv('LAB_DB_PATH',str(self.root/'.data/strategy-lab.sqlite3'))),
            self.root/'.cache/patterns.sqlite3',self.root/'.data/auto-paper-42.sqlite3')
        if any(self.path.resolve()==p.resolve() or (self.path.exists() and p.exists() and self.path.samefile(p)) for p in forbidden):
            raise LabError('RESEARCH_STORAGE_CONFLICT')
        for p in (self.root/'.data',self.path.parent,self.path):
            if p.is_symlink():raise LabError('RESEARCH_STORAGE_CONFLICT')
        if self.path.exists() and (self.path.stat().st_nlink!=1 or self.path.stat().st_size>DB_LIMIT):raise LabError('RESEARCH_STORAGE_CONFLICT')

    @contextmanager
    def connect(self):
        self._safe_path()
        if self.readonly:
            from urllib.parse import quote
            c=sqlite3.connect('file:'+quote(str(self.path.resolve()))+'?mode=ro',uri=True,timeout=2)
        else:c=sqlite3.connect(self.path,timeout=5)
        c.row_factory=sqlite3.Row
        if not self.readonly:
            page=c.execute('pragma page_size').fetchone()[0];c.execute('pragma max_page_count='+str(DB_LIMIT//page))
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()

    def enqueue(self,config:dict) -> str:
        now=int(self.clock());raw_config=canonical(config)
        if type(config) is not dict or len(raw_config)>65536:raise LabError('INVALID_DATA')
        fp=digest(config);ident=uuid.uuid4().hex
        with self.connect() as c:
            c.execute('begin immediate')
            row=c.execute('select id from queue where fingerprint=?',(fp,)).fetchone()
            if row:return row['id']
            if c.execute('select count(*) from queue').fetchone()[0]>=32:raise LabError('RESEARCH_QUEUE_FULL')
            c.execute('insert into queue(id,fingerprint,hypothesis,state,created,updated,config) values(?,?,?,?,?,?,?)',(ident,fp,config['hypothesis'],'QUEUED',now,now,canonical(config).decode()))
            c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(ident,now,'RESEARCHER','FROZEN_CONFIG'))
        return ident

    def claim(self,ident:str) -> dict:
        with self.connect() as c:
            c.execute('begin immediate')
            row=c.execute("select state,fingerprint,case when length(config)<=65536 then config else null end config from queue where id=?",(ident,)).fetchone()
            if not row:raise LabError('RESEARCH_NOT_FOUND')
            if row['state']!='QUEUED':raise LabError('RESEARCH_ALREADY_PROCESSED')
            if c.execute("select 1 from queue where state='RUNNING'").fetchone():raise LabError('BUSY')
            now=int(self.clock());attempt=uuid.uuid4().hex
            c.execute("update queue set state='RUNNING',updated=?,attempt=? where id=?",(now,attempt,ident))
            c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(ident,now,'BACKTESTER','TESTING'))
            config=decode(row['config'])
            if type(config) is not dict or digest(config)!=row['fingerprint']:bad()
            return dict(config=config,attempt=attempt)

    def finish(self,ident:str,result:dict|None,error:str|None=None,*,attempt:str):
        if (result is None)==(error is None):raise LabError('INVALID_DATA')
        with self.connect() as c:
            c.execute('begin immediate');now=int(self.clock())
            row=c.execute("select config from queue where id=? and state='RUNNING' and attempt=?",(ident,attempt)).fetchone()
            if not row:raise LabError('RESEARCH_ALREADY_PROCESSED')
            blob=None
            if result is not None:
                if type(result) is not dict or result.get('config')!=decode(row['config']):bad()
                def emit(run_key,kind,ordinal,start,count,raw):
                    import hashlib
                    c.execute('insert into chunks values(?,?,?,?,?,?)',(ident,attempt,run_key,kind,ordinal,gzip.compress(raw,mtime=0)))
                    return dict(ordinal=ordinal,start=start,count=count,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                compact=split_report(result,emit);blob=canonical(compact)
            status='ERROR' if error else result['auditor']['status']
            c.execute("update queue set state=?,updated=?,result=?,error=? where id=? and state='RUNNING' and attempt=?",(status,now,blob,error,ident,attempt))
            c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(ident,now,'AUDITOR',status))

    def interrupt_stale(self):
        with self.connect() as c:
            c.execute('begin immediate');now=int(self.clock())
            rows=c.execute("select id from queue where state='RUNNING' and updated<?",(now-600,)).fetchall()
            for row in rows:
                c.execute("update queue set state='ERROR',error='INTERRUPTED_MANUAL_RECOVERY',updated=? where id=?",(now,row['id']))
                c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(row['id'],now,'AUDITOR','INTERRUPTED'))
            return len(rows)

    def retry(self,ident:str):
        with self.connect() as c:
            c.execute('begin immediate');now=int(self.clock())
            changed=c.execute("update queue set state='QUEUED',updated=?,error=null where id=? and state='ERROR' and result is null",(now,ident)).rowcount
            if changed!=1:raise LabError('RESEARCH_ALREADY_PROCESSED')
            c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(ident,now,'RESEARCHER','MANUAL_RETRY_FROZEN_CONFIG'))

    def list(self) -> list:
        with self.connect() as c:return [dict(r) for r in c.execute('select id,hypothesis,state,created,updated,error from queue order by created desc,id limit 32')]

    def get(self,ident:str) -> dict:
        with self.connect() as c:
            row=c.execute('select id,fingerprint,hypothesis,state,created,updated,case when length(config)<=65536 then config else null end config,case when length(result)<=? then result else null end result,length(result) result_bytes,error,attempt from queue where id=?',(COMPACT_LIMIT,ident)).fetchone()
            if not row:raise LabError('RESEARCH_NOT_FOUND')
            result=dict(row);blob=result.pop('result');size=result.pop('result_bytes');result['config']=decode(result['config'])
            if size is not None and size>COMPACT_LIMIT:bad()
            if result['state'] in ('REJECTED','NEEDS_VALIDATION') and not blob:bad()
            if type(result['config']) is not dict or digest(result['config'])!=result['fingerprint']:bad()
            if blob:
                if len(blob)>COMPACT_LIMIT:bad()
                manifest=checked_manifest(decode(blob))
                if manifest['config']!=result['config'] or manifest['auditor']['status']!=result['state']:bad()
                result['report']=manifest
            else:result['report']=None
            result['events']=list(reversed([dict(x) for x in c.execute('select seq,at,role,state from events where job_id=? order by seq desc limit 100',(ident,))]))
            result['event_total']=c.execute('select count(*) from events where job_id=?',(ident,)).fetchone()[0]
            return result

    def reserve(self,provider:str,model:str,amount:int,daily:int,total:int) -> str:
        now=int(self.clock());ident=uuid.uuid4().hex
        with self.connect() as c:
            c.execute('begin immediate')
            cost=c.execute('select coalesce(sum(reserved),0) from llm_calls').fetchone()[0]
            today=c.execute('select coalesce(sum(reserved),0) from llm_calls where at>=?',(now//86400*86400,)).fetchone()[0]
            if type(amount) is not int or amount<=0 or cost+amount>total or today+amount>daily:raise LabError('LLM_BUDGET_EXCEEDED')
            if c.execute('select count(*) from llm_calls').fetchone()[0]>=1000:raise LabError('LLM_BUDGET_EXCEEDED')
            c.execute('insert into llm_calls values(?,?,?,?,?,?,?)',(ident,now,provider,model,amount,'RESERVED',None))
        return ident

    def call_done(self,ident:str,state:str,usage:dict|None=None):
        with self.connect() as c:c.execute("update llm_calls set state=?,usage=? where id=? and state='RESERVED'",(state,canonical(usage or {}).decode(),ident))

    def calls(self) -> list:
        with self.connect() as c:return [dict(x,usage=json.loads(x['usage']) if x['usage'] else None) for x in c.execute('select * from llm_calls order by at desc limit 100')]

    def page(self,ident:str,run_key:str,kind:str,offset:int=0,limit:int=100) -> dict:
        if kind not in ARRAYS or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise LabError('INVALID_DATA')
        row=self.get(ident);report=row['report']
        if not report:raise LabError('RESEARCH_NOT_FOUND')
        run=next((r for r in report['runs'] if r['run_key']==run_key),None)
        if run is None:raise LabError('RESEARCH_NOT_FOUND')
        ref=run['artifacts'][kind];values=[]
        if offset<ref['records']:
            descriptor=next(d for d in ref['chunks'] if d['start']<=offset<d['start']+d['count'])
            with self.connect() as c:
                chunk=c.execute('select case when length(payload)<=? then payload else null end payload from chunks where job_id=? and attempt=? and run_key=? and kind=? and ordinal=?',(CHUNK_LIMIT+1024,ident,row['attempt'],run_key,kind,descriptor['ordinal'])).fetchone()
            if chunk is None or chunk['payload'] is None:bad()
            records=unpack_chunk(chunk['payload'],descriptor);left=offset-descriptor['start'];values=records[left:left+limit]
        return dict(id=ident,run_key=run_key,kind=kind,records=values,total=ref['records'],offset=offset,
            next_offset=offset+len(values) if offset+len(values)<ref['records'] else None,research_only=True)

    def materialize(self,ident:str) -> dict:
        # CLI-only reconstruction in the resource-limited child. No HTTP route.
        import hashlib
        from .artifacts import streamed_digest
        row=self.get(ident);compact=row['report']
        if compact is None:raise LabError('RESEARCH_NOT_FOUND')
        result={k:v for k,v in compact.items() if k not in ('storage_format','logical_report_checksum','checksum','runs')};runs=[]
        for run in compact['runs']:
            restored={k:v for k,v in run.items() if k not in ('artifacts','run_key')}
            for kind in ARRAYS:
                values=[];offset=0;h=hashlib.sha256()
                while offset<run['artifacts'][kind]['records']:
                    page=self.page(ident,run['run_key'],kind,offset);values.extend(page['records'])
                    for record in page['records']:h.update(canonical(record)+b'\n')
                    offset=page['next_offset'] or run['artifacts'][kind]['records']
                if h.hexdigest()!=run['artifacts'][kind]['sha256']:bad()
                restored[kind]=values
            runs.append(restored)
        result['runs']=runs
        if streamed_digest(result)!=compact['logical_report_checksum']:bad()
        result['checksum']=compact['logical_report_checksum'];return result

    def verify_chunks(self,ident:str):
        import hashlib
        report=self.get(ident)['report']
        if report is None:raise LabError('RESEARCH_NOT_FOUND')
        for run in report['runs']:
            for kind,ref in run['artifacts'].items():
                offset=0;h=hashlib.sha256()
                while offset<ref['records']:
                    page=self.page(ident,run['run_key'],kind,offset)
                    for record in page['records']:h.update(canonical(record)+b'\n')
                    offset=page['next_offset'] or ref['records']
                if h.hexdigest()!=ref['sha256']:bad()
        return dict(status='PASS',logical_report_checksum=report['logical_report_checksum'])

    def events(self,ident:str,after:int=0,limit:int=100):
        if type(after) is not int or not 0<=after<=9223372036854775807 or type(limit) is not int or not 1<=limit<=100:raise LabError('INVALID_DATA')
        self.get(ident)
        with self.connect() as c:rows=[dict(r) for r in c.execute('select seq,at,role,state from events where job_id=? and seq>? order by seq limit ?',(ident,after,limit))]
        return dict(id=ident,events=rows,next_after=rows[-1]['seq'] if rows else after,research_only=True)
