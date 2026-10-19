"""Frozen local experiment: production Active transitions, Spot only, no accounts.

Selection is written before any final-test computation. No LLM/optimizer, no
production configuration, no separate financial simulator.
"""
import argparse,hashlib,json,os,time
from bisect import bisect_left
from collections import Counter
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from app.active43.strategies import PARAMETERS,STEPS,PROTOCOL,config,signals
from app.active43.core import initial,advance,plan,close,POLICY
from app.automated.engine import mark
from app.lab.execution import metrics
from app.lab.models import Baseline,digest,money,text
from scripts.active43_history import load,aggregate

ROOT=Path(__file__).resolve().parents[1]
FILES=('app/active43/core.py','app/active43/strategies.py','app/automated/engine.py','app/lab/strategies.py','app/lab/indicators.py','app/lab/models.py','app/lab/execution.py','scripts/active43_history.py','scripts/research_active43.py')

def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def rolling_signals(bars,name,step):
    times=[b.time for b in bars];result=[None]*len(bars);day=(bars[0].time+step)//86400*86400
    while day<=bars[-1].time+step:
        left=bisect_left(times,day-1000*step);right=bisect_left(times,day+86400-step)
        window=bars[left:right];values=signals(window,name)
        begin=bisect_left(times,day-step)
        for i in range(begin,right):result[i]=values[i-left]
        day+=86400
    return result


def simulate(bars,values,cfg,start,end):
    step=STEPS[cfg['timeframe']];times=[b.time for b in bars]
    begin=bisect_left(times,start);finish=bisect_left(times,end)
    if begin<1000 or begin==finish or bars[begin].time!=start or bars[finish-1].time+step!=end:raise ValueError('INCOMPLETE_SEGMENT')
    s=initial(start,cfg,epoch='HISTORICAL_ONLY');s.update(mode='ON',watermark=start,last_bar_hash=digest(bars[begin-1].data()))
    trades=[];curve=[dict(time=start,balance='10000',equity='10000')];reasons=Counter();directions=Counter();exec_reject=Counter();opens=0
    for i in range(begin,finish):
        b=bars[i];d=values[i]
        if d is None:raise ValueError('MISSING_SIGNAL_HISTORY')
        p=plan(d,b,step,d.stop_distance if cfg['strategy']=='TREND_ATR' else None)
        directions[d.direction or 'WAIT']+=1;reasons[d.reason]+=1
        s,events=advance(s,bars[i-1:i+1],p,b.time+step+1)
        for ev in events:
            if ev['kind']=='OPEN':opens+=1
            if ev['kind']=='REJECT':exec_reject[ev['payload']['reason']]+=1
            if ev['kind']=='CLOSE':trades.append(deepcopy(ev['payload']))
        if b.time+step==end and s['position']:
            ev=close(s,b.close,end,'HISTORICAL_SEGMENT_END');trades.append(ev['payload']);mark(s,b,end)
        # Full close curve; never passed to signal generation or parameter choice.
        curve.append(dict(time=b.time+step,balance=s['balance'],equity=s['equity']))
    for t in trades:
        q=D(t['size']);t['slippage_usdt']=text(money((abs(D(t['entry_price'])-D(t['entry_raw_price']))+abs(D(t['exit_price'])-D(t['exit_raw_price'])))*q))
    stats=metrics(trades,curve,Baseline(risk_pct='.5',development_pct='60'))
    stats['max_drawdown_pct']=text(max(D(stats['max_drawdown_pct']),D(s['max_drawdown_pct'])))
    duration=sum(t['exit_time']-t['entry_time'] for t in trades)
    gross=sum((D(t['gross_price_pnl']) for t in trades),D(0));fees=D(stats['total_fees']);net=D(stats['net_profit'])
    stats.update(trades_per_week=text(money(D(len(trades))*604800/(end-start))),
        mean_duration_hours=text(money(D(duration)/len(trades)/3600)) if trades else None,
        fees_to_abs_gross_pct=text(money(fees/abs(gross)*100)) if gross else None,
        fees_to_abs_net_pct=text(money(fees/abs(net)*100)) if net else None,
        fees_ratio_definition='Fees / absolute gross or net PnL; undefined at zero, can exceed 100%.',
        long_trades=sum(t['direction']=='LONG' for t in trades),short_trades=sum(t['direction']=='SHORT' for t in trades))
    return dict(start=start,end_exclusive=end,metrics=stats,trades=trades,equity_curve=curve,
        signal_counts=dict(directions),first_decision_reasons=dict(reasons),execution_rejections=dict(exec_reject),
        opened=opens,final_mode=s['mode'],policy=POLICY,scope='HISTORICAL_ONLY_NOT_LIVE')


