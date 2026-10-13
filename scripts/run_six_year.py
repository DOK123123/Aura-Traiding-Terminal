"""Offline six-year segmented, censored research; checkpoint every completed job."""
import argparse
from bisect import bisect_left
from collections import Counter
from dataclasses import replace
from decimal import Decimal as D
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.models import Baseline,canonical,money,precise,text
from app.lab.execution import simulate,metrics
from scripts.lab3_history import load_years
from scripts.lab3_strategies import generate,labels
from scripts.run_lab3 import audit_trailing,stamp
from scripts.research_inverse import invert,economy,verify_accounting
from scripts.research_candidates import registry
from scripts.run_research_cycle import load_protocol
from scripts.offline_fixed_strategies import monthly,buy_hold,event_month

PROTOCOL=ROOT/'docs/AURA_LAB31_PROTOCOL.json'
PROTOCOL_SHA='e5892355aad45d1e4f31c7609bcba50b820fc9629d16a1b6264a8679f40948b2'


def segments(bars):
    start=0;result=[]
    for i in range(1,len(bars)):
        if bars[i].time-bars[i-1].time!=900:result.append(bars[start:i]);start=i
    result.append(bars[start:]);return result


@precise
def censor_gap(outcome):
    """Known closed-trade conditional ledger; preserve unknown position separately."""
    position=outcome.get('open_position')
    if position is None:return None
    restored=money(D(outcome['equity_curve'][-1]['balance'])+D(position['entry_fee']))
    for point in outcome['equity_curve']:
        if point['time']>=position['entry_time']+900:
            point.update(balance=text(restored),equity=text(restored))
    return dict(position=position,exit_price=None,realized_pnl=None,
                reason='UNRESOLVED_DATA_GAP',known_entry_fee=position['entry_fee'],
                conditional_ledger_restores_entry_fee=True)


