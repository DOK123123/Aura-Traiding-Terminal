"""Research-only August replay for Historical Pattern configurations.

This adapter uses the production evaluator, Auto coordinator and Paper Engine,
but keeps experimental PatternConfig values out of production configuration.
It never accesses exchange clients or the network.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lab.local_csv import load_binance_csv
from app.models import Candle
from app.patterns.config import PatternConfig
from app.patterns.engine import evaluate
from app.patterns.features import Features, build_features
from app.paper.auto import Signal, Auto
from app.paper.engine import Engine
from app.paper.market import Market
from app.paper.models import Settings
from app.paper.storage import Store
from scripts import backtest_aura_history as backtest
from scripts import import_binance_csv as importer

STEP = 900
SOURCE = 'Binance · Spot'
START = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
END = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
CONFIGS = {
    'A': dict(similarity=75, minimum_sample=20),
    'B': dict(similarity=60, minimum_sample=20),
    'C': dict(similarity=60, minimum_sample=10),
    'D': dict(similarity=60, minimum_sample=5),
    'E': dict(similarity=65, minimum_sample=5),
}


def utc(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def _causal_features(features: Features, n: int) -> Features:
    """Expose only the prefix ending at the current closed candle."""
    return Features(features.vectors[:n], features.facts[:n], features.valid_from)


def _signal(candles, index, config, features):
    n = index + 1
    result = evaluate(candles[:n], STEP, 500, config, index,
                      _causal_features(features, n), False)
    signal = Signal('BTCUSDT', '15m', SOURCE, candles[index].time,
                    result['signal'], Decimal(str(result['confidence'])))
    return signal, result


async def _run_one(candles, warmup, config, name, budget):
    prefix = list(candles[:warmup])
    clock = [START * 1000]

    async def fetch(symbol, timeframe):
        return dict(symbol=symbol, timeframe=timeframe, source=SOURCE, stale=False,
                    fetched_at=backtest.core.utc(clock[0] / 1000),
                    last_closed_at=prefix[-1].time + STEP,
                    candles=[asdict(c) for c in prefix[-500:]])

    market = Market(fetch, clock=lambda: clock[0])
    features = build_features(list(candles), config.lookback, 500)
    features.vectors.setflags(write=False)
    signals = Counter()
    decisions = Counter()
    first_signals = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f'aura-august-{name.lower()}-') as folder:
        engine = Engine(Store(Path(folder) / 'paper.sqlite3'), Settings(), clock=lambda: clock[0])
        auto = Auto(engine)
        auto.configure(True, await market.window('BTCUSDT', '15m'), fallback_policy='PAPER_SETTINGS')
        generation = auto.state()['generation']
        audit = []
        for index in range(warmup, len(candles)):
            if time.monotonic() - started > budget:
                raise TimeoutError('Research replay budget exceeded')
            candle = candles[index]
            prefix.append(candle)
            clock[0] = (candle.time + STEP) * 1000
            window = await market.window('BTCUSDT', '15m')
            engine.advance(window)
            signal, evaluated = _signal(candles, index, config, features)
            signals[signal.direction] += 1
            if signal.direction in ('LONG', 'SHORT') and len(first_signals) < 5:
                first_signals.append(dict(direction=signal.direction,
                                          candle_open_utc=utc(candle.time),
                                          signal_close_utc=utc(candle.time + STEP)))
            auto.process(window, signal, generation)
            decision = next(d for d in auto.state()['decisions'] if d['candle_time'] == candle.time)
            reason = decision['rejection_reason'] or 'OPENED'
            decisions[reason] += 1
            audit.append(dict(candle_open_utc=utc(candle.time), signal=signal.direction,
                               confidence=signal.confidence, decision=reason,
                               trade_opened=decision['trade_opened'],
                               rejection_reason=decision['rejection_reason'],
                               evaluated_status=evaluated['status']))
            if (index - warmup + 1) % 500 == 0:
                print(f'{name}: {index - warmup + 1}/{len(candles) - warmup}', file=sys.stderr, flush=True)
        snapshot = engine.snapshot('ALL')
        with engine.store.transaction(write=False) as db:
            trades = engine.store.trades(db)
            curve = [dict(row) for row in db.execute('SELECT * FROM curve ORDER BY seq')]
    closed = [trade for trade in trades if trade['status'] == 'CLOSED']
    # Independent Decimal check of the journal, matching the established replay audit.
    with localcontext() as context:
        context.prec = 64
        expected = Decimal(0)
        for trade in closed:
            entry, exit_price, size = map(Decimal, (trade['entry_price'], trade['exit_price'], trade['position_size']))
            sign = 1 if trade['direction'] == 'LONG' else -1
            gross = (sign * (exit_price - entry) * size).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_EVEN)
            rate = Decimal(trade['commission_pct']) / 100
            entry_fee = (entry * size * rate).quantize(Decimal('0.00000001'), rounding=ROUND_CEILING)
            exit_fee = (exit_price * size * rate).quantize(Decimal('0.00000001'), rounding=ROUND_CEILING)
            expected += (gross - entry_fee - exit_fee).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_EVEN)
    if expected != Decimal(snapshot['statistics']['net_pnl']):
        raise ValueError(f'{name}: Decimal PnL journal mismatch')
    return dict(name=name, config=config.model_dump(), signals=dict(signals), decision_counts=dict(decisions),
                first_five_signals=first_signals, entries=sum(t['entry_type'] == 'AUTO_SIGNAL' for t in trades),
                closed_trades=len(closed), net_realized_pnl=str(expected),
                statistics=snapshot['statistics'], open_positions=[t for t in trades if t['status'] == 'OPEN'],
                trades=trades, equity_curve=curve, decisions=audit,
                execution='production Paper Engine; closed-candle close; PAPER_SETTINGS fallback',
                lookahead_check='Features and evaluation prefix end at current candle; future rows excluded')


def _load(path: Path):
    bars, metadata = load_binance_csv(path)
    before = [bar for bar in bars if bar.time < START]
    test = [bar for bar in bars if START <= bar.time < END]
    if not test or test[-1].time + STEP != END:
        raise ValueError('August coverage is incomplete')
    if len(before) < 500:
        raise ValueError('Fewer than 500 causal warm-up candles')
    # Exclude every September row from the selected replay dataset.
    selected = before + test
    candles = [Candle(bar.time, float(bar.open), float(bar.high), float(bar.low),
                       float(bar.close), float(bar.volume)) for bar in selected]
    return candles, metadata, len(before), len(test)


async def run(path: Path, budget: int):
    candles, metadata, warmup, test_count = _load(path)
    results = []
    for name, values in CONFIGS.items():
        config = PatternConfig(minimum_similarity=values['similarity'],
                               minimum_sample=values['minimum_sample'])
        results.append(await _run_one(candles, warmup, config, name, budget))
    return dict(status='COMPLETE', research_only=True, symbol='BTCUSDT', timeframe='15m',
                period_start_utc=utc(START), period_end_exclusive_utc=utc(END),
                source_csv=metadata, warmup_requested=10000, warmup_actual=warmup,
                test_candles=test_count, future_candles_excluded=True,
                configurations=CONFIGS, paper_settings=Settings().to_dict(),
                fallback_policy='PAPER_SETTINGS', results=results,
                september_comparison='See docs/AURA_SEPTEMBER_2026_BACKTEST.md; September used 10000 warm-up and production 75/20.',
                limitations=[
                    'Only 8832 pre-August candles are available; this is not a full 10000-candle warm-up.',
                    'User-supplied CSV provenance is claimed Binance but not independently authenticated.',
                    'Fresh ledgers are used per research configuration; no Render state is accessed.',
                    'No slippage, spread, funding or forced close at period end is modeled by production Paper Engine.',
                    'Results are a single historical month and do not establish profitability or production safety.',
                ],
                software_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((ROOT / 'app' / 'patterns').glob('*.py'))},
                diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-seconds-per-config', type=int, default=1800)
    args = parser.parse_args(argv)
    if args.output.exists() or not 1 <= args.max_seconds_per_config <= 3600:
        parser.error('Output must be new and budget must be 1..3600 seconds')
    result = asyncio.run(run(args.csv, args.max_seconds_per_config))
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
    print('COMPLETE')


if __name__ == '__main__':
    raise SystemExit(main())
