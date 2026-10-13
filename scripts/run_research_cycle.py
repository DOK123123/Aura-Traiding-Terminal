"""Offline frozen research cycle. Uses existing Lab execution; no live integration."""
import argparse
from collections import Counter
from dataclasses import replace
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from app.lab.models import Baseline,canonical,money,precise,text
from app.lab.execution import simulate,metrics
from app.patterns.config import PatternConfig
from scripts.offline_fixed_strategies import dataset,monthly,buy_hold,START,SPLIT,END,WARMUP
from scripts.research_candidates import registry,regimes

PROTOCOL=ROOT/'docs/RESEARCH_CYCLE_PROTOCOL.json'
PROTOCOL_HASH='6eabecd3300e203d5418538be0b71bd2529d6424b71e89a6e10f5e59aa9cf5a3'


def load_protocol():
    raw=PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_HASH:raise ValueError('Frozen research protocol changed')
    return json.loads(raw)


def native_reference(csv_meta):
    path=ROOT/'docs/FIXED_STRATEGY_RESULTS.json'
    previous=json.loads(path.read_bytes())
    native=previous['historical_pattern']
    if (previous['status']!='COMPLETE' or previous['csv']['sha256']!=csv_meta['sha256']
            or canonical(native['production_config'])!=canonical(PatternConfig().model_dump())
            or previous['test_candles']!=5856 or native['warmup_test']!=8832):
        raise ValueError('Native reference data/config mismatch')
    for name,digest in native['software_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Native reference source version changed')
    return dict(**native,reference_report='docs/FIXED_STRATEGY_RESULTS.json',
                reference_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                provenance='REUSED_VERIFIED_ACTUAL_PRODUCTION_REPLAY; NOT REEXECUTED IN THIS TASK')


@precise
def regime_summary(trades,labels,bars):
    by_time={b.time:label for b,label in zip(bars,labels)}
    result={}
    for regime in ('RANGE','TRANSITION','TREND','UNAVAILABLE'):
        subset=[t for t in trades if by_time.get(t['signal_time']-900,'UNAVAILABLE')==regime]
        pnl=[D(t['realized_pnl']) for t in subset]
        win=sum((p for p in pnl if p>0),D(0));loss=-sum((p for p in pnl if p<0),D(0))
        result[regime]=dict(trades=len(subset),net_pnl=text(sum(pnl,D(0))),
            expectancy=text(money(sum(pnl,D(0))/len(pnl))) if pnl else None,
            win_rate=text(money(D(sum(p>0 for p in pnl))/len(pnl)*100)) if pnl else None,
            profit_factor=text(money(win/loss)) if loss else None,
            interpretation='Entry-time descriptive attribution, not independent regime backtests')
    return result


@precise
def open_position_audit(run,bars,begin,end):
    # Segment liquidation means final open count zero; still expose monthly carry.
    states=[]
    for row in run['monthly']:
        selected=[b for b in bars[begin:end] if time_month(b.time)==row['month']]
        cutoff=selected[-1].time+900
        opening_exits=('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE','STRATEGY_EXIT_NEXT_OPEN')
        carries=[t for t in run['trades'] if t['entry_time']<cutoff and
                 (t['exit_time']>cutoff or (t['exit_time']==cutoff and t['exit_reason'] in opening_exits))]
        states.append(dict(month=row['month'],cutoff=cutoff,positions_carrying_next_month=len(carries)))
    return states


def time_month(stamp):
    from datetime import datetime,timezone
    return datetime.fromtimestamp(stamp,timezone.utc).strftime('%Y-%m')


