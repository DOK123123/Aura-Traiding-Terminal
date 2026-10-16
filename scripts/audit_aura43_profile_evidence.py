"""Additional real-data causality/native equivalence audit. Offline, no accounts."""
import argparse
from bisect import bisect_left
from dataclasses import replace
import gzip
import json
from pathlib import Path
from app.lab.models import digest
from app.lab.adaptive43 import choose
from app.lab.adaptive43_profiles import PROFILES,propose
from scripts.aura43_history import load_history
from scripts.aura43_profile_context import snapshot as projected
from scripts.replay_auto42_verification import PrefixCache,snapshot
from scripts.research_aura43_profiles import code_hashes,PROTOCOL,read_checkpoint,eligible

def audit(report_path,csv,checkpoint):
    report=json.loads(gzip.decompress(report_path.read_bytes()));bars,info=load_history(csv)
    assert report['source']['sha256']==info['sha256'] and report['code_hashes']==code_hashes()
    fingerprint=digest(dict(data=info['sha256'],code=code_hashes(),protocol=PROTOCOL))
    rows,filters=read_checkpoint(checkpoint,fingerprint,report['start'],report['end_exclusive'])
    assert len(rows)==17568 and dict(filters)==report['filter_counts']
    for row in rows:
        a=row['original'];b=choose(row['profiles']['Conservative'])
        for key in ('direction','signal_at','stop_loss','take_profit'):
            assert a.get(key)==b.get(key),(row['closed_at'],key)
    # Check complete native snapshots at every 15m phase, in a real development
    # window and in a real validation window. Expected from unchanged production.
    times=[b.time for b in bars];checked=0
    for base in (report['start']+10*86400,report['split_at']//14400*14400+10*86400):
        first=bisect_left(times,base-4160*900);full=bars[first:first+4175];cache=PrefixCache(full)
        with cache.installed():
            for n in range(4160,4176):
                window=full[:n];at=window[-1].time+900;a=snapshot(window,at);b=projected(cache,window,at)
                for key in b:
                    assert b[key]==(a[key] if key!='history' else dict(source_sha256=a['history']['source_sha256'])),key
                checked+=1
        window=full[:4161]
        changed=window+[replace(b,open=b.open*2,high=b.high*2,low=b.low*2,close=b.close*2) for b in full[4161:]]
        at=window[-1].time+900;a=projected(cache,window,at);b=projected(PrefixCache(changed),window,at)
        assert a==b
        for p in PROFILES:assert propose(a,window,p)==propose(b,window,p)
    dev=[r for r in report['runs'] if r['split']=='development' and r['variant'] in PROFILES and eligible(r)]
    winner=max(dev,key=lambda r:float(r['metrics']['expectancy']))['variant'] if dev else None
    assert report['development_selection']['winner']==winner
    assert digest(report['development_selection'])==report['selection_hash']
    return dict(status='PASS',source_sha256=info['sha256'],closed_decisions=17568,
        conservative_original_signal_sl_tp_equal=True,native_projection_real_cutoffs_checked=checked,
        future_price_perturbation_prefix_invariance=True,selection_from_development_only=True,
        production_access=False,proves_live_execution=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);p.add_argument('--csv',required=True,type=Path)
    p.add_argument('--checkpoint',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if not __debug__:raise RuntimeError('ASSERTIONS_REQUIRED')
    result=audit(a.report,a.csv,a.checkpoint);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
