"""Offline, isolated replay of production Historical Pattern -> Auto -> Paper.

No private clients, production database, strategy replacement or settings writes.
Public historical GET is opt-in (--fetch); the default mode is entirely offline.
"""
import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext, ROUND_CEILING, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import Candle, validate_candles
from app.paper.auto import Auto, STRATEGY_VERSION
from app.paper.engine import Engine
from app.paper.market import Market
from app.paper.models import Settings
from app.paper.signals import SignalReader
from app.paper.storage import Store
from app.patterns.history import Dataset
from app.patterns.config import PatternConfig

STEP = 900
SOURCE = 'Binance · Spot'
MAX_CANDLES = 20000
MAX_BYTES = 8 * 1024 * 1024
PUBLIC_URL = 'https://data-api.binance.vision/api/v3/klines'


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def period(end_date=None, days=30):
    if type(days) is not int or days not in (30,90):
        raise ValueError('Only fixed 30/90 day diagnostic periods are supported')
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc) if end_date else today
    if end > today:
        raise ValueError('End date must be a complete UTC boundary, not in the future')
    return int((end - timedelta(days=days)).timestamp()), int(end.timestamp())


def code_hashes():
    paths = sorted((ROOT / 'app' / 'patterns').glob('*.py')) + sorted((ROOT / 'app' / 'paper').glob('*.py'))
    paths += [ROOT / 'app' / name for name in ('models.py','indicators.py','main.py','providers.py')]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def manifest(start, end, warmup):
    return dict(status='NO_HISTORY', symbol='BTCUSDT', timeframe='15m',
                start_utc=utc(start), end_exclusive_utc=utc(end), expected_candles=(end-start)//STEP,
                observed_candles=None, warmup_requested=warmup, source=SOURCE,
                strategy_version=STRATEGY_VERSION, software_sha256=code_hashes(),
                pattern_config=PatternConfig().model_dump(), python_version=sys.version.split()[0],
                settings=Settings().to_dict(), fallback_policy='PAPER_SETTINGS',
                signals=None, entries=None, rejections=None, closed_trades=None,
                net_realized_pnl=None, maximum_drawdown_pct=None, first_five_signals=None,
                execution='Production verified closed-candle close; not Strategy Lab next-open',
                limitations=['Replay requires an authentic public historical snapshot.',
                            'Live archive may contain a different amount of historical analogs.',
                            'Sequential replay assumes every candle is delivered; it does not reproduce Render sleep.',
                            'No slippage model exists in the production Paper engine.',
                            'No live Render state or credentials are accessed.'])


def load_snapshot(path, start, end, warmup):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Snapshot exceeds 8 MiB limit')
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or (data.get('symbol'), data.get('timeframe'), data.get('source')) != ('BTCUSDT', '15m', SOURCE):
        raise ValueError('Snapshot scope/source mismatch')
    records = data.get('candles')
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_CANDLES:
        raise ValueError('Invalid or oversized candle list')
    candles = []
    for item in records:
        if not isinstance(item, dict) or type(item.get('time')) is not int:
            raise ValueError('Invalid candle timestamp')
        values = [item.get(k) for k in ('open', 'high', 'low', 'close', 'volume')]
        if any(type(v) not in (int, float) for v in values):
            raise ValueError('Snapshot must use production numeric OHLCV types')
        candles.append(Candle(item['time'], *values))
    # Reject duplicates, gaps and ordering even in unused future rows. Future/forming
    # observations are then excluded, never used by features or paper execution.
    validate_candles(candles, '15m', now=max(end, candles[-1].time+STEP), contiguous=True)
    low = start-warmup*STEP
    selected = [c for c in candles if low <= c.time and c.time+STEP <= end]
    expected = warmup+(end-start)//STEP
    if len(selected) != expected or selected[0].time != low or selected[-1].time+STEP != end:
        raise ValueError('Missing requested coverage or warm-up; no truncation/fill permitted')
    return selected, hashlib.sha256(raw).hexdigest(), len(candles)-len(selected)


