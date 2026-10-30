"""Observational rule traces. This module never produces or qualifies a trade plan."""
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path

from .engine import FAMILIES, RULES, VERSION, net_rr
from .market import SOURCE, LIVE_INPUT_CONTRACT
from .costs import filled_in_zone

DIAGNOSTICS_VERSION='AURA5_DIAGNOSTICS_1'
DIAGNOSTICS_HASH=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def utc(at):
    return datetime.fromtimestamp(at,timezone.utc).isoformat().replace('+00:00','Z') if at is not None else None


def failure_code(exc,stage='market'):
    # No upstream message/URL/credential is ever persisted.
    code=str(exc) if isinstance(exc,ValueError) else ''
    if code in {'STALE_OR_INCOMPLETE_CANDLES','OBSERVER_STALE_CANDLES'}:return 'STALE_CANDLES'
    if code in {'STALE_OR_CONFLICTING_QUOTE','UNVERIFIED_OBSERVER_SNAPSHOT'}:return 'QUOTE_GAP'
    if code in {'INVALID_OHLCV_OR_GAP','OBSERVER_WINDOW_MISMATCH','EMPTY_HISTORY','CONFLICTING_DUPLICATE'}:return 'CANDLE_GAP'
    if code in {'MARKET_IDENTITY_MISMATCH','OBSERVER_FRAME_MISMATCH'}:return 'SOURCE_MISMATCH'
    if stage=='observer':return 'OBSERVER_PROCESSING_FAILED'
    return 'PUBLIC_FRAME_UNAVAILABLE'


def predicates(p,i,family,side):
    """Explain the unchanged BASE predicates; plans() remains authoritative.

    Planning rejection is deliberately one stage, not a fabricated numeric RR
    for a plan which the engine did not return. Tests compare real rule outputs.
    """
    if i<249 or not p.valid[i] or not math.isfinite(p.atr[i]) or p.atr[i]<=0 or p.volume20[i-1]<=0:
        return {'INDICATORS_OR_VOLUME_UNAVAILABLE':False},{}
    s=1 if side=='LONG' else -1;long=s==1
    o,h,l,c=(float(x[i]) for x in (p.open,p.high,p.low,p.close))
    a=float(p.atr[i]);prev=float(p.close[i-1]);er=float(p.er20[i]);rsi=float(p.rsi[i])
    volume=float(p.volume[i]/p.volume20[i-1]);body=abs(c-o);span=h-l
    if family=='TREND_PULLBACK':
        setup={'TREND_DIRECTION':s*(p.ema50[i]-p.ema200[i])>0,'TREND_EFFICIENCY':er>=RULES['rules']['trend']['er_min'],
               'EMA20_TOUCH':p.low[i-1]<=p.ema20[i-1] if long else p.high[i-1]>=p.ema20[i-1],
               'EMA20_DISTANCE':abs(c-p.ema20[i])<=2*a}
        trigger={'DIRECTIONAL_BODY':s*(c-o)>0,'PREVIOUS_EXTREME_CLOSE':c>p.high[i-1] if long else c<p.low[i-1],
                 'RSI_PULLBACK':45<=rsi<=70 if long else 30<=rsi<=55,'TRIGGER_VOLUME':volume>=.8}
    elif family=='BREAKOUT_RETEST':
        level=p.high20[i-2] if long else p.low20[i-2]
        bv=p.volume[i-1]/p.volume20[i-2] if p.volume20[i-2]>0 else 0
        setup={'CLOSED_BREAKOUT':s*(prev-level)>.2*p.atr[i-1],'RETEST_DISTANCE':abs((l if long else h)-level)<=.5*a,
               'BREAKOUT_VOLUME':bv>=RULES['rules']['breakout']['volume']}
        trigger={'RETEST_RECLAIM':s*(c-level)>.1*a,'DIRECTIONAL_BODY':s*(c-o)>0}
    elif family=='MOMENTUM_EXPANSION':
        tr=max(span,abs(h-prev),abs(l-prev));av=p.atr[i-1];level=p.high20[i-1] if long else p.low20[i-1]
        setup={'MOMENTUM_TREND':s*(p.ema20[i]-p.ema50[i])>0,'MOMENTUM_VOLUME':volume>=RULES['rules']['momentum']['volume'],
               'SETUP_TRUE_RANGE':1.2*av<=tr<=3*av,'NEAR_RANGE_BREAK':s*(c-level)>-.25*a}
        trigger={'TRIGGER_TRUE_RANGE':tr>=1.5*av,'BODY_FRACTION':body>=.6*span,'DIRECTIONAL_BODY':s*(c-o)>0,
                 'CLOSED_RANGE_BREAK':s*(c-level)>.1*a,'RSI_MOMENTUM':55<=rsi<=80 if long else 20<=rsi<=45}
    elif family=='MEAN_REVERSION':
        width=RULES['rules']['mean_reversion']['stddev'];band=p.mean20[i-1]-s*width*p.std20[i-1]
        setup={'MEAN_REVERSION_REGIME':er<=.3,'RSI_EXTREME':p.rsi[i-1]<30 if long else p.rsi[i-1]>70,
               'PREVIOUS_BAND_EXCURSION':s*(prev-band)<0}
        trigger={'BAND_REENTRY':s*(c-(p.mean20[i]-s*width*p.std20[i]))>0,'RSI_RECOVERY':s*(p.rsi[i]-p.rsi[i-1])>0}
    elif family=='LIQUIDITY_SWEEP':
        level=p.low20[i-1] if long else p.high20[i-1];extreme=l if long else h;wick=min(o,c)-l if long else h-max(o,c)
        setup={'EXTREME_SWEEP':s*(extreme-level)<-.1*a,'SWEEP_VOLUME':volume>=RULES['rules']['sweep']['volume'],'REJECTION_WICK':wick>=body}
        trigger={'EXTREME_RECLAIM':s*(c-level)>0,'DIRECTIONAL_BODY':s*(c-o)>0}
    elif family=='RANGE_REJECTION':
        upper,lower=p.high40[i-1],p.low40[i-1];width=upper-lower;edge=lower+.2*width if long else upper-.2*width
        setup={'RANGE_EFFICIENCY':er<=RULES['rules']['range']['er_max'],'EMA_SEPARATION':abs(p.ema20[i]-p.ema50[i])<=.5*a,
               'RANGE_WIDTH':width>=4*a,'RANGE_EDGE_TOUCH':l<=edge if long else h>=edge,
               'RANGE_EDGE_CLOSE':c<=edge+.5*a if long else c>=edge-.5*a}
        trigger={'DIRECTIONAL_BODY':s*(c-o)>0,'CLOSE_RECOVERY':s*(c-prev)>0,'RSI_RANGE':rsi<45 if long else rsi>55}
    else:raise ValueError('UNREGISTERED_RULE')
    return {k:bool(v) for k,v in setup.items()},{k:bool(v) for k,v in trigger.items()}


