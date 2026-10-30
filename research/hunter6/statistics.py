"""Transparent group metrics and deterministic dependent-block intervals, no profit probabilities."""
import datetime as dt
import hashlib
import math
import numpy as np


def closed(t):
    return t.get('entered') and t.get('outcome') in ('SL','TP','TIMEOUT') and t.get('r') is not None


def stats(trades, *, intervals=False, key='', start=None, end=None):
    done=sorted([t for t in trades if closed(t)],key=lambda t:(t['exit_time'],t['id']))
    pnls=[float(t['pnl_usdt']) for t in done];rs=[t['r'] for t in done]
    wins=[p for p in pnls if p>0];losses=[p for p in pnls if p<0]
    total=peak=dd=0.;total_r=peak_r=dd_r=0.
    for p,r in zip(pnls,rs):
        total+=p;peak=max(peak,total);dd=max(dd,peak-total)
        total_r+=r;peak_r=max(peak_r,total_r);dd_r=max(dd_r,peak_r-total_r)
    result={'signals':len(trades),'entered':sum(bool(t.get('entered')) for t in trades),'closed':len(done),
            'no_fill':sum(t['outcome']=='NO_FILL' for t in trades),'overlap_excluded':sum(t['outcome']=='OVERLAP' for t in trades),
            'unknown':sum(t['outcome']=='UNKNOWN' for t in trades),'win_rate':len(wins)/len(done) if done else None,
            'profit_factor':sum(wins)/abs(sum(losses)) if losses else None,
            'expectancy_R':float(np.mean(rs)) if rs else None,'pnl_usdt':sum(pnls) if done else None,
            'max_drawdown_usdt':dd if done else None,'max_drawdown_R':dd_r if done else None,
            'average_win_usdt':float(np.mean(wins)) if wins else None,'average_loss_usdt':float(np.mean(losses)) if losses else None,
            'fees_usdt':sum(float(t.get('fees_usdt',0)) for t in done),
            'funding_usdt':sum(float(t.get('funding_usdt',0)) for t in done),
            'modeled_funding_settlements':sum(t.get('missing_funding_settlements',0) for t in done),
            'portfolio_return':None,'statistical_status':'UNVALIDATED'}
    if intervals:result['uncertainty']=bootstrap(done,key,start,end)
    return result


def bootstrap(trades,key,start,end):
    n=len(trades)
    blocks={}
    for t in trades:blocks.setdefault(t['signal_time']//(14*86400),[]).append(t)
    out={'confidence':.95,'method':'14_DAY_CALENDAR_CLUSTER_BOOTSTRAP','trades':n,'active_blocks':len(blocks),
         'replicates':1000,'expectancy_R':None,'win_rate':None,'profit_factor':None,'status':'INSUFFICIENT_EVIDENCE'}
    if n<30 or len(blocks)<10:return out
    first=start//(14*86400);last=(end-1)//(14*86400)
    values=[]
    for block in range(first,last+1):
        ts=blocks.get(block,[]);p=[float(t['pnl_usdt']) for t in ts]
        values.append([len(ts),sum(t['r'] for t in ts),sum(x>0 for x in p),sum(x for x in p if x>0),-sum(x for x in p if x<0)])
    values=np.asarray(values,dtype=float)
    seed=int.from_bytes(hashlib.sha256((key+'6002026').encode()).digest()[:8],'big')
    rng=np.random.default_rng(seed)
    totals=values[rng.integers(0,len(values),size=(1000,len(values)))].sum(axis=1)
    count=totals[:,0]
    for name,column,denom in [('expectancy_R',1,count),('win_rate',2,count),('profit_factor',3,totals[:,4])]:
        samples=totals[denom>0,column]/denom[denom>0]
        out[name]=[float(x) for x in np.quantile(samples,[.025,.975])] if len(samples)>=800 else None
    out['status']='EXPLORATORY_DEPENDENT_INTERVAL_NOT_VALIDATION'
    out['limitations']='Cross-block dependence, reused final history and multiple comparisons remain; no calibration.'
    return out


def group_summary(trades, start, end, key):
    result=stats(trades,intervals=True,key=key,start=start,end=end)
    months={};regimes={}
    for t in trades:
        month=dt.datetime.fromtimestamp(t['signal_time'],dt.UTC).strftime('%Y-%m')
        months.setdefault(month,[]).append(t);regimes.setdefault(t['regime'],[]).append(t)
    result['months']={k:stats(v) for k,v in sorted(months.items())}
    result['regimes']={k:stats(v) for k,v in sorted(regimes.items())}
    return result


def eligible(metrics, minimum):
    months=metrics['months'];positive=sum(m['expectancy_R'] is not None and m['expectancy_R']>0 for m in months.values())
    lower=metrics['uncertainty']['expectancy_R']
    return bool(metrics['closed']>=minimum and metrics['profit_factor'] is not None and metrics['profit_factor']>=1.2
                and lower is not None and lower[0]>0 and months and positive/len(months)>=.6)
