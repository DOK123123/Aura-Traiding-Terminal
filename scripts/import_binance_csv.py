"""Create an immutable local historical snapshot for Strategy Lab.

The output is research-only JSON.  It never contacts an exchange and never
touches the Paper Trading database.  A full Strategy Lab experiment requires
its normal 250 four-hour-bar warm-up; ``--start`` selects the first evaluated
UTC boundary after that warm-up and does not discard source rows from the
provenance section.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lab.local_csv import load_binance_csv
from app.lab.models import LabError, STEPS, SOURCE, WARMUP_4H, canonical
from app.lab.data import restore


def snapshot(path: Path, *, start: int | None = None, output_format: str = 'raw', month: str | None = None) -> dict:
    bars, info = load_binance_csv(path, timeframe="15m")
    if month is not None:
        try:
            begin = datetime.strptime(month, '%Y-%m').replace(tzinfo=timezone.utc)
            next_month = begin.replace(year=begin.year+1, month=1) if begin.month==12 else begin.replace(month=begin.month+1)
        except ValueError:
            raise LabError('INVALID_MONTH') from None
        if (bars[0].time != int(begin.timestamp()) or bars[-1].time+900 != int(next_month.timestamp())
                or len(bars) != int((next_month-begin).total_seconds())//900):
            raise LabError('INCOMPLETE_MONTH')
    if output_format == 'diagnostic':
        if start is not None:
            raise LabError('INVALID_RANGE')
        # Existing production diagnostic loader expects numeric Candle OHLCV.
        # Decimal originals remain in bars for an auditable precision boundary.
        return dict(symbol='BTCUSDT', timeframe='15m', source='Binance · Spot',
                    candles=[dict(time=b.time, **{k:float(getattr(b,k)) for k in ('open','high','low','close','volume')}) for b in bars],
                    bars=[b.data() for b in bars], local_csv=info, history_truncated=False)
    if output_format not in ('raw', 'lab') or (output_format == 'lab' and start is None):
        raise LabError('INVALID_FORMAT')
    step = STEPS["15m"]
    # Without --start this is a complete raw local snapshot.  It is useful for
    # provenance and production-diagnostic tooling, but is deliberately not
    # advertised as a Strategy Lab run (which requires 250 four-hour warm-up
    # bars).  Supplying --start requests the stricter Lab-compatible shape.
    if start is None:
        selected_start = bars[0].time
        warmup_start = None
        selected = bars
        lab_ready = False
    else:
        selected_start = start
        if selected_start % (4 * 3600) or selected_start < bars[0].time:
            raise LabError("INVALID_RANGE")
        warmup_start = selected_start - WARMUP_4H * STEPS["4h"]
        if warmup_start < bars[0].time:
            raise LabError("INSUFFICIENT_WARMUP")
        if bars[-1].time + step <= selected_start:
            raise LabError("INSUFFICIENT_DATA")
        selected = [b for b in bars if b.time >= warmup_start]
        lab_ready = True
    result = {
        "symbol": "BTCUSDT",
        "source": SOURCE,
        "start": selected_start,
        "end": bars[-1].time + step,
        "warmup_start": warmup_start,
        "base_timeframe": "15m",
        "base_count": len(selected),
        "bars": [b.data() for b in selected],
        "excluded_forming": 0,
        "requested_count": len(selected),
        "actual_common_coverage": {"start": selected_start, "end_exclusive": bars[-1].time + step},
        "history_truncated": False,
        "strategy_lab_compatible": lab_ready,
        "local_csv": {**info, "rows_available": len(bars),
                       "warmup_bars": 0 if not lab_ready else WARMUP_4H * 16,
                       "excluded_before_warmup": len(bars)-len(selected)},
    }
    if lab_ready:
        restore(result)  # Check the actual existing backtester contract/bounds.
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, help="UTC evaluation start, aligned to a 4h boundary")
    parser.add_argument('--format', choices=['raw', 'lab', 'diagnostic'], default='raw')
    parser.add_argument('--month', help='Require exact full UTC month coverage, e.g. 2026-09')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output must be a new file")
    try:
        data = snapshot(args.csv, start=args.start, output_format=args.format, month=args.month)
    except LabError as error:
        parser.error(error.code)
    with args.output.open('xb') as stream:
        stream.write(canonical(data))
    print(f"imported={data['local_csv']['count']} selected={data.get('base_count', len(data.get('candles', [])))} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
