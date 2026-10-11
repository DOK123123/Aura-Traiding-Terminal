from dataclasses import dataclass
import math

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


@dataclass(frozen=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None

    def __post_init__(self):
        if isinstance(self.time, bool) or not isinstance(self.time, int) or self.time < 0:
            raise ValueError("Invalid candle timestamp")
        values = (self.open, self.high, self.low, self.close) + (() if self.volume is None else (self.volume,))
        if (not all(math.isfinite(v) for v in values) or self.low <= 0
                or self.high < max(self.open, self.close, self.low)
                or self.low > min(self.open, self.close) or (self.volume is not None and self.volume < 0)):
            raise ValueError("Invalid OHLCV candle")


def validate_candles(candles, timeframe, *, now, closed=True, contiguous=False, count=None):
    """Validate a complete ordered window before analysis; never fill missing prices."""
    step = INTERVALS[timeframe]
    if not candles or (count is not None and len(candles) != count):
        raise ValueError("Incomplete candle window")
    for candle in candles:
        if not isinstance(candle, Candle):
            raise ValueError("Invalid candle record")
        candle.__post_init__()
        if candle.time % step or candle.time > now or (closed and candle.time + step > now):
            raise ValueError("Misaligned or future candle")
    for previous, current in zip(candles, candles[1:]):
        if current.time <= previous.time:
            raise ValueError("Duplicate or unordered candles")
        if contiguous and current.time != previous.time + step:
            raise ValueError("Candle gap: history refresh required")


def data_fresh(candle, timeframe, now, *, closed=True):
    step = INTERVALS[timeframe]
    reference = candle.time + step if closed else candle.time
    return reference <= now and now - reference <= 2 * step