async def fetch_snapshot(path, start, end, warmup):
    """Explicit public-only GET; fixed host, no credentials/redirects/retries."""
    import httpx
    low = start-warmup*STEP
    rows = []
    cursor = low*1000
    async with asyncio.timeout(90):
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            for _ in range((warmup+(end-start)//STEP+999)//1000):
                response = await client.get(PUBLIC_URL, params=dict(symbol='BTCUSDT', interval='15m',
                                          startTime=cursor, endTime=end*1000-1, limit=1000))
                if response.status_code != 200:
                    raise ValueError(f'Public history HTTP {response.status_code}; no retries/fallback')
                if len(response.content) > 1024*1024:
                    raise ValueError('Historical response exceeds size limit')
                batch = response.json()
                if not isinstance(batch, list) or not batch:
                    raise ValueError('Public history is incomplete')
                for row in batch:
                    if not isinstance(row, list) or len(row) < 7 or type(row[0]) is not int or type(row[6]) is not int:
                        raise ValueError('Malformed public kline')
                    if row[0] % (STEP*1000) or row[6] != row[0]+STEP*1000-1 or row[6] >= end*1000:
                        raise ValueError('Malformed/unclosed kline timestamps')
                    c = Candle(row[0]//1000, *map(float, row[1:6]))
                    rows.append(asdict(c))
                next_cursor = batch[-1][0]+STEP*1000
                if next_cursor <= cursor or len(rows) > MAX_CANDLES:
                    raise ValueError('Non-progressing/oversized history')
                cursor = next_cursor
                if cursor >= end*1000:
                    break
    payload = dict(symbol='BTCUSDT', timeframe='15m', source=SOURCE, public_endpoint=PUBLIC_URL,
                   fetched_at_utc=datetime.now(timezone.utc).isoformat(), candles=rows)
    encoded = json.dumps(payload, allow_nan=False).encode()
    if len(encoded) > MAX_BYTES:
        raise ValueError('Snapshot exceeds size limit')
    # Never overwrite an existing snapshot: retain immutable input evidence.
    with path.open('xb') as out:
        out.write(encoded)
    load_snapshot(path, start, end, warmup)


async def replay(candles, start, end, *, max_seconds=600, settings=None, fallback_policy='PAPER_SETTINGS'):
    """Same ordered calls as Service.auto_tick, excluding owner/network lifecycle.

    Store lives in TemporaryDirectory; no import of app.main or private clients.
    SignalReader evaluates unchanged production formulas and exact snapshot match.
    """
    validate_candles(candles, '15m', now=end, contiguous=True)
    clock = [(start)*1000]
    prefix = [c for c in candles if c.time < start]
    if len(prefix) < 500:
        raise ValueError('Production context requires at least 500 warm-up candles')
    requested = [c for c in candles if start <= c.time < end]
    if not requested:
        raise ValueError('No evaluation candles')
    async def fetch(symbol, timeframe):
        return dict(symbol=symbol, timeframe=timeframe, source=SOURCE, stale=False,
                    fetched_at=utc(clock[0]/1000), last_closed_at=prefix[-1].time+STEP,
                    candles=[asdict(c) for c in prefix[-500:]])
    async def history(symbol, timeframe):
        return Dataset(list(prefix), SOURCE, clock[0]/1000, len(prefix), 'Frozen causal diagnostic snapshot')
    market = Market(fetch, clock=lambda: clock[0])
    reader = SignalReader(history)
    signals, refusals, decisions = Counter(), Counter(), Counter()
    first, ledger_decisions = [], []
    opened = 0
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='aura-auto-diagnostic-') as folder:
        engine = Engine(Store(Path(folder)/'diagnostic.sqlite3'), settings or Settings(), clock=lambda: clock[0])
        auto = Auto(engine)
        auto.configure(True, await market.window('BTCUSDT', '15m'), fallback_policy=fallback_policy)
        generation = auto.state()['generation']
        processed = 0
        for candle in requested:
            if time.monotonic()-began > max_seconds:
                raise TimeoutError('Replay CPU budget exceeded; no complete performance result available')
            prefix.append(candle)
            clock[0] = (candle.time+STEP)*1000
            window = await market.window('BTCUSDT', '15m')
            # Production exits precede entries; no pre-entry candle SL/TP lookup.
            engine.advance(window)
            signal = await reader.read(window)
            signals[signal.direction] += 1
            if signal.direction in ('LONG', 'SHORT') and len(first) < 5:
                first.append(dict(direction=signal.direction, candle_open_utc=utc(candle.time),
                                  signal_close_utc=utc(candle.time+STEP)))
            auto.process(window, signal, generation)
            decision = next(d for d in auto.state()['decisions'] if d['candle_time'] == candle.time)
            ledger_decisions.append(decision)
            reason = decision['rejection_reason']
            decisions[reason or 'OPENED'] += 1
            if decision['trade_opened']:
                opened += 1
            elif signal.direction in ('LONG', 'SHORT'):
                refusals[reason] += 1
            processed += 1
            if processed % 100 == 0:
                print(f'Processed {processed}/{len(requested)} closed candles', file=sys.stderr)
        snapshot = engine.snapshot('ALL')
        with engine.store.transaction(write=False) as db:
            trades = engine.store.trades(db)
            curve = [dict(r) for r in db.execute('SELECT * FROM curve ORDER BY seq')]
        closed = [t for t in trades if t['status']=='CLOSED']
        # Independent exact-decimal cross-check, not another execution engine.
        expected_pnl = sum((Decimal(t['realized_pnl']) for t in closed), Decimal(0))
        with localcontext() as context:
            context.prec = 64
            tick = Decimal('0.00000001')
            for trade in closed:
                entry, exit_price, size = map(Decimal, (trade['entry_price'], trade['exit_price'], trade['position_size']))
                sign = 1 if trade['direction']=='LONG' else -1
                gross = (sign*(exit_price-entry)*size).quantize(tick, rounding=ROUND_HALF_EVEN)
                rate=Decimal(trade['commission_pct'])/100
                entry_fee = (entry*size*rate).quantize(tick, rounding=ROUND_CEILING)
                exit_fee = (exit_price*size*rate).quantize(tick, rounding=ROUND_CEILING)
                reference = (gross-entry_fee-exit_fee).quantize(tick, rounding=ROUND_HALF_EVEN)
                if reference != Decimal(trade['realized_pnl']):
                    raise ValueError('Independent LONG/SHORT fee-inclusive PnL mismatch')
        if expected_pnl != Decimal(snapshot['statistics']['net_pnl']):
            raise ValueError('Independent realized PnL journal consistency failure')
        if signals['LONG']+signals['SHORT'] != opened+sum(refusals.values()):
            raise ValueError('Signal accounting mismatch')
        return dict(status='COMPLETE', observed_candles=processed,
                    signals={side: signals[side] for side in ('LONG','SHORT','WAIT')},
                    entries=opened, rejections=dict(refusals), decision_counts=dict(decisions),
                    closed_trades=len(closed), net_realized_pnl=str(expected_pnl),
                    maximum_drawdown_pct=snapshot['statistics']['maximum_drawdown_pct'],
                    first_five_signals=first, statistics=snapshot['statistics'],
                    trades=trades, decisions=ledger_decisions, equity_curve=curve,
                    activation_baseline_utc=utc(start-STEP))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-date', help='Exclusive complete UTC day boundary (YYYY-MM-DD)')
    parser.add_argument('--snapshot', type=Path, help='Authentic frozen numeric OHLCV JSON')
    parser.add_argument('--fetch', action='store_true', help='Opt-in public GET, no credentials, no retries')
    parser.add_argument('--warmup', type=int, default=10000)
    parser.add_argument('--max-seconds', type=int, default=600)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    start, end = period(args.end_date)
    if not 500 <= args.warmup <= MAX_CANDLES-(end-start)//STEP or not 1 <= args.max_seconds <= 3600:
        parser.error('Warm-up/budget outside bounded range')
    # Reject overwrites, including an accidentally supplied live SQLite file.
    if args.output.exists() or (args.snapshot and args.output.resolve()==args.snapshot.resolve()):
        parser.error('Output must be a new file distinct from snapshot')
    result = manifest(start, end, args.warmup)
    exit_code = 2
    try:
        if args.fetch:
            if args.snapshot is None:
                parser.error('--fetch requires a new --snapshot path')
            asyncio.run(fetch_snapshot(args.snapshot, start, end, args.warmup))
        if args.snapshot is not None:
            candles, digest, excluded = load_snapshot(args.snapshot, start, end, args.warmup)
            result.update(snapshot_sha256=digest, excluded_candles=excluded, warmup_actual=args.warmup)
            result.update(asyncio.run(replay(candles, start, end, max_seconds=args.max_seconds)))
            exit_code = 0
    except (ValueError, OSError, TimeoutError) as error:
        # Never expose raw upstream response/error bodies or URLs.
        result.update(status='INCOMPLETE', error_type=type(error).__name__)
    except Exception:
        result.update(status='INCOMPLETE', error_type='DIAGNOSTIC_FAILED')
    with args.output.open('x') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
    print(f"{result['status']}: {args.output}")
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
