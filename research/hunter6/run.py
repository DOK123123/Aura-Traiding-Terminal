"""Six-family research with chronology, sealed selection and explicitly reused final holdout."""
import datetime as dt
import gzip
import hashlib
import json
from bisect import bisect_left,bisect_right
from pathlib import Path
import sys

from app.hunter.engine import Prepared,FAMILIES,RULES
from app.hunter.outcomes import simulate
from app.hunter.store import MODEL_HASH
from .data import load,aggregate,audit
from .statistics import group_summary,eligible,closed

P=json.loads(Path(__file__).with_name('protocol.json').read_text())
T=lambda s:int(dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())


def evaluate(prepared,plans,start,end,funding,cost):
    times=prepared.time.tolist();fundtimes=[r[0] for r in funding];busy={};trades=[]
    for p in plans:
        if not start<=p['signal_time']<end:continue
        key=(p['strategy'],p['variant'],p['direction'])
        if p['signal_time']<busy.get(key,0):
            trades.append({**p,'outcome':'OVERLAP','entered':False,'r':None,'pnl_usdt':None,'note':'ONE_HYPOTHESIS_PER_GROUP'});continue
        first=bisect_left(times,p['signal_time']);stop=min(bisect_left(times,end),first+p['hold_bars'])
        rates=funding[bisect_left(fundtimes,p['signal_time']):bisect_right(fundtimes,p['signal_time']+(p['hold_bars']+1)*p['step'])]
        result=simulate(p,prepared.rows[first:stop],rates,multiplier=cost)
        if result['entered']:busy[key]=result['last_time']+p['step']
        trades.append(result)
    return trades