def candidate(job):
    csv,name,tf,start,train_end,val_end=job;bars=aggregate(load(csv),STEPS[tf]);cfg=config(name,tf)
    values=rolling_signals(bars,name,STEPS[tf])
    return dict(config=cfg,development=simulate(bars,values,cfg,start,train_end),validation=simulate(bars,values,cfg,train_end,val_end))


def score(row):
    a=row['development']['metrics'];b=row['validation']['metrics']
    sufficient=a['trades']>=20 and b['trades']>=10
    positive=D(a['net_profit'])>0 and D(b['net_profit'])>0 and (a['profit_factor'] is not None and D(a['profit_factor'])>1) and (b['profit_factor'] is not None and D(b['profit_factor'])>1)
    # Conservative worst-segment comparison. No held-out test fields consulted.
    return (sufficient and positive,min(D(a['net_profit']),D(b['net_profit'])),-max(D(a['max_drawdown_pct']),D(b['max_drawdown_pct'])))


def main(folder,workers=2):
    if not __debug__ or os.getenv('RENDER'):raise ValueError('LOCAL_RESEARCH_ONLY')
    folder=Path(folder);csv=folder/'btc-5m.csv';prov=json.loads((folder/'provenance.json').read_text())
    if hashlib.sha256(csv.read_bytes()).hexdigest()!=prov['csv_sha256'] or not prov['checksums_verified']:raise ValueError('SOURCE_INTEGRITY')
    code=hashes();identity=digest(dict(data=prov['csv_sha256'],code=code,protocol=PROTOCOL))
    start=prov['evaluation_start'];end=prov['evaluation_end'];days=(end-start)//86400
    train_end=start+(days*60//100)*86400;val_end=start+(days*80//100)*86400
    checkpoint=folder/'experiment-identity.json'
    if checkpoint.exists() and json.loads(checkpoint.read_text())!={'fingerprint':identity}:raise ValueError('EXPERIMENT_SOURCE_OR_PROTOCOL_CHANGED')
    checkpoint.write_text(json.dumps(dict(fingerprint=identity)))
    jobs=[];rows=[]
    for tf in STEPS:
        for name in PARAMETERS:
            path=folder/(tf+'-'+name+'-development.json')
            if path.exists():rows.append(json.loads(path.read_text()))
            else:jobs.append((str(csv),name,tf,start,train_end,val_end))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(candidate,jobs):
            cfg=row['config'];(folder/(cfg['timeframe']+'-'+cfg['strategy']+'-development.json')).write_text(json.dumps(row))
            rows.append(row);print('DEVELOPMENT_VALIDATION',cfg['strategy'],cfg['timeframe'],flush=True)
    ranked=sorted(rows,key=score,reverse=True);eligible=[r for r in ranked if score(r)[0]]
    chosen=eligible[0]['config'] if eligible else config('DONCHIAN','15m')
    selection=dict(config=chosen,development_validation_edge=bool(eligible),verdict='NEEDS_VALIDATION' if eligible else 'NO_EDGE_FOUND',
        reason='Worst-segment positive net with adequate development/validation sample' if eligible else 'No candidate passed the predeclared development/validation criteria. Fixed Donchian 15m is an experimental execution candidate, not a profitable winner.',
        selected_before_final_test=True,protocol_hash=digest(PROTOCOL),fingerprint=identity)
    selection_path=folder/'selection-before-test.json'
    if selection_path.exists() and json.loads(selection_path.read_text())!=selection:raise ValueError('SELECTION_CHANGED_AFTER_TEST')
    selection_path.write_text(json.dumps(selection,indent=2));print('SELECTION_FROZEN',json.dumps(selection),flush=True)
    # Final test cannot alter the selection or parameters, even if another row wins.
    for row in rows:
        cfg=row['config'];path=folder/(cfg['timeframe']+'-'+cfg['strategy']+'-final-test.json')
        if path.exists():row['final_test']=json.loads(path.read_text())
        else:
            bars=aggregate(load(csv),STEPS[cfg['timeframe']]);values=rolling_signals(bars,cfg['strategy'],STEPS[cfg['timeframe']])
            row['final_test']=simulate(bars,values,cfg,val_end,end);path.write_text(json.dumps(row['final_test']))
        print('FINAL_TEST',cfg['strategy'],cfg['timeframe'],row['final_test']['metrics']['net_profit'],flush=True)
    # True expanding-window selection inside development only. Later final 20%
    # is never fed back into training, ranking or walk-forward reselection.
    folds=[]
    for offset in (120,150,180):
        cut=start+offset*86400;finish=cut+30*86400;ranking=[]
        for row in rows:
            closed=[t for t in row['development']['trades'] if t['exit_time']<=cut]
            net=sum((D(t['realized_pnl']) for t in closed),D(0))
            ranking.append((len(closed)>=10,net,row['config']['strategy']+'_'+row['config']['timeframe'],row['config']))
        cfg=max(ranking,key=lambda v:v[:3])[3];bars=aggregate(load(csv),STEPS[cfg['timeframe']]);values=rolling_signals(bars,cfg['strategy'],STEPS[cfg['timeframe']])
        run=simulate(bars,values,cfg,cut,finish)
        folds.append(dict(training_end=cut,selection_basis='Only CLOSED trades in expanding development prefix; no validation/final data',config=cfg,result=run))
    selected=next(r for r in rows if r['config']==chosen)
    edge=bool(eligible) and selected['final_test']['metrics']['trades']>=20 and D(selected['final_test']['metrics']['net_profit'])>0
    result=dict(schema='ACTIVE43_RESEARCH_1',fingerprint=identity,code_hashes=code,protocol=PROTOCOL,source=prov,
        split=dict(start=start,development_end=train_end,validation_end=val_end,end_exclusive=end),selection=selection,
        verdict='NEEDS_FORWARD_VALIDATION' if edge else 'NO_EDGE_FOUND',no_profitability_claim=True,
        independent_pristine_project_holdout=False,candidates=[dict(config=r['config'],**{seg:{k:v for k,v in r[seg].items() if k not in ('trades','equity_curve')} for seg in ('development','validation','final_test')}) for r in rows],walk_forward=[dict(f, result={k:v for k,v in f['result'].items() if k not in ('trades','equity_curve')}) for f in folds],
        production_paper_verified=False,execution='SAME_ACTIVE43_PRODUCTION_TRANSITIONS',
        limits=['Spot virtual SHORT, no futures funding or borrow costs.','Previous project holdouts overlap: only current frozen protocol chronological OOS, not pristine evidence.',
                'Fixed costs and conservative OHLC fills, no order book/latency reconstruction.','Risk stops remain latched pending owner review, as in production.',
                'Segment-end positions closed only in historical comparison, never a production signal.'])
    if hashes()!=code:raise ValueError('CODE_CHANGED_DURING_RESEARCH')
    (folder/'results.json').write_text(json.dumps(result));print('RESEARCH_COMPLETE',result['verdict'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True);p.add_argument('--workers',type=int,choices=(1,2),default=2)
    a=p.parse_args();main(a.folder,a.workers)
