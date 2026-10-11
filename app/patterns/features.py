"""Causal, price-scale invariant descriptors. No fitted full-sample scaler."""
from dataclasses import dataclass
import math
import numpy as np

from ..indicators import ema, rsi, atr
from ..models import Candle


@dataclass
class Features:
    vectors: np.ndarray
    facts: list[dict]
    valid_from: int


def build_features(candles: list[Candle], lookback=20, context=500):
    n = len(candles)
    close = np.array([c.close for c in candles])
    e20,e50,e200 = (np.array(ema(close.tolist(),p),dtype=float) for p in (20,50,200))
    rs = np.array(rsi(close.tolist()),dtype=float)
    at = np.array(atr(candles),dtype=float)
    e12,e26 = (np.array(ema(close.tolist(),p),dtype=float) for p in (12,26))
    macd = e12-e26
    macd_signal = np.full(n,np.nan)
    if n > 25:
        macd_signal[25:] = ema(macd[25:].tolist(),9)
    returns = np.zeros(n)
    returns[1:] = np.log(close[1:]/close[:-1])
    primitive = np.zeros((n,5))
    facts, core = [], []
    valid_from = max(205,context-1,lookback+14)
    for i,c in enumerate(candles):
        scale = max(float(at[i]),c.close*1e-10) if i >= 13 else c.close
        primitive[i] = [(c.close-(close[i-1] if i else c.open))/scale,
                        (c.close-c.open)/scale,(c.high-max(c.open,c.close))/scale,
                        (min(c.open,c.close)-c.low)/scale,returns[i]/max(scale/c.close,1e-10)]
        if i < valid_from:
            core.append(None); facts.append({}); continue
        recent_vol = float(np.std(returns[i-19:i+1],ddof=1))
        previous_vol = float(np.std(returns[i-39:i-19],ddof=1))
        ratio = recent_vol/max(previous_vol,1e-10) if recent_vol or previous_vol else 1.
        window = candles[i-context+1:i+1]
        local = candles[i-lookback+1:i+1]
        hi,lo = max(c.high for c in local),min(c.low for c in local)
        context_hi,context_lo = max(c.high for c in window),min(c.low for c in window)
        prior_volumes = [c.volume for c in candles[i-20:i] if c.volume is not None]
        volume = None
        if c.volume is not None and len(prior_volumes)==20 and sum(prior_volumes)>0:
            volume = math.log1p(c.volume/(sum(prior_volumes)/20))/math.log(2)-1
        slope20 = (e20[i]-e20[i-5])/scale
        momentum = (c.close/close[i-10]-1)*100
        fact = dict(price=c.close,atr=float(at[i]),atr_pct=float(at[i]/c.close*100),
                    rsi=float(rs[i]),rsi_change=float(rs[i]-rs[i-5]),
                    ema20=float(e20[i]),ema50=float(e50[i]),ema200=float(e200[i]),
                    slope20=float(slope20),momentum_pct=float(momentum),volatility_ratio=ratio,
                    distance_high_atr=(hi-c.close)/scale,distance_low_atr=(c.close-lo)/scale,
                    volume_available=volume is not None)
        facts.append(fact)
        core.append([
            (e20[i]-e50[i])/scale,(e50[i]-e200[i])/scale,
            (c.close-e20[i])/scale,(c.close-e50[i])/scale,(c.close-e200[i])/scale,
            slope20,(e50[i]-e50[i-5])/scale,(e200[i]-e200[i-5])/scale,
            (rs[i]-50)/25,(rs[i]-rs[i-5])/10,macd[i]/scale,(macd[i]-macd_signal[i])/scale,
            math.log(max(at[i]/c.close,1e-10))/5,
            (c.close-close[i-10])/scale,(hi-c.close)/scale,(c.close-lo)/scale,
            (c.close-close[i-lookback+1])/(scale*math.sqrt(lookback)),math.log(max(ratio,1e-10)),
            (c.close-close[i-context+1])/(scale*math.sqrt(context)),
            (c.close-context_lo)/max(context_hi-context_lo,scale)*2-1,
            volume if volume is not None else np.nan,
        ])
    # Fixed bounded transforms are causal; never fit normalization on future rows.
    vectors = np.full((n,21+lookback*5),np.nan)
    for i in range(valid_from,n):
        vectors[i,:21] = np.tanh(np.asarray(core[i])/3)
        vectors[i,21:] = np.tanh(primitive[i-lookback+1:i+1].ravel()/3)
    return Features(vectors,facts,valid_from)


def multi_timeframe(candles, target, timeframe_seconds):
    """Only complete higher-TF buckets known by target close, same source."""
    horizon_seconds = {'5m':300,'15m':900,'1h':3600,'4h':14400}
    cutoff = candles[target].time+timeframe_seconds
    result=[]
    for name,seconds in horizon_seconds.items():
        if seconds <= timeframe_seconds:
            continue
        buckets={}
        for c in candles[:target+1]:
            bucket=c.time//seconds*seconds
            if bucket+seconds <= cutoff:
                buckets.setdefault(bucket,[]).append(c)
        complete=[]
        for stamp,rows in sorted(buckets.items()):
            if len(rows)!=seconds//timeframe_seconds or any(c.time!=stamp+j*timeframe_seconds for j,c in enumerate(rows)):
                continue
            complete.append(Candle(stamp,rows[0].open,max(c.high for c in rows),min(c.low for c in rows),rows[-1].close,None))
        if len(complete)<50:
            result.append(dict(timeframe=name,trend='UNAVAILABLE',bars=len(complete))); continue
        closes=[c.close for c in complete]
        spread=(ema(closes,20)[-1]-ema(closes,50)[-1])/max(atr(complete)[-1],closes[-1]*1e-10)
        result.append(dict(timeframe=name,trend='Bullish' if spread>.1 else 'Bearish' if spread<-.1 else 'Neutral',
                           bars=len(complete),last_closed_at=complete[-1].time+seconds))
        if len(result)>=2:
            break
    return result
