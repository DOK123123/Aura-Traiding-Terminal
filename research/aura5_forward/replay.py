"""Bounded pre-registered alternative audit. No optimization or account traffic."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
from app.hunter.engine import Prepared, FAMILIES
from app.hunter.store import MODEL_HASH
from app.hunter.outcomes import simulate
from research.hunter6.data import load, aggregate
from research.aura5_cost_audit.run import evaluate, metrics, T


def run(destination):
    raw=Path(__file__).with_name('protocol.json').read_bytes();protocol=json.loads(raw)
    base,funding,_=load();rows=aggregate(base,14400);plans=[];candidates=Counter();rejected=Counter()
    for i,b in enumerate(rows):
        if i<259:continue
        at=b[0]+14400
        if not T(protocol['splits'][0]['start'])<=at<T(protocol['splits'][-1]['end']):continue
        prepared=Prepared(rows[i-259:i+1],'4h')
        for family in FAMILIES:
            for variant in protocol['variants']:
                trace=[];accepted=prepared.plans(259,family,variant,cutoff=at,watch=False,audit=trace)
                candidates[(family,variant)]+=len(trace)
                rejected[(family,variant)]+=sum(r['rejection'] is not None for r in trace)
                for p in accepted:p['step']=14400
                plans.extend(accepted)
    output=[];results=[]
    for split in protocol['splits']:
        start,end=T(split['start']),T(split['end'])
        selected=[p for p in plans if start<=p['signal_time']<end]
        for multiplier in (1,1.5,2):
            # evaluate groups independently including variant; no pooled portfolio claims.
            for family in FAMILIES:
                for variant in protocol['variants']:
                    group=[p for p in selected if p['strategy']==family and p['variant']==variant]
                    rs=evaluate(group,rows,funding,simulate,multiplier,end)
                    for r in rs:r.update(split=split['name'],cost_multiplier=multiplier)
                    results.extend(rs)
                    for side in ('LONG','SHORT'):
                        subset=[r for r in rs if r['direction']==side]
                        output.append({'split':split['name'],'strategy':family,'variant':variant,'frame':'4h','direction':side,
                                       'cost_multiplier':multiplier,'signals_per_30_days':len(subset)/((end-start)/86400)*30,
                                       **metrics(subset)})
    summary={'protocol_sha256':hashlib.sha256(raw).hexdigest(),'model_sha256':MODEL_HASH,
             'untouched_holdout':False,'approved_for_confirmed':[],'status':'NO_EDGE_FOUND',
             'configuration_count':12,'threshold_search':0,'metrics':output,
             'candidates':[{'strategy':f,'variant':v,'candidates':candidates[f,v],'planning_rejected':rejected[f,v]} for f in FAMILIES for v in protocol['variants']],
             'orders':0,'warning':'All archive periods previously inspected. No selection/validation claim. Independent 1 BTC hypotheses, not portfolio returns.'}
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    (out/'alternatives.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    (out/'alternatives-outcomes.json.gz').write_bytes(gzip.compress(json.dumps(results,sort_keys=True,allow_nan=False).encode(),mtime=0))
    return summary

if __name__=='__main__':
    r=run(sys.argv[1]);print(json.dumps({k:v for k,v in r.items() if k!='metrics'}))
