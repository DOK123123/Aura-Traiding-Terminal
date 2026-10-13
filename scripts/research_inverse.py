"""Frozen offline inverse-signal experiments; no account or live-state access."""
import argparse
from collections import Counter
from dataclasses import replace
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_EVEN
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lab.execution import simulate
from app.lab.models import Baseline, canonical, money, precise, text
from scripts.offline_fixed_strategies import dataset, monthly, START, SPLIT, WARMUP
from scripts.research_candidates import registry, regimes
from scripts.run_research_cycle import load_protocol, regime_summary

PROTOCOL = ROOT / 'docs/AURA_INVERSE_STRATEGY_PROTOCOL.json'
PROTOCOL_SHA = '3736a3825a8bb017a29b386a06869f60c51622cafd1b10adec86f58f57442fae'
OPEN_EXITS = ('STOP_GAP', 'TAKE_PROFIT_GAP_CONSERVATIVE', 'STRATEGY_EXIT_NEXT_OPEN')


def freeze():
    raw = PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA:
        raise ValueError('Frozen inverse protocol mismatch')
    return json.loads(raw)


def invert(decisions, variant):
    """I retains physical-side exit predicates; II follows original signal-side exits."""
    if variant not in ('ORIGINAL', 'I', 'II'):
        raise ValueError('Unsupported inversion')
    if variant == 'ORIGINAL':
        return list(decisions)
    result = []
    for decision in decisions:
        if decision.direction not in (None, 'LONG', 'SHORT'):
            raise ValueError('Invalid original direction')
        direction = {'LONG': 'SHORT', 'SHORT': 'LONG', None: None}[decision.direction]
        xl, xs = decision.exit_long, decision.exit_short
        if variant == 'II':
            xl, xs = xs, xl
        result.append(replace(decision, direction=direction, exit_long=xl, exit_short=xs,
                              reason='INVERSE_' + variant + ':' + decision.reason))
    return result