@precise
def period_job(parts,streams,regimes,start,end,baseline,deadline):
    balance=D(baseline.starting_balance);trades=[];curve=[];unknown=[];rejected=Counter();signals=Counter();used=0;warmup_skipped=0;audited=0;halted=False
    for part,(decisions,trail),label in zip(parts,streams,regimes):
        times=[b.time for b in part];left=bisect_left(times,start);right=bisect_left(times,end)
        if left==right:continue
        begin=max(left,1000);warmup_skipped+=max(0,min(right,1000)-left)
        if begin>=right:continue
        if balance<D('.01'):halted=True;break
        b=replace(baseline,starting_balance=text(balance))
        # Only a declared PERIOD boundary has known terminal liquidation.
        gap_end=right==len(part) and part[-1].time+900<end
        value=simulate(part,decisions,begin,right,900,b,deadline,trailing_atr=trail,close_at_end=not gap_end)
        excluded=censor_gap(value) if gap_end else None
        if excluded is not None:
            excluded.update(last_observed_close_time=part[right-1].time+900);unknown.append(excluded)
        value['metrics']=metrics(value['trades'],value['equity_curve'],b)
        audited+=audit_trailing(value,part,trail,b) if trail is not None else verify_accounting(value,part,b)
        balance=D(value['equity_curve'][-1]['balance'])
        for trade in value['trades']:
            trade['regime']=label[bisect_left(times,trade['signal_time']-900)]
        trades.extend(value['trades']);curve.extend(value['equity_curve']);rejected.update(value['rejections'])
        signals.update(d.direction or 'WAIT' for d in decisions[begin:right]);used+=right-begin
    if not curve:curve=[dict(time=start,balance=baseline.starting_balance,equity=baseline.starting_balance),dict(time=end,balance=baseline.starting_balance,equity=baseline.starting_balance)]
    outcome=dict(metrics=metrics(trades,curve,baseline),trades=trades,equity_curve=curve,
        unresolved_positions=unknown,excluded_known_entry_fees=text(sum((D(x['known_entry_fee']) for x in unknown),D(0))),
        full_period_execution_valid=not unknown and not halted,statistics_scope='CONDITIONAL_CLOSED_TRADES' if unknown else 'SEGMENT_RESET_POLICY_OBSERVED_CURVE',
        gap_observation_drawdown_is_lower_bound=True,signals=dict(signals),rejections=dict(rejected),
        processed_candles=used,warmup_skipped=warmup_skipped,audited_trades=audited,halted_below_engine_minimum_balance=halted)
    allbars=[b for part in parts for b in part if start<=b.time<end]
    outcome['monthly']=monthly(outcome,allbars,0,len(allbars),baseline)
    outcome['yearly']=[dict(year=year,**economy([t for t in trades if event_month(t['exit_time'],t['exit_reason'] not in ('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE','STRATEGY_EXIT_NEXT_OPEN'))[:4]==year])) for year in sorted({event_month(b.time)[:4] for b in allbars})]
    outcome['direction']={side:economy([t for t in trades if t['direction']==side]) for side in ('LONG','SHORT')}
    outcome['regimes']={r:economy([t for t in trades if t['regime']==r]) for r in sorted({t['regime'] for t in trades})}
    outcome['economics']=economy(trades)
    return outcome


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);parser.add_argument('--work-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--max-seconds-job',type=int,default=900)
    args=parser.parse_args(argv)
    if args.output.exists() or not 1<=args.max_seconds_job<=900:parser.error('New output; job budget1..900')
    raw=PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA:raise ValueError('Frozen gap protocol changed')
    protocol=json.loads(raw)
    if hashlib.sha256((ROOT/'docs/AURA_LAB3_PROTOCOL.json').read_bytes()).hexdigest()!=protocol['frozen_strategy_protocol_sha256']:raise ValueError('Strategy protocol changed')
    bars,quality=load_years(args.archive,allow_gaps=True)
    if quality['bundle_sha256']!=protocol['archive_sha256']:raise ValueError('Frozen archive mismatch')
    args.work_dir.mkdir(parents=True,exist_ok=True);parts=segments(bars)
    paths=[Path(__file__),PROTOCOL,ROOT/'docs/AURA_LAB3_PROTOCOL.json',ROOT/'scripts/lab3_history.py',ROOT/'scripts/lab3_strategies.py',ROOT/'scripts/run_lab3.py',ROOT/'scripts/research_candidates.py',ROOT/'scripts/research_inverse.py',ROOT/'scripts/offline_fixed_strategies.py',ROOT/'app/indicators.py']+sorted((ROOT/'app/lab').glob('*.py'))
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    signature=hashlib.sha256(canonical(dict(software=hashes,protocol=protocol))).hexdigest()
    regimes=[labels(p) for p in parts];results=[]
    candidates=registry(load_protocol())
    for name in [*'ABCDE',*[f'OLD_{n}_{v}' for n in 'ABCD' for v in ('ORIGINAL','I','II')]]:
        streams=[]
        for part in parts:
            if name.startswith('OLD_'):
                _,n,v=name.split('_');streams.append((invert(candidates[n].generate(part),v),None))
            else:streams.append(generate(part,name))
        for scenario,(fees,slip) in protocol['scenarios'].items():
            baseline=replace(Baseline(),fee_bps=fees,slippage_bps=slip)
            for period,(start,end) in protocol['periods'].items():
                key=f'{name}-{scenario}-{period}';checkpoint=args.work_dir/(key+'.json');ledger=args.work_dir/(key+'.journal.json.gz')
                if checkpoint.exists():
                    row=json.loads(checkpoint.read_bytes())
                    if row['signature']!=signature or hashlib.sha256(ledger.read_bytes()).hexdigest()!=row['ledger_gzip_sha256']:raise ValueError('Checkpoint/source mismatch')
                else:
                    outcome=period_job(parts,streams,regimes,stamp(start),stamp(end),baseline,time.monotonic()+args.max_seconds_job)
                    ledger_bytes=canonical(outcome.pop('trades'))
                    compressed=gzip.compress(ledger_bytes,mtime=0);ledger.write_bytes(compressed)
                    curve=outcome.pop('equity_curve')
                    row=dict(strategy=name,scenario=scenario,period=period,baseline=baseline.data(),signature=signature,
                        ledger_filename=ledger.name,ledger_gzip_sha256=hashlib.sha256(compressed).hexdigest(),ledger_uncompressed_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
                        equity_full_sha256=hashlib.sha256(canonical(curve)).hexdigest(),
                        equity_daily=[p for i,p in enumerate(curve) if i in (0,len(curve)-1) or p['time']%86400==0],**outcome)
                    tmp=checkpoint.with_suffix('.partial');tmp.write_bytes(canonical(row));tmp.replace(checkpoint)
                results.append(row)
                print(key,row['metrics']['trades'],row['metrics']['net_profit'],'excluded',len(row['unresolved_positions']),flush=True)
    benchmarks=[]
    for period,(start,end) in protocol['periods'].items():
        chosen=[b for b in bars if stamp(start)<=b.time<stamp(end)]
        for cap in ('2000','10000'):
            value=buy_hold(chosen,0,len(chosen),Baseline(),cap)
            benchmarks.append(dict(period=period,allocation=cap,metrics=value['metrics'],risk_equivalent=False,full_gap_drawdown_verified=False))
    report=dict(status='COMPLETE',protocol=protocol,protocol_sha256=PROTOCOL_SHA,dataset_quality=quality,software_sha256=hashes,
        results=results,buy_hold=benchmarks,journals_scope='Local work-dir full compressed ledgers; hashes in report; no raw archive in git',
        safety=dict(real_money_execution='DISABLED',auto_activation=False,private_clients=False),
        audit_trades=sum(r['audited_trades'] for r in results))
    args.output.write_bytes(canonical(report));print('COMPLETE',report['audit_trades'])


if __name__=='__main__':main()
