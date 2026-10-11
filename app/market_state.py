"""Small live window, independent of HTTP, providers and future archive storage."""
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from .models import Candle, INTERVALS
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
    def __init__(self, candles, timeframe, limit):
        if len(candles) != limit:
            raise DataUnavailable("Incomplete live bootstrap")
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
            self.candles[-1] = candle
        if closed:
            self.closed_through = candle.time
        self.event_time = event_time
        return rolled
