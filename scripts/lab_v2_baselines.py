"""Exact native Aura baselines on annual history; offline bounded checkpoints."""
import argparse
from bisect import bisect_left
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import os
import time
from app.lab.models import digest,canonical
from app.lab.adaptive43 import propose,choose
from app.lab.indicators import rsi
from app.automated.strategy import strategy
from scripts import replay_auto42_verification as native
from scripts.aura43_profile_context import snapshot
from scripts.aura43_history import load_history
from scripts.research_aura43 import compact,FILES as ORIGINAL_FILES

ROOT=Path(__file__).resolve().parents[1]
FILES=ORIGINAL_FILES+('scripts/replay_auto42_verification.py','scripts/aura43_profile_context.py','scripts/aura43_history.py','scripts/lab_v2_baselines.py')
def code_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
def init_worker(path):
    native._BARS,_=load_history(path);native._TIMES=[b.time for b in native._BARS]
def analyze_group(job):
    first,last=job;start=first//14400*14400-4160*900;left=bisect_left(native._TIMES,start)
    full=native._BARS[left:bisect_left(native._TIMES,last)]
    if not full or full[0].time!=start:raise ValueError('WARMUP')
    cache=native.PrefixCache(full);rs=rsi([float(b.close) for b in full]);result=[]
    for at in range(first,last+1,900):
        w=full[:bisect_left(native._TIMES,at)-left];s=snapshot(cache,w,at)
        result.append(dict(closed_at=at,decision=compact(strategy(s,w,at+30)),original=compact(choose(propose(s,w,rsi_history=rs[:len(w)])))))
    return result

def read_checkpoint(path,fingerprint,start,end):
    if path.stat().st_size>8*1024*1024:raise ValueError('CHECKPOINT_LIMIT')
    with gzip.open(path,'rb') as f:raw=f.read(40*1024*1024+1)
    if len(raw)>40*1024*1024:raise ValueError('CHECKPOINT_LIMIT')
    lines=raw.splitlines()
    if json.loads(lines[0])!={'fingerprint':fingerprint}:raise ValueError('CHECKPOINT_IDENTITY')
    rows=[];expected=start+900
    for line in lines[1:]:
        block=json.loads(line)
        if not isinstance(block,list) or not 1<=len(block)<=16:raise ValueError('CHECKPOINT_BLOCK')
        for r in block:
            if r.get('closed_at')!=expected or expected>end or not isinstance(r.get('decision'),dict) or not isinstance(r.get('original'),dict):raise ValueError('CHECKPOINT_SEQUENCE')
            rows.append(r);expected+=900
    return rows

def validated_seed(bars,path):
    # Optional acceleration only. Reproduction without the local seed recomputes
    # every native window. Compare entire seed CSV against matching annual bars.
    from scripts import research_aura43_profiles as old
    seed_csv=ROOT/'docs/data/AURA43_PROFILES_BTCUSDT_15m.csv.gz'
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='lab-v2-seed-') as folder:
        csv=Path(folder)/'seed.csv';csv.write_bytes(gzip.decompress(seed_csv.read_bytes()));seed,info=load_history(csv)
    mapping={b.time:b for b in bars}
    if any(mapping.get(b.time)!=b for b in seed):raise ValueError('SEED_DATA_MISMATCH')
    report=json.loads(gzip.decompress((ROOT/'docs/AURA43_PROFILES_COMPARISON.json.gz').read_bytes()))
    if old.code_hashes()!=report['code_hashes'] or info['sha256']!=report['source']['sha256']:raise ValueError('SEED_CODE_MISMATCH')
    fp=digest(dict(data=info['sha256'],code=old.code_hashes(),protocol=old.PROTOCOL))
    rows,_=old.read_checkpoint(path,fp,report['start'],report['end_exclusive'])
    return {r['closed_at']:dict(closed_at=r['closed_at'],decision=r['decision'],original=r['original']) for r in rows}

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--seed-checkpoint',type=Path);p.add_argument('--max-seconds',type=int,default=1800);a=p.parse_args(argv)
    if not 30<=a.max_seconds<=3600:p.error('max-seconds 30..3600')
    bars,source=load_history(a.csv);protocol=json.loads((ROOT/'docs/STRATEGY_LAB_V2_PROTOCOL.json').read_text())
    stamp=lambda k:int(datetime.fromisoformat(protocol[k].replace('Z','+00:00')).timestamp());start=stamp('start_utc');end=stamp('end_exclusive_utc')
    if bars[0].time!=start-4160*900 or bars[-1].time+900!=end:raise ValueError('COVERAGE')
    fp=digest(dict(data=source['sha256'],code=code_hashes(),start=start,end=end));rows=[]
    if a.output.exists():rows=read_checkpoint(a.output,fp,start,end)
    else:a.output.write_bytes(gzip.compress(canonical(dict(fingerprint=fp))+b'\n',mtime=0))
    seeds=validated_seed(bars,a.seed_checkpoint) if a.seed_checkpoint else {};first=rows[-1]['closed_at']+900 if rows else start+900;jobs=[]
    while first<=end:
        last=min(end,(first//14400+1)*14400-900);jobs.append((first,last));first=last+900
    began=time.monotonic()
    with ProcessPoolExecutor(max_workers=2,initializer=init_worker,initargs=(str(a.csv),)) as pool:
        queue=deque();iterator=iter(jobs)
        def submit(job):
            first,last=job
            if all(at in seeds for at in range(first,last+1,900)):return [seeds[at] for at in range(first,last+1,900)]
            return pool.submit(analyze_group,job)
        for _ in range(2):
            job=next(iterator,None)
            if job:queue.append(submit(job))
        while queue:
            value=queue.popleft();block=value if isinstance(value,list) else value.result()
            with a.output.open('ab') as f:f.write(gzip.compress(canonical(block)+b'\n',mtime=0));f.flush();os.fsync(f.fileno())
            rows.extend(block)
            if len(rows)%768<16:print('native closed candles',len(rows),'/',(end-start)//900,flush=True)
            if time.monotonic()-began>a.max_seconds:
                print('BUDGET_REACHED: resume exact command',flush=True);return
            job=next(iterator,None)
            if job:queue.append(submit(job))
    assert len(rows)==(end-start)//900
    print('NATIVE_BASELINES_COMPLETE',len(rows),fp,flush=True)

if __name__=='__main__':main()
