"""Frozen six-month 70/30 comparison. Offline only, no service/storage/private API."""
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
import os
import time
from app.lab.models import digest,canonical,money,text,precise
from app.lab.indicators import rsi
from app.lab.adaptive43 import choose,SCENARIOS,propose as original43
from app.lab.adaptive43_profiles import propose,PROFILES,PROTOCOL
from app.automated.strategy import strategy as strategy42
from app.automated.engine import initial,advance,mark,validate,DemoError,POLICY
from scripts import replay_auto42_verification as native
from scripts.research_aura43 import compact,FILES as ORIGINAL_FILES
from scripts.aura43_history import load_history
from scripts.aura43_profile_context import snapshot

ROOT=Path(__file__).resolve().parents[1]
FILES=ORIGINAL_FILES+('app/lab/adaptive43_profiles.py','scripts/research_aura43_profiles.py',
 'scripts/aura43_history.py','scripts/aura43_profile_context.py','docs/AURA43_PROFILES_PROTOCOL.json',
 'scripts/replay_auto42_verification.py')
VARIANTS=('AURA42','AURA43_ORIGINAL')+tuple(p+suffix for p in PROFILES for suffix in ('',)+tuple('_'+s for s in SCENARIOS))

def code_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def init_worker(path):
    native._BARS,_=load_history(path);native._TIMES=[b.time for b in native._BARS]

def analyze_group(job):
    first,last=job;start=first//14400*14400-4160*900
    left=bisect_left(native._TIMES,start);full=native._BARS[left:bisect_left(native._TIMES,last)]
    if not full or full[0].time!=start:raise ValueError('WARMUP')
    cache=native.PrefixCache(full);rs=rsi([float(b.close) for b in full]);rows=[];counts=Counter()
    for at in range(first,last+1,900):
        window=full[:bisect_left(native._TIMES,at)-left];snap=snapshot(cache,window,at)
        native_decision=compact(strategy42(snap,window,at+30))
        prior=compact(choose(original43(snap,window,rsi_history=rs[:len(window)])))
        variants={}
        for profile in PROFILES:
            proposals=propose(snap,window,profile,rsi_history=rs[:len(window)])
            for scenario,d in proposals.items():
                diag=d.pop('diagnostics',{})
                if not diag:counts[profile+'|'+scenario+'|GLOBAL|'+d['reason']]+=1
                for side,diagnostic in diag.items():
                    gates=diagnostic['gates'];failed=[k for k,v in gates.items() if not v]
                    prefix=profile+'|'+scenario+'|'+side+'|'
                    counts[prefix+'evaluated']+=1
                    for k in failed:counts[prefix+'failed:'+k]+=1
                    if failed:counts[prefix+'first:'+failed[0]]+=1
                    if len(failed)==1:counts[prefix+'only_blocker:'+failed[0]]+=1
                    if diagnostic['plan']:counts[prefix+'plan:'+diagnostic['plan']]+=1
                # Stable compact output; no large repeated context on waits.
                proposals[scenario]=compact(d) if d.get('direction') else dict(direction=None,reason=d['reason'],regime=d['regime'])
            variants[profile]=proposals
        rows.append(dict(closed_at=at,decision=native_decision,original=prior,profiles=variants))
    return dict(rows=rows,filters=dict(counts))

