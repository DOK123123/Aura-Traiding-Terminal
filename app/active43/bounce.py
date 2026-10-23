"""Experimental closed-5m support/resistance bounce. No execution or network."""
from decimal import Decimal as D
from app.lab.indicators import atr
from app.lab.strategies import Decision

NAME='SR_BOUNCE'
PARAMETERS=dict(level_bars=48,atr_period=14,touch_atr='0.15',penetration_atr='0.5',sl_atr='1.5',wick_buffer_atr='0.25',reward_risk='1.5')


def decisions(bars):
    values=atr(bars,14);result=[]
    for i,b in enumerate(bars):
        if i<49 or values[i] is None or values[i]<=0:
            result.append(Decision(reason='BOUNCE_WARMUP'));continue
        # Exclude both the touch bar and confirming bar from level formation.
        prior=bars[i-49:i-1];touch=bars[i-1]
        support=min(x.low for x in prior);resistance=max(x.high for x in prior)
        a=D(str(values[i]));touch_atr=D(str(values[i-1]))
        long=(support-touch_atr*D('.5')<=touch.low<=support+touch_atr*D('.15')
              and touch.close>=support and b.close>touch.high and b.close>b.open)
        short=(resistance-touch_atr*D('.15')<=touch.high<=resistance+touch_atr*D('.5')
               and touch.close<=resistance and b.close<touch.low and b.close<b.open)
        if long==short:
            result.append(Decision(reason='BOUNCE_NO_CONFIRMED_REJECTION'));continue
        distance=max(a*D('1.5'),b.close-min(touch.low,b.low)+a*D('.25') if long else max(touch.high,b.high)-b.close+a*D('.25'))
        result.append(Decision('LONG' if long else 'SHORT',distance,distance*D('1.5'),False,False,
            'CLOSED_SUPPORT_BOUNCE' if long else 'CLOSED_RESISTANCE_REJECTION'))
    return result
