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

APP_ID=0x41524c31
MAX_RAW=32*1024*1024

class Store:
    def __init__(self,root:Path,clock=time.time):
        self.root=Path(root).resolve();self.path=self.root/'.data/ai-research/ai-research-v1.sqlite3';self.clock=clock
        self._safe_path();self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            with self.connect() as c:
                if c.execute('pragma application_id').fetchone()[0]!=APP_ID:raise LabError('RESEARCH_STORAGE_CONFLICT')
        else:
            # Exclusive creation prevents adopting an unrelated database in a race.
            try:
                with self.path.open('xb'):pass
            except FileExistsError:raise LabError('RESEARCH_STORAGE_CONFLICT') from None
            with sqlite3.connect(self.path) as c:
                c.execute(f'pragma application_id={APP_ID}')
                c.executescript('''
                 create table queue(id text primary key, fingerprint text unique not null, hypothesis text not null, state text not null, created integer not null, updated integer not null, config text not null, result blob, error text, attempt text);
                 create table events(seq integer primary key, job_id text not null, at integer not null, role text not null, state text not null);
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
        if self.path.exists() and (self.path.stat().st_nlink!=1 or self.path.stat().st_size>128*1024*1024):raise LabError('RESEARCH_STORAGE_CONFLICT')

    @contextmanager
    def connect(self):
        self._safe_path()
        c=sqlite3.connect(self.path,timeout=5);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()

    def enqueue(self,config:dict) -> str:
        now=int(self.clock());fp=digest(config);ident=uuid.uuid4().hex
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
            row=c.execute('select * from queue where id=?',(ident,)).fetchone()
            if not row:raise LabError('RESEARCH_NOT_FOUND')
            if row['state']!='QUEUED':raise LabError('RESEARCH_ALREADY_PROCESSED')
            if c.execute("select 1 from queue where state='RUNNING'").fetchone():raise LabError('BUSY')
            now=int(self.clock());attempt=uuid.uuid4().hex
            c.execute("update queue set state='RUNNING',updated=?,attempt=? where id=?",(now,attempt,ident))
            c.execute('insert into events(job_id,at,role,state) values(?,?,?,?)',(ident,now,'BACKTESTER','TESTING'))
            return dict(config=json.loads(row['config']),attempt=attempt)

    def finish(self,ident:str,result:dict|None,error:str|None=None,*,attempt:str):
        blob=None
        if result is not None:
            raw=canonical(result)
            if len(raw)>MAX_RAW:raise LabError('RESULT_LIMIT')
            blob=gzip.compress(raw,mtime=0)
            if len(blob)>8*1024*1024:raise LabError('RESULT_LIMIT')
        with self.connect() as c:
            c.execute('begin immediate');now=int(self.clock())
            status='ERROR' if error else result['auditor']['status']
            count=c.execute("update queue set state=?,updated=?,result=?,error=? where id=? and state='RUNNING' and attempt=?",(status,now,blob,error,ident,attempt)).rowcount
            if count!=1:raise LabError('RESEARCH_ALREADY_PROCESSED')
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
            row=c.execute('select * from queue where id=?',(ident,)).fetchone()
            if not row:raise LabError('RESEARCH_NOT_FOUND')
            result=dict(row);blob=result.pop('result');result['config']=json.loads(result['config'])
            if blob:
                import io
                with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:raw=stream.read(MAX_RAW+1)
                if len(raw)>MAX_RAW:raise LabError('RESEARCH_INTEGRITY')
                report=json.loads(raw);checksum=report.pop('checksum',None)
                if digest(report)!=checksum:raise LabError('RESEARCH_INTEGRITY')
                report['checksum']=checksum;result['report']=report
            else:result['report']=None
            result['events']=[dict(x) for x in c.execute('select at,role,state from events where job_id=? order by seq',(ident,))]
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
