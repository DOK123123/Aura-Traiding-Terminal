"""Frozen Aura 4.3 candidate rules, RESEARCH ONLY; no activation/account access."""
from decimal import Decimal as D
from .indicators import rsi
from .models import SOURCE,digest,precise

VERSION='AURA43_RESEARCH_1'
SCENARIOS=('TREND_PULLBACK','BREAKOUT','REVERSAL')
PARAMETERS=dict(ema_fast=20,ema_slow=50,adx_trending=25,adx_entry=20,atr_period=14,
    volatility_high='1.5',shock_range_atr='3',breakout_lookback=20,breakout_buffer_atr='.1',
    high_vol_buffer_atr='.2',volume_breakout='1.5',volume_high='2',volume_pullback='.8',volume_reversal='1',
    touch_atr='.25',resume_atr='.05',stop_min_atr='1.2',stop_max_atr='3',stop_buffer_atr='.25',
    rr='2',opposing_4h_rr='1.75',net_rr_min='1.2',fee_rate='.001',slippage='.0005',
    pullback_rsi_long=[45,68],pullback_rsi_short=[32,55],breakout_rsi_long=[55,75],
    breakout_rsi_short=[25,45],reversal_rsi_extremes=[35,65],reversal_lookback=8,
    scenario_priority=list(SCENARIOS))


def empty(reason,regime='UNKNOWN',context=None):
    return dict(direction=None,reason=reason,version=VERSION,source=SOURCE,regime=regime,
        parameters_hash=digest(PARAMETERS),context=context or {})