def monthly_results(curve,trades,start,end):
    months={};prior=curve[0]
    for point in curve[1:]:
        month=datetime.fromtimestamp(point['time']-1,timezone.utc).strftime('%Y-%m')
        r=months.setdefault(month,dict(start=prior['time'],end=point['time'],start_equity=prior['equity'],end_equity=point['equity'],trades=0))
        r.update(end=point['time'],end_equity=point['equity']);prior=point
    for t in trades:
        key=datetime.fromtimestamp(min(t['exit_time'],end-1),timezone.utc).strftime('%Y-%m');months[key]['trades']+=1
    for key,r in months.items():
        r['net_profit']=text(money(D(r['end_equity'])-D(r['start_equity'])))
        r['complete_calendar_month']=datetime.fromtimestamp(r['start'],timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')==key+'-01T00:00:00' and datetime.fromtimestamp(r['end'],timezone.utc).day==1 and r['end']%86400==0
    return months

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
        k=bisect_left(times,at);window=bars[k-2:k]  # Both previously validated bars; identical execution inputs, no analysis here.
        s,events=advance(s,window,decision,at+30)
        for event in events:
            p=event['payload']
            if event['kind']=='OPEN':opens.append(p)
            if event['kind']=='CLOSE':closes.append(p)
            if event['kind']=='REJECT':execution_rejections[p['reason']]+=1
            if event['kind']=='DECISION':
                if decision.get('direction') and p['reason']!='SIGNAL_QUEUED_NEXT_OPEN':execution_rejections[p['reason']]+=1
                if decision.get('direction') or (at-start)//900%96==0:
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
    # Display all trades and a labelled daily/signal decision sample, full counts. Raw full daily returns
    # remain available for independent metrics checks; no forced final settlement.
    n=len(curve);indices={0,n-1}
    indices.update(i*(n-1)//299 for i in range(300))
    indices.update((max(range(n),key=lambda i:D(curve[i]['equity'])),min(range(n),key=lambda i:D(curve[i]['equity']))))
    monthly=monthly_results(curve,closes,start,end)
    metrics['trades_per_30d']=len(closes)*30*86400/(end-start)
    return dict(monthly=monthly,decision_log_scope='ALL_SIGNAL_DECISIONS_PLUS_DAILY_SAMPLE; COUNTS_USE_ALL_CANDLES',variant=variant,split=label,start=start,end_exclusive=end,metrics=metrics,trades=closes,
        equity_curve=[curve[i] for i in sorted(indices)],curve_points_full=n,daily_equity=daily,
        decisions=journal,decision_counts=dict(reason_counts),execution_rejections=dict(execution_rejections),
        regimes=dict(regimes),scenario_attribution=attribution,open_position=s['position'],pending=s['pending'])


def selected_rows(rows,variant):
    for row in rows:
        if variant=='AURA42':d=row['decision']
        elif variant=='AURA43_ORIGINAL':d=row['original']
        else:
            profile=variant.split('_')[0];scenario=variant[len(profile)+1:] or None
            d=choose(row['profiles'][profile],scenario)
        yield dict(closed_at=row['closed_at'],decision=d)

def eligible(run):
    m=run['metrics'];months=[x for x in run['monthly'].values() if x['complete_calendar_month']]
    return bool(m['trades']>=20 and D(m['net_profit'])>0 and m['profit_factor'] is not None and
        D(m['profit_factor'])>=D('1.1') and D(m['max_drawdown_pct'])<10 and months and
        sum(D(x['net_profit'])>0 for x in months)*2>=len(months))

def read_checkpoint(path,fingerprint,start,end):
    if path.stat().st_size>8*1024*1024:raise ValueError('CHECKPOINT_LIMIT')
    with gzip.open(path,'rb') as f:raw=f.read(100*1024*1024+1)
    if len(raw)>100*1024*1024:raise ValueError('CHECKPOINT_LIMIT')
    lines=raw.splitlines();header=json.loads(lines[0])
    if header!={'fingerprint':fingerprint}:raise ValueError('CHECKPOINT_IDENTITY')
    rows=[];filters=Counter();expected=start+900
    for line in lines[1:]:
        block=json.loads(line)
        if not 1<=len(block['rows'])<=16:raise ValueError('CHECKPOINT_BLOCK')
        for row in block['rows']:
            if row['closed_at']!=expected or expected>end:raise ValueError('CHECKPOINT_SEQUENCE')
            expected+=900;rows.append(row)
        filters.update(block['filters'])
    return rows,filters

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--max-seconds',type=int,default=1800)
    a=p.parse_args(argv)
    if not 30<=a.max_seconds<=3600:p.error('max-seconds 30..3600')
    bars,info=load_history(a.csv);stamp=lambda k:int(datetime.fromisoformat(PROTOCOL[k].replace('Z','+00:00')).timestamp())
    start=stamp('start_utc');end=stamp('end_exclusive_utc');total=(end-start)//900;split=start+(total*7//10)*900
    if bars[0].time!=start-4160*900 or bars[-1].time+900!=end:p.error('EXACT_COVERAGE_REQUIRED')
    fingerprint=digest(dict(data=info['sha256'],code=code_hashes(),protocol=PROTOCOL))
    checkpoint=a.output.with_suffix('.checkpoint.gz');rows=[];filters=Counter()
    if checkpoint.exists():rows,filters=read_checkpoint(checkpoint,fingerprint,start,end)
    else:checkpoint.write_bytes(gzip.compress(canonical(dict(fingerprint=fingerprint))+b'\n',mtime=0))
    first=rows[-1]['closed_at']+900 if rows else start+900;jobs=[]
    while first<=end:
        last=min(end,(first//14400+1)*14400-900);jobs.append((first,last));first=last+900
    began=time.monotonic()
    with ProcessPoolExecutor(max_workers=2,initializer=init_worker,initargs=(str(a.csv),)) as pool:
        queue=deque();iterator=iter(jobs)
        for _ in range(2):
            job=next(iterator,None)
            if job:queue.append(pool.submit(analyze_group,job))
        while queue:
            block=queue.popleft().result()
            with checkpoint.open('ab') as f:f.write(gzip.compress(canonical(block)+b'\n',mtime=0));f.flush();os.fsync(f.fileno())
            rows.extend(block['rows']);filters.update(block['filters'])
            if len(rows)%384<16:print('closed candles',len(rows),'/',total,flush=True)
            if time.monotonic()-began>a.max_seconds:
                for future in queue:future.cancel()
                print('BUDGET_REACHED: resume exact command',flush=True);return
            job=next(iterator,None)
            if job:queue.append(pool.submit(analyze_group,job))
    if len(rows)!=total:raise ValueError('INCOMPLETE')
    runs=[]
    for variant in VARIANTS:
        r=replay(bars,selected_rows(rows,variant),start,split,'AURA42','development');r['variant']=variant;runs.append(r)
        print('development done',variant,flush=True)
    candidates=[r for r in runs if r['variant'] in PROFILES and eligible(r)]
    winner=max(candidates,key=lambda r:D(r['metrics']['expectancy']))['variant'] if candidates else None
    selection=dict(winner=winner,eligible=[r['variant'] for r in candidates],basis='DEVELOPMENT_ONLY',
        frozen_before_validation_metrics=True,protocol_hash=digest(PROTOCOL),source_sha256=info['sha256'],
        frozen_at_utc=datetime.now(timezone.utc).isoformat(),development_metrics={r['variant']:r['metrics'] for r in runs})
    selection_path=a.output.with_suffix('.selection.json');selection_path.write_bytes(canonical(selection));selection_hash=digest(selection)
    print('SELECTION_FROZEN',winner,selection_hash,flush=True)
    for variant in VARIANTS:
        for label,lo,hi in (('validation',split,end),('full_6m',start,end)):
            r=replay(bars,selected_rows(rows,variant),lo,hi,'AURA42',label);r['variant']=variant;runs.append(r)
        print('validation/full done',variant,flush=True)
    validation=next((r for r in runs if r['variant']==winner and r['split']=='validation'),None)
    report=dict(version=PROTOCOL['version'],symbol='BTCUSDT',research_only=True,activation_available=False,real_money_execution='DISABLED',
        status='VALIDATION_CRITERIA_MET_RESEARCH_ONLY' if validation and eligible(validation) else 'NO_ROBUST_ADVANTAGE',
        source=info,code_hashes=code_hashes(),protocol=PROTOCOL,protocol_hash=digest(PROTOCOL),policy=POLICY,
        start=start,split_at=split,end_exclusive=end,closed_candles_processed=total,
        filter_counts=dict(filters),filter_scope='ALL_FULL_6M_CANDLES; NONEXCLUSIVE PER SCENARIO/SIDE; ONLY_BLOCKER MEANS ALL OTHER SETUP GATES PASS',
        development_selection=selection,selection_hash=selection_hash,runs=runs,
        limitations=PROTOCOL['limitations']+['Full history rows and scenario-only portfolios are descriptive; not independent confirmations.',
            'Ideal every-candle replay is not live Render execution; OHLC SL-first/adverse gaps; no funding, borrow or market impact.',
            'New 30% validation overlaps previously examined dates; insufficient for a blind robustness claim.',
            'Sharpe undefined below 20 trades/30 daily returns; final positions marked, never force-closed.'])
    report['checksum']=digest(report);raw=canonical(report)
    if len(raw)>16*1024*1024:raise ValueError('REPORT_LIMIT')
    a.output.write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
    print(json.dumps(dict(status=report['status'],winner=winner,runs=[dict(variant=r['variant'],split=r['split'],metrics=r['metrics']) for r in runs])),flush=True)

if __name__=='__main__':main()
