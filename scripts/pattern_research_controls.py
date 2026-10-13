"""Frozen offline controls and anchored walk-forward; no parameter optimisation."""
import argparse
from collections import Counter
from dataclasses import replace
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.models import Bar,Baseline,digest
from app.lab.strategies import decisions
from scripts.pattern_research import (period_run,side_for,stamp,PERIODS,STEPS,
    atomic_json,write_artifact,blocked_bootstrap)
from scripts.run_pattern_research import artifact_read,summary
from scripts.offline_fixed_strategies import buy_hold


def control_rows(prepared,kind,start,end,reference=None,seed=20261013):
    """Signals use only causal prices. Random comparator conditions on event count."""
    result=[];rng=random.Random(seed)
    for part,rows in prepared:
        eligible=[i for i,r in enumerate(rows) if r is not None and start<=part[i].time<end]
        sides={}
        if kind=='RANDOM_MATCHED':
            n=sum(side_for(rows[i],reference) is not None for i in eligible)
            for i in rng.sample(eligible,min(n,len(eligible))):sides[i]=rng.choice(('LONG','SHORT'))
        else:
            ds=decisions(part,kind)
            sides={i:ds[i].direction for i in eligible if ds[i].direction is not None}
        altered=[]
        for i,r in enumerate(rows):
            altered.append(None if r is None else dict(r,patterns={kind:sides[i]} if i in sides else {}))
        result.append((part,altered))
    return result


