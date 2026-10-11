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
        values = (self.open, self.high, self.low, self.close) + (() if self.volume is None else (self.volume,))
        if (not all(math.isfinite(v) for v in values) or self.low <= 0
                or self.high < max(self.open, self.close, self.low)
                or self.low > min(self.open, self.close) or (self.volume is not None and self.volume < 0)):
            raise ValueError("Invalid OHLCV candle")