def explain(prepared,plans,now,model_hash,*,quote=None,states=None,replay=False):
    """12 per-candle decisions. No history or timestamp outside the closed prefix."""
    i=len(prepared.rows)-1;step=prepared.step;cutoff=int(prepared.time[i])+step
    lookup={(p['strategy'],p['direction']):p for p in plans};rows=[]
    for family in FAMILIES:
        for side in ('LONG','SHORT'):
            setup,trigger=predicates(prepared,i,family,side);candidate=all(setup.values());technical=candidate and all(trigger.values())
            p=lookup.get((family,side));reasons=[k for k,v in setup.items() if not v]
            if candidate:reasons.extend(k for k,v in trigger.items() if not v)
            integrity=not p or candidate and technical==p['technical_trigger']
            if not integrity:reasons.append('DIAGNOSTIC_TRACE_MISMATCH')
            if candidate and not p:reasons.append('PLANNING_NET_RR_OR_GEOMETRY')
            state='REJECTED' if candidate and not p else 'NO TRADE'
            if p:
                if replay:state='REPLAY_PLAN'
                else:
                    ref=quote['ask' if side=='LONG' else 'bid']
                    rr=net_rr(ref,p['sl'],p['tp'],side,step,p['hold_bars'],quote['ask']-quote['bid'])
                    if not filled_in_zone(ref,p['zone'],p['direction']):reasons.append('ENTRY_OUTSIDE_ZONE')
                    if rr is None or rr<1.5:reasons.append('QUOTE_NET_RR_OR_GEOMETRY')
                    if now>=p['valid_until']:reasons.append('ENTRY_EXPIRED')
                    state=(states or {}).get((family,side),'REJECTED')
                    if state=='NO TRADE':state='REJECTED'
            rows.append({'strategy':family,'frame':prepared.frame,'direction':side,'variant':'BASE',
                         'candidate':candidate if integrity else None,'technical_trigger':bool(p['technical_trigger']) if p else technical,
                         'rule_plan':p is not None,'state':state,'reason_codes':reasons,
                         'setup_checks':setup,'trigger_checks':trigger,'trace_integrity':'OK' if integrity else 'MISMATCH',
                         'observed_at':now,'observed_at_utc':utc(now),'closed_candle_open':cutoff-step,'closed_candle_close':cutoff,
                         'closed_candle_open_utc':utc(cutoff-step),'closed_candle_close_utc':utc(cutoff),
                         'source':SOURCE,'input_contract':'ARCHIVE_AGGREGATED_260_DIAGNOSTIC_ONLY' if replay else LIVE_INPUT_CONTRACT,
                         'engine_version':VERSION,'model_sha256':model_hash,'diagnostics_version':DIAGNOSTICS_VERSION,
                         'diagnostics_sha256':DIAGNOSTICS_HASH,'quote_time_utc':utc(quote['time']) if quote else None,
                         'bid':quote['bid'] if quote else None,'ask':quote['ask'] if quote else None,
                         'bid_ask_age_seconds':now-quote['time'] if quote else None,
                         'quote_receive_age_seconds':now-quote['received_at'] if quote else None,
                         'scope':'HISTORICAL_RULE_DIAGNOSTICS_NO_DELIVERY' if replay else 'PUBLIC_OBSERVATION_ONLY'})
    return rows
