"""Offline full-month production replay from local Binance CSV, no network.

Reuses import_binance_csv and backtest_aura_history. A causal feature-prefix
cache removes repeated computation only; the production signal evaluator,
matching, filters, MTF, SignalReader, Auto and Paper Engine remain unchanged.
Run only in a standalone diagnostic process, never import into the web worker.
"""
import argparse
import asyncio
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import import_binance_csv as importer
from scripts import backtest_aura_history as backtest
from app.patterns.config import PatternConfig
from app.patterns.features import Features, build_features
from app.patterns.engine import evaluate
from app.lab.models import canonical


class CausalFeatureCache:
    """Only a verified historical prefix is exposed to production evaluate.

    build_features has no full-sample fit: every descriptor uses its own past.
    Prefix equivalence and future perturbation are independently tested. No
    future vector/fact is exposed; outcomes/MTF still read the supplied prefix.
    """
    def __init__(self, candles):
        self.candles = tuple(candles)
        self.config = PatternConfig()
        self.features = build_features(list(candles), self.config.lookback, 500)
        self.features.vectors.setflags(write=False)

    def __call__(self, candles, step, context, config, target=None, features=None, include_charts=True):
        n = len(candles)
        if (step != 900 or context != 500 or config != self.config or features is not None
                or n > len(self.candles) or tuple(candles) != self.candles[:n]
                or target not in (None, n-1)):
            raise ValueError('Causal cache scope/prefix mismatch')
        prefix = Features(self.features.vectors[:n], self.features.facts[:n], self.features.valid_from)
        return evaluate(candles, step, context, config, target, prefix, include_charts)

    def verify(self, indices):
        for index in indices:
            rows = list(self.candles[:index+1])
            direct = evaluate(rows,900,500,self.config,index,None,False)
            cached = self(rows,900,500,self.config,index,None,False)
            if direct != cached:
                raise ValueError('Cached/direct production signal mismatch')
        return list(indices)


async def run(csv_path, end_date, budget, *, cache_enabled=True):
    # The task is Binance's complete 12-column format, not an OHLCV shorthand.
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        if len(next(csv.reader(stream), [])) != 12:
            raise ValueError('This replay requires 12-column Binance CSV')
    snapshot = importer.snapshot(csv_path, output_format='diagnostic')
    start,end = backtest.core.period(end_date,30)
    if backtest.core.utc(start)[8:10] != '01' or backtest.core.utc(end)[8:10] != '01':
        raise ValueError('Require a complete 30-day UTC calendar month')
    with tempfile.TemporaryDirectory(prefix='aura-csv-replay-') as directory:
        path = Path(directory)/'input.json'
        path.write_bytes(canonical(snapshot))
        candles,_,excluded = backtest.core.load_snapshot(path,start,end,10000)
        cache = CausalFeatureCache(candles) if cache_enabled else None
        indices = [9999,10000,10500,11500,12879]
        verified = cache.verify(indices) if cache else []
        args = SimpleNamespace(paper_config=None, fetch_dir=None, snapshot=path, periods=[30],
                               end_date=end_date, warmup=10000, max_seconds=budget)
        if cache is not None:
            with patch.object(backtest.production_signals, 'evaluate', cache):
                result = await backtest.run(args)
        else:
            result = await backtest.run(args)
    result['local_csv'] = snapshot['local_csv']
    result['data_selection'] = dict(total_csv_candles=len(snapshot['candles']),
            selected_candles=len(candles),excluded_before_warmup=excluded,
            warmup_candles=10000,warmup_start_utc=backtest.core.utc(candles[0].time),
            evaluation_start_utc=backtest.core.utc(start),end_exclusive_utc=backtest.core.utc(end))
    result['diagnostic_adapter'] = dict(sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            feature_mode='CAUSAL_PREFIX_CACHE' if cache else 'DIRECT_PRODUCTION',
            direct_equivalence_verified_indices=verified,
            future_features_exposed=False,live_database_access=False,network_used=False)
    return result


def enable_sandbox_poll():
    """Explicit diagnostic-only workaround for sandbox selector thread wakeups."""
    class PollLoop(asyncio.SelectorEventLoop):
        def _run_once(self):
            self.call_later(.01, lambda: None)
            super()._run_once()
    class PollPolicy(asyncio.DefaultEventLoopPolicy):
        def new_event_loop(self):
            return PollLoop()
    asyncio.set_event_loop_policy(PollPolicy())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path)
    parser.add_argument('--end-date',default='2026-10-01')
    parser.add_argument('--max-seconds',type=int,default=3600)
    parser.add_argument('--direct',action='store_true',help='Disable causal cache; slow exact recomputation')
    parser.add_argument('--sandbox-poll',action='store_true',help='Explicit standalone sandbox wakeup workaround')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.exists() or not 1<=args.max_seconds<=86400:
        parser.error('Output must be new; budget must be 1..86400 seconds')
    if args.sandbox_poll:
        enable_sandbox_poll()
    result=asyncio.run(run(args.csv,args.end_date,args.max_seconds,cache_enabled=not args.direct))
    result['diagnostic_adapter']['sandbox_poll']=args.sandbox_poll
    with args.output.open('xb') as stream:
        stream.write(canonical(result))
    print(' '.join(f"{r['days']}d={r['status']}" for r in result['results']))
    return 0 if result['actual_backtest_performed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
