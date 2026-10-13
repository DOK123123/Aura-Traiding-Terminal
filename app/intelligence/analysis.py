"""Past-only descriptive analog evidence, conservative experimental selector."""
from math import sqrt
from statistics import mean,stdev
from .patterns import features,detect

VERSION='ADAPTIVE_INTELLIGENCE_1.0'
CONFIG=dict(starting_balance='10000',fee_bps='10',slippage_bps='5',risk_pct='1',max_notional='2000',stop_pct='2',target_pct='4',horizon_days=4,min_samples=20,max_analogs=64,proposal_ttl_seconds=300)


def analyze(bars,index,timeframe):
    context=features(bars);patterns=detect(bars,timeframe=timeframe);step={'15m':900,'1h':3600,'4h':14400}[timeframe]
    at=bars[-1].time+step;direction=context['direction'];ids={p['pattern_id'] for p in patterns}
    ranked=[]
    for row in index:
        if row['timeframe']!=timeframe or row['resolved_at']>=at or row['direction']!=direction:continue
        other=set(row['patterns']);categorical=1-len(ids&other)/max(1,len(ids|other))
        distance=sqrt(sum((a-b)**2 for a,b in zip(context['vector'],row['vector'])))+.5*categorical
        if distance<=1.5:ranked.append((distance,row))
    ranked.sort(key=lambda x:(x[0],x[1]['timestamp']));selected=[]
    for _,row in ranked:
        if all(abs(row['timestamp']-r['timestamp'])>=CONFIG['horizon_days']*86400 for r in selected):selected.append(row)
        if len(selected)>=CONFIG['max_analogs']:break
    pnl=[float(r['net_pnl']) for r in selected];n=len(pnl);wins=sum(v>0 for v in pnl);losses=sum(v<0 for v in pnl)
    avg=mean(pnl) if pnl else None;low=avg-1.96*stdev(pnl)/sqrt(n) if n>=2 else None
    z=1.96;p=wins/n if n else 0
    wilson=((p+z*z/(2*n))-z*sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n) if n else None
    ordered=sorted(selected,key=lambda r:r['timestamp']);capital=10000.;peak=capital;drawdown=0.
    for row in ordered:
        capital+=float(row['net_pnl']);peak=max(peak,capital);drawdown=max(drawdown,(peak-capital)/peak*100)
    reason='INSUFFICIENT_DATA' if n<CONFIG['min_samples'] else 'NO_EDGE' if low is None or low<=0 else 'CONTEXT_UNKNOWN' if context['adx']<25 or direction is None else None
    strategy='WAIT' if reason else 'BREAKOUT' if any(p['pattern_id']=='breakout' and p['direction']==direction for p in patterns) else 'TREND_CONTINUATION'
    return dict(timestamp=at,symbol='BTCUSDT',timeframe=timeframe,context=context,patterns=patterns,strategy=strategy,reason=reason,
        evidence=dict(count=n,wins=wins,losses=losses,expectancy_after_costs=avg,mean_ci95_lower=low,
            win_frequency=p if n else None,win_frequency_wilson_lower=wilson,
            target_before_stop_frequency=sum(r['target_first'] for r in selected)/n if n else None,
            sample_curve_drawdown_pct=drawdown if n else None,last_resolved=max((r['resolved_at'] for r in selected),default=None),
            interpretation='Past non-overlapping hypothetical events, descriptive uncalibrated evidence; not a guaranteed probability or validated strategy. Multiple testing/regime dependence remain.'),
        validated_for_live=False,version=VERSION,correlation_policy='No vote count: related patterns share one feature/evidence group.',
        available_strategies=['BREAKOUT','TREND_CONTINUATION','WAIT'],planned_strategies=['RETEST','PULLBACK','MEAN_REVERSION','FALSE_BREAKOUT','REVERSAL'])
