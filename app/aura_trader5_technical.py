"""Causal context for the manual analyst. No execution or account dependencies.

A swing at index i becomes visible only after `radius` subsequent bars CLOSE.
Divergences describe confirmed price/RSI pivots, not proven predictive signals.
"""
from collections.abc import Sequence
from app.models import Candle
from .aura_trader5_analysis import ema, rsi


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    # Reuse validation/seeding from the established pure primitive.
    ema(values, period)
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    value = sum(values[:period]) / period
    out[period - 1] = value
    for i in range(period, len(values)):
        value += 2 / (period + 1) * (values[i] - value)
        out[i] = value
    return out


def macd(values: Sequence[float]) -> dict:
    """12/26 SMA-seeded EMAs; 9-period signal begins at first valid MACD."""
    fast, slow = ema_series(values, 12), ema_series(values, 26)
    line = [a-b for a,b in zip(fast,slow) if a is not None and b is not None]
    signal = ema(line, 9)
    if signal is None:
        return dict(line=None, signal=None, histogram=None, bias='UNAVAILABLE')
    hist = line[-1] - signal
    return dict(line=line[-1], signal=signal, histogram=hist,
                bias='LONG' if hist > 0 else 'SHORT' if hist < 0 else 'NEUTRAL')


def confirmed_swings(bars: Sequence[Candle], step: int, radius: int = 2) -> list[dict]:
    if type(radius) is not int or not 1 <= radius <= 10:
        raise ValueError('INVALID_PIVOT_RADIUS')
    if type(step) is not int or step <= 0:
        raise ValueError('INVALID_STEP')
    result = []
    for i in range(radius, len(bars)-radius):
        b = bars[i]
        neighbors = list(bars[i-radius:i]) + list(bars[i+1:i+radius+1])
        for kind, price, is_extreme in (
            ('HIGH', b.high, all(b.high > n.high for n in neighbors)),
            ('LOW', b.low, all(b.low < n.low for n in neighbors)),
        ):
            if is_extreme:
                result.append(dict(kind=kind,price=price,time=b.time,index=i,
                                   confirmed_at=bars[i+radius].time+step))
    return result


def technical_context(bars: Sequence[Candle], step: int) -> dict:
    # Called only AFTER frame_analysis validates the closed, contiguous window.
    closes = [b.close for b in bars]
    swings = confirmed_swings(bars, step)
    highs = [p for p in swings if p['kind']=='HIGH']
    lows = [p for p in swings if p['kind']=='LOW']
    structure = 'UNCONFIRMED'
    if len(highs)>=2 and len(lows)>=2:
        dh=highs[-1]['price']-highs[-2]['price'];dl=lows[-1]['price']-lows[-2]['price']
        structure='HH_HL' if dh>0 and dl>0 else 'LH_LL' if dh<0 and dl<0 else 'RANGE'
    divergences=[]
    for points, side in ((lows,'LONG'),(highs,'SHORT')):
        if len(points)<2:
            continue
        a,b=points[-2:]
        # Reject old/widely separated pivots; RSI at a pivot uses its prefix only.
        if b['index']-a['index']>50 or len(bars)-1-b['index']>10:
            continue
        ra=rsi(closes[:a['index']+1]);rb=rsi(closes[:b['index']+1])
        if ra is None or rb is None:
            continue
        matched=b['price']<a['price'] and rb>ra if side=='LONG' else b['price']>a['price'] and rb<ra
        if matched:
            divergences.append(dict(side=side,first_at=a['time'],second_at=b['time'],
                                    confirmed_at=b['confirmed_at'],first_rsi=ra,second_rsi=rb))
    prior=[b.volume for b in bars[-21:-1]]
    baseline=sum(prior)/20 if len(prior)==20 and all(v is not None for v in prior) else None
    ratio=bars[-1].volume/baseline if baseline and bars[-1].volume is not None else None
    return dict(macd=macd(closes),structure=structure,swings=swings[-12:],
                rsi_divergences=divergences,volume=dict(last=bars[-1].volume,
                previous20_mean=baseline,ratio=ratio,directional=False),pivot_radius=2)


def evidence_summary(frames: dict, state: str, scenario: dict | None) -> dict:
    reference=state if state in ('LONG','SHORT') else frames['1h']['trend']
    evidence=[]
    for tf,f in frames.items():
        context=f['technical']
        structure=context['structure']
        signals=[('EMA20_50',f['trend']),('MACD_HISTOGRAM',context['macd']['bias']),
                 ('SWING_STRUCTURE','LONG' if structure=='HH_HL' else 'SHORT' if structure=='LH_LL' else 'NEUTRAL')]
        signals += [('RSI_DIVERGENCE',d['side']) for d in context['rsi_divergences']]
        for name,side in signals:
            relation='NEUTRAL' if reference not in ('LONG','SHORT') or side not in ('LONG','SHORT') else 'SUPPORTS' if side==reference else 'CONFLICTS'
            evidence.append(dict(timeframe=tf,signal=name,side=side,relation=relation))
    return dict(reference=reference,items=evidence,context_only=True,
        invalidation=dict(stop_loss=scenario['stop_loss'] if scenario else None,
            rules=['SCENARIO_TTL_EXPIRED','FRESH_HISTORY_REQUIRED','EMA_ALIGNMENT_LOST',
                   'CLOSED_5M_BEYOND_STOP' if scenario else 'NO_CONFIRMED_ENTRY']),
        interpretation='CONTEXT_NOT_EXTRA_ENTRY_CONFIRMATION',funding='NOT_INCLUDED')
