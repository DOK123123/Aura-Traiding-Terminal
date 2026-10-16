"""Offline frozen 90-day comparison: production 4.2 vs Lab-only 4.3 candidates.

The production pure Decimal engine is reused unchanged. No Service, storage,
Supabase, private client, activation or live configuration is invoked.
"""
import argparse
from bisect import bisect_left
from collections import Counter,deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from decimal import Decimal as D
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import math
import time
import os

from app.lab.local_csv import load_binance_csv
from app.lab.models import digest,canonical,money,text,precise
from app.lab.adaptive43 import propose,choose,SCENARIOS,PARAMETERS
from app.lab.indicators import rsi
from app.automated.strategy import strategy as strategy42
from app.automated.engine import initial,advance,mark,validate,DemoError,POLICY
from scripts import replay_auto42_verification as native

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'docs/AURA43_PROTOCOL.json'
FILES=('app/lab/adaptive43.py','scripts/research_aura43.py','docs/AURA43_PROTOCOL.json',
    'app/automated/engine.py','app/automated/strategy.py','app/intelligence/market_context.py',
    'app/automated/alignment.py','research/market_intelligence/structure.py','app/intelligence/patterns.py',
    'app/lab/indicators.py','app/lab/models.py','app/lab/series.py','app/lab/execution.py')
VARIANTS=('AURA42','AURA43_ADAPTIVE')+tuple('AURA43_'+s for s in SCENARIOS)


def code_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}


def compact(d):
    return {k:v for k,v in d.items() if k not in ('timeframe_alignment','classification','parameters_hash')}


def analyze_group(job):
    first,last=job;start=first//14400*14400-4160*900
    left=bisect_left(native._TIMES,start);full=native._BARS[left:bisect_left(native._TIMES,last)]
    if not full or full[0].time!=start:raise ValueError('PRODUCTION_WARMUP_UNAVAILABLE')
    cache=native.PrefixCache(full);rs=rsi([float(b.close) for b in full]);rows=[]
    with cache.installed():
        for at in range(first,last+1,900):
            window=full[:bisect_left(native._TIMES,at)-left];snap=native.snapshot(window,at)
            try:d=compact(strategy42(snap,window,at+30))
            except DemoError as exc:d=dict(direction=None,reason=exc.code,error=exc.code)
            proposals={k:compact(v) for k,v in propose(snap,window,rsi_history=rs[:len(window)]).items()}
            rows.append(dict(closed_at=at,decision=d,proposals=proposals))
    return rows


