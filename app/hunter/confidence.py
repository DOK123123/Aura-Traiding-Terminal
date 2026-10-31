"""Causal, descriptive 0–100 technical score for manual research only.

This score is *not* an empirical win probability or a strategy approval.
Correlated observations share bounded groups rather than being multiplied.
"""
import hashlib
import math
from pathlib import Path
import numpy as np

from .costs import risk_reward
from .engine import Prepared, ema, wilder, RULES
from .market import SOURCE, fresh_quote


VERSION = 'AURA5_TECHNICAL_SCORE_V1_FROZEN'
SCORE_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
GROUP_CAPS = {'trend': 30, 'momentum': 25, 'structure': 20,
              'volume': 10, 'support_resistance': 15}


def _macd(closes):
    fast, slow = ema(closes, 12), ema(closes, 26)
    macd = fast - slow
    signal = ema(macd[25:], 9)
    return float(macd[-1]), float(signal[-1])


def _fixed_window_indicators(prepared, i):
    """Exactly the 260-bar seed used by the live Bitget observer.

    Historical full-series EMA200 would otherwise silently disagree with live.
    """
    w=slice(i-259,i+1)
    if np.any(np.diff(prepared.time[w]) != prepared.step):
        return None
    c,h,l=prepared.close[w],prepared.high[w],prepared.low[w]
    e20,e50,e200=(float(ema(c,n)[-1]) for n in (20,50,200))
    previous=np.r_[c[0],c[:-1]]
    tr=np.maximum(h-l,np.maximum(abs(h-previous),abs(l-previous)))
    atr=float(wilder(tr)[-1])
    delta=np.diff(c)
    gain=float(wilder(np.maximum(delta,0))[-1])
    loss=float(wilder(np.maximum(-delta,0))[-1])
    rsi=50. if gain==0 and loss==0 else 100-100/(1+gain/loss) if loss>0 else 100.
    macd,signal=_macd(c)
    return e20,e50,e200,atr,rsi,macd,signal


def score_at(prepared: Prepared, i: int) -> list[dict]:
    """Pure historical score at an existing closed-bar index; never reads i+1.

    A bounded 260-bar MACD seed matches the live input contract. The caller
    must supply complete, actual closed OHLCV; no historical Bid/Ask is implied.
    """
    if (not isinstance(prepared, Prepared) or type(i) is not int or i < 259
            or i >= len(prepared.rows) or not prepared.valid[i]):
        return []
    indicators=_fixed_window_indicators(prepared,i)
    if indicators is None:return []
    e20,e50,e200,atr,rsi,macd,macd_signal=indicators
    denominator = float(prepared.volume20[i-1])
    if not denominator > 0:
        return []
    relative_volume = float(prepared.volume[i] / denominator)
    if not all(math.isfinite(x) for x in (atr, relative_volume, macd, macd_signal)) or atr <= 0:
        return []
    price = float(prepared.close[i])
    previous = float(prepared.close[i-1])
    upper, lower = float(prepared.high20[i-1]), float(prepared.low20[i-1])
    if not lower < upper or not math.isfinite(rsi):
        return []
    output = []
    for direction, sign in (('LONG', 1), ('SHORT', -1)):
        groups = {}
        factors, conflicts = [], []
        trend = (15 if sign * (e20-e50) > 0 else 0)
        trend += 15 if sign * (e50-e200) > 0 else 0
        groups['trend'] = trend
        (factors if trend >= 15 else conflicts).append('EMA20/50/200: единая группа тренда')
        momentum = (12 if sign * (rsi-50) > 0 and 30 <= rsi <= 70 else 0)
        momentum += 13 if sign * (macd-macd_signal) > 0 else 0
        groups['momentum'] = momentum
        (factors if momentum >= 13 else conflicts).append('RSI + MACD: общая группа импульса')
        structure = 10 if sign * (price-previous) > 0 else 0
        structure += 10 if sign * (price-(upper+lower)/2) > 0 else 0
        groups['structure'] = structure
        (factors if structure >= 10 else conflicts).append('Положение закрытия в предыдущем диапазоне')
        directional_body = sign * (price-float(prepared.open[i])) > 0
        groups['volume'] = (10 if relative_volume >= 1.2 else 5 if relative_volume >= .8 else 0) if directional_body else 0
        (factors if groups['volume'] else conflicts).append('Объём и направление закрытой свечи')
        # Correlated range/support/breakout tests never create separate votes.
        near = abs(price-(lower if sign == 1 else upper)) <= atr
        breakout = sign * (price-(upper if sign == 1 else lower)) > 0
        groups['support_resistance'] = 15 if near or breakout else 0
        (factors if groups['support_resistance'] else conflicts).append('Поддержка/сопротивление 20 закрытых свечей')
        score = sum(groups.values())
        if set(groups) != set(GROUP_CAPS) or any(not 0 <= groups[k] <= GROUP_CAPS[k] for k in groups):
            raise ValueError('INVALID_SCORE_COMPONENTS')
        output.append({'direction': direction, 'score': int(score),
                       'score_groups': groups, 'factors': factors, 'contradictions': conflicts,
                       'atr': atr, 'reference_close': price, 'support': lower, 'resistance': upper,
                       'closed_at': int(prepared.time[i]) + prepared.step})
    return output


