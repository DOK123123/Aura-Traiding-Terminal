"""Isolated 30/90-day production Paper replay; public history is explicit opt-in.

No strategy fitting, live database, credentials or private exchange clients.
This models uninterrupted delivery into a fresh virtual ledger, not live Render.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts import diagnose_aura_auto as core
from app.paper.models import Settings, money
from app.patterns.config import PatternConfig
from app.patterns.signals import wilson_lower
import app.paper.signals as production_signals


def configuration(path=None):
    if path is None:
        return Settings(),'PAPER_SETTINGS','documented defaults; live settings not verified',None
    raw=path.read_bytes()
    if len(raw)>16384:
        raise ValueError('Configuration exceeds bound')
    data=json.loads(raw)
    if not isinstance(data,dict) or set(data)!={'settings','fallback_policy'}:
        raise ValueError('Only public paper settings and policy are accepted')
    policy=data['fallback_policy']
    if policy not in ('SKIP','PAPER_SETTINGS'):
        raise ValueError('Invalid paper policy')
    return Settings.from_dict(data['settings']),policy,'supplied snapshot; not verified against Render',hashlib.sha256(raw).hexdigest()


def evidence(result):
    """Explain the unchanged production decision; never select or alter a signal."""
    config=PatternConfig()
    main=result['outcomes'][str(config.decision_horizon)]
    n=result['historical_matches']
    side='LONG' if (main['up_pct'] or 0)>=(main['down_pct'] or 0) else 'SHORT'
    sign=1 if side=='LONG' else -1
    c=result['confidence_components']
    raw=100*c['sample']*c['similarity']*c['directional_rate']*(.5+.5*c['consistency'])*c['volatility']*(.75+.25*c['mtf'])
    failed=[]
    for name,passed in (
        ('MINIMUM_SAMPLE',n>=config.minimum_sample),
        ('DIRECTIONAL_RATE',result['directional_rate_pct']>=config.signal_threshold),
        ('WILSON',wilson_lower(main['up'] if side=='LONG' else main['down'],n)>.5),
        ('CONFIDENCE',raw>=config.minimum_confidence),
        ('EXPECTED_MOVE_COST',sign*(main['average_move_pct'] or 0)>config.round_trip_cost_bps/100),
        ('MEDIAN_DIRECTION',sign*(main['median_move_pct'] or 0)>0),
        ('HORIZON_CONSISTENCY',c['consistency']>=.5)):
        if not passed:failed.append(name)
    if result['signal']!=(side if not failed else 'WAIT'):
        raise ValueError('Diagnostic gate explanation disagrees with production signal')
    return dict(candidate=side if n else None,failed=failed,confidence_raw=raw)


def month(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m')


def monthly(result,candles,start,end,settings):
    """Candles use open UTC month; decisions/fills use their close/event UTC month."""
    names={month(c.time*1000) for c in candles if start<=c.time<end}
    names.update(month(d['timestamp']) for d in result['decisions'])
    names.update(month(t[k]) for t in result['trades'] for k in ('entry_time','exit_time') if t.get(k) is not None)
    curve=result['equity_curve']
    rows=[]
    with localcontext() as context:
        context.prec=64
        for name in sorted(names):
            decisions=[d for d in result['decisions'] if month(d['timestamp'])==name]
            entries=[t for t in result['trades'] if month(t['entry_time'])==name]
            closed=[t for t in result['trades'] if t['status']=='CLOSED' and month(t['exit_time'])==name]
            pnl=[Decimal(t['realized_pnl']) for t in closed]
            profit=sum((p for p in pnl if p>0),Decimal(0));loss=-sum((p for p in pnl if p<0),Decimal(0))
            fees=sum((Decimal(t['entry_fee']) for t in entries),Decimal(0))+sum((Decimal(t['exit_fee']) for t in closed),Decimal(0))
            points=[p for p in curve if month(p['recorded_at'])==name]
            before=[p for p in curve if month(p['recorded_at'])<name]
            baseline=before[-1] if before else dict(balance=str(settings.starting_balance),equity=str(settings.starting_balance))
            dd=None
            if baseline['equity'] is not None and all(p['equity'] is not None for p in points):
                peak=Decimal(baseline['equity']);dd=Decimal(0)
                for point in points:
                    value=Decimal(point['equity']);peak=max(peak,value)
                    if peak>0:dd=max(dd,(peak-value)/peak*100)
            last=points[-1] if points else baseline
            rows.append(dict(month=name,candles=sum(start<=c.time<end and month(c.time*1000)==name for c in candles),
                signals=dict(Counter(d['signal_result'] for d in decisions)),
                decisions=len(decisions),entries=len(entries),closed_trades=len(closed),
                rejections=dict(Counter(d['rejection_reason'] for d in decisions if d['rejection_reason'])),
                win_rate=str(money(Decimal(sum(p>0 for p in pnl))/len(pnl)*100)) if pnl else None,
                net_realized_pnl=str(sum(pnl,Decimal(0))),fees_charged=str(fees),
                profit_factor=str(money(profit/loss)) if loss else None,
                profit_factor_status='DEFINED' if loss else 'NO_LOSSES' if profit else 'UNDEFINED',
                maximum_drawdown_pct=None if dd is None else str(money(dd)),
                opening_balance=baseline['balance'],closing_balance=last['balance'],
                balance_change=str(Decimal(last['balance'])-Decimal(baseline['balance'])),
                opening_equity=baseline['equity'],closing_equity=last['equity']))
    return rows


async def measured_replay(candles,start,end,settings,policy,budget):
    gates=Counter();candidates=Counter();per_month={};observed=0
    original=production_signals.evaluate
    def recording(*args,**kwargs):
        nonlocal observed
        result=original(*args,**kwargs) # Unchanged production evaluator; one call per candle.
        info=evidence(result)
        observed+=1
        if info['candidate']:candidates[info['candidate']]+=1
        if result['signal']=='WAIT':gates.update(info['failed'])
        name=month(result['as_of']*1000)
        bucket=per_month.setdefault(name,Counter())
        if result['signal']=='WAIT':bucket.update(info['failed'])
        return result
    # CLI-only temporary observation. Never import/run this inside a live web worker.
    with patch.object(production_signals,'evaluate',recording):
        result=await core.replay(candles,start,end,max_seconds=budget,settings=settings,fallback_policy=policy)
    if observed!=result['observed_candles']:
        raise ValueError('Incomplete evidence observation')
    result.update(candidate_directions=dict(candidates),strategy_gate_failures=dict(gates),
                  strategy_gates_by_month={k:dict(v) for k,v in per_month.items()},
                  monthly=monthly(result,candles,start,end,settings))
    stats=result['statistics']
    result['profit_factor_status']='DEFINED' if stats['profit_factor'] is not None else 'NO_LOSSES' if Decimal(stats['gross_profit'])>0 else 'UNDEFINED'
    return result


async def run(args):
    settings,policy,source,config_hash=configuration(args.paper_config)
    report=dict(symbol='BTCUSDT',timeframe='15m',production_config=PatternConfig().model_dump(),
                paper_settings=settings.to_dict(),fallback_policy=policy,settings_source=source,
                configuration_sha256=config_hash,software_sha256=core.code_hashes(),
                diagnostic_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(core.__file__))},
                replay_model='COUNTERFACTUAL_PRODUCTION_PAPER_REPLAY',results=[],
                limitations=['Render persisted settings/history/positions and original archive are unknown.',
                    '30/90 runs each start a fresh ledger; monthly rows belong to that ledger, not independent backtests.',
                    'Sequential verified candle-close replay assumes every candle is delivered without outages.',
                    'Existing paper fees/stops/gaps are used; no slippage/spread/funding realism is added.',
                    'Gate failure counts overlap; similarity/purge exclusions are not reconstructed as invented counts.',
                    'Monthly candles use open UTC; decisions and cashflows use close/event UTC.',
                    'Month realized PnL includes both trade fees; charged fees and balance changes follow event time.',
                    'No force-close at the end: open trades, balance and liquidation equity stay distinct.',
                    'Long replay is CPU intensive; run separately from Render/web workers.'])
    if args.fetch_dir is not None:
        args.fetch_dir.mkdir(parents=True,exist_ok=False)
    blocked=False
    for days in args.periods:
        start,end=core.period(args.end_date,days)
        row=core.manifest(start,end,args.warmup)
        row.update(days=days,settings=settings.to_dict(),fallback_policy=policy,settings_source=source)
        if blocked:
            row.update(status='NOT_RUN',reason='Previous stage did not complete')
        elif args.snapshot is None and args.fetch_dir is None:
            row.update(status='NO_HISTORY',reason='No verified public-market snapshot supplied')
        else:
            try:
                path=args.snapshot or args.fetch_dir/f'BTCUSDT-15m-{args.end_date or "utc-today"}-{days}d.json'
                if args.fetch_dir is not None:
                    await core.fetch_snapshot(path,start,end,args.warmup)
                candles,digest,excluded=core.load_snapshot(path,start,end,args.warmup)
                row.update(snapshot_sha256=digest,excluded_candles=excluded,
                    selected_dataset_sha256=hashlib.sha256(json.dumps([core.asdict(c) for c in candles],sort_keys=True).encode()).hexdigest(),
                    warmup_actual=args.warmup)
                row.update(await measured_replay(candles,start,end,settings,policy,args.max_seconds))
            except Exception as error:
                row.update(status='INCOMPLETE',error_type=type(error).__name__)
                blocked=True # Stop before 90-day fetch/compute if the first stage failed.
        report['results'].append(row)
    report['actual_backtest_performed']=any(r['status']=='COMPLETE' for r in report['results'])
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-date')
    parser.add_argument('--periods',type=int,nargs='+',default=[30,90],choices=[30,90])
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--snapshot',type=Path)
    group.add_argument('--fetch-dir',type=Path,help='Explicit bounded public GET; create a new directory')
    parser.add_argument('--warmup',type=int,default=10000)
    parser.add_argument('--paper-config',type=Path,help='Public settings/policy JSON, never credentials')
    parser.add_argument('--max-seconds',type=int,default=600)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.periods not in ([30],[30,90]):parser.error('Run 30 first, optionally followed by 90')
    if not 500<=args.warmup<=core.MAX_CANDLES-8640 or not 1<=args.max_seconds<=86400:
        parser.error('Warm-up/budget outside bounded research limits')
    if args.output.exists():parser.error('Output must be a new file')
    if args.fetch_dir is not None and args.fetch_dir.exists():parser.error('Fetch directory must be new')
    # Validate configuration/date before network, simulated activation or output writes.
    core.period(args.end_date,30)
    report=asyncio.run(run(args))
    with args.output.open('x') as out:json.dump(report,out,indent=2,ensure_ascii=False,allow_nan=False)
    print(' '.join(f"{r['days']}d={r['status']}" for r in report['results']))
    return 0 if all(r['status']=='COMPLETE' for r in report['results']) else 2


if __name__=='__main__':raise SystemExit(main())