@precise
def replay(bars,rows,start,end,variant,label):
    times=[b.time for b in bars];i=bisect_left(times,start)
    s=initial(start,epoch='LAB_ONLY_'+variant+'_'+label);s.update(mode='ON',watermark=start,last_bar_hash=digest(bars[i-1].data()))
    mark(s,bars[i-1],start);curve=[dict(time=start,balance=s['balance'],equity=s['equity'])]
    closes=[];opens=[];journal=[];reason_counts=Counter();execution_rejections=Counter();regimes=Counter();signals=0
    for row in rows:
        at=row['closed_at']
        if not start<at<=end:continue
        if variant=='AURA42':decision=row['decision']
        else:decision=choose(row['proposals'],None if variant=='AURA43_ADAPTIVE' else variant.removeprefix('AURA43_'))
        reason_counts[decision['reason']]+=1;regimes[decision.get('regime','PRODUCTION_42')]+=1
        if decision.get('direction'):signals+=1
        if decision.get('error'):raise ValueError('HISTORICAL_DATA_ERROR:'+decision['error'])
        k=bisect_left(times,at);window=bars[bisect_left(times,at//14400*14400-4160*900):k]
        s,events=advance(s,window,decision,at+30)
        for event in events:
            p=event['payload']
            if event['kind']=='OPEN':opens.append(p)
            if event['kind']=='CLOSE':closes.append(p)
            if event['kind']=='REJECT':execution_rejections[p['reason']]+=1
            if event['kind']=='DECISION':
                if decision.get('direction') and p['reason']!='SIGNAL_QUEUED_NEXT_OPEN':execution_rejections[p['reason']]+=1
                journal.append(dict(closed_at=at,reason=p['reason'],strategy_reason=decision['reason'],
                    direction=decision.get('direction'),scenario=decision.get('scenario'),regime=decision.get('regime'),
                    context=decision.get('context') if decision.get('direction') else None))
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
        subset=[t for t in closes if t['reason']=='AURA43:'+name]
        attribution[name]=dict(trades=len(subset),net_realized_pnl=text(sum((D(t['realized_pnl']) for t in subset),D(0))))
    # Display all trades/decisions, bounded sampled curve. Raw full daily returns
    # remain available for independent metrics checks; no forced final settlement.
    n=len(curve);indices={0,n-1}
    indices.update(i*(n-1)//299 for i in range(300))
    indices.update((max(range(n),key=lambda i:D(curve[i]['equity'])),min(range(n),key=lambda i:D(curve[i]['equity']))))
    return dict(variant=variant,split=label,start=start,end_exclusive=end,metrics=metrics,trades=closes,
        equity_curve=[curve[i] for i in sorted(indices)],curve_points_full=n,daily_equity=daily,
        decisions=journal,decision_counts=dict(reason_counts),execution_rejections=dict(execution_rejections),
        regimes=dict(regimes),scenario_attribution=attribution,open_position=s['position'],pending=s['pending'])


def build_report(bars,info,rows,protocol):
    end=bars[-1].time+900;start=end-90*86400;split=start+60*86400;runs=[]
    for variant in VARIANTS:
        for label,a,b in (('full_90d',start,end),('development',start,split),('validation',split,end)):
            runs.append(replay(bars,rows,a,b,variant,label))
    return dict(version='AURA43_RESEARCH_1',symbol='BTCUSDT',source=info,research_only=True,activation_available=False,
        real_money_execution='DISABLED',status='COMPLETED_DESCRIPTIVE_ONLY',code_hashes=code_hashes(),
        protocol=protocol,protocol_hash=digest(protocol),parameters=PARAMETERS,policy=POLICY,
        start=start,split_at=split,end_exclusive=end,closed_candles_processed=len(rows),runs=runs,
        recommendation='DO_NOT_ACTIVATE_AUTOMATICALLY',
        limitations=['One 90-day sample is insufficient for reliability/edge or tail-risk claims.',
            'Validation dates are chronologically separated, but parts of 2026 were previously examined.',
            'No parameter search or validation tuning. Five related variants imply multiple comparisons.',
            'SHORT is simulated directional exposure, not actual Spot borrowing.',
            'OHLC ambiguity: SL-first, adverse stop gaps and conservative target gaps; no intrabar path known.',
            'Risk is planned fee-inclusive risk; adverse gaps can exceed 0.5% or loss limits.',
            'Risk-triggered PAUSED remains latched, matching 4.2; no automatic research resume.',
            'Net profit uses terminal liquidation equity, including open exposure; closed-trade metrics are separate.',
            'Sharpe requires >=20 closed trades and >=30 daily returns, zero RF, sample stdev, sqrt(365).',
            'Ideal every-candle replay does not reproduce Render network/Supabase outages.'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,choices=(1,2),default=2)
    p.add_argument('--max-seconds',type=int,default=1800);a=p.parse_args(argv)
    if not 30<=a.max_seconds<=3600:p.error('max-seconds must be 30..3600')
    protocol=json.loads(PROTOCOL.read_text());bars,info=load_binance_csv(a.csv)
    end=int(datetime.fromisoformat(protocol['end_exclusive_utc'].replace('Z','+00:00')).timestamp());start=end-90*86400
    if bars[-1].time+900!=end or bars[0].time>start-4160*900:p.error('Exact 90-day coverage plus production warm-up required')
    fingerprint=digest(dict(data=info['sha256'],code=code_hashes(),protocol=protocol))
    checkpoint=a.output.with_suffix('.checkpoint.jsonl');rows=[]
    if checkpoint.exists():rows=native.read_checkpoint(checkpoint,fingerprint,start,end)
    else:checkpoint.parent.mkdir(parents=True,exist_ok=True);checkpoint.write_bytes(canonical(dict(fingerprint=fingerprint))+b'\n')
    first=rows[-1]['closed_at']+900 if rows else start+900;jobs=[]
    while first<=end:
        last=min(end,(first//14400+1)*14400-900);jobs.append((first,last));first=last+900
    began=time.monotonic()
    if jobs:
        with ProcessPoolExecutor(max_workers=a.workers,initializer=native.init_worker,initargs=(str(a.csv),)) as pool:
            iterator=iter(jobs);queue=deque()
            for _ in range(a.workers):
                job=next(iterator,None)
                if job:queue.append(pool.submit(analyze_group,job))
            while queue:
                block=queue.popleft().result()
                with checkpoint.open('ab') as f:f.write(canonical(block)+b'\n');f.flush();os.fsync(f.fileno())
                rows.extend(block)
                if len(rows)%384<16:print('closed candles',len(rows),flush=True)
                if time.monotonic()-began>a.max_seconds:
                    for future in queue:future.cancel()
                    print('BUDGET_REACHED: resume exact command',flush=True);return
                job=next(iterator,None)
                if job:queue.append(pool.submit(analyze_group,job))
    if len(rows)!=8640:raise ValueError('INCOMPLETE_REPLAY')
    report=build_report(bars,{k:v for k,v in info.items() if k!='path'},rows,protocol)
    report['checksum']=digest(report);raw=canonical(report)
    if len(raw)>24*1024*1024:raise ValueError('REPORT_LIMIT')
    a.output.write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
    print(json.dumps(dict(status=report['status'],runs=[dict(variant=r['variant'],split=r['split'],metrics=r['metrics']) for r in report['runs']])),flush=True)


if __name__=='__main__':main()
