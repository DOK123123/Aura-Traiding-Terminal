"""Strict, offline Binance kline CSV importer for research snapshots.

This module has no network, Paper, exchange-account or execution imports.  It
accepts the Binance archive CSV shape and returns validated :class:`Bar`
records.  The caller decides whether the resulting range has enough warm-up
history for a particular experiment; this importer never fabricates bars.
"""
from __future__ import annotations

import csv
import io
import hashlib
import time
from pathlib import Path

from .models import Bar, LabError, STEPS, number, validate_series

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 20_000
BINANCE_HEADER = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume", "ignore",
)


def _timestamp(value: str, *, step: int) -> int:
    value = value.strip()
    if not value.isascii() or not value.isdigit() or len(value) not in (13, 16):
        raise LabError("INVALID_TIMESTAMPS")
    raw = int(value)
    # Binance exports use milliseconds; some exports use microseconds.  Do
    # not accept seconds because silently interpreting them is dangerous.
    if raw >= 10**15:
        stamp, remainder = divmod(raw, 1_000_000)
    elif raw >= 10**12:
        stamp, remainder = divmod(raw, 1_000)
    else:
        raise LabError("INVALID_TIMESTAMPS")
    if remainder or stamp % step:
        raise LabError("INVALID_TIMESTAMPS")
    return stamp


HEADERS = {6: BINANCE_HEADER[:6], 7: BINANCE_HEADER[:7], 12: BINANCE_HEADER}


def load_binance_csv(path: str | Path, *, timeframe: str = "15m", now: int | None = None) -> tuple[list[Bar], dict]:
    """Read and validate one local Binance archive CSV.

    Both the usual headerless Binance archive and the documented header form
    are accepted.  OHLCV, ordering, duplicate rows and interval gaps are
    validated before any snapshot can be produced.
    """
    step = STEPS.get(timeframe)
    if step is None:
        raise LabError("INVALID_TIMESTAMPS")
    file = Path(path)
    try:
        size = file.stat().st_size
        if size > MAX_BYTES:
            raise LabError("LOCAL_FILE_TOO_LARGE")
        with file.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
    except (OSError, ValueError):
        raise LabError("LOCAL_FILE_UNAVAILABLE") from None
    if size != len(raw) or size > MAX_BYTES:
        raise LabError("LOCAL_FILE_TOO_LARGE")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise LabError("INVALID_CSV") from None
    rows = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        first = next(rows)
    except (StopIteration, csv.Error):
        raise LabError("INVALID_CSV") from None
    normalized = tuple(cell.strip().lower().replace(" ", "_") for cell in first)
    has_header = bool(first) and any(c.isalpha() for c in first[0])
    if has_header and normalized != HEADERS.get(len(first)):
        raise LabError("INVALID_HEADERS")
    from itertools import chain
    data = rows if has_header else chain([first], rows)
    bars: list[Bar] = []
    def records():
        try:
            yield from data
        except csv.Error:
            raise LabError("INVALID_CSV") from None
    for row in records():
        if len(bars) >= MAX_ROWS:
            raise LabError("INVALID_ROW_COUNT")
        if len(row) != len(first) or len(row) not in HEADERS:
            raise LabError("INVALID_COLUMNS")
        try:
            stamp = _timestamp(row[0], step=step)
            values = [number(row[i].strip(), positive=(i < 5)) for i in range(1, 6)]
            bar = Bar(stamp, *values)
            if len(row) >= 7:
                close_raw = row[6].strip()
                if not close_raw.isascii() or not close_raw.isdigit():
                    raise LabError("INVALID_TIMESTAMPS")
                close_time = int(close_raw)
                unit = 1_000_000 if close_time >= 10**15 else 1_000
                if close_time != (stamp + step) * unit - 1:
                    raise LabError("INVALID_TIMESTAMPS")
                open_unit = 1_000_000 if int(row[0]) >= 10**15 else 1_000
                if unit != open_unit:
                    raise LabError("INVALID_TIMESTAMPS")
            if len(row) == 12:
                for i in (7, 9, 10, 11):
                    number(row[i].strip())
                trades = row[8].strip()
                if not trades.isascii() or not trades.isdigit() or len(trades) > 24:
                    raise LabError("INVALID_DATA")
            bars.append(bar)
        except LabError:
            raise
        except (ValueError, ArithmeticError, TypeError):
            raise LabError("INVALID_OHLCV") from None
    if not bars:
        raise LabError("INVALID_ROW_COUNT")
    # Check ordering before the common validator derives its closed-through
    # bound; this preserves the useful duplicate/unordered error even when a
    # duplicate happens to be the final row.
    for previous, current in zip(bars, bars[1:]):
        if current.time <= previous.time:
            raise LabError("DUPLICATE_OR_UNORDERED")
        if current.time - previous.time != step:
            raise LabError("MISSING_CANDLES")
    validate_series(bars, step, int(time.time()) if now is None else now)
    return bars, {
        "path": str(file),
        "format": "Binance kline CSV",
        "header": has_header,
        "timestamp_units": "microseconds or milliseconds",
        "timeframe": timeframe,
        "count": len(bars),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "transport": "local_file",
        "source_claim": "User-supplied Binance CSV; provenance not independently verified",
        "start": bars[0].time,
        "end_exclusive": bars[-1].time + step,
    }