def main(out='docs/aura6',folder='data/hunter6'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    base,funding,acquisition=load(folder);quality=audit(base,funding,acquisition)
    (out/'DATA_AUDIT.json').write_text(json.dumps(quality,indent=2))
    results=[];alltrades=[];walk=[];selection=[]
    start=T(P['splits'][0]['start']);end=T(P['splits'][-1]['end'])
    for frame,step in P['frames'].items():
        rows=aggregate(base,step);prepared=Prepared(rows,frame);plans=[]
        for family in FAMILIES:
            for index in prepared.candidate_indices(family):
                i=int(index)
                if not start<=int(prepared.time[i])+step<end:continue
                for variant in P['variants']:
                    for p in prepared.plans(i,family,variant,cutoff=int(prepared.time[i])+step):plans.append({**p,'step':step})
        plans.sort(key=lambda p:(p['signal_time'],p['id']))
        print(json.dumps({'frame':frame,'candles':len(rows),'technical_plans':len(plans)}),flush=True)
        # Train and validation are evaluated and selection frozen before test/final are opened.
        for stage in P['splits'][:2]:
            for cost in P['costs']['multipliers']:
                trades=evaluate(prepared,plans,T(stage['start']),T(stage['end']),funding,cost)
                for family in FAMILIES:
                    for variant in P['variants']:
                        for side in ['LONG','SHORT']:
                            ts=[t for t in trades if (t['strategy'],t['variant'],t['direction'])==(family,variant,side)]
                            metrics=group_summary(ts,T(stage['start']),T(stage['end']),f'{frame}:{family}:{variant}:{side}:{stage["name"]}:{cost}')
                            results.append({'frame':frame,'strategy':family,'variant':variant,'side':side,'stage':stage['name'],'cost':cost,**metrics})
                alltrades.append({'frame':frame,'stage':stage['name'],'cost':cost,'trades':trades})
        chosen=[]
        for family in FAMILIES:
            for variant in P['variants']:
                for side in ['LONG','SHORT']:
                    r=[x for x in results if (x['frame'],x['strategy'],x['variant'],x['side'])==(frame,family,variant,side)]
                    tr=next(x for x in r if x['stage']=='train' and x['cost']==1);val=next(x for x in r if x['stage']=='validation' and x['cost']==1)
                    stress=[x for x in r if x['cost']==2]
                    accepted=eligible(tr,100) and eligible(val,50) and all(x['expectancy_R'] is not None and x['expectancy_R']>0 for x in stress)
                    chosen.append({'frame':frame,'strategy':family,'variant':variant,'side':side,'cost_model_screen_passed':accepted,'selected_before_test':accepted and tr['modeled_funding_settlements']==0 and val['modeled_funding_settlements']==0,
                                   'basis':'TRAIN_VALIDATION_ONLY','score':val['uncertainty']['expectancy_R'][0] if val['uncertainty']['expectancy_R'] else None})
        selection.extend(chosen)
        (out/('selection-'+frame+'.json')).write_text(json.dumps({'model_sha256':MODEL_HASH,'candidates':chosen,'sealed_before_test':True,'sealed_before_final':True},indent=2))
        for stage in P['splits'][2:]:
            for cost in P['costs']['multipliers']:
                trades=evaluate(prepared,plans,T(stage['start']),T(stage['end']),funding,cost)
                for family in FAMILIES:
                    for variant in P['variants']:
                        for side in ['LONG','SHORT']:
                            ts=[t for t in trades if (t['strategy'],t['variant'],t['direction'])==(family,variant,side)]
                            metrics=group_summary(ts,T(stage['start']),T(stage['end']),f'{frame}:{family}:{variant}:{side}:{stage["name"]}:{cost}')
                            results.append({'frame':frame,'strategy':family,'variant':variant,'side':side,'stage':stage['name'],'cost':cost,**metrics})
                alltrades.append({'frame':frame,'stage':stage['name'],'cost':cost,'trades':trades})
        # Frozen-rule expanding walk-forward: purged train, independent no-carry quarterly blocks.
        boundaries=[T(x+'T00:00:00Z') for x in ['2023-10-01','2024-01-01','2024-04-01','2024-07-01','2024-10-01','2025-01-01','2025-04-01','2025-07-01','2025-10-01']]
        for left,right in zip(boundaries,boundaries[1:]):
            train_end=left-49*step
            train=evaluate(prepared,plans,start,train_end,funding,1)
            test=evaluate(prepared,plans,left,right,funding,1)
            for family in FAMILIES:
                for variant in P['variants']:
                    for side in ['LONG','SHORT']:
                        key=(family,variant,side);ts=[t for t in train if (t['strategy'],t['variant'],t['direction'])==key];te=[t for t in test if (t['strategy'],t['variant'],t['direction'])==key]
                        m=group_summary(ts,start,train_end,f'WFTRAIN:{frame}:{key}:{left}')
                        walk.append({'frame':frame,'strategy':family,'variant':variant,'side':side,'train_end':train_end,'test_start':left,'test_end':right,
                                     'eligible_prior_only':eligible(m,100),'train_closed':m['closed'],'test':group_summary(te,left,right,f'WFTEST:{frame}:{key}:{left}')})
    candidates=[];model_candidates=[]
    for c in selection:
        if not c['cost_model_screen_passed']:continue
        matching=[r for r in results if all(r[k]==c[k] for k in ['frame','strategy','variant','side'])]
        test=next(x for x in matching if x['stage']=='test' and x['cost']==1)
        stress=[r for r in matching if r['stage'] in ('test','final') and r['cost']==2]
        if eligible(test,50) and all(r['expectancy_R'] is not None and r['expectancy_R']>0 for r in stress):
            model_candidates.append({**c,'status':'MODELED_FUNDING_RESEARCH_ONLY'})
            if c['selected_before_test'] and not any(r['modeled_funding_settlements'] for r in stress):candidates.append({**c,'status':'FORWARD_RESEARCH_ONLY_NOT_VALIDATED'})
    summary={'version':P['version'],'model_sha256':MODEL_HASH,'protocol_sha256':hashlib.sha256(Path(__file__).with_name('protocol.json').read_bytes()).hexdigest(),
             'data_audit':quality,'selection':selection,'cost_model_candidates':model_candidates,'forward_candidates':candidates,'verdict':'FORWARD_RESEARCH_CANDIDATES_UNVALIDATED' if candidates else 'NO_EDGE_FOUND',
             'independent_oos':False,'funding_complete':quality['funding_coverage_complete'],'approved_for_confirmed':[],
             'results':results,'walk_forward':walk,'source':'BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2','probabilities':None}
    (out/'summary.json.gz').write_bytes(gzip.compress(json.dumps(summary,separators=(',',':')).encode(),mtime=0))
    (out/'trades.json.gz').write_bytes(gzip.compress(json.dumps(alltrades,separators=(',',':')).encode(),mtime=0))
    from .report import write
    write(summary,out)
    print(json.dumps({'verdict':summary['verdict'],'forward_candidates':candidates,'groups':len(results),'walk_forward':len(walk)}),flush=True)


if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'docs/aura6',sys.argv[2] if len(sys.argv)>2 else 'data/hunter6')
