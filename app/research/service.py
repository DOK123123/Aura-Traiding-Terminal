"""Agent Orchestrator: explicit manual dispatch only; no background scheduler."""
import asyncio
from pathlib import Path
from app.lab.models import LabError,digest
from .registry import registry,SOURCES,PROTOCOL
from .data import available,load_dataset
from .experiment import frozen_config,execute
from .storage import Store
from .llm import Advisor
from .published import summary as published_summary

class Service:
    def __init__(self,root:Path,*,store=None,advisor=None):
        self.store=store or Store(root);self.advisor=advisor or Advisor(self.store)

    async def overview(self) -> dict:
        queue,calls=await asyncio.gather(asyncio.to_thread(self.store.list),asyncio.to_thread(self.store.calls))
        active=any(q['state']=='RUNNING' for q in queue)
        hypotheses=registry()
        for row in reversed(queue):
            hypotheses[row['hypothesis']]['status']={'QUEUED':'RESEARCHING','RUNNING':'TESTING','ERROR':'NEEDS_VALIDATION'}.get(row['state'],row['state'])
        return dict(title='AURA AI RESEARCH LAB',research_only=True,activation_available=False,manual_only=True,
            llm=self.advisor.status(),agents=[
             dict(id='RESEARCHER',state='AI_NOT_CONFIGURED' if not self.advisor.status()['enabled'] else 'READY_ADVISORY_ONLY',deterministic='FROZEN_PROTOCOLS_AVAILABLE',capabilities=['curated hypotheses','optional LLM advisory proposal'],can_trade=False),
             dict(id='BACKTESTER',state='TESTING' if active else 'IDLE',capabilities=['existing Lab replay on isolated RAM ledgers'],can_trade=False),
             dict(id='AUDITOR',state='PENDING_BACKTEST' if active else 'IDLE',capabilities=['independent arithmetic','raw candle fills','data and causality checks','reject promotion'],can_trade=False)],
            registry=hypotheses,published=await asyncio.to_thread(published_summary),sources=SOURCES,dataset=available(),protocol=PROTOCOL,queue=queue,llm_calls=calls,
            persistence='DEDICATED_LOCAL_SQLITE; EPHEMERAL_ON_RENDER_UNLESS_DISK_PERSISTED; NO_SUPABASE')

    async def enqueue(self,name:str) -> dict:
        config=frozen_config(name,available());ident=await asyncio.to_thread(self.store.enqueue,config)
        return dict(id=ident,config_hash=digest(config),status='SAVED_FROZEN_PROTOCOL')

    async def run(self,ident:str) -> dict:
        claimed=await asyncio.to_thread(self.store.claim,ident)
        config=claimed['config'];attempt=claimed['attempt']
        def worker():
            try:
                bars,source=load_dataset();report=execute(config,bars,source);self.store.finish(ident,report,attempt=attempt)
            except Exception:
                self.store.finish(ident,None,'RESEARCH_FAILED_NO_PROMOTION',attempt=attempt)
                raise LabError('RESEARCH_RUN_FAILED') from None
            return self.store.get(ident)
        task=asyncio.create_task(asyncio.to_thread(worker))
        try:return self.summarize(await asyncio.shield(task))
        except asyncio.CancelledError:
            # No detached unbounded worker or silent automatic retry after disconnect.
            try:await task
            except Exception:pass
            raise

    @staticmethod
    def summarize(row:dict) -> dict:
        report=row.get('report')
        if report:
            row=dict(row,report={k:v for k,v in report.items() if k!='runs'})
            row['report']['runs']=[{k:v for k,v in run.items() if k not in ('trades','decisions','equity_curve','daily_equity')} for run in report['runs']]
        return row

    async def get(self,ident:str,export=False) -> dict:
        row=await asyncio.to_thread(self.store.get,ident)
        return row if export else self.summarize(row)