def controls(output,report):
    main=json.loads(report.read_text());frozen=main['protocol']
    if main['status'].startswith('INCOMPLETE'):raise ValueError('Finish discovery before controls')
    if not (output/'finalists.lock.json').exists():raise ValueError('HOLDOUT_NOT_LOCKED')
    lock=json.loads((output/'finalists.lock.json').read_text())
    if lock['protocol_sha256']!=main['protocol_sha256']:raise ValueError('LOCK_CHANGED')
    fixed=dict(version='PATTERN_CONTROLS_1',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        baseline=['NO_TRADE','DONCHIAN','EMA_RSI_ADX','RANDOM_MATCHED_5_SEEDS','BUY_HOLD_2000_SEPARATE'],
        random_seeds=list(range(20261013,20261018)),
        random_scope='Per continuous segment and period, exactly matched eligible reference signal count; unbiased random side. Ex-post frequency-conditioned comparator, NOT live tradable strategy or fully matched position duration.',
        exits='Shared PCT2/4 or reference ATR2/4; UTC4-day timed exits, fees/risk/maxnotional unchanged; simple baselines use existing signal functions but shared protective exits, not their native exits.',
        walk_forward='Frozen standalone-pattern subset (NONE context only, both stop policies), train2020->test2021, train2020-21->test2022, train2020-22->test2023, train2020-23->test2024. Pick at most one numerical case per timeframe using prior train only, no retuning. Selection may fail inference gates; reported descriptive only.',
        holdout='No extra trading PnL calculated on2025 if no locked finalist. Buy-and-hold2025 preregistered separate risk reference; never used for selection.',
        uncertainty='14/28/56-day block sensitivity; no iid bootstrap',protocol_hash=main['protocol_sha256'])
    path=output/'controls.protocol.json'
    if path.exists() and json.loads(path.read_text())!=fixed:raise ValueError('CONTROL_PROTOCOL_CHANGED')
    if not path.exists():atomic_json(path,fixed)
    result=dict(protocol=fixed,controls=[],walk_forward=[],block_sensitivity=[],no_trade=dict(net_profit='0',fees='0',max_drawdown_pct='0',trades=0))
    cp_path=output/'controls.checkpoint.json'
    cp=json.loads(cp_path.read_text()) if cp_path.exists() else dict(key=digest(fixed),jobs={})
    if cp['key']!=digest(fixed):raise ValueError('CONTROL_CHECKPOINT_CHANGED')
    def execute(tag,prepared,h,start,end):
        key=digest(dict(tag=tag,h=h,start=start,end=end))
        if key in cp['jobs']:
            record=cp['jobs'][key]
            return artifact_read(output/record['artifact'],record['sha256'])
        value=period_run(prepared,h,start,end,Baseline(),STEPS[h['timeframe']])
        path=output/(key+'.control-checkpoint.gz');sha=write_artifact(path,value)
        cp['jobs'][key]=dict(artifact=path.name,sha256=sha)
        atomic_json(cp_path,cp)
        print('Control checkpoint',len(cp['jobs']),tag,h['id'],flush=True)
        return value

    for tf in STEPS:
        cm=json.loads((output/(tf+'.cache.json')).read_text());cache=artifact_read(output/(tf+'.cache.gz'),cm['sha256'])
        prepared=[([Bar.restore(b) for b in p['bars']],p['rows']) for p in cache]
        candidates=sorted([r for r in main['development'] if r['hypothesis']['timeframe']==tf and r['full_period_execution_valid']],key=lambda r:(-D(r['metrics']['net_profit']),r['hypothesis']['id']))
        if not candidates:continue
        best=candidates[0]['hypothesis']
        for period in ('development','validation'):
            a,b=map(stamp,PERIODS[period])
            for kind in ('DONCHIAN','EMA_RSI_ADX','RANDOM_MATCHED'):
                for seed in fixed['random_seeds'] if kind=='RANDOM_MATCHED' else [20261013]:
                    control=control_rows(prepared,kind,a,b,best,seed)
                    h=dict(id=f'{tf}:{kind}:{period}:{seed}',timeframe=tf,pattern=kind,context='NONE',exit=best['exit'] if kind=='RANDOM_MATCHED' else 'PCT_2_4')
                    run=execute(kind+':'+period+':'+str(seed),control,h,a,b);artifact=output/(digest(h)+'.control.gz')
                    sha=write_artifact(artifact,run)
                    result['controls'].append(dict(period=period,seed=seed,matched_reference=best if kind=='RANDOM_MATCHED' else None,artifact=artifact.name,sha256=sha,**summary(run)))
        # Genuine anchored out-of-time selection, budget held fixed at original grid.
        # Prior development jobs alone are not sufficient for early folds: resimulate training.
        grid=[h for h in main['hypotheses'] if h['timeframe']==tf and h['context']=='NONE']
        for year in (2021,2022,2023,2024):
            train_end=stamp(f'{year}-01-01');train_start=stamp('2020-01-01')
            winner=None
            for h in grid:
                train=execute('walk-train:'+str(year),prepared,h,train_start,train_end)
                if not train['full_period_execution_valid'] or train['metrics']['trades']<20:continue
                rank=(D(train['metrics']['net_profit']),h['id'])
                if winner is None or rank>winner[0]:winner=(rank,h)
            if winner is None:
                result['walk_forward'].append(dict(timeframe=tf,test_year=year,status='NO_ELIGIBLE_NUMERICAL_REFERENCE'));continue
            test=execute('walk-test:'+str(year),prepared,winner[1],train_end,stamp(f'{year+1}-01-01'))
            artifact=output/(digest(dict(tf=tf,year=year)) +'.walk.gz');sha=write_artifact(artifact,test)
            result['walk_forward'].append(dict(timeframe=tf,test_year=year,selected_from_past=winner[1],training_net=str(winner[0][0]),artifact=artifact.name,sha256=sha,**summary(test)))
        # Block-length sensitivity of previously ranked development cases, never new selection.
        for r in candidates[:3]:
            key=r['hypothesis']['id']+'|development |base';rec=json.loads((output/'checkpoint.json').read_text())['jobs'][key]
            run=artifact_read(output/rec['artifact'],rec['sha256'])
            result['block_sensitivity'].append(dict(id=r['hypothesis']['id'],full_valid=r['full_period_execution_valid'],blocks={str(n):blocked_bootstrap(run['equity_curve'],days=n) for n in (14,28,56)}))
    # Buy-and-hold does not use a stop and is NOT risk-comparable.
    cm=json.loads((output/'15m.cache.json').read_text());cache=artifact_read(output/'15m.cache.gz',cm['sha256'])
    for period,(a,b) in PERIODS.items():
        start,end=stamp(a),stamp(b);selected=[Bar.restore(x) for p in cache for x in p['bars'] if start<=x['time']<end]
        if any(v.time-u.time!=900 for u,v in zip(selected,selected[1:])):
            result.setdefault('buy_hold',[]).append(dict(period=period,status='UNRESOLVED_GAPS_NO_FAKE_FULL_PERIOD_RETURN',risk_equivalent=False));continue
        run=buy_hold(selected,0,len(selected),Baseline(),'2000');artifact=output/(period+'.buyhold.gz');sha=write_artifact(artifact,run)
        result.setdefault('buy_hold',[]).append(dict(period=period,metrics=run['metrics'],risk_equivalent=False,allocation='2000',artifact=artifact.name,sha256=sha))
    main['controls']=result
    main['baseline_note']='See controls: comparable shared-risk signal baselines and five random seeds; no-trade; buy-and-hold separately labelled, gap periods unavailable.'
    atomic_json(report,main)
    atomic_json(output/'controls.results.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    r=controls(a.output,a.report);print('Controls',len(r['controls']),'walk-forward',len(r['walk_forward']))
