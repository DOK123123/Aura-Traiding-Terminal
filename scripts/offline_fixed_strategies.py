"""Fixed retrospective CSV research; no web routes, live state or private clients."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lab.local_csv import load_binance_csv
from app.lab.models import Baseline, canonical, money, precise, quantity, text
from app.lab.indicators import ema, atr
from app.lab.strategies import Decision
from app.lab.execution import simulate, metrics, fee, fill
from app.models import Candle
from scripts import backtest_aura_history as native
from scripts.replay_aura_csv import CausalFeatureCache, enable_sandbox_poll

STEP = 900
START = 1777593600
SPLIT = 1785542400
END = 1790812800
WARMUP = 500
NAMES = ('A_DONCHIAN20', 'B_EMA20_50_CROSS', 'C_DONCHIAN_EMA50_ATR14')
PROTOCOL_PATH = ROOT / 'docs/FIXED_STRATEGY_PROTOCOL.json'
PROTOCOL_SHA256 = '3bd6063ba598381d6a4838f61a841ea89fd650474d60dce7d656c6020b4e9a86'


def utc(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def freeze_protocol(path=PROTOCOL_PATH):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PROTOCOL_SHA256:
        raise ValueError('Frozen protocol hash mismatch; no research run allowed')
    return json.loads(raw), digest


@precise
def signals(bars, name):
    if name not in NAMES:
        raise ValueError('Unsupported fixed strategy')
    closes = [float(b.close) for b in bars]
    fast, slow = ema(closes, 20), ema(closes, 50)
    volatility = atr(bars, 14)
    result = []
    for i, bar in enumerate(bars):
        if i < 50:
            result.append(Decision(reason='WARMUP'))
            continue
        above = bar.close > max(b.high for b in bars[i-20:i])
        below = bar.close < min(b.low for b in bars[i-20:i])
        exit_long = bar.close < min(b.low for b in bars[i-10:i])
        exit_short = bar.close > max(b.high for b in bars[i-10:i])
        stop, target = bar.close * D('.02'), bar.close * D('.04')
        if name == NAMES[0]:
            long, short = above, below
        elif name == NAMES[1]:
            long = fast[i-1] <= slow[i-1] and fast[i] > slow[i]
            short = fast[i-1] >= slow[i-1] and fast[i] < slow[i]
            exit_long, exit_short = short, long
        else:
            if volatility[i] is None or volatility[i] <= 0:
                result.append(Decision(reason='INVALID_ATR'))
                continue
            long = above and closes[i] > slow[i]
            short = below and closes[i] < slow[i]
            exit_long = exit_long or closes[i] <= slow[i]
            exit_short = exit_short or closes[i] >= slow[i]
            stop, target = D(str(volatility[i])) * 2, D(str(volatility[i])) * 4
        result.append(Decision('LONG' if long else 'SHORT' if short else None,
                               stop, target, exit_long, exit_short,
                               'CLOSED_' + name if long or short else 'NO_SIGNAL'))
    return result


def event_month(stamp, close_event=False):
    return datetime.fromtimestamp(stamp - int(close_event), timezone.utc).strftime('%Y-%m')


@precise
def monthly(run, bars, begin, end, baseline):
    rows = []
    curve = run['equity_curve']
    for name in sorted({event_month(b.time) for b in bars[begin:end]}):
        start = int(datetime.strptime(name, '%Y-%m').replace(tzinfo=timezone.utc).timestamp())
        following = datetime.fromtimestamp(start, timezone.utc)
        stop = int(datetime(following.year + (following.month == 12),
                            following.month % 12 + 1, 1, tzinfo=timezone.utc).timestamp())
        opening = [p for p in curve if p['time'] <= start]
        initial = opening[-1] if opening else curve[0]
        points = [p for p in curve if start < p['time'] <= stop]
        final = points[-1] if points else initial
        entries = [t for t in run['trades'] if event_month(t['entry_time']) == name]
        closed = [t for t in run['trades'] if event_month(t['exit_time'],
                     t['exit_reason'] not in ('STOP_GAP', 'TAKE_PROFIT_GAP_CONSERVATIVE', 'STRATEGY_EXIT_NEXT_OPEN')) == name]
        pnl = [D(t['realized_pnl']) for t in closed]
        gains = sum((p for p in pnl if p > 0), D(0))
        losses = -sum((p for p in pnl if p < 0), D(0))
        fees = sum((D(t['entry_fee']) for t in entries), D(0)) + sum((D(t['exit_fee']) for t in closed), D(0))
        cashflow = sum((D(t['gross_price_pnl']) - D(t['exit_fee']) for t in closed), D(0)) - sum((D(t['entry_fee']) for t in entries), D(0))
        peak, dd = D(initial['equity']), D(0)
        for point in points:
            value = D(point['equity']); peak = max(peak, value)
            dd = max(dd, (peak - value) / peak * 100)
        rows.append(dict(month=name, candles=sum(event_month(b.time) == name for b in bars[begin:end]),
            entries=len(entries), closed_trades=len(closed), net_closed_trade_pnl=text(sum(pnl, D(0))),
            cashflow_pnl=text(cashflow), fees_charged=text(fees),
            win_rate=text(money(D(sum(p > 0 for p in pnl)) / len(pnl) * 100)) if pnl else None,
            profit_factor=text(money(gains / losses)) if losses else None,
            opening_balance=initial['balance'], closing_balance=final['balance'],
            opening_equity=initial['equity'], closing_equity=final['equity'],
            equity_change=text(D(final['equity']) - D(initial['equity'])),
            max_drawdown_pct=text(money(dd))))
    return rows


@precise
def buy_hold(bars, begin, end, baseline, allocation):
    rate, slip = D(baseline.fee_bps)/10000, D(baseline.slippage_bps)/10000
    start = D(baseline.starting_balance)
    entry = fill(bars[begin].open, 'LONG', True, slip)
    size = quantity(min(D(allocation) / entry, (start-D('.00000002'))/(entry*(1+rate))))
    entry_fee = fee(entry, size, rate)
    balance = money(start-entry_fee)
    curve = [dict(time=bars[begin].time, balance=text(start), equity=text(start))]
    for bar in bars[begin:end]:
        exit_price = fill(bar.close, 'LONG', False, slip)
        equity = money(balance + money((exit_price-entry)*size) - fee(exit_price, size, rate))
        curve.append(dict(time=bar.time+STEP, balance=text(balance), equity=text(equity)))
    exit_price = fill(bars[end-1].close, 'LONG', False, slip)
    exit_fee = fee(exit_price, size, rate)
    gross = money((exit_price-entry)*size)
    pnl = money(gross-entry_fee-exit_fee)
    final = money(start+pnl)
    curve[-1].update(balance=text(final), equity=text(final))
    trade = dict(direction='LONG', entry_time=bars[begin].time, entry_raw_price=text(bars[begin].open),
        entry_price=text(entry), size=text(size), notional=text(money(entry*size, ceil=True)),
        exit_time=bars[end-1].time+STEP, exit_raw_price=text(bars[end-1].close), exit_price=text(exit_price),
        exit_reason='SEGMENT_END_CLOSE', entry_reason='PRECOMMITTED_BUY_HOLD', entry_fee=text(entry_fee),
        exit_fee=text(exit_fee), fees=text(entry_fee+exit_fee), gross_price_pnl=text(gross),
        realized_pnl=text(pnl), status='CLOSED',
        slippage_usdt=text(money((abs(entry-bars[begin].open)+abs(exit_price-bars[end-1].close))*size)))
    return dict(status='OK', metrics=metrics([trade], curve, baseline), trades=[trade], equity_curve=curve,
                allocation_usdt=allocation, risk_equivalent=False, stop_loss=None, take_profit=None,
                rejections={}, real_money_execution='DISABLED')


def dataset(path):
    bars, metadata = load_binance_csv(path)
    selected = [b for b in bars if START <= b.time < END]
    if len(selected) != (END-START)//STEP or selected[0].time != START or selected[-1].time+STEP != END:
        raise ValueError('Complete May-September history required; no filling/truncation')
    return selected, metadata


def experimental(path, budget=120):
    protocol, protocol_hash = freeze_protocol()  # Before any strategy/metric computation.
    bars, metadata = dataset(path)
    baseline = Baseline()
    split = (SPLIT-START)//STEP
    deadline = time.monotonic()+budget
    runs = []
    for name in NAMES:
        decisions = signals(bars, name)
        for label, begin, end in (('development', WARMUP, split), ('test', split, len(bars))):
            result = simulate(bars, decisions, begin, end, STEP, baseline, deadline)
            result.update(strategy=name, split=label, candles=end-begin,
                signals=dict(Counter(d.direction or 'WAIT' for d in decisions[begin:end])),
                monthly=monthly(result, bars, begin, end, baseline))
            runs.append(result)
    for allocation in ('2000', '10000'):
        for label, begin, end in (('development', WARMUP, split), ('test', split, len(bars))):
            result = buy_hold(bars, begin, end, baseline, allocation)
            result.update(strategy='BUY_HOLD_'+allocation, split=label, candles=end-begin,
                          monthly=monthly(result, bars, begin, end, baseline))
            runs.append(result)
    paths = [Path(__file__), PROTOCOL_PATH] + sorted((ROOT/'app/lab').glob('*.py'))
    return dict(status='EXPERIMENTS_COMPLETE', protocol=protocol, protocol_sha256=protocol_hash,
        csv=metadata, baseline=baseline.data(), selected_candles=len(bars),
        development_candles=split-WARMUP, test_candles=len(bars)-split, runs=runs,
        software_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        python=platform.python_version(), source_authentication='USER_CLAIM_NOT_INDEPENDENTLY_VERIFIED',
        baseline_development_pct_ignored=True,
        holdout_is_blind=False, selection_or_optimization=False, real_money_execution='DISABLED'), bars


async def historical_pattern(bars, budget):
    candles = [Candle(b.time, *(float(getattr(b, k)) for k in ('open','high','low','close','volume'))) for b in bars]
    cache = CausalFeatureCache(candles)
    split = (SPLIT-START)//STEP
    verified = cache.verify([WARMUP-1, WARMUP, split-1, split, len(candles)-1])
    rows = []
    # Fixed defaults: no environment variables, production settings or private clients.
    settings, policy, source, _ = native.configuration()
    for label, selected, begin, end in (
        ('development', candles[:split], START+WARMUP*STEP, SPLIT),
        ('test', candles, SPLIT, END)):
        with patch.object(native.production_signals, 'evaluate', cache):
            result = await native.measured_replay(selected, begin, end, settings, policy, budget)
        result.update(split=label, settings_source=source, comparable_to_next_open=False,
                      direct_equivalence_verified_indices=verified)
        rows.append(result)
    return dict(status='COMPLETE', production_config=cache.config.model_dump(), native_paper_settings=settings.to_dict(),
        fallback_policy=policy, slippage_supported=False, warmup_development=WARMUP, warmup_test=split,
        forced_final_close=False, ranked=False, results=rows,
        reason='Unchanged production close-fill Paper replay, not common next-open/slippage execution',
        software_sha256=native.core.code_hashes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sandbox-poll', action='store_true')
    parser.add_argument('--max-seconds-native-split', type=int, default=900)
    args = parser.parse_args(argv)
    if args.output.exists() or not 1 <= args.max_seconds_native_split <= 1800:
        parser.error('New output and bounded native replay budget required')
    report, bars = experimental(args.csv)
    if args.sandbox_poll:
        enable_sandbox_poll()
    report['historical_pattern'] = asyncio.run(historical_pattern(bars, args.max_seconds_native_split))
    report['status'] = 'COMPLETE'
    report['sandbox_poll'] = args.sandbox_poll
    with args.output.open('xb') as out:
        out.write(canonical(report))
    print('COMPLETE')


if __name__ == '__main__':
    raise SystemExit(main())
