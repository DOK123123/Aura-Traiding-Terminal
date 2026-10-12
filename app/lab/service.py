"""Bounded one-at-a-time research jobs with immutable snapshot replay."""
import asyncio
import os
from pathlib import Path
import time

from .models import Baseline,LabError,digest,STEPS
from .data import Loader
from .experiment import execute,summary,software_hash
from .storage import Store


class Service:
    def __init__(self,root,page,clock=time.time):
        root=Path(root);self.clock=clock;self.loader=Loader(page,clock);self.lock=asyncio.Lock();self.read_lock=asyncio.Lock()
        paper=Path(os.getenv('PAPER_DB_PATH',str(root/'.data/paper.sqlite3')))
        self.store=Store(Path(os.getenv('LAB_DB_PATH',str(root/'.data/strategy-lab.sqlite3'))),forbidden=(paper,root/'.cache/patterns.sqlite3'))

    async def compute(self,snapshot,config):
        task=asyncio.create_task(asyncio.to_thread(execute,snapshot,config,time.monotonic()+30))
        try:return await asyncio.shield(task)
        except asyncio.CancelledError:
            # The lock is held until the bounded worker actually exits; no unbounded detached CPU tasks.
            try:await task
            except Exception:pass
            raise

    async def run(self,body):
        if self.lock.locked():raise LabError('BUSY')
        async with self.lock:
            end=body.get('end')
            if end is None:end=int(self.clock())//14400*14400
            start=body.get('start')
            if start is None:start=end-body['days']*86400
            config=Baseline(development_pct=body['development_pct'],fee_bps=body['fee_bps'],slippage_bps=body['slippage_bps'])
            config.validate()
            snapshot=await self.loader.fetch(start,end)
            report=await self.compute(snapshot,config)
            ident=await asyncio.to_thread(self.store.save,snapshot,config.data(),report)
            return dict(id=ident,**summary(report))

    async def _load(self,ident):
        if self.read_lock.locked():raise LabError('BUSY')
        async with self.read_lock:
            task=asyncio.create_task(asyncio.to_thread(self.store.load,ident))
            try:return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:await task
                except Exception:pass
                raise

    async def get(self,ident):
        _,_,report=await self._load(ident)
        return dict(id=ident,**summary(report))

    async def replay(self,ident):
        if self.lock.locked():raise LabError('BUSY')
        async with self.lock:
            snapshot,config,original=await self._load(ident)
            if original['software_hash']!=software_hash():raise LabError('SOFTWARE_MISMATCH')
            report=await self.compute(snapshot,Baseline(**config))
            if digest(report)!=digest(original):raise LabError('REPRODUCIBILITY_ERROR')
            return dict(id=ident,replay_identical=True,**summary(report))

    async def detail(self,ident,timeframe,split,strategy,offset,limit):
        _,_,report=await self._load(ident)
        row=next((r for r in report['runs'] if (r['timeframe'],r['split'],r['strategy'])==(timeframe,split,strategy)),None)
        if row is None:raise LabError('INVALID_DATA')
        curve=row['equity_curve'];n=len(curve)
        indices={0,n-1} if n else set()
        if n:
            indices.update(i*(n-1)//299 for i in range(300))
            # Extrema are always shown, even when not on the regular sampled grid.
            from decimal import Decimal
            indices.add(max(range(n),key=lambda i:Decimal(curve[i]['equity'])))
            indices.add(min(range(n),key=lambda i:Decimal(curve[i]['equity'])))
        return dict(**{k:v for k,v in row.items() if k not in ('trades','equity_curve')},
                    trades=row['trades'][offset:offset+limit],trade_total=len(row['trades']),offset=offset,limit=limit,
                    has_more=offset+limit<len(row['trades']),equity_curve=[curve[i] for i in sorted(indices)],curve_total=n,
                    curve_display='Sampled <=302 points including endpoints and extrema; full curve in experiment export.')

    async def export(self,ident):
        snapshot,config,report=await self._load(ident)
        return dict(id=ident,snapshot=snapshot,config=config,report=report)