def technical_scores(prepared: Prepared, quote: dict, now: float) -> list[dict]:
    """Evaluate only the last closed exchange candle, both independent sides.

    Entry/SL/TP are illustrative quote-priced plans, never order instructions.
    The existing technical trigger, eligibility and CONFIRMED gates are untouched.
    """
    if not isinstance(prepared, Prepared) or len(prepared.rows) < RULES['warmup']:
        return []
    i = len(prepared.rows) - 1
    cutoff = int(prepared.time[i]) + prepared.step
    if (not prepared.valid[i] or cutoff != int(now // prepared.step) * prepared.step
            or not fresh_quote(quote, now)):
        return []
    output = []
    for evidence in score_at(prepared, i):
        direction = evidence['direction']
        sign = 1 if direction == 'LONG' else -1
        score = evidence['score']
        atr = evidence['atr']
        entry = float(quote['ask' if sign == 1 else 'bid'])
        anchor = evidence['support'] if sign == 1 else evidence['resistance']
        stop_distance = max(1.5*atr, sign*(entry-anchor)+.25*atr)
        stop = entry-sign*stop_distance
        target = entry+sign*2.5*stop_distance
        costs = risk_reward(entry, stop, target, direction, prepared.step, 24,
                            float(quote['ask']-quote['bid']))
        allowed = bool(costs and costs['net_rr'] >= RULES['planning']['min_net_rr']
                       and math.isfinite(stop) and math.isfinite(target) and stop > 0 and target > 0)
        identity = f'{VERSION}:{prepared.frame}:{direction}:{cutoff}'
        output.append({
            'id': hashlib.sha256(identity.encode()).hexdigest(), 'score_version': VERSION,
            'score_model_sha256': SCORE_HASH,
            'score': int(score), 'score_groups': evidence['score_groups'],
            'strength': 'WEAK' if score < 65 else 'MODERATE' if score < 80 else 'STRONG',
            'direction': direction, 'frame': prepared.frame, 'source': SOURCE,
            'symbol': 'BTCUSDT', 'closed_at': cutoff, 'observed_at': now,
            'valid_until': cutoff + prepared.step,
            'quote_time': quote['time'], 'quote_received_at': quote['received_at'],
            'bid': quote['bid'], 'ask': quote['ask'],
            'entry': entry, 'sl': stop, 'tp': target, 'net_rr': costs['net_rr'] if costs else None,
            'costs': costs, 'risk_gates_passed': allowed,
            'technical_trigger': False, 'statistical_status': 'UNVALIDATED',
            'probability_tp_before_sl': None,
            'factors': evidence['factors'], 'contradictions': evidence['contradictions'],
            'assumptions': 'Illustrative ATR stop and 2.5R target; not a six-family technical trigger',
            'cancel': 'Stale Bid/Ask, new candle, invalid geometry, net R/R below 1.5, or manual cancellation',
            'state': 'WATCH_RESEARCH' if allowed and score >= 50 else 'NOT_READY',
            'manual_only': True, 'exchange_execution': False,
        })
    return output
