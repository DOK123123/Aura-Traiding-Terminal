"""LOCAL TEST ONLY: synthetic closed 5m bars -> production Service/engine.

No Supabase/exchange clients, public endpoint or production portfolio access.
python -m scripts.verify_active43_bounce --output /tmp/bounce-report.json
"""
import argparse,asyncio,json,os,tempfile
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
from app.active43.core import SOURCE,validate
from app.active43.market import analyze
from app.active43.service import Service
from app.active43.strategies import config
from app.lab.models import Bar,digest
from scripts.verify_auto42_execution import check_accounting
from tests.test_active43 import MemoryStore


class BounceMarket:
    def __init__(self,side):
        self.side=side;self.step=300;self.at=1700000000//86400*86400;self.now=[self.at+30]
        self.bars=[Bar(self.at-(1000-i)*300,*map(D,('68000','68050','67950','68000','100'))) for i in range(1000)]
        self.failure=None;self.cache=None
    async def close(self):pass
    def add(self,phase):
        values={'touch':(68000,68010,67945,67980),'confirm':(67985,68080,67970,68060),
                'fill':(68060,68080,68040,68060),'update':(68060,68080,68040,68060),
                'TP':(68060,71000,68040,68060),'SL':(68060,68080,65000,68060),'BOTH':(68060,71000,65000,68060)}[phase]
        o,h,l,c=map(D,map(str,values))
        if self.side=='SHORT':o,h,l,c=D(136000)-o,D(136000)-l,D(136000)-h,D(136000)-c
        self.bars.append(Bar(self.at,o,h,l,c,D(100)));self.at+=300;self.now[0]=self.at+30
    async def snapshot(self,cfg):
        if self.failure:
            from app.automated.engine import DemoError
            raise DemoError(self.failure)
        decision=analyze(self.bars,cfg)
        decision.update(source=SOURCE,source_sha256=digest([b.data() for b in self.bars]))
        return self.bars,decision,self.now[0]


async def cycle(side,exit_kind):
    if os.getenv('RENDER') or not __debug__:raise ValueError('LOCAL_OFFLINE_ONLY')
    market=BounceMarket(side);cfg=config('SR_BOUNCE','5m');store=MemoryStore(cfg,market.now[0])
    service=Service(store,market,cfg,clock=lambda:market.now[0])
    with patch('app.active43.service.scheduler_configured',return_value=True):await service.control('START','d'*32,1)
    for phase in ('touch','confirm','fill'):
        market.add(phase);await service.tick()
    opened=deepcopy(store.state['position']);assert opened and opened['direction']==side
    # Durable temporary checkpoint models restart, never production storage.
    with tempfile.TemporaryDirectory(prefix='aura43-bounce-isolated-') as folder:
        checkpoint=Path(folder)/'checkpoint.json'
        checkpoint.write_text(json.dumps(dict(state=store.state,revision=store.revision,events=store.events)))
        await service.close();saved=json.loads(checkpoint.read_text());validate(saved['state'])
        restored=MemoryStore(cfg,market.now[0]);restored.state=saved['state'];restored.revision=saved['revision'];restored.events=saved['events']
        service=Service(restored,market,cfg,clock=lambda:market.now[0]);store=restored
        duplicate=await service.tick();assert duplicate['duplicate']
        market.add('update');await service.tick()
        market.add(exit_kind);await service.tick();await service.tick()
    closed=[e['payload'] for e in store.events if e['kind']=='CLOSE']
    assert len(closed)==1 and len([e for e in store.events if e['kind']=='OPEN'])==1
    check_accounting(opened,closed[0],store.state)
    assert store.state['position'] is None and not (await service.dashboard())['production_paper_verified']
    await service.close()
    return dict(direction=side,case=exit_kind,open=opened,close=closed[0],final_balance=store.state['balance'],
                open_count=1,close_count=1,restart_restored=True,duplicate_guard=True,independent_accounting=True)


def run(output):
    if os.getenv('RENDER') or not __debug__:raise ValueError('LOCAL_OFFLINE_ONLY')
    output=Path(output)
    if output.exists():raise ValueError('New output required')
    async def execute():return [await cycle(side,kind) for side in ('LONG','SHORT') for kind in ('TP','SL','BOTH')]
    result=dict(status='PASS',scope='TEST_ONLY_SYNTHETIC_LOCAL_MEMORY_AND_TEMP_CHECKPOINT',
        production_paper_verified=False,production_writes=False,real_orders=False,cases=asyncio.run(execute()))
    output.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.output);print(json.dumps(dict(status=report['status'],cases=len(report['cases']),production_paper_verified=False)))
