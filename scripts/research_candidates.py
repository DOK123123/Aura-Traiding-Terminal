"""Frozen offline strategy interface; consumes bars, never account/execution clients."""
from dataclasses import dataclass
from decimal import Decimal as D
from types import MappingProxyType
from typing import Protocol, Mapping, Sequence

from app.indicators import ema, rsi
from app.lab.indicators import atr, adx
from app.lab.models import Bar, precise
from app.lab.strategies import Decision, decisions as lab_decisions


class Strategy(Protocol):
    identifier: str
    parameters: Mapping
    def generate(self, bars: Sequence[Bar]) -> list[Decision]: ...


def context(bars, parameters=None):
    p = parameters or {}
    values = [float(b.close) for b in bars]
    fast, slow = ema(values, p.get('ema_fast',20)), ema(values, p.get('ema_slow',50))
    strength, volatility = rsi(values, p.get('rsi',14)), atr(bars, p.get('atr',14))
    trend, _, _ = adx(bars, p.get('adx',14))
    mf, ms, smooth = p.get('macd',(12,26,9))
    short, long = ema(values, mf), ema(values, ms)
    macd = [short[i]-long[i] for i in range(ms-1, len(bars))]
    signal = ema(macd, smooth)
    histogram = [None]*len(bars)
    for j, value in enumerate(signal):
        if value is not None:
            histogram[j+ms-1] = macd[j]-value
    return fast, slow, strength, volatility, trend, histogram


@dataclass(frozen=True)
class Candidate:
    identifier: str
    parameters: Mapping

    @precise
    def generate(self, bars):
        p = self.parameters
        if self.identifier == 'A':
            if (p['entry_channel'],p['exit_channel'],p['atr'],p['stop_atr'],p['target_atr']) != (20,10,14,2,4):
                raise ValueError('Shared Donchian parameter contract mismatch')
            return lab_decisions(bars, 'DONCHIAN')
        fast, slow, rs, at, ax, hist = context(bars,p)
        output = []
        for i, bar in enumerate(bars):
            if i < 50 or at[i] is None or at[i] <= 0 or ax[i] is None:
                output.append(Decision(reason='WARMUP_OR_INVALID_ATR'))
                continue
            if self.identifier == 'B':
                long = fast[i] > slow[i] and float(bar.close) > fast[i]
                short = fast[i] < slow[i] and float(bar.close) < fast[i]
                xl = fast[i] <= slow[i] or float(bar.close) < fast[i]
                xs = fast[i] >= slow[i] or float(bar.close) > fast[i]
            elif self.identifier == 'C':
                regime = ax[i] <= p['adx_entry_max'] and abs(fast[i]-slow[i])/at[i] <= p['spread_atr_max']
                long = regime and rs[i-1] <= p['rsi_low'] < rs[i]
                short = regime and rs[i-1] >= p['rsi_high'] > rs[i]
                xl = rs[i] >= p['rsi_exit'] or ax[i] >= p['adx_exit_min']
                xs = rs[i] <= p['rsi_exit'] or ax[i] >= p['adx_exit_min']
            elif self.identifier == 'D':
                average = sum((b.volume for b in bars[i-p['volume_window']:i]), D(0))/p['volume_window']
                volume = average > 0 and bar.volume >= average
                long = fast[i] > slow[i] and rs[i] >= p['rsi_long'] and hist[i] > 0 and volume
                short = fast[i] < slow[i] and rs[i] <= p['rsi_short'] and hist[i] < 0 and volume
                xl = fast[i] <= slow[i] or rs[i] < 50 or hist[i] <= 0
                xs = fast[i] >= slow[i] or rs[i] > 50 or hist[i] >= 0
            else:
                raise ValueError('Unsupported offline candidate')
            distance = D(str(at[i]))
            output.append(Decision('LONG' if long else 'SHORT' if short else None,
                distance*p['stop_atr'], distance*p['target_atr'], xl, xs,
                'CLOSED_RESEARCH_'+self.identifier if long or short else 'NO_SIGNAL'))
        return output


def registry(protocol) -> Mapping[str, Strategy]:
    # No production registry/activation is touched. Parameter mapping immutable.
    return MappingProxyType({name:Candidate(name, MappingProxyType({k:tuple(v) if isinstance(v,list) else v
        for k,v in protocol[name].items()})) for name in 'ABCD'})


def regimes(bars):
    trend = adx(bars, 14)[0]
    return ['UNAVAILABLE' if v is None else 'RANGE' if v <= 20 else 'TREND' if v >= 25 else 'TRANSITION' for v in trend]
