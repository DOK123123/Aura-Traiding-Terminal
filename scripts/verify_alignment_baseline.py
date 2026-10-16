"""Compare original production outputs against additive diagnostic changes offline."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PROGRAM=r'''
import json,sys
from bisect import bisect_left
from app.lab.models import digest
from app.lab.local_csv import load_binance_csv
from scripts.replay_auto42_verification import snapshot
from app.automated.strategy import strategy
bars,info=load_binance_csv(sys.argv[1]);times=[b.time for b in bars];end=bars[-1].time+900
def original(value):
    if isinstance(value,dict):return {k:original(v) for k,v in value.items() if k not in ('trend_indicators','alignment_inputs','timeframe_alignment')}
    if isinstance(value,list):return [original(v) for v in value]
    return value
out=[]
for at in (end-i*14400 for i in range(7)):
    start=at//14400*14400-4160*900;window=bars[bisect_left(times,start):bisect_left(times,at)]
    if not window or window[0].time!=start:raise ValueError('INSUFFICIENT_BASELINE_HISTORY')
    snap=snapshot(window,at);decision=strategy(snap,window,at+30)
    out.append(dict(closed_at=at,reason=decision['reason'],sha256=digest(dict(snapshot=original(snap),decision=original(decision)))))
print(json.dumps(dict(source_sha256=info['sha256'],cases=out)))
'''


def compare(csv: Path, baseline_root: Path) -> dict:
    current=Path(__file__).resolve().parents[1];values=[]
    for root in (baseline_root,current):
        result=subprocess.run([sys.executable,'-B','-c',PROGRAM,str(csv.resolve())],cwd=root,
            check=True,capture_output=True,text=True,timeout=60)
        values.append(json.loads(result.stdout))
    if values[0]!=values[1]:raise ValueError('BASELINE_OUTPUT_MISMATCH')
    return dict(status='PASS',baseline_commit=subprocess.run(['git','rev-parse','HEAD'],cwd=baseline_root,
        check=True,capture_output=True,text=True).stdout.strip(),**values[1],
        compared='ALL_ORIGINAL_SNAPSHOT_AND_STRATEGY_FIELDS_EXCLUDING_ONLY_ADDITIVE_DIAGNOSTICS',
        orders_submitted=0,live_autonomy='NOT_TESTED')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=compare(args.csv,args.baseline_root)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
