"""Light web facade: never dispatches a process/thread/backtest. Manual external runner only."""
import asyncio
from pathlib import Path
from app.lab.models import LabError,digest
from .registry import registry,SOURCES,PROTOCOL
from .data import available
from .experiment import frozen_config
from .llm import Advisor
from .published import summary as published_summary

class Service:
    def __init__(self,root:Path,*,store=None,advisor=None,writable=False):
        self.store=store;self.writable=writable;self.advisor=advisor or (Advisor(store) if store and writable else None)

    def require_write(self):
        if not self.writable:raise LabError('RESEARCH_READ_ONLY')
        if self.store is None:raise LabError('RESEARCH_STORAGE_NOT_CONFIGURED')

    async def overview(self) -> dict:
        queue,calls=await asyncio.gather(asyncio.to_thread(self.store.list),asyncio.to_thread(self.store.calls)) if self.store else ([],[])
        active=any(q['state']=='RUNNING' for q in queue);hypotheses=registry()
        for row in reversed(queue):hypotheses[row['hypothesis']]['status']={'QUEUED':'RESEARCHING','RUNNING':'TESTING','ERROR':'NEEDS_VALIDATION'}.get(row['state'],row['state'])
        ai=self.advisor.status() if self.advisor else dict(status='AI_NOT_CONFIGURED',enabled=False)
        return dict(title='AURA AI RESEARCH LAB',research_only=True,activation_available=False,manual_only=True,llm=ai,
            writable=self.writable,runner='EXTERNAL_MANUAL_CLI_ONLY; HTTP_NEVER_DISPATCHES',
            agents=[dict(id='RESEARCHER',state=ai['status'],capabilities=['curated protocols','optional advisory in isolated workbench'],can_trade=False),
             dict(id='BACKTESTER',state='EXTERNAL_WORKER_RUNNING' if active else 'IDLE',capabilities=['external manual resource-limited runner'],can_trade=False),
             dict(id='AUDITOR',state='EXTERNAL_WORKER_ONLY' if active else 'IDLE',capabilities=['independent deterministic audit'],can_trade=False)],
            registry=hypotheses,published=await asyncio.to_thread(published_summary),sources=SOURCES,dataset=available(),protocol=PROTOCOL,queue=queue,llm_calls=calls,
            persistence=('OWNER_REVIEWED_GIT_SNAPSHOT' if hasattr(self.store,'index') else 'EXTERNAL_DURABLE_SQLITE_CONFIGURED') if self.store else 'RESEARCH_STORAGE_NOT_CONFIGURED; PUBLISHED_RESULTS_ONLY')

    async def enqueue(self,name:str) -> dict:
        self.require_write();config=frozen_config(name,available());ident=await asyncio.to_thread(self.store.enqueue,config)
        return dict(id=ident,config_hash=digest(config),status='QUEUED_EXTERNAL_RUNNER_REQUIRED')

    async def run(self,ident:str) -> dict:
        # Compatibility route now returns instructions; does NOT claim or execute.
        self.require_write();row=await asyncio.to_thread(self.store.get,ident)
        if row['state']!='QUEUED':raise LabError('RESEARCH_ALREADY_PROCESSED')
        return dict(id=ident,state='QUEUED',status='EXTERNAL_RUNNER_REQUIRED',executed=False)

    async def get(self,ident:str,export=False) -> dict:
        if self.store is None:raise LabError('RESEARCH_STORAGE_NOT_CONFIGURED')
        row=await asyncio.to_thread(self.store.get,ident)
        if export:row['export_format']='CHUNKED_MANIFEST_V2; ARRAYS_VIA_OWNER_PAGINATION_OR_CLI_BACKUP'
        return row

    async def page(self,ident,run_key,kind,offset,limit):
        if self.store is None:raise LabError('RESEARCH_STORAGE_NOT_CONFIGURED')
        return await asyncio.to_thread(self.store.page,ident,run_key,kind,offset,limit)

    async def propose(self):
        self.require_write()
        if not self.advisor:raise LabError('AI_NOT_CONFIGURED')
        return await self.advisor.propose()