@precise
def propose(snapshot: dict,bars: list,*,rsi_history=None) -> dict:
    """Return independent scenario candidates; callers cannot activate them.

    All inputs must be from the closed prefix. 4h affects RR/context, never a
    mandatory trend-alignment veto. Parameters are not selected from outcomes.
    """
    s=snapshot.get('state') or {};at=snapshot.get('last_closed_at')
    h1=(s.get('mtf') or {}).get('h1') or {};h4=(s.get('mtf') or {}).get('h4') or {}
    if (snapshot.get('status')!='OK' or snapshot.get('freshness',{}).get('status')!='FRESH'
            or snapshot.get('source')!=SOURCE or snapshot.get('symbol')!='BTCUSDT'
            or snapshot.get('timeframe')!='15m' or type(at) is not int or len(bars)<250
            or bars[-1].time+900!=at or s.get('timestamp')!=at
            or any(b.time+900>at for b in bars)
            or any(b.time-a.time!=900 for a,b in zip(bars,bars[1:]))):
        return {k:empty('INVALID_OR_UNCLOSED_INPUT') for k in SCENARIOS}
    ht=h1.get('closed_at')
    if type(ht) is not int or ht!=at//3600*3600:
        return {k:empty('H1_CONTEXT_UNAVAILABLE') for k in SCENARIOS}
    if type(h4.get('closed_at')) is not int or h4['closed_at']!=at//14400*14400:
        h4={}  # Optional context must never introduce a future/stale 4h state.
    ind=s.get('trend_indicators') or {}
    hi=(snapshot.get('alignment_inputs') or {}).get('1h',{}).get('trend_indicators') or {}
    required=[ind.get(k) for k in ('ema20','ema50','adx14','atr14','rsi14')]+[hi.get('adx14')]
    import math
    if any(type(v) not in (float,int) or not math.isfinite(v) for v in required):
        return {k:empty('INDICATORS_UNAVAILABLE') for k in SCENARIOS}
    av=D(str(ind['atr14']));price=bars[-1].close
    if av<=0:return {k:empty('INVALID_ATR') for k in SCENARIOS}
    volatility=D(str(s['volatility_ratio']));adx=D(str(ind['adx14']));h1_adx=D(str(hi['adx14']))
    regime='HIGH_VOLATILITY' if volatility>=D('1.5') else 'TRENDING' if h1_adx>=25 and h1.get('direction') in (-1,1) else 'RANGING'
    context=dict(h1_direction=h1.get('direction'),h1_closed_at=ht,h4_direction=h4.get('direction'),
        h4_closed_at=h4.get('closed_at'),adx15m=str(adx),adx1h=str(h1_adx),volatility_ratio=str(volatility))
    result={k:empty('NO_'+k+'_SETUP',regime,context) for k in SCENARIOS}
    if bars[-1].high-bars[-1].low>av*3:
        return {k:empty('SHOCK_CANDLE',regime,context) for k in SCENARIOS}
    volume=s.get('relative_volume')
    if volume is None:return {k:empty('VOLUME_UNAVAILABLE',regime,context) for k in SCENARIOS}
    volume=D(str(volume));fast=D(str(ind['ema20']));slow=D(str(ind['ema50']));rs=D(str(ind['rsi14']))
    b,prev=bars[-1],bars[-2]

    def plan(name,side,structural_stop):
        sign=1 if side=='LONG' else -1
        stop=min(structural_stop,price-av*D('1.2'))-av*D('.25') if sign==1 else max(structural_stop,price+av*D('1.2'))+av*D('.25')
        distance=sign*(price-stop)
        if distance>av*3 or distance<=0:return empty('STRUCTURE_STOP_TOO_WIDE',regime,context)
        rr=D('1.75') if h4.get('direction')==-sign else D('2')
        target=price+sign*distance*rr
        if min(stop,target)<=0:return empty('INVALID_STOPS',regime,context)
        entry=price*(1+sign*D('.0005'));stop_fill=stop*(1-sign*D('.0005'));target_fill=target*(1-sign*D('.0005'))
        risk=sign*(entry-stop_fill)+D('.001')*(entry+stop_fill)
        reward=sign*(target_fill-entry)-D('.001')*(entry+target_fill)
        if risk<=0 or reward/risk<D('1.2'):return empty('COST_ADJUSTED_RR_TOO_LOW',regime,context)
        return dict(direction=side,reason='AURA43:'+name,scenario=name,version=VERSION,source=SOURCE,
            signal_at=at,stop_loss=str(stop),take_profit=str(target),parameters_hash=digest(PARAMETERS),
            regime=regime,context=dict(context,rr=str(rr),expected_net_rr=str(reward/risk)))

    if regime=='TRENDING':
        for side,sign in (('LONG',1),('SHORT',-1)):
            touch=any(prev.low-av*D('.25')<=e<=prev.high+av*D('.25') for e in (fast,slow))
            resumes=(b.close>prev.high+av*D('.05') and b.close>b.open and b.close>fast) if sign==1 else (b.close<prev.low-av*D('.05') and b.close<b.open and b.close<fast)
            opposing=(s.get('high_leg')=='LH' and s.get('low_leg')=='LL') if sign==1 else (s.get('high_leg')=='HH' and s.get('low_leg')=='HL')
            rsi_ok=45<=rs<=68 if sign==1 else 32<=rs<=55
            if h1.get('direction')==s.get('trend_direction')==sign and adx>=20 and touch and resumes and rsi_ok and volume>=D('.8') and not opposing:
                structure=min(x.low for x in bars[-5:]) if sign==1 else max(x.high for x in bars[-5:])
                result['TREND_PULLBACK']=plan('TREND_PULLBACK',side,structure)
    else:result['TREND_PULLBACK']=empty('REGIME_EXCLUDES_PULLBACK',regime,context)

    prior=bars[-21:-1];upper=max(x.high for x in prior);lower=min(x.low for x in prior)
    buffer=av*(D('.2') if regime=='HIGH_VOLATILITY' else D('.1'))
    vol_min=D('2') if regime=='HIGH_VOLATILITY' else D('1.5')
    for side,sign in (('LONG',1),('SHORT',-1)):
        crosses=(price>upper+buffer and prev.close<=upper) if sign==1 else (price<lower-buffer and prev.close>=lower)
        rsi_ok=55<=rs<=75 if sign==1 else 25<=rs<=45
        trend_ok=h1_adx<25 or h1.get('direction')==sign
        if crosses and upper-lower<=av*6 and volume>=vol_min and adx>=20 and rsi_ok and trend_ok:
            result['BREAKOUT']=plan('BREAKOUT',side,upper-av*D('.5') if sign==1 else lower+av*D('.5'))

    if regime=='RANGING':
        history=rsi_history if rsi_history is not None else rsi([float(x.close) for x in bars])
        if len(history)!=len(bars):raise ValueError('RSI_PREFIX_MISMATCH')
        tail=[D(str(x)) for x in history[-9:-1] if x is not None];previous=history[-2]
        for side,sign in (('LONG',1),('SHORT',-1)):
            exhausted=bool(tail) and previous is not None and (min(tail)<=35 and rs>D(str(previous)) if sign==1 else max(tail)>=65 and rs<D(str(previous)))
            events=snapshot.get('structure_events') or []
            confirmed=any(e.get('type')=='structure_event' and e.get('value')=='CHoCH' and at-8*900<=e.get('confirmed_at',0)<at and
                any(x.get('type')=='breakout' and x.get('value')==side and x.get('confirmed_at')==e['confirmed_at'] for x in events) for e in events)
            if exhausted and 40<=rs<=60 and s.get('retest')==side and confirmed and volume>=1:
                structure=min(x.low for x in bars[-8:]) if sign==1 else max(x.high for x in bars[-8:])
                result['REVERSAL']=plan('REVERSAL',side,structure)
    else:result['REVERSAL']=empty('REGIME_EXCLUDES_REVERSAL',regime,context)
    return result


def choose(proposals: dict,scenario: str | None=None) -> dict:
    names=(scenario,) if scenario else SCENARIOS
    for name in names:
        if proposals[name].get('direction'):return proposals[name]
    value=proposals[names[0]]
    return dict(value,reason=value['reason'] if scenario else 'NO_ADAPTIVE_SETUP')
