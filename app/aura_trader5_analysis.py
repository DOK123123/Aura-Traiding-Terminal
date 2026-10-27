"""Read-only technical analysis primitives for Aura Trader 5.

Pure calculations: no exchange access, no order submission, no persistence.
All candles must be closed and supplied in chronological order.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class Candle:
    high: float
    low: float
    close: float


def _period(period: int) -> None:
    if type(period) is not int or not 1 <= period <= 10000:
        raise ValueError("period must be an integer between 1 and 10000")


def _finite(value: float) -> bool:
    try:return type(value) in (int,float) and isfinite(value)
    except OverflowError:return False


def _validate(candles: Sequence[Candle]) -> None:
    if not candles:
        raise ValueError("No candles")
    for c in candles:
        if not all(_finite(v) and v>0 for v in (c.high, c.low, c.close)):
            raise ValueError("Non-finite candle")
        if c.low > c.high or not c.low <= c.close <= c.high:
            raise ValueError("Invalid OHLC candle")


def ema(values: Sequence[float], period: int) -> float | None:
    _period(period)
    if not all(_finite(v) for v in values):
        raise ValueError("Non-finite value")
    if len(values) < period:
        return None
    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for value in values[period:]:
        result += alpha * (value - result)
    return result


def rsi(closes: Sequence[float], period: int = 14) -> float | None:
    """Wilder RSI, seeded with the first period's average gains/losses."""
    _period(period)
    if not all(_finite(v) for v in closes):
        raise ValueError("Non-finite value")
    if len(closes) < period + 1:
        return None
    deltas = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(d, 0) for d in deltas[:period]) / period
    loss = sum(max(-d, 0) for d in deltas[:period]) / period
    for delta in deltas[period:]:
        gain = (gain * (period - 1) + max(delta, 0)) / period
        loss = (loss * (period - 1) + max(-delta, 0)) / period
    if loss == 0:
        return 50.0 if gain == 0 else 100.0
    return 100 - 100 / (1 + gain / loss)


def atr(candles: Sequence[Candle], period: int = 14) -> float | None:
    """Wilder ATR; first TR uses previous close, so period+1 candles required."""
    _period(period)
    _validate(candles)
    if len(candles) < period + 1:
        return None
    trs = [
        max(curr.high - curr.low, abs(curr.high - prev.close), abs(curr.low - prev.close))
        for prev, curr in zip(candles, candles[1:])
    ]
    result = sum(trs[:period]) / period
    for tr in trs[period:]:
        result = (result * (period - 1) + tr) / period
    return result


def fibonacci_levels(swing_low: float, swing_high: float, direction: str) -> dict[str, float]:
    """Retracement prices measured from the end of an up/down impulse."""
    if not all(_finite(v) and v>0 for v in (swing_low, swing_high)) or swing_high <= swing_low:
        raise ValueError("Invalid swing range")
    if direction not in ("up", "down"):
        raise ValueError("direction must be up or down")
    span = swing_high - swing_low
    ratios = (0.236, 0.382, 0.5, 0.618, 0.786)
    if direction == "up":
        return {f"{r:.3f}": swing_high - span * r for r in ratios}
    return {f"{r:.3f}": swing_low + span * r for r in ratios}


def risk_plan(entry: float, stop: float, target: float, side: str,
              account_equity: float, risk_pct: float = 1.0,
              fee_rate: float = 0.0006, slippage_rate: float = 0.0002) -> dict[str, float]:
    """Hypothetical linear USDT contract sizing, fees on entry+exit.

    Returns a planning estimate, not an order size validated against Bitget lot rules.
    """
    vals = (entry, stop, target, account_equity, risk_pct, fee_rate, slippage_rate)
    if not all(_finite(v) for v in vals) or min(entry, stop, target, account_equity, risk_pct) <= 0:
        raise ValueError("Invalid risk inputs")
    if not 0 <= fee_rate < 1 or not 0 <= slippage_rate < 1 or risk_pct > 100:
        raise ValueError("Invalid rates")
    if side == "long":
        if not stop < entry < target:
            raise ValueError("LONG requires stop < entry < target")
        reward = target - entry
        loss = entry - stop
    elif side == "short":
        if not target < entry < stop:
            raise ValueError("SHORT requires target < entry < stop")
        reward = entry - target
        loss = stop - entry
    else:
        raise ValueError("side must be long or short")
    entry_fill=entry*(1+slippage_rate if side=="long" else 1-slippage_rate)
    stop_fill=stop*(1-slippage_rate if side=="long" else 1+slippage_rate)
    target_fill=target*(1-slippage_rate if side=="long" else 1+slippage_rate)
    sign=1 if side=="long" else -1
    per_unit_risk=sign*(entry_fill-stop_fill)+(entry_fill+stop_fill)*fee_rate
    per_unit_reward=sign*(target_fill-entry_fill)-(entry_fill+target_fill)*fee_rate
    budget=account_equity*risk_pct/100
    quantity=budget/per_unit_risk
    estimated_reward=quantity*max(0.0,per_unit_reward)
    if not all(isfinite(v) for v in (budget,quantity,estimated_reward,per_unit_risk)):
        raise ValueError("Risk estimate overflow")
    return {
        "risk_budget_usdt": budget,
        "estimated_quantity": quantity,
        "estimated_loss_usdt": quantity * per_unit_risk,
        "estimated_reward_usdt": estimated_reward,
        "estimated_rr_after_costs": estimated_reward / budget,
    }
