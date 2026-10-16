"""Annual frozen Strategy Lab v2 study. Offline only, no accounts/network on GET."""
import argparse
from bisect import bisect_left
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal as D
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import math
from app.lab.models import digest,canonical,money,text,precise
from app.lab.series import higher
from app.lab.v2_strategies import prepare,decide,FAMILIES,STEPS
from app.lab.v2_execution import initial,advance,mark,validate,ratchet
from app.automated.engine import POLICY
from scripts.aura43_history import load_history
from scripts.lab_v2_baselines import read_checkpoint,code_hashes as native_hashes,FILES as NATIVE_FILES
from scripts.research_aura43_profiles import monthly_results

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=json.loads((ROOT/'docs/STRATEGY_LAB_V2_PROTOCOL.json').read_text())
FILES=NATIVE_FILES+('app/lab/v2_strategies.py','app/lab/v2_execution.py','scripts/research_lab_v2.py',
    'docs/STRATEGY_LAB_V2_PROTOCOL.json','scripts/research_aura43_profiles.py')
SCENARIOS=FAMILIES
VARIANTS=('AURA42','AURA43')+tuple(f+'_'+tf for f in FAMILIES for tf in STEPS)

def code_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def side_results(trades):
    result={}
    for side in ('LONG','SHORT'):
        ts=[t for t in trades if t['direction']==side];pnls=[D(t['realized_pnl']) for t in ts]
        profit=sum((max(n,D(0)) for n in pnls),D(0));loss=sum((max(-n,D(0)) for n in pnls),D(0));net=sum(pnls,D(0))
        result[side]=dict(trades=len(ts),net_profit=text(net),return_pct=text(money(net/100)),
            win_rate=text(money(D(sum(n>0 for n in pnls))/len(ts)*100)) if ts else None,
            profit_factor=text(money(profit/loss)) if loss else None,expectancy=text(money(net/len(ts))) if ts else None,
            fees=text(sum((D(t['fees']) for t in ts),D(0))),scope='REALIZED_ATTRIBUTION_WITHIN_JOINT_PORTFOLIO_NOT_INDEPENDENT_BACKTEST')
    return result

