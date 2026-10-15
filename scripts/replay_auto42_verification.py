"""Offline-only exact Auto42 strategy/engine replay, with bounded causal memoization.

No Service configuration, DB, HTTP client, owner credentials or live account calls.
Prices are loaded exclusively by the existing validated Binance CSV importer.
"""
import argparse
from bisect import bisect_left
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch

from app.lab.local_csv import load_binance_csv
from app.lab.models import digest,text,money,canonical
from app.lab.series import higher
import app.intelligence.market_context as mc
from app.automated.strategy import strategy,PARAMETERS
from app.automated.engine import initial,advance,mark,validate,DemoError,POLICY,VERSION

NATIVE_STATES=mc.segment_states
FILES=('app/automated/engine.py','app/automated/strategy.py','app/automated/service.py',
       'app/automated/storage.py','app/intelligence/market_context.py','research/market_intelligence/structure.py',
       'app/intelligence/patterns.py','app/lab/models.py','app/lab/indicators.py','app/lab/series.py','app/lab/execution.py')
ROOT=Path(__file__).resolve().parents[1]

def code_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

class PrefixCache:
    """Reuse PURE causal production states for prefixes of one UTC four-hour window.

    A state is never returned after the caller's closed-candle cutoff. All raw
    strategy inputs remain the caller's prefix. Exact native equality is tested.
    No cache is installed in the running web app; this is offline process-local.
    """
    def __init__(self,bars):
        self.frames={step:(bars if step==900 else higher(bars,step)) for step in (900,3600,14400)}
        self.states={step:NATIVE_STATES(frame,step) for step,frame in self.frames.items()}
    def states_for(self,bars,step=900,*,deadline=None):
        if bars!=self.frames[step][:len(bars)]:raise ValueError('PREFIX_CACHE_MISMATCH')
        return self.states[step][:len(bars)]
    @contextmanager
    def installed(self):
        with patch.object(mc,'segment_states',self.states_for):yield

def snapshot(window,at):
    # Same production assembly, event truncation, rolling starts and MTF alignment.
    value=mc.analyze_window(window,at+30)['15m']
    value.update(freshness=dict(status='FRESH'),fetched_at=at+30,analyzed_at=at+30)
    return value

_BARS=None
_TIMES=None

def init_worker(path):
    global _BARS,_TIMES
    _BARS,_=load_binance_csv(Path(path));_TIMES=[b.time for b in _BARS]

def analyze_group(job):
    first,last=job;start=first//14400*14400-4160*900
    begin=bisect_left(_TIMES,start);end=bisect_left(_TIMES,last)
    full=_BARS[begin:end]
    cache=PrefixCache(full);result=[]
    with cache.installed():
        for at in range(first,last+1,900):
            window=full[:bisect_left(_TIMES,at)-begin]
            try:decision=strategy(snapshot(window,at),window,at+30)
            except DemoError as exc:decision=dict(direction=None,reason=exc.code,error=exc.code)
            result.append(dict(closed_at=at,decision=decision))
    return result

