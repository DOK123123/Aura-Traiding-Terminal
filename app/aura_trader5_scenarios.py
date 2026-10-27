"""Closed-candle manual scenarios. No account, persistence or execution authority."""
from math import isfinite
from decimal import Decimal,localcontext,ROUND_CEILING,ROUND_FLOOR
from app.models import Candle
from .aura_trader5_technical import technical_context,evidence_summary
from .aura_trader5_analysis import Candle as HLC,ema,rsi,atr,fibonacci_levels,risk_plan

SOURCE='Bitget · USDT-M Futures / api.bitget.com'
STEPS={'5m':300,'15m':900,'1h':3600,'4h':14400}
VERSION='AURA_MANUAL_ANALYST_1'
FEE=.001
SLIPPAGE=.0005


def wait(code,now,frames=None):
    return dict(version=VERSION,source=SOURCE,symbol='BTCUSDT',market='USDT-M Futures',
        state='WAIT',reasons=[code],frames=frames or {},scenario=None,fibonacci=None,
        generated_at=now,valid_until=now,read_only=True,manual_only=True,
        exchange_execution=False,profitability_verified=False)


def frame_analysis(bars,frame,asof):
    step=STEPS[frame]
    if not isinstance(bars,list) or not 100<=len(bars)<=300:raise ValueError('INSUFFICIENT_HISTORY')
    for i,b in enumerate(bars):
        if not isinstance(b,Candle):raise ValueError('INVALID_CANDLE')
        b.__post_init__()
        if b.volume is None or b.time%step or b.time+step>asof or i and b.time-bars[i-1].time!=step:
            raise ValueError('INVALID_CLOSED_HISTORY')
    if bars[-1].time+step!=int(asof)//step*step:raise ValueError('STALE_CANDLES')
    closes=[b.close for b in bars];e20=ema(closes,20);e50=ema(closes,50)
    av=atr([HLC(b.high,b.low,b.close) for b in bars]);rs=rsi(closes)
    trend='LONG' if e20-e50>.1*av else 'SHORT' if e50-e20>.1*av else 'NEUTRAL'
    return dict(ema20=e20,ema50=e50,rsi=rs,atr=av,trend=trend,close=closes[-1],
        last_closed_at=bars[-1].time+step,bars=len(bars),technical=technical_context(bars,step))


def price_step(value,tick,up=False):
    with localcontext() as ctx:
        ctx.prec=64
        return float((Decimal(str(value))/Decimal(str(tick))).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR)*Decimal(str(tick)))


def _assess(windows,asof,price_tick=.1):
    if type(price_tick) not in (int,float) or not isfinite(price_tick) or price_tick<=0:raise ValueError('INVALID_PRICE_TICK')
    if set(windows)!=set(STEPS):return wait('MISSING_TIMEFRAME',asof)
    frames={frame:frame_analysis(windows[frame],frame,asof) for frame in STEPS}
    result=wait('NO_CONFIRMED_SCENARIO',asof,frames)
    result.update(price_tick=price_tick,valid_until=min(int(asof)+60,(int(asof)//300+1)*300),asof_closed_at=int(asof)//300*300,
        cost_model=dict(fee_per_side=FEE,adverse_slippage_per_side=SLIPPAGE,funding='NOT_INCLUDED'))
    side=frames['1h']['trend']
    if side=='NEUTRAL' or any(frames[f]['trend']!=side for f in ('5m','15m')):
        result['reasons']=['TREND_NOT_CONFIRMED'];return result
    if frames['4h']['trend'] not in (side,'NEUTRAL'):
        result['reasons']=['CONFLICTING_4H_CONTEXT'];return result
    long=side=='LONG';direction='up' if long else 'down'
    # Extremes are inside a past-only fixed window; no future pivot confirmation.
    history=windows['15m'][-61:-1]
    lo=min(range(len(history)),key=lambda i:history[i].low)
    hi=max(range(len(history)),key=lambda i:history[i].high)
    low=history[lo].low;high=history[hi].high
    if high<=low or (lo>=hi if long else hi>=lo):
        result['reasons']=['NO_ORDERED_SWING'];return result
    fib=fibonacci_levels(low,high,direction)
    result['fibonacci']=dict(direction=direction,low=low,high=high,low_at=history[lo].time,
        high_at=history[hi].time,levels=fib,lookback_bars=60,timeframe='15m')
    f=frames['5m'];av=f['atr'];last=windows['5m'][-1];previous=windows['5m'][-2]
    if av<=0 or not (52<=f['rsi']<=68 if long else 32<=f['rsi']<=48):
        result['reasons']=['RSI_NOT_CONFIRMED'];return result
    lower=max(min(fib['0.382'],fib['0.618']),f['ema20']-.5*av)
    upper=min(max(fib['0.382'],fib['0.618']),f['ema20']+.5*av)
    lower=price_step(lower,price_tick,True);upper=price_step(upper,price_tick)
    if lower>=upper or not lower-.25*av<=last.close<=upper+.25*av:
        result['reasons']=['NO_ENTRY_CONFLUENCE'];return result
    confirmed=(last.close>last.open and last.close>previous.close+.05*av and last.low<=upper) if long else (
        last.close<last.open and last.close<previous.close-.05*av and last.high>=lower)
    if not confirmed:
        result['reasons']=['CLOSED_CANDLE_NOT_CONFIRMED'];return result
    entry=upper if long else lower
    recent=windows['5m'][-3:]
    stop=min(min(b.low for b in recent)-.25*av,lower-1.5*av) if long else max(max(b.high for b in recent)+.25*av,upper+1.5*av)
    stop=price_step(stop,price_tick,not long)
    distance=abs(entry-stop)
    target=min(high,entry+2.5*distance) if long else max(low,entry-2.5*distance)
    target=price_step(target,price_tick,not long)
    try:plan=risk_plan(entry,stop,target,'long' if long else 'short',1,.5,FEE,SLIPPAGE)
    except ValueError:
        result['reasons']=['INVALID_SCENARIO_GEOMETRY'];return result
    if plan['estimated_rr_after_costs']<1.5:
        result['reasons']=['INSUFFICIENT_RR_AFTER_COSTS'];return result
    if not all(isfinite(n) and n>0 for n in (lower,upper,entry,stop,target)):
        result['reasons']=['INVALID_SCENARIO_GEOMETRY'];return result
    result.update(state=side,reasons=['TREND_5M_15M_1H','CLOSED_RSI_MOMENTUM','EMA_FIBONACCI_CONFLUENCE','CLOSED_CANDLE_CONFIRMATION','RR_AFTER_COSTS'],scenario=dict(
        entry_zone=dict(low=lower,high=upper),reference_entry=entry,stop_loss=stop,take_profit=target,
        gross_rr=abs(target-entry)/distance,net_rr=plan['estimated_rr_after_costs'],
        based_on='CLOSED_5M_AND_PAST_15M_SWING',execution='MANUAL_REVIEW_ONLY'))
    return result


def assess(windows,asof,price_tick=.1):
    result=_assess(windows,asof,price_tick)
    if set(result["frames"])==set(STEPS):
        result["evidence"]=evidence_summary(result["frames"],result["state"],result["scenario"])
    return result