@precise
def replay(bars,rows,start,end,variant,label,*,trail_data=None):
    times=[b.time for b in bars];i=bisect_left(times,start)
    s=initial(start,epoch='LAB_ONLY_'+variant+'_'+label);s.update(mode='ON',watermark=start,last_bar_hash=digest(bars[i-1].data()))
    mark(s,bars[i-1],start);curve=[dict(time=start,balance=s['balance'],equity=s['equity'])]
    closes=[];opens=[];journal=[];reason_counts=Counter();execution_rejections=Counter();regimes=Counter();signals=0
    for row in rows:
        at=row['closed_at']
        if not start<at<=end:continue
        decision=row['decision']
        if decision['reason']!='NO_NEW_CLOSED_TIMEFRAME':reason_counts[decision['reason']]+=1
        regimes[decision.get('regime','UNCLASSIFIED')]+=1
        if decision.get('direction'):signals+=1
        if decision.get('error'):raise ValueError('HISTORICAL_DATA_ERROR:'+decision['error'])
        k=bisect_left(times,at);window=bars[k-2:k]  # Both previously validated bars; identical execution inputs, no analysis here.
        s,events=advance(s,window,decision,at+30)
        for event in events:
            p=event['payload']
            if event['kind']=='OPEN':opens.append(p)
            if event['kind']=='CLOSE':closes.append(p)
            if event['kind']=='REJECT':execution_rejections[p['reason']]+=1
            if event['kind']=='DECISION':
                if decision.get('direction') and p['reason']!='SIGNAL_QUEUED_NEXT_OPEN':execution_rejections[p['reason']]+=1
                if decision['reason']!='NO_NEW_CLOSED_TIMEFRAME' or p['reason'] not in ('NO_NEW_CLOSED_TIMEFRAME','POSITION_ALREADY_OPEN'):
                    journal.append(dict(closed_at=at,reason=p['reason'],strategy_reason=decision['reason'],
                    direction=decision.get('direction'),scenario=decision.get('scenario'),regime=decision.get('regime'),
                    original_signal_at=decision.get('original_signal_at',at),gates=decision.get('gates'),context=decision.get('context') if decision.get('direction') else None))
        if trail_data is not None and s['position']:
            ti=bisect_left(trail_data['times'],at)-1
            if ti>=0 and trail_data['bars'][ti].time+trail_data['step']==at:
                ratchet(s,trail_data['bars'][ti],trail_data['atr'][ti],step=trail_data['step'])
        curve.append(dict(time=at,balance=s['balance'],equity=s['equity']))
    validate(s)
    pnls=[D(t['realized_pnl']) for t in closes];wins=[p for p in pnls if p>0];losses=[-p for p in pnls if p<0]
    net=D(s['equity'])-D(10000);profit=sum(wins,D(0));loss=sum(losses,D(0))
    daily=[x for x in curve if x['time']%86400==0]
    returns=[float(D(b['equity'])/D(a['equity'])-1) for a,b in zip(daily,daily[1:]) if b['time']-a['time']==86400 and D(a['equity'])>0]
    sharpe=None
    if len(pnls)>=20 and len(returns)>=30 and statistics.stdev(returns)>0:
        sharpe=statistics.mean(returns)/statistics.stdev(returns)*math.sqrt(365)
    metrics=dict(trades=len(closes),opened=len(opens),signals=signals,net_profit=text(money(net)),
        realized_net_pnl=s['realized_pnl'],return_pct=text(money(net/100)),
        win_rate=text(money(D(len(wins))/len(pnls)*100)) if pnls else None,
        profit_factor=text(money(profit/loss)) if loss else None,max_drawdown_pct=s['max_drawdown_pct'],
        average_win=text(money(profit/len(wins))) if wins else None,average_loss=text(money(loss/len(losses))) if losses else None,
        expectancy=text(money(sum(pnls,D(0))/len(pnls))) if pnls else None,sharpe=sharpe,
        sharpe_daily_returns=len(returns),fees=s['fees'],slippage=s['slippage'],
        final_balance=s['balance'],final_equity=s['equity'],final_mode=s['mode'],
        sample_status='INSUFFICIENT_TRADES' if len(pnls)<20 else 'DESCRIPTIVE_ONLY')
    attribution={}
    for name in SCENARIOS:
        subset=[t for t in closes if t['reason']=='LABV2:'+name]
        attribution[name]=dict(trades=len(subset),net_realized_pnl=text(sum((D(t['realized_pnl']) for t in subset),D(0))))
    # All trades and evaluated decisions are retained in bounded artifacts. Raw full daily returns
    # remain available for independent metrics checks; no forced final settlement.
    n=len(curve);indices={0,n-1}
    indices.update(i*(n-1)//299 for i in range(300))
    indices.update((max(range(n),key=lambda i:D(curve[i]['equity'])),min(range(n),key=lambda i:D(curve[i]['equity']))))
    monthly=monthly_results(curve,closes,start,end)
    metrics['trades_per_30d']=len(closes)*30*86400/(end-start)
    return dict(monthly=monthly,decision_log_scope='ALL_EVALUATED_STRATEGY_CANDLES_AND_EXECUTION_REJECTIONS',variant=variant,split=label,start=start,end_exclusive=end,metrics=metrics,trades=closes,
        equity_curve=[curve[i] for i in sorted(indices)],curve_points_full=n,daily_equity=daily,
        decisions=journal,decision_counts=dict(reason_counts),execution_rejections=dict(execution_rejections),
        regimes=dict(regimes),scenario_attribution=attribution,side_results=side_results(closes),open_position=s['position'],pending=s['pending'])


def decisions(bars,variant,native_rows,frames,start,end,delay=0):
    if variant in ('AURA42','AURA43'):
        key='decision' if variant=='AURA42' else 'original';source=((r['closed_at'],r[key]) for r in native_rows)
    else:
        family,tf=variant.rsplit('_',1);data=frames[tf]
        source=((b.time+data['step'],decide(data,i,family,closed_at=b.time+data['step'])) for i,b in enumerate(data['bars']) if start<b.time+data['step']<=end)
    mapping={at+delay*900:dict(d,original_signal_at=d.get('signal_at',at),strategy_timeframe=variant.rsplit('_',1)[1] if variant not in ('AURA42','AURA43') else '15m') for at,d in source if start<at<=end}
    for at in range(start+900,end+1,900):
        yield dict(closed_at=at,decision=mapping.get(at,dict(direction=None,reason='NO_NEW_CLOSED_TIMEFRAME')))

def eligible(run,minimum):
    m=run['metrics'];months=[x for x in run['monthly'].values() if x['complete_calendar_month']]
    return bool(m['trades']>=minimum and D(m['net_profit'])>0 and m['profit_factor'] is not None and
        D(m['profit_factor'])>=D('1.1') and D(m['max_drawdown_pct'])<10 and months and sum(D(x['net_profit'])>0 for x in months)*2>=len(months))

def save_run(row,directory):
    log=directory/('decisions_'+row['variant']+'_'+row['split']+'.jsonl.gz')
    raw=b''.join(canonical(d)+b'\n' for d in row.pop('decisions'))
    if len(raw)>32*1024*1024:raise ValueError('DECISION_LOG_LIMIT')
    compressed=gzip.compress(raw,compresslevel=9,mtime=0);log.write_bytes(compressed)
    row.update(decision_artifact=log.name,decision_sha256=hashlib.sha256(compressed).hexdigest(),decision_total=raw.count(b'\n'))
    return row

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True,type=Path);p.add_argument('--native',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args(argv);a.output_dir.mkdir(parents=True,exist_ok=True)
    bars,source=load_history(a.csv);stamp=lambda k:int(datetime.fromisoformat(PROTOCOL[k].replace('Z','+00:00')).timestamp())
    start=stamp('start_utc');end=stamp('end_exclusive_utc');split=start+((end-start)//900*7//10)*900
    if bars[0].time!=start-4160*900 or bars[-1].time+900!=end:raise ValueError('COVERAGE')
    fp=digest(dict(data=source['sha256'],code=native_hashes(),start=start,end=end))
    native_rows=read_checkpoint(a.native,fp,start,end)
    if len(native_rows)!=35040:raise ValueError('INCOMPLETE_NATIVE_DECISIONS')
    frames={tf:dict(prepare(bars,step),times=[b.time for b in (bars if step==900 else higher(bars,step))]) for tf,step in STEPS.items()}
    runs=[]
    def run(variant,label,lo,hi,delay=0):
        trail=frames[variant.rsplit('_',1)[1]] if variant.startswith('TREND_ATR_') else None
        row=replay(bars,decisions(bars,variant,native_rows,frames,lo,hi,delay),lo,hi,variant,label,trail_data=trail)
        runs.append(save_run(row,a.output_dir));print('completed',variant,label,flush=True)
    for variant in VARIANTS:run(variant,'development',start,split)
    candidates=[r for r in runs if eligible(r,30)];winner=max(candidates,key=lambda r:D(r['metrics']['expectancy']))['variant'] if candidates else None
    selection=dict(winner=winner,eligible=[r['variant'] for r in candidates],basis='DEVELOPMENT_ONLY',
        frozen_before_validation_metrics=True,frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        protocol_hash=digest(PROTOCOL),source_sha256=source['sha256'],development_metrics={r['variant']:r['metrics'] for r in runs})
    (a.output_dir/'selection.json').write_bytes(canonical(selection));print('SELECTION_FROZEN',winner,flush=True)
    for variant in VARIANTS:
        run(variant,'validation',split,end);run(variant,'full_12m',start,end);run(variant,'validation_delayed',split,end,1)
    selected=next((r for r in runs if r['variant']==winner and r['split']=='validation'),None)
    delayed=next((r for r in runs if r['variant']==winner and r['split']=='validation_delayed'),None)
    passed=selected and eligible(selected,20) and delayed and D(delayed['metrics']['net_profit'])>0 and delayed['metrics']['profit_factor'] is not None and D(delayed['metrics']['profit_factor'])>=D('1.1')
    report=dict(version=PROTOCOL['version'],symbol='BTCUSDT',research_only=True,activation_available=False,real_money_execution='DISABLED',
        status='VALIDATION_CRITERIA_MET_NOT_PROOF_OF_EDGE' if passed else 'NO_ROBUST_ADVANTAGE',
        source=source,code_hashes=code_hashes(),native_fingerprint=fp,protocol=PROTOCOL,protocol_hash=digest(PROTOCOL),policy=POLICY,
        start=start,split_at=split,end_exclusive=end,closed_candles_processed=35040,development_selection=selection,selection_hash=digest(selection),runs=runs,
        limitations=PROTOCOL['limitations'])
    report['checksum']=digest(report);raw=canonical(report)
    if len(raw)>16*1024*1024:raise ValueError('REPORT_LIMIT')
    (a.output_dir/'report.json.gz').write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
    print(json.dumps(dict(status=report['status'],winner=winner,runs=[dict(variant=r['variant'],split=r['split'],metrics=r['metrics']) for r in runs])),flush=True)

if __name__=='__main__':main()
