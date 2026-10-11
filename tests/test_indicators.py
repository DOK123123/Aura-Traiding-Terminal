import math

import pytest

from app.indicators import analyze, atr, ema, rsi
from app.models import Candle


def candles(values):
    return [Candle(i * 60, p, p + 1, p - 1, p, 10) for i, p in enumerate(values)]


def test_ema_sma_seed_and_recurrence():
    assert ema([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]


def test_rsi_wilder_reference():
    prices = [44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28]
    assert rsi(prices)[14] == pytest.approx(70.4641, abs=.001)


def test_flat_market_has_neutral_score():
    result = analyze(candles([100.] * 500))
    assert result['rsi'] == 50
    assert result['atr'] == 2
    assert result['signal_up'] == result['signal_down'] == 50
    assert result['trend'] == 'Neutral'
    assert result['volatility_pct'] == 0


def test_atr_includes_gap():
    bars = [Candle(0, 100, 101, 99, 100, 1), Candle(60, 110, 111, 109, 110, 1), Candle(120, 110, 112, 109, 111, 1)]
    assert atr(bars, 2) == [None, 6.5, 4.75]


@pytest.mark.parametrize('direction', [1, -1])
def test_direction_and_score_bounds(direction):
    result = analyze(candles([1000 + direction * i for i in range(500)]))
    assert result['trend'] == ('Bullish' if direction == 1 else 'Bearish')
    assert 5 <= result['signal_up'] <= 95
    assert result['signal_up'] + result['signal_down'] == 100
    assert (result['signal_up'] > 50) == (direction == 1)
    assert result['rsi'] == (100 if direction == 1 else 0)


def test_zero_atr_does_not_divide_by_zero():
    result = analyze([Candle(i * 60, 100, 100, 100, 100, 0) for i in range(50)])
    assert result['signal_up'] == 50
    assert all(math.isfinite(result[k]) for k in ('rsi','atr','volatility_pct'))


def test_volatility_spike_damps_signal():
    values = [1000 + i * .1 for i in range(480)] + [1050 + i * 5 * (-1)**i for i in range(20)]
    result = analyze(candles(values))
    assert result['volatility_ratio'] > 1
    assert result['damping'] < 1
    raw = 45 * sum(result['factors'].values())
    assert abs(result['signal_up'] - 50) <= abs(raw) + .05


def test_insufficient_history():
    with pytest.raises(ValueError):
        analyze(candles([100] * 49))
