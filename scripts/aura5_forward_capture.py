"""Bounded public Bitget forward capture; no account keys, orders or daemon claims."""
import argparse
import asyncio
import gzip
import json
from pathlib import Path
import time

from app.hunter.main import Hunter
from app.hunter.market import PublicMarket, STEPS
from app.hunter.store import Store, MODEL_HASH
from research.hunter6.forward import audit_page


async def capture(destination: Path, seconds: int):
    if not 1<=seconds<=172800:raise ValueError('DURATION_OUT_OF_RANGE')
    destination.mkdir(parents=True,exist_ok=False)
    store=Store(destination/'observer.sqlite');market=PublicMarket()
    h=Hunter(store,market,{'approved':[]});started=time.time();deadline=time.monotonic()+seconds
    samples=[]
    try:
        while time.monotonic()<deadline:
            try:
                async with asyncio.timeout(min(45,max(.01,deadline-time.monotonic()))):await h.cycle()
            except TimeoutError:
                h.quotes.clear();h.error='BOUNDED_CAPTURE_TIMEOUT'
            at=time.time()
            state=store.snapshot(at,dict(h.quotes),h.error)
            samples.append({'at':at,'error':h.error,'frame_errors':dict(h.frame_errors),
                            'quotes':state['quotes'],'fresh_frames':state['fresh_frames'],'state':state['state']})
            # Checkpoint after every cycle. No successful 24/48h claim on crash.
            (destination/'progress.json').write_text(json.dumps({'started_at':started,'last_at':at,'cycles':h.cycles,'completed':False}))
            remaining=deadline-time.monotonic()
            if remaining>0:await asyncio.sleep(min(5,remaining))
    finally:
        await market.close()
        ended=time.time();audits=[]
        for frame in STEPS:
            after=0;page_number=0
            while True:
                page=store.export_inputs(frame,after,100);audits.append(audit_page(page))
                (destination/f'inputs-{frame}-{page_number}.json.gz').write_bytes(gzip.compress(json.dumps(page,allow_nan=False).encode(),mtime=0))
                if not page['has_more']:break
                after=page['next_after'];page_number+=1
        snapshot=store.snapshot(ended,dict(h.quotes),h.error)
        summary={'scope':'AURA5_PUBLIC_FORWARD_LOCAL_NOT_HOSTED','model_sha256':MODEL_HASH,
                 'started_at':started,'ended_at':ended,'elapsed_seconds':ended-started,'requested_seconds':seconds,
                 'cycles':h.cycles,'samples':samples,'input_audits':audits,'diagnostics':store.diagnostics(ended,48),
                 'records':snapshot['records'],'confirmed':0,'orders':0,'approved_for_confirmed':[],
                 'continuous_24_48h_pass':False,'physical_audio_verified':False,'telegram_verified':False}
        (destination/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path);parser.add_argument('--seconds',type=int,default=300)
    args=parser.parse_args();r=asyncio.run(capture(args.destination,args.seconds))
    print(json.dumps({k:r[k] for k in ('scope','elapsed_seconds','cycles','orders','continuous_24_48h_pass')}))
