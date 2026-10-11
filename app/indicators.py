"""Pure indicator functions. No provider or HTTP dependencies."""
import math
from statistics import stdev

from .models import Candle


def ema(values: list[float], period: int) -> list[float | None]:
    result = [None] * len(values)
    if len(values) < period:
        return result
    value = sum(values[:period]) / period
    result[period - 1] = value
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        value += alpha * (values[i] - value)
        result[i] = value
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    result = [None] * len(values)
    if len(values) <= period:
        return result
    changes = [b - a for a, b in zip(values, values[1:])]
    gain = sum(max(d, 0) for d in changes[:period]) / period
    loss = sum(max(-d, 0) for d in changes[:period]) / period

    def value():
        return 50.0 if gain == loss == 0 else (100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))

    result[period] = value()
    for i in range(period + 1, len(values)):
        delta = changes[i - 1]
        gain = (gain * (period - 1) + max(delta, 0)) / period
        loss = (loss * (period - 1) + max(-delta, 0)) / period
        result[i] = value()
    return result


def atr(candles: list[Candle], period: int = 14) -> list[float | None]:
    result = [None] * len(candles)
    if len(candles) < period:
        return result
    ranges = [c.high - c.low if i == 0 else max(
        c.high - c.low, abs(c.high - candles[i - 1].close), abs(c.low - candles[i - 1].close)
    ) for i, c in enumerate(candles)]
    value = sum(ranges[:period]) / period
    result[period - 1] = value
    for i in range(period, len(candles)):
        value = (value * (period - 1) + ranges[i]) / period
        result[i] = value
    return result


def clip(value: float, low: float = -1, high: float = 1) -> float:
    return max(low, min(high, value))


def analyze(candles: list[Candle]) -> dict:
    if len(candles) < 50:
        raise ValueError("At least 50 candles required")
    closes = [c.close for c in candles]
    e20, e50, rs, at = ema(closes, 20), ema(closes, 50), rsi(closes), atr(candles)
    price, strength, average_range = closes[-1], rs[-1], at[-1]
    log_returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    volatility = stdev(log_returns)
    recent_volatility = stdev(log_returns[-20:])
    ratio = recent_volatility / volatility if volatility else 1.0
    damping = 1 / max(1.0, ratio)
    scale = max(average_range, price * 1e-10)
    factors = {
        "ema": 0.5 * clip((e20[-1] - e50[-1]) / scale),
        "rsi": 0.2 * clip((strength - 50) / 25),
        "momentum": 0.3 * clip((price - closes[-11]) / (3 * scale)),
    }
    up = round(50 + 45 * sum(factors.values()) * damping, 1)
    spread = (e20[-1] - e50[-1]) / scale
    trend = "Bullish" if spread > 0.1 else "Bearish" if spread < -0.1 else "Neutral"
    return {
        "trend": trend, "signal_up": up, "signal_down": round(100 - up, 1),
        "price": price, "rsi": strength, "atr": average_range,
        "ema20": e20[-1], "ema50": e50[-1], "count": len(candles),
        "return_pct": (price / closes[0] - 1) * 100,
        "volatility_pct": volatility * 100,
        "momentum_pct": (price / closes[-11] - 1) * 100,
        "factors": factors, "volatility_ratio": ratio, "damping": damping,
        "series": {name: [{"time": c.time, "value": value} for c, value in zip(candles, values)
                           if value is not None]
                   for name, values in (("ema20", e20), ("ema50", e50), ("rsi", rs), ("atr", at))},
    }