def replay(bars,rows,start,end,days):
    times=[b.time for b in bars];i=bisect_left(times,start);previous=bars[i-1]
    s=initial(start,epoch='HISTORICAL_REPLAY_ONLY_'+str(days));s.update(mode='ON',watermark=start,last_bar_hash=digest(previous.data()))
    mark(s,previous,start);counts=Counter();waits=Counter();rejections=Counter();execution_errors=Counter();events=[];equity=[];signals=0
    for row in rows:
        at=row['closed_at']
        if not start<at<=end:continue
        decision=row['decision'];direction=decision.get('direction');counts[direction or 'WAIT']+=1
        if direction:signals+=1
        else:waits[decision['reason']]+=1
        k=bisect_left(times,at);window=bars[bisect_left(times,at//14400*14400-4160*900):k]
        if decision.get('error'):
            # Mirrors controller failure handling: no fill or watermark movement.
            s.update(pending=None,last_error=decision['error'],mode='PAUSED');execution_errors[decision['error']]+=1
            continue
        try:s,new=advance(s,window,decision,at+30)
        except DemoError as exc:execution_errors[exc.code]+=1;continue
        events.extend(new)
        for e in new:
            if e['kind']=='REJECT':rejections[e['payload']['reason']]+=1
            if e['kind']=='DECISION' and direction and e['payload']['reason']!='SIGNAL_QUEUED_NEXT_OPEN':rejections[e['payload']['reason']]+=1
        equity.append(dict(closed_at=at,equity=s['equity'],balance=s['balance']))
    validate(s)
    closes=[e['payload'] for e in events if e['kind']=='CLOSE'];opens=[e['payload'] for e in events if e['kind']=='OPEN']
    months={}
    prior=D(10000)
    for x in equity:
        month=datetime.fromtimestamp(x['closed_at']-1,timezone.utc).strftime('%Y-%m')
        r=months.setdefault(month,dict(starting_equity=text(prior),ending_equity=None,trades=0,net_realized_pnl='0'))
        r['ending_equity']=x['equity'];prior=D(x['equity'])
    for t in closes:
        month=datetime.fromtimestamp(min(t['exit_time'],end-1),timezone.utc).strftime('%Y-%m');r=months[month]
        r['trades']+=1;r['net_realized_pnl']=text(D(r['net_realized_pnl'])+D(t['realized_pnl']))
    return dict(days=days,start=start,end_exclusive=end,evaluated_candles=sum(counts.values()),expected_candles=(end-start)//900,
        signal_counts=dict(counts),valid_signals=signals,non_signal_filter_counts=dict(waits),execution_rejection_reasons=dict(rejections),rejected_signals=sum(rejections.values()),
        opened=len(opens),closed=len(closes),tp_exits=sum(t['exit_reason'].startswith('TAKE_PROFIT') for t in closes),
        sl_exits=sum(t['exit_reason'].startswith('STOP') for t in closes),fees=s['fees'],slippage=s['slippage'],
        realized_net_pnl=s['realized_pnl'],net_pnl_mark_to_market=text(money(D(s['equity'])-10000)),
        return_pct=text(money((D(s['equity'])/10000-1)*100)),max_drawdown_pct=s['max_drawdown_pct'],
        win_rate=text(money(D(s['wins'])/s['trades']*100)) if s['trades'] else None,
        profit_factor=text(money(D(s['gross_profit'])/D(s['gross_loss']))) if D(s['gross_loss']) else None,
        final_mode=s['mode'],final_balance=s['balance'],final_equity=s['equity'],remaining_position=s['position'],pending=s['pending'],
        execution_errors=dict(execution_errors),monthly=months,trades=closes,open_events=opens,equity_curve=equity,
        status='PASS' if sum(counts.values())==(end-start)//900 and not execution_errors else 'INCONCLUSIVE')

def read_checkpoint(path,fingerprint,start,end):
    """Reject completed corrupt blocks; discard only an incomplete final write."""
    if path.stat().st_size>32*1024*1024:raise ValueError('CHECKPOINT_LIMIT')
    raw=path.read_bytes();complete=raw.rfind(b'\n')+1
    lines=raw[:complete].splitlines()
    if not lines or json.loads(lines[0])!={'fingerprint':fingerprint}:raise ValueError('CHECKPOINT_IDENTITY')
    result=[];expected=start+900
    for line in lines[1:]:
        block=json.loads(line)
        if not isinstance(block,list) or not 1<=len(block)<=16:raise ValueError('CHECKPOINT_BLOCK')
        for row in block:
            if (type(row.get('closed_at')) is not int or row['closed_at']!=expected or expected>end
                    or not isinstance(row.get('decision'),dict)):raise ValueError('CHECKPOINT_SEQUENCE')
            expected+=900;result.append(row)
    if complete!=len(raw):
        with path.open('r+b') as f:f.truncate(complete)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,choices=(1,2),default=2);p.add_argument('--max-seconds',type=int,default=1500)
    args=p.parse_args(argv)
    if not 30<=args.max_seconds<=3600:p.error('max-seconds must be 30..3600')
    bars,info=load_binance_csv(args.csv);end=bars[-1].time+900;start=end-90*86400
    if start//14400*14400-4160*900<bars[0].time:p.error('90 days plus exact production warm-up unavailable')
    fingerprint=digest(dict(data=info['sha256'],code=code_hashes(),parameters=PARAMETERS,policy=POLICY,end=end))
    checkpoint=args.output.with_suffix('.checkpoint.jsonl');rows=[]
    if checkpoint.exists():
        try:rows=read_checkpoint(checkpoint,fingerprint,start,end)
        except (ValueError,KeyError,TypeError):p.error('checkpoint is corrupt or does not match data/code/configuration')
    else:
        checkpoint.parent.mkdir(parents=True,exist_ok=True);checkpoint.write_bytes(canonical(dict(fingerprint=fingerprint))+b'\n')
    first=rows[-1]['closed_at']+900 if rows else start+900;jobs=[]
    while first<=end:
        last=min(end,(first//14400+1)*14400-900);jobs.append((first,last));first=last+900
    began=time.monotonic()
    from collections import deque
    import os
    with ProcessPoolExecutor(max_workers=args.workers,initializer=init_worker,initargs=(str(args.csv),)) as pool:
        queue=deque();iterator=iter(jobs)
        for _ in range(args.workers):
            job=next(iterator,None)
            if job:queue.append(pool.submit(analyze_group,job))
        while queue:
            block=queue.popleft().result()
            with checkpoint.open('ab') as f:
                f.write(canonical(block)+b'\n');f.flush();os.fsync(f.fileno())
            rows.extend(block)
            if len(rows)%384<16:print('closed candles',len(rows),flush=True)
            if time.monotonic()-began>args.max_seconds:
                for future in queue:future.cancel()
                print('BUDGET_REACHED — resume with same command',flush=True);break
            job=next(iterator,None)
            if job:queue.append(pool.submit(analyze_group,job))
    complete=bool(rows) and rows[-1]['closed_at']==end
    periods=[]
    if complete:
        for days in (7,30,90):periods.append(replay(bars,rows,end-days*86400,end,days))
    result=dict(status='PASS' if complete and all(r['status']=='PASS' for r in periods) else 'INCONCLUSIVE',
        evidence_type='HISTORICAL_REPLAY_NOT_LIVE',version=VERSION,code_hashes=code_hashes(),fingerprint=fingerprint,
        source=dict(sha256=info['sha256'],count=info['count'],start=info['start'],end_exclusive=info['end_exclusive'],
            provenance=info['source_claim'],identity=mc.SOURCE),policy=POLICY,strategy_parameters=PARAMETERS,
        production_window='UTC_4H_BOUNDARY_MINUS_4160_15M_BARS',closed_candles_processed=len(rows),
        cache='PURE_PRODUCTION_PREFIX_STATES; EXACT_NATIVE_EQUIVALENCE_TESTED; NOT_INSTALLED_IN_WEB_APP',
        warmup_minimum_bars=4160,live_autonomy='NOT_TESTED',periods=periods,
        limitations=['Local supplied CSV provenance is not independently verified against Binance archive checksums.',
            'Ideal every-closed-candle scheduler replay; not a reproduction of Render network/sleep or Supabase latency.',
            'Strategy is EXPERIMENTAL / NO_EDGE_FOUND; historical results do not prove forward profitability.',
            'A valid signal without a next available closed execution candle remains pending, never force-closed.'])
    args.output.write_bytes(canonical(result));print(json.dumps(dict(status=result['status'],candles=len(rows),periods=[{k:v for k,v in r.items() if k not in ('trades','open_events','equity_curve')} for r in periods]),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
