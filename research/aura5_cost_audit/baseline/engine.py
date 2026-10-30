"""Six causal hypothesis families shared by offline research and the read-only Hunter."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .market import SOURCE, STEPS, validate_bars

RULES = json.loads(Path(__file__).with_name('rules.json').read_text())
VERSION = RULES['version']
FAMILIES = tuple(RULES['families'])


def rolling(values, size, maximum=True):
    result = np.full(len(values), np.nan)
    queue = deque()
    for i, x in enumerate(values):
        while queue and queue[0] <= i - size:
            queue.popleft()
        while queue and (values[queue[-1]] <= x if maximum else values[queue[-1]] >= x):
            queue.pop()
        queue.append(i)
        if i >= size - 1:
            result[i] = values[queue[0]]
    return result


def average(values, n):
    result = np.full(len(values), np.nan)
    if len(values) >= n:
        c = np.r_[0., np.cumsum(values)]
        result[n-1:] = (c[n:] - c[:-n]) / n
    return result


def ema(values, n):
    out = np.full(len(values), np.nan)
    if len(values) >= n:
        out[n-1] = np.mean(values[:n])
        for i in range(n, len(values)):
            out[i] = out[i-1] + 2 / (n+1) * (values[i] - out[i-1])
    return out


def wilder(values, n=14):
    out = np.full(len(values), np.nan)
    if len(values) >= n:
        out[n-1] = np.mean(values[:n])
        for i in range(n, len(values)):
            out[i] = (out[i-1] * (n-1) + values[i]) / n
    return out


def net_rr(entry, stop, target, direction, step, hold, spread=None):
    sign = 1 if direction == 'LONG' else -1
    if not all(math.isfinite(x) and x > 0 for x in (entry, stop, target)):
        return None
    if sign * (entry-stop) <= 0 or sign * (target-entry) <= 0:
        return None
    half = (RULES['costs']['full_spread_bps'] / 2e4) if spread is None else spread / (2*entry)
    slip = RULES['costs']['slippage_bps_per_side'] / 1e4
    fee = RULES['costs']['fee_bps_per_side'] / 1e4
    funding = entry * math.ceil(hold * step / 28800) * RULES['planning']['funding_reserve_bps_per_8h'] / 1e4
    e, s, t = entry*(1+sign*(half+slip)), stop*(1-sign*(half+slip)), target*(1-sign*(half+slip))
    loss = sign*(e-s)+fee*(e+s)+funding
    reward = sign*(t-e)-fee*(e+t)-funding
    return reward/loss if loss > 0 else None


class Prepared:
    def __init__(self, rows, frame):
        if frame not in STEPS:
            raise ValueError('INVALID_FRAME')
        validate_bars(rows, STEPS[frame], contiguous=False)
        self.frame, self.step, self.rows = frame, STEPS[frame], rows
        self.x = np.asarray(rows, dtype=float)
        self.time, self.open, self.high, self.low, self.close, self.volume = self.x.T
        n = len(rows)
        self.valid = np.zeros(n, dtype=bool)
        keys = ['ema20', 'ema50', 'ema200', 'atr', 'rsi', 'mean20', 'std20', 'er20', 'volume20', 'high20', 'low20', 'high40', 'low40']
        for key in keys:
            setattr(self, key, np.full(n, np.nan))
        breaks = [0, *list(np.flatnonzero(np.diff(self.time) != self.step)+1), n]
        for start, end in zip(breaks, breaks[1:]):
            c, h, l, v = self.close[start:end], self.high[start:end], self.low[start:end], self.volume[start:end]
            length = end-start
            if length < RULES['warmup']:
                continue
            for size in (20, 50, 200):
                getattr(self, 'ema'+str(size))[start:end] = ema(c, size)
            previous = np.r_[c[0], c[:-1]]
            tr = np.maximum(h-l, np.maximum(np.abs(h-previous), np.abs(l-previous)))
            self.atr[start:end] = wilder(tr)
            change = np.r_[0., np.diff(c)]
            gain = np.r_[np.nan, wilder(np.maximum(np.diff(c), 0))]
            loss = np.r_[np.nan, wilder(np.maximum(-np.diff(c), 0))]
            rs = np.divide(gain, loss, out=np.full(length, np.inf), where=loss>0)
            self.rsi[start:end] = np.where((gain==0)&(loss==0), 50, 100-100/(1+rs))
            mean = average(c, 20)
            self.mean20[start:end] = mean
            self.std20[start:end] = np.sqrt(np.maximum(0, average(c*c, 20)-mean*mean))
            path = average(np.abs(change), 20)*20
            movement = np.r_[np.full(20, np.nan), np.abs(c[20:]-c[:-20])]
            self.er20[start:end] = np.divide(movement, path, out=np.zeros(length), where=path>0)
            self.volume20[start:end] = average(v, 20)
            for size in (20, 40):
                getattr(self, 'high'+str(size))[start:end] = rolling(h, size)
                getattr(self, 'low'+str(size))[start:end] = rolling(l, size, False)
            self.valid[start+RULES['warmup']-1:end] = True

    def plans(self, i, family, variant='BASE', *, cutoff=None, watch=False):
        if family not in FAMILIES or variant not in RULES['variants']:
            raise ValueError('UNREGISTERED_RULE')
        if type(i) is not int or i < 249 or i >= len(self.rows) or not self.valid[i]:
            return []
        at = int(self.time[i])+self.step
        if cutoff is not None and cutoff != at:
            raise ValueError('NONCAUSAL_DECISION_CUTOFF')
        a = float(self.atr[i])
        if not math.isfinite(a) or a <= 0 or self.volume20[i-1] <= 0:
            return []
        o, h, l, c = map(float, (self.open[i], self.high[i], self.low[i], self.close[i]))
        prev_c = float(self.close[i-1])
        er, rsi = float(self.er20[i]), float(self.rsi[i])
        volume = float(self.volume[i]/self.volume20[i-1])
        span = h-l
        body = abs(c-o)
        strict = variant == 'STRICT'
        output = []
        for direction, sign in [('LONG', 1), ('SHORT', -1)]:
            long = sign == 1
            setup = trigger = False
            stop_distance, target, hold = 2*a, None, 24
            reasons, confirmation = [], ''
            if family == 'TREND_PULLBACK':
                rules = RULES['rules']['trend']
                trend = sign*(self.ema50[i]-self.ema200[i]) > 0
                touch = self.low[i-1] <= self.ema20[i-1] if long else self.high[i-1] >= self.ema20[i-1]
                setup = trend and er >= (rules['strict_er_min'] if strict else rules['er_min']) and touch and abs(c-self.ema20[i]) <= 2*a
                trigger = setup and sign*(c-o)>0 and (c>self.high[i-1] if long else c<self.low[i-1]) and (45<=rsi<=70 if long else 30<=rsi<=55) and volume>=.8
                anchor = min(l, self.low[i-1]) if long else max(h, self.high[i-1])
                stop_distance = max(rules['stop_atr']*a, sign*(c-anchor)+.5*a)
                target, hold = c+sign*rules['target_R']*stop_distance, rules['hold']
                reasons = ['EMA50/200 trend', 'ER20 regime', 'closed EMA20 pullback']
                confirmation = 'directional close beyond previous high/low; RSI and relative volume'
            elif family == 'BREAKOUT_RETEST':
                rules = RULES['rules']['breakout']
                level = self.high20[i-2] if long else self.low20[i-2]
                break_volume = self.volume[i-1]/self.volume20[i-2] if self.volume20[i-2]>0 else 0
                broken = sign*(prev_c-level)>.2*self.atr[i-1]
                near = abs((l if long else h)-level) <= .5*a
                setup = broken and near and break_volume >= (rules['strict_volume'] if strict else rules['volume'])
                trigger = setup and sign*(c-level)>.1*a and sign*(c-o)>0
                anchor = min(l, level) if long else max(h, level)
                stop_distance = max(2*a, sign*(c-anchor)+.5*a)
                target, hold = c+sign*2*stop_distance, rules['hold']
                reasons = ['prior 20-bar level before closed breakout', 'breakout relative volume', 'separate closed retest candle']
                confirmation = 'directional retest close back beyond level +0.1 ATR'
            elif family == 'MOMENTUM_EXPANSION':
                rules = RULES['rules']['momentum']
                tr = max(span, abs(h-prev_c), abs(l-prev_c))
                av = self.atr[i-1]
                level = self.high20[i-1] if long else self.low20[i-1]
                setup = sign*(self.ema20[i]-self.ema50[i])>0 and volume >= (rules['strict_volume'] if strict else rules['volume']) and 1.2*av<=tr<=3*av and sign*(c-level)>-.25*a
                trigger = setup and tr>=1.5*av and body>=.6*span and sign*(c-o)>0 and sign*(c-level)>.1*a and (55<=rsi<=80 if long else 20<=rsi<=45)
                stop_distance = 1.8*a
                target, hold = c+sign*2.5*stop_distance, rules['hold']
                reasons = ['EMA20/50 direction', 'true-range expansion', 'volume expansion', 'prior range break']
                confirmation = 'closed range break with >=60% directional body and RSI momentum'
            elif family == 'MEAN_REVERSION':
                rules = RULES['rules']['mean_reversion']
                width = rules['strict_stddev'] if strict else rules['stddev']
                band = self.mean20[i-1]-sign*width*self.std20[i-1]
                extreme = self.rsi[i-1]<30 if long else self.rsi[i-1]>70
                setup = er<=.3 and extreme and sign*(prev_c-band)<0
                current_band = self.mean20[i]-sign*width*self.std20[i]
                trigger = setup and sign*(c-current_band)>0 and sign*(self.rsi[i]-self.rsi[i-1])>0
                anchor = min(l, self.low[i-1]) if long else max(h, self.high[i-1])
                stop_distance = max(1.5*a, sign*(c-anchor)+.25*a)
                target, hold = float(self.mean20[i]), rules['hold']
                reasons = ['previous closed Bollinger excursion', 'RSI extreme', 'low efficiency regime']
                confirmation = 'closed reentry into band and RSI recovery'
            elif family == 'LIQUIDITY_SWEEP':
                rules = RULES['rules']['sweep']
                level = self.low20[i-1] if long else self.high20[i-1]
                extreme = l if long else h
                wick = min(o,c)-l if long else h-max(o,c)
                setup = sign*(extreme-level)<-.1*a and volume>=(rules['strict_volume'] if strict else rules['volume']) and wick>=body
                trigger = setup and sign*(c-level)>0 and sign*(c-o)>0
                stop_distance = max(1.5*a, sign*(c-extreme)+.25*a)
                target, hold = c+sign*2*stop_distance, rules['hold']
                reasons = ['sweep of prior 20-bar extreme (liquidity proxy, not observed orders)', 'rejection wick', 'relative volume']
                confirmation = 'directional closed reclaim of prior extreme'
            else:
                rules = RULES['rules']['range']
                upper, lower = self.high40[i-1], self.low40[i-1]
                width = upper-lower
                regime = er <= (rules['strict_er_max'] if strict else rules['er_max']) and abs(self.ema20[i]-self.ema50[i])<=.5*a
                edge = lower+.2*width if long else upper-.2*width
                setup = regime and width>=4*a and (l<=edge if long else h>=edge) and (c<=edge+.5*a if long else c>=edge-.5*a)
                trigger = setup and sign*(c-o)>0 and sign*(c-prev_c)>0 and (rsi<45 if long else rsi>55)
                anchor = lower-.5*a if long else upper+.5*a
                stop_distance = max(1.5*a, sign*(c-anchor))
                target, hold = float((upper+lower)/2), rules['hold']
                reasons = ['low efficiency and small EMA separation', 'prior 40-bar range edge', 'known range midpoint target']
                confirmation = 'closed directional rejection and RSI at range edge'
            if not setup or not trigger and not watch:
                continue
            stop = c-sign*stop_distance
            rr = net_rr(c, stop, target, direction, self.step, hold)
            if rr is None or rr < RULES['planning']['min_net_rr']:
                continue
            identity = f'{VERSION}:{family}:{variant}:{self.frame}:{direction}:{at}'
            output.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'version': VERSION,
                           'strategy': family, 'variant': variant, 'frame': self.frame, 'direction': direction,
                           'signal_time': at, 'valid_until': at+self.step, 'entry': c, 'sl': float(stop), 'tp': float(target),
                           'zone': [c-.5*a, c+.5*a], 'atr': a, 'net_rr': float(rr), 'hold_bars': hold,
                           'technical_trigger': bool(trigger), 'reasons': reasons, 'confirmation': confirmation,
                           'cancel': 'entry expiry, zone departure, SL/TP crossed, stale or inconsistent public data',
                           'regime': 'TREND' if er>=.3 else 'RANGE', 'rsi': rsi, 'er20': er,
                           'source': SOURCE, 'statistical_status': 'UNVALIDATED', 'probability_tp_before_sl': None})
        return output

    def candidate_indices(self, family):
        """Lossless performance prefilter; plans() remains the sole rule evaluator."""
        previous_close=np.roll(self.close,1)
        if family=='TREND_PULLBACK':
            mask=(self.close>np.roll(self.high,1))|(self.close<np.roll(self.low,1))
        elif family=='BREAKOUT_RETEST':
            mask=(previous_close>np.roll(self.high20,2))|(previous_close<np.roll(self.low20,2))
        elif family=='MOMENTUM_EXPANSION':
            tr=np.maximum(self.high-self.low,np.maximum(abs(self.high-previous_close),abs(self.low-previous_close)))
            mask=tr>=1.5*np.roll(self.atr,1)
        elif family=='MEAN_REVERSION':
            mask=(np.roll(self.rsi,1)<30)|(np.roll(self.rsi,1)>70)
        elif family=='LIQUIDITY_SWEEP':
            mask=(self.low<np.roll(self.low20,1))|(self.high>np.roll(self.high20,1))
        elif family=='RANGE_REJECTION':
            mask=(self.er20<=.2)&(abs(self.ema20-self.ema50)<=.5*self.atr)
        else:raise ValueError('UNREGISTERED_RULE')
        return np.flatnonzero(self.valid & (self.atr>0) & mask)
