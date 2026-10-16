"""Preregistered Lab-only frequency candidates. No storage, scheduler or network."""
from decimal import Decimal as D
import json
from pathlib import Path
from .adaptive43 import propose as conservative,SCENARIOS,empty
from .indicators import rsi
from .models import precise,digest

PROTOCOL_PATH=Path(__file__).resolve().parents[2]/'docs/AURA43_PROFILES_PROTOCOL.json'
PROTOCOL=json.loads(PROTOCOL_PATH.read_text())
PROFILES=PROTOCOL['profiles']
VERSION=PROTOCOL['version']

@precise
def propose(snapshot,bars,profile,*,rsi_history=None):
    p=PROFILES[profile]
    # Reuse the original closed-prefix/source/indicator validity checks and fixed
    # shock protection; no relaxed profile can override an invalid input.
    original=conservative(snapshot,bars,rsi_history=rsi_history)
    first=original[SCENARIOS[0]]
    if first['reason'] in ('INVALID_OR_UNCLOSED_INPUT','H1_CONTEXT_UNAVAILABLE','INDICATORS_UNAVAILABLE','INVALID_ATR','VOLUME_UNAVAILABLE','SHOCK_CANDLE'):
        return {k:dict(v,diagnostics={}) for k,v in original.items()}
    state=snapshot['state'];at=snapshot['last_closed_at'];ind=state['trend_indicators']
    h1=state['mtf']['h1'];h4=state['mtf'].get('h4') or {}
    if h4.get('closed_at')!=at//14400*14400:h4={}
    num=lambda x:D(str(x))
    av=num(ind['atr14']);rs=num(ind['rsi14']);ax=num(ind['adx14'])
    hax=num(snapshot['alignment_inputs']['1h']['trend_indicators']['adx14'])
    fast=num(ind['ema20']);slow=num(ind['ema50']);volume=num(state['relative_volume'])
    regime='HIGH_VOLATILITY' if num(state['volatility_ratio'])>=D('1.5') else 'TRENDING' if hax>=p['h1_adx'] and h1.get('direction') in (-1,1) else 'RANGING'
    context=dict(h1_direction=h1.get('direction'),h1_closed_at=h1['closed_at'],h4_direction=h4.get('direction'),
        h4_closed_at=h4.get('closed_at'),adx15m=str(ax),adx1h=str(hax),volatility_ratio=str(state['volatility_ratio']))
    b,prev=bars[-1],bars[-2];result={};history=rsi_history if rsi_history is not None else rsi([float(x.close) for x in bars])
    if len(history)!=len(bars):raise ValueError('RSI_PREFIX_MISMATCH')
    def plan(name,side,level):
        sign=1 if side=='LONG' else -1
        stop=min(level,b.close-av*D('1.2'))-av*D('.25') if sign==1 else max(level,b.close+av*D('1.2'))+av*D('.25')
        distance=sign*(b.close-stop)
        if distance<=0 or distance>av*3:return empty('STRUCTURE_STOP_TOO_WIDE',regime,context)
        rr=D('1.75') if h4.get('direction')==-sign else D(2);target=b.close+sign*distance*rr
        if min(stop,target)<=0:return empty('INVALID_STOPS',regime,context)
        entry=b.close*(1+sign*D('.0005'));sf=stop*(1-sign*D('.0005'));tf=target*(1-sign*D('.0005'))
        risk=sign*(entry-sf)+D('.001')*(entry+sf);reward=sign*(tf-entry)-D('.001')*(entry+tf)
        if risk<=0 or reward/risk<D('1.2'):return empty('COST_ADJUSTED_RR_TOO_LOW',regime,context)
        return dict(direction=side,reason='AURA43:'+name,scenario=name,version=VERSION,source=snapshot['source'],
            signal_at=at,stop_loss=str(stop),take_profit=str(target),profile=profile,regime=regime,
            parameters_hash=digest(p),context=dict(context,rr=str(rr),expected_net_rr=str(reward/risk)))
    for name in SCENARIOS:
        selected=None;diagnostics={}
        for side,sign in (('LONG',1),('SHORT',-1)):
            if name=='TREND_PULLBACK':
                touch=any(prev.low-av*num(p['touch'])<=e<=prev.high+av*num(p['touch']) for e in (fast,slow))
                threshold=(prev.high if sign==1 else prev.low) if p['pullback_confirmation']=='WICK' else (max(prev.open,prev.close) if sign==1 else min(prev.open,prev.close))
                resume=sign*(b.close-threshold)>av*num(p['resume']) and sign*(b.close-b.open)>0 and sign*(b.close-fast)>0
                opposing=(state['high_leg']=='LH' and state['low_leg']=='LL') if sign==1 else (state['high_leg']=='HH' and state['low_leg']=='HL')
                lo,hi=p['pullback_rsi'][:2] if sign==1 else p['pullback_rsi'][2:]
                gates=dict(regime=regime=='TRENDING',ema_direction=h1.get('direction')==state['trend_direction']==sign,
                    adx=ax>=p['entry_adx'],ema_touch=touch,entry_confirmation=resume,rsi=lo<=rs<=hi,
                    volume=volume>=num(p['pullback_volume']),structure=not opposing)
                level=min(x.low for x in bars[-5:]) if sign==1 else max(x.high for x in bars[-5:])
            elif name=='BREAKOUT':
                prior=bars[-p['breakout_lookback']-1:-1];upper=max(x.high for x in prior);lower=min(x.low for x in prior)
                buffer=av*(D('.2') if regime=='HIGH_VOLATILITY' else num(p['breakout_buffer']))
                crosses=(b.close>upper+buffer and prev.close<=upper) if sign==1 else (b.close<lower-buffer and prev.close>=lower)
                lo,hi=p['breakout_rsi'][:2] if sign==1 else p['breakout_rsi'][2:]
                gates=dict(range_width=upper-lower<=av*num(p['range_atr']),entry_confirmation=crosses,
                    volume=volume>=(D(2) if regime=='HIGH_VOLATILITY' else num(p['breakout_volume'])),
                    adx=ax>=p['entry_adx'],rsi=lo<=rs<=hi,h1_context=hax<25 or h1.get('direction')==sign)
                level=upper-av*D('.5') if sign==1 else lower+av*D('.5')
            else:
                look=p['reversal_lookback'];tail=[num(x) for x in history[-look-1:-1] if x is not None];previous=history[-2]
                exhausted=bool(tail) and previous is not None and (min(tail)<=p['reversal_extreme'][0] and rs>num(previous) if sign==1 else max(tail)>=p['reversal_extreme'][1] and rs<num(previous))
                events=snapshot.get('structure_events') or []
                confirmed=any(e.get('type')=='structure_event' and e.get('value')=='CHoCH' and at-look*900<=e.get('confirmed_at',0)<at and
                    any(x.get('type')=='breakout' and x.get('value')==side and x.get('confirmed_at')==e['confirmed_at'] for x in events) for e in events)
                directed_break=(b.close>max(x.high for x in bars[-4:-1]) and b.close>b.open) if sign==1 else (b.close<min(x.low for x in bars[-4:-1]) and b.close<b.open)
                confirmation=state.get('retest')==side or (p['reversal_confirmation']=='RETEST_OR_BREAK' and directed_break)
                gates=dict(regime=regime=='RANGING',rsi_exhaustion=exhausted,rsi=p['reversal_rsi'][0]<=rs<=p['reversal_rsi'][1],
                    structure=confirmed,entry_confirmation=confirmation,volume=volume>=num(p['reversal_volume']))
                level=min(x.low for x in bars[-look:]) if sign==1 else max(x.high for x in bars[-look:])
            candidate=plan(name,side,level) if all(gates.values()) else empty('FILTERS_REJECTED',regime,context)
            diagnostics[side]=dict(gates=gates,plan=candidate['reason'] if all(gates.values()) else None)
            if candidate.get('direction'):selected=candidate
        result[name]=dict(selected or empty('FILTERS_REJECTED',regime,context),diagnostics=diagnostics)
    return result