@precise
def economy(trades):
    """Attribution on fixed realized paths; do not subtract slippage twice."""
    pnls = [D(t['realized_pnl']) for t in trades]
    gross = sum((D(t['gross_price_pnl']) for t in trades), D(0))
    fees = sum((D(t['fees']) for t in trades), D(0))
    slip = sum((D(t['slippage_usdt']) for t in trades), D(0))
    raw = sum((money((1 if t['direction'] == 'LONG' else -1) *
                     (D(t['exit_raw_price']) - D(t['entry_raw_price'])) * D(t['size']))
               for t in trades), D(0))
    turnover = sum(((D(t['entry_price']) + D(t['exit_price'])) * D(t['size'])
                    for t in trades), D(0))
    raw_turnover = sum(((D(t['entry_raw_price']) + D(t['exit_raw_price'])) * D(t['size'])
                        for t in trades), D(0))
    holds = sorted(t['exit_time'] - t['entry_time'] for t in trades)
    n = len(holds)
    median = (D(holds[(n-1)//2]) + D(holds[n//2])) / 2 if n else None
    win = [p for p in pnls if p > 0]; loss = [-p for p in pnls if p < 0]
    filled_pnls=[D(t['gross_price_pnl']) for t in trades]
    raw_pnls=[money((1 if t['direction']=='LONG' else -1)*(D(t['exit_raw_price'])-D(t['entry_raw_price']))*D(t['size'])) for t in trades]
    fee_budget = money(gross / turnover * 10000) if turnover else None
    return dict(trades=n, net_pnl=text(sum(pnls, D(0))),
                gross_filled_price_pnl=text(gross), gross_raw_path_pnl=text(raw),
                fees=text(fees), slippage=text(slip), turnover=text(money(turnover)),
                raw_turnover=text(money(raw_turnover)),
                rounding_residual=text(raw-gross-slip),
                gross_profit_net_trade_basis=text(sum(win, D(0))),
                gross_loss_net_trade_basis=text(sum(loss, D(0))),
                gross_profit_filled_price_basis=text(sum((p for p in filled_pnls if p>0),D(0))),
                gross_loss_filled_price_basis=text(-sum((p for p in filled_pnls if p<0),D(0))),
                gross_profit_raw_price_basis=text(sum((p for p in raw_pnls if p>0),D(0))),
                gross_loss_raw_price_basis=text(-sum((p for p in raw_pnls if p<0),D(0))),
                win_rate=text(money(D(len(win))/n*100)) if n else None,
                expectancy=text(money(sum(pnls,D(0))/n)) if n else None,
                profit_factor=text(money(sum(win,D(0))/sum(loss,D(0)))) if loss else None,
                average_win=text(money(sum(win,D(0))/len(win))) if win else None,
                average_loss=text(money(sum(loss,D(0))/len(loss))) if loss else None,
                raw_price_winning_trades=sum((1 if t['direction']=='LONG' else -1) *
                    (D(t['exit_raw_price'])-D(t['entry_raw_price'])) > 0 for t in trades),
                fixed_path_fee_break_even_bps=text(fee_budget),
                nonnegative_break_even_fee_exists=fee_budget is not None and fee_budget >= 0,
                fixed_path_total_cost_budget_bps=text(money(raw/raw_turnover*10000)) if raw_turnover else None,
                break_even_scope='FIXED_REALIZED_PATH_ONLY; fee ceiling residual; combined budget first-order. Changing costs can change trades; not a feasible tariff prediction.',
                holding_seconds=dict(min=holds[0] if n else None, median=text(median),
                    mean=text(money(D(sum(holds))/n)) if n else None, max=holds[-1] if n else None),
                holding_candle_buckets=dict(one=sum(h<=900 for h in holds),
                    two_to_four=sum(900<h<=3600 for h in holds),
                    five_to_sixteen=sum(3600<h<=14400 for h in holds),
                    more_than_sixteen=sum(h>14400 for h in holds)),
                exits=dict(Counter(t['exit_reason'] for t in trades)))


@precise
def verify_accounting(outcome, bars, baseline):
    """Independent rational fills, Decimal PnL/risk, price touches and full equity DD."""
    prices = {b.time: b for b in bars}
    tick = D('.00000001'); rate = D(baseline.fee_bps)/10000
    slip = Fraction(baseline.slippage_bps)/10000
    def nearest(v): return v.quantize(tick, rounding=ROUND_HALF_EVEN)
    def charged(p, q): return (p*q*rate).quantize(tick, rounding=ROUND_CEILING)
    total = D(0); previous_exit = None
    curve=outcome['equity_curve'];curve_index={p['time']:i for i,p in enumerate(curve)}
    balance_events=[D(0)]*len(curve);mark=[None]*len(curve)
    for t in outcome['trades']:
        sign = 1 if t['direction']=='LONG' else -1
        ep, xp, er, xr, q = [D(t[k]) for k in ('entry_price','exit_price','entry_raw_price','exit_raw_price','size')]
        if Fraction(ep) != Fraction(er)*(1+sign*slip) or Fraction(xp) != Fraction(xr)*(1-sign*slip):
            raise ValueError('Independent adverse fill mismatch')
        ef, xf = charged(ep,q), charged(xp,q)
        expected = nearest(nearest(sign*(xp-ep)*q)-ef-xf)
        if expected != D(t['realized_pnl']) or ef != D(t['entry_fee']) or xf != D(t['exit_fee']):
            raise ValueError('Independent PnL/fee mismatch')
        if er != prices[t['entry_time']].open or t['signal_time'] != t['entry_time']:
            raise ValueError('Next-open execution mismatch')
        if previous_exit is not None and t['entry_time'] < previous_exit:
            raise ValueError('Concurrent position')
        previous_exit = t['exit_time']
        if D(t['risk_usdt']) > D(t['risk_budget_usdt']) or D(t['notional']) > D(baseline.max_notional):
            raise ValueError('Risk/notional mismatch')
        stop, target = D(t['stop_loss']), D(t['take_profit'])
        if not (stop < ep < target if sign==1 else target < ep < stop):
            raise ValueError('Protective sides mismatch')
        stop_fill = stop*(1-D(sign)*D(baseline.slippage_bps)/10000)
        risk = (abs(ep-stop_fill)*q).quantize(tick,rounding=ROUND_CEILING)+ef+charged(stop_fill,q)
        if risk != D(t['risk_usdt']): raise ValueError('Independent planned risk mismatch')
        opening = t['exit_reason'] in OPEN_EXITS
        b = prices[t['exit_time'] if opening else t['exit_time']-900]
        reason = t['exit_reason']
        if reason.startswith('STOP'):
            if not (b.low <= stop if sign==1 else b.high >= stop):
                raise ValueError('Stop not touched')
            raw_exit = b.open if opening else stop
        elif reason.startswith('TAKE_PROFIT'):
            if not (b.high >= target if sign==1 else b.low <= target):
                raise ValueError('Target not touched')
            raw_exit = target
        elif reason == 'STRATEGY_EXIT_NEXT_OPEN': raw_exit = b.open
        elif reason == 'SEGMENT_END_CLOSE': raw_exit = b.close
        else: raise ValueError('Unknown exit')
        if xr != raw_exit: raise ValueError('Exit raw price mismatch')
        entry_point=curve_index[t['entry_time']+900]
        exit_point=curve_index[t['exit_time']+(900 if opening else 0)]
        balance_events[entry_point]-=ef
        balance_events[exit_point]+=nearest(sign*(xp-ep)*q)-xf
        for ci in range(entry_point,exit_point):
            if mark[ci] is not None: raise ValueError('Overlapping equity exposure')
            mark[ci]=(sign,ep,q)
        total += expected
    peak = D(baseline.starting_balance); dd = D(0);cash=D(baseline.starting_balance)
    for ci,point in enumerate(curve):
        cash=nearest(cash+balance_events[ci]);expected_equity=cash
        if mark[ci] is not None:
            sign,ep,q=mark[ci]
            raw=prices[point['time']-900].close
            liquidation=raw*(1-D(sign)*D(baseline.slippage_bps)/10000)
            expected_equity=nearest(cash+nearest(sign*(liquidation-ep)*q)-charged(liquidation,q))
        if cash!=D(point['balance']) or expected_equity!=D(point['equity']):
            raise ValueError('Independent candle equity/accounting mismatch')
        e = D(point['equity']); peak=max(peak,e); dd=max(dd,(peak-e)/peak*100)
    if nearest(dd) != D(outcome['metrics']['max_drawdown_pct']):
        raise ValueError('Independent drawdown mismatch')
    if total != D(outcome['metrics']['net_profit']) or D(outcome['metrics']['final_balance']) != D(baseline.starting_balance)+total:
        raise ValueError('Balance sum mismatch')
    e = economy(outcome['trades'])
    if D(e['net_pnl']) != D(e['gross_filled_price_pnl'])-D(e['fees']):
        raise ValueError('Double-counted slippage')
    if abs(D(e['rounding_residual'])) > tick*len(outcome['trades']):
        raise ValueError('Raw/fill/slippage reconciliation mismatch')
    return len(outcome['trades'])


@precise
def verify_signal_execution(outcome, bars, signals):
    """Decision at entry-open minus one candle; no later input determines entry."""
    index={b.time:i for i,b in enumerate(bars)}
    for trade in outcome['trades']:
        i=index[trade['entry_time']]
        if i==0: raise ValueError('Entry without previous closed signal')
        decision=signals[i-1]
        if decision.direction != trade['direction']:
            raise ValueError('Entry side inconsistent with causal signal')
        if abs(D(trade['entry_price'])-D(trade['stop_loss'])) != decision.stop_distance:
            raise ValueError('Signal stop-distance mismatch')
        if abs(D(trade['entry_price'])-D(trade['take_profit'])) != decision.target_distance:
            raise ValueError('Signal target-distance mismatch')
        if trade['exit_reason']=='STRATEGY_EXIT_NEXT_OPEN':
            exit_decision=signals[index[trade['exit_time']]-1]
            if not (exit_decision.exit_long if trade['direction']=='LONG' else exit_decision.exit_short):
                raise ValueError('Exit side inconsistent with causal closed decision')


def run(path, budget=180, full_curves=False):
    protocol = freeze(); parent = load_protocol()
    if not path.is_file():
        return dict(status='BLOCKED_HISTORY',actual_backtest_performed=False,protocol=protocol,
                    protocol_sha256=PROTOCOL_SHA,results=None,reason='Original CSV absent; no synthetic performance')
    bars, meta = dataset(path)
    if meta['sha256'] != protocol['csv_sha256']: raise ValueError('Frozen dataset mismatch')
    original_path = ROOT/'docs/RESEARCH_CYCLE_RESULTS.json'
    if hashlib.sha256(original_path.read_bytes()).hexdigest() != protocol['original_results_sha256']:
        raise ValueError('Original results changed')
    original = json.loads(original_path.read_bytes())
    for name, digest in original['software_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Original software changed: '+name)
    deadline = time.monotonic()+budget; split=(SPLIT-START)//900
    labels=regimes(bars); results=[]; zero=[]; audited=0
    for name, candidate in registry(parent).items():
        decisions=candidate.generate(bars)
        transformed={v:invert(decisions,v) for v in ('ORIGINAL','I','II')}
        equivalent=all(replace(a,reason='') == replace(b,reason='') for a,b in zip(transformed['I'],transformed['II']))
        for variant, signals in transformed.items():
            for costs in ('BASELINE','ZERO_COST'):
                base=Baseline() if costs=='BASELINE' else replace(Baseline(),fee_bps='0',slippage_bps='0')
                for section,begin,end in (('development',WARMUP,split),('test',split,len(bars))):
                    outcome=simulate(bars,signals,begin,end,900,base,deadline)
                    audited+=verify_accounting(outcome,bars,base)
                    verify_signal_execution(outcome,bars,signals)
                    if variant=='ORIGINAL' and costs=='BASELINE':
                        prior=next(r for r in original['results'] if r['strategy']==name and r['section']==section)
                        for key in ('metrics','trades','equity_curve','rejections'):
                            if outcome[key] != prior[key]: raise ValueError('Original reproducibility mismatch: '+key)
                    outcome.update(strategy=name,variant=variant,section=section,costs=costs,
                        baseline=base.data(),candles=end-begin,signals=dict(Counter(d.direction or 'WAIT' for d in signals[begin:end])),
                        economics=economy(outcome['trades']),
                        direction={side:economy([t for t in outcome['trades'] if t['direction']==side]) for side in ('LONG','SHORT')},
                        monthly=monthly(outcome,bars,begin,end,base),
                        regimes=regime_summary(outcome['trades'],labels,bars),
                        regime_economics={regime:economy([t for t in outcome['trades'] if labels[(t['signal_time']-900-START)//900]==regime]) for regime in ('RANGE','TRANSITION','TREND')},
                        variants_I_II_equivalent_on_all_dataset_decisions=equivalent,
                        signal_stream_sha256=hashlib.sha256(canonical([dict(direction=d.direction,stop=text(d.stop_distance),target=text(d.target_distance),exit_long=d.exit_long,exit_short=d.exit_short) for d in signals])).hexdigest(),
                        final_open_positions=0)
                    outcome['economics']['trades_per_performance_day']=text(money(D(len(outcome['trades']))/D((end-begin)*900)*86400))
                    outcome['equity_curve_full_sha256']=hashlib.sha256(canonical(outcome['equity_curve'])).hexdigest()
                    if costs=='ZERO_COST':
                        zero.append({k:v for k,v in outcome.items() if k not in ('trades','equity_curve')})
                    else:
                        if not full_curves:
                            curve=outcome['equity_curve']
                            outcome['equity_curve']=[p for i,p in enumerate(curve) if i in (0,len(curve)-1) or p['time']%86400==0]
                        outcome['equity_curve_scope']='FULL_15M' if full_curves else 'DAILY_AND_ENDPOINTS; metrics/audit use full15m; CLI --full-curves reconstructs all'
                        results.append(outcome)
    sources=[Path(__file__),PROTOCOL,ROOT/'scripts/research_candidates.py',ROOT/'scripts/run_research_cycle.py',ROOT/'scripts/offline_fixed_strategies.py',ROOT/'app/indicators.py']+sorted((ROOT/'app/lab').glob('*.py'))
    return dict(status='COMPLETE',actual_backtest_performed=True,protocol=protocol,protocol_sha256=PROTOCOL_SHA,
        csv=meta,results=results,zero_cost=zero,original_results_exact_match=True,independent_trades_audited=audited,
        software_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        safety=dict(research_only=True,real_money_execution='DISABLED',private_clients=False,production_changes=False),
        history_expansion=dict(status='BLOCKED_NETWORK',error='ConnectError',attempts=1,timeout_seconds=8,archives_received=0),
        limitations=['Already studied retrospective August/September, not blind OOS.',
            'Binance-format source user-provided, not independently authenticated.',
            'Fixed-path cost budgets do not predict different-cost executions.',
            'No spread/funding/borrow/liquidity/latency model; SHORT virtual collateral, not tradable Spot short.',
            'Forced final liquidation; no final open position by design; fresh split ledgers.',
            'No production activation or parameter optimization.'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--full-curves',action='store_true');parser.add_argument('--max-seconds',type=int,default=180)
    args=parser.parse_args(argv)
    if args.output.exists() or not 1<=args.max_seconds<=600:
        parser.error('New output and bounded duration required')
    report=run(args.csv,args.max_seconds,args.full_curves)
    with args.output.open('xb') as out: out.write(canonical(report))
    if report['status']!='COMPLETE': print(report['status']);return 2
    for row in report['results']:
        if row['section']=='test': print(row['strategy'],row['variant'],row['metrics']['trades'],row['metrics']['net_profit'])
    return 0


if __name__=='__main__':raise SystemExit(main())