def run(path,budget=180):
    protocol=load_protocol() # Freeze before signals or metrics.
    if not path.is_file():
        return dict(status='BLOCKED_HISTORY',version=protocol['version'],protocol=protocol,
            protocol_sha256=PROTOCOL_HASH,actual_backtest_performed=False,
            reason='Original CSV and temporary snapshots unavailable in the current environment',
            required_file='BTCUSDT-15m-2026-05_to_09.csv',
            expected_previous_csv_sha256='cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07',
            results=[dict(strategy=name,status='NOT_RUN',metrics=None,signals=None,
                          trades=None,equity_curve=None) for name in 'ABCD'],
            prior_controls=dict(report='docs/FIXED_STRATEGY_RESULTS.json',
                provenance='PRIOR_REPORT_ONLY_NOT_A_NEW_CANDIDATE_EVALUATION'),
            archive_expansion=dict(status='BLOCKED_NETWORK',normal_attempt='ConnectError',
                permission_attempt='ABORTED_NO_RESULT',archives_received=0),
            safety=dict(research_only=True,real_money_execution='DISABLED',production_activation=False),
            software_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__),ROOT/'scripts/research_candidates.py',PROTOCOL)},
            python_version=platform.python_version())
    bars,meta=dataset(path)
    candidates=registry(protocol);labels=regimes(bars)
    split=(SPLIT-START)//900;deadline=time.monotonic()+budget
    results=[];sensitivity=[]
    for name,candidate in candidates.items():
        decisions=candidate.generate(bars)
        for scenario,(fees,slip) in protocol['cost_scenarios'].items():
            baseline=replace(Baseline(),fee_bps=fees,slippage_bps=slip)
            for section,a,b in (('development',WARMUP,split),('test',split,len(bars))):
                outcome=simulate(bars,decisions,a,b,900,baseline,deadline)
                outcome.update(strategy=name,section=section,scenario=scenario,
                    parameters=dict(protocol[name]),baseline=baseline.data(),
                    signals={side:sum(d.direction==side for d in decisions[a:b]) for side in ('LONG','SHORT')},
                    candles=b-a,monthly=monthly(outcome,bars,a,b,baseline),
                    regimes=regime_summary(outcome['trades'],labels,bars),
                    final_open_positions=0,forced_segment_liquidation=True,
                    equity_scope='mark-to-adverse-liquidation including fee')
                outcome['signals']['WAIT']=(b-a)-sum(outcome['signals'].values())
                outcome['monthly_carry']=open_position_audit(outcome,bars,a,b)
                if scenario=='baseline':results.append(outcome)
                else:sensitivity.append({k:v for k,v in outcome.items() if k not in ('trades','equity_curve')})
    baseline=Baseline()
    for cap in ('2000','10000'):
        for section,a,b in (('development',WARMUP,split),('test',split,len(bars))):
            outcome=buy_hold(bars,a,b,baseline,cap)
            outcome.update(strategy='BUY_HOLD_'+cap,section=section,scenario='baseline',
                monthly=monthly(outcome,bars,a,b,baseline),candles=b-a,final_open_positions=0)
            results.append(outcome)
    native=native_reference(meta)
    paths=[Path(__file__),ROOT/'scripts/research_candidates.py',PROTOCOL]
    paths+=sorted((ROOT/'app/lab').glob('*.py'))+[ROOT/'app/indicators.py',ROOT/'scripts/offline_fixed_strategies.py']
    return dict(status='COMPLETE',actual_backtest_performed=True,version=protocol['version'],protocol=protocol,protocol_sha256=PROTOCOL_HASH,
        csv=meta,development_candles=split-WARMUP,test_candles=len(bars)-split,
        initial_warmup=500,test_warmup=split,results=results,cost_sensitivity=sensitivity,
        native_historical_pattern=native,blind_independent_validation=False,
        parameter_search_performed=False,software_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        python_version=platform.python_version(),safety=dict(research_only=True,production_activation=False,
            private_exchange_clients=False,real_money_execution='DISABLED'),
        archive_expansion=dict(status='BLOCKED_NETWORK',official_probe='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2023-01.zip.CHECKSUM',
            normal_attempt='ConnectError',permission_attempt='ABORTED_NO_RESULT',archives_received=0),
        limitations=['Retrospective already-viewed August/September: not blind independent proof.',
            'User-provided Binance-format history has not been independently authenticated.',
            'Same upper stop-risk budget, not identical realized exposure/risk; notional cap often binds.',
            'Fixed fee/slippage assumptions do not model spread/funding/liquidity/latency.',
            'Native HP retained as noncomparable execution reference; previously executed and source/hash verified.',
            'Sensitivity rows omit full ledgers/curves for bounded artifact size; deterministic commands reproduce them.',
            'Default 70% fraction in Baseline is unused; exact UTC dates govern this run.'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-seconds',type=int,default=180)
    a=p.parse_args(argv)
    if a.output.exists() or not 1<=a.max_seconds<=600:p.error('New output and bounded budget required')
    result=run(a.csv,a.max_seconds)
    with a.output.open('xb') as out:out.write(canonical(result))
    if result['status']!='COMPLETE':
        print(result['status']+': no actual candidate backtest performed')
        return 2
    for r in result['results']:
        if r['section']=='test':print(r['strategy'],r['metrics']['net_profit'],r['metrics']['trades'])
    return 0


if __name__=='__main__':raise SystemExit(main())
