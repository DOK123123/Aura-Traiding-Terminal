"""Small live window, independent of HTTP, providers and future archive storage."""
from dataclasses import dataclass
from typing import AsyncIterator, Protocol
import time

from .models import Candle, INTERVALS, validate_candles, data_fresh
from .providers import DataUnavailable


@dataclass(frozen=True)
class SeriesKey:
    symbol: str
    timeframe: str
    source: str
    price_type: str


class HistoryReader(Protocol):
    """Future archive contract: source-separated, closed candles, bounded chunks.

    start inclusive, end exclusive, UTC epoch seconds. No implementation or
    similarity search yet. A large archive must never be loaded into LiveWindow.
    """
    def iter_chunks(self, key: SeriesKey, start: int, end: int,
                    chunk_size: int = 10000) -> AsyncIterator[list[Candle]]: ...


class LiveWindow:
    def __init__(self, candles, timeframe, limit, *, now=None):
        if len(candles) != limit:
            raise DataUnavailable("Incomplete live bootstrap")
        now = time.time() if now is None else now
        validate_candles(candles, timeframe, now=now,
                         contiguous=True, count=limit)
        if not data_fresh(candles[-1], timeframe, now):
            raise DataUnavailable('Stale live bootstrap: fresh history required')
        self.candles = list(candles)
        self.step, self.limit = INTERVALS[timeframe], limit
        self.closed_through = candles[-1].time
        self.event_time = 0

    def apply(self, candle: Candle, closed: bool, event_time: int):
        """Return None for old events; bool says whether the window rolled."""
        last = self.candles[-1]
        if candle.time <= self.closed_through or event_time <= self.event_time:
            return None
        if candle.time % self.step:
            raise DataUnavailable("Misaligned live candle")
        if candle.time < last.time:
            return None
        rolled = candle.time > last.time
        if rolled:
            if candle.time != last.time + self.step or self.closed_through < last.time:
                raise DataUnavailable("Stream gap: fresh history required")
            self.candles.append(candle)
            self.candles = self.candles[-self.limit:]
        else:
            if (candle.open != last.open or candle.high < last.high or candle.low > last.low
                    or (last.volume is not None and candle.volume is not None and candle.volume < last.volume)):
                raise DataUnavailable("Regressing live OHLCV: fresh history required")
            self.candles[-1] = candle
        if closed:
            self.closed_through = candle.time
        self.event_time = event_time
        return rolled
