"""OFFLINE LAB ONLY. Native accounting plus an explicit causal ATR ratchet.

Production engine is untouched. With no ratchet, transitions match native.
New stop takes effect only after the candle that computed it has been processed.
"""
from copy import deepcopy
from decimal import Decimal as D
from app.lab.models import precise,digest,text,money
from app.automated.engine import (initial,mark,risk_reason,event,roll_day,liquidation_equity,
    open_virtual,protective,validate_bars,DemoError,STEP,dec,validate as native_validate)

def validate(s):
    p=s.get('position')
    if not p or not p.get('lab_v2_trailing'):
        native_validate(s);return
    stop=D(p['stop_loss']);initial_stop=D(p['initial_stop_loss']);target=D(p['take_profit']);entry=D(p['entry_price'])
    long=p['direction']=='LONG'
    if not stop.is_finite() or stop<=0 or not (initial_stop<=stop<target if long else target<stop<=initial_stop):raise DemoError('INVALID_LAB_TRAILING_STOP')
    proxy=deepcopy(s);proxy['position']['stop_loss']=p['initial_stop_loss']
    native_validate(proxy)  # ALL original fee/balance/pending/risk state checks.
    previous=initial_stop;last=p['entry_time']
    for row in p['stop_history']:
        value=D(row['stop_loss'])
        if row['computed_closed_at']!=row['effective_from'] or row['effective_from']>s['watermark'] or row['effective_from']<last or not (value>=previous if long else value<=previous):raise DemoError('NON_CAUSAL_LAB_TRAIL')
        previous=value;last=row['effective_from']
    if previous!=stop:raise DemoError('TRAIL_HISTORY_MISMATCH')

@precise
def ratchet(s,bar,atr,*,step):
    p=s['position']
    if not p or bar.time<p['entry_time']:return
    if bar.time+step!=s['watermark']:raise DemoError('UNCLOSED_TRAIL_INPUT')
    av=D(str(atr))
    if not av.is_finite() or av<=0:raise DemoError('INVALID_TRAIL_ATR')
    if not p.get('lab_v2_trailing'):
        p.update(lab_v2_trailing=True,initial_stop_loss=p['stop_loss'],stop_history=[],trailing_extreme=p['entry_raw_price'])
    long=p['direction']=='LONG';old=D(p['stop_loss']);extreme=max(D(p['trailing_extreme']),bar.high) if long else min(D(p['trailing_extreme']),bar.low)
    candidate=min(extreme-3*av,bar.close) if long else max(extreme+3*av,bar.close)
    updated=max(old,candidate) if long else min(old,candidate)
    if updated<=0:raise DemoError('INVALID_TRAIL_STOP')
    p['trailing_extreme']=text(extreme)
    if updated!=old:
        p['stop_loss']=text(updated);p['stop_history'].append(dict(effective_from=bar.time+step,computed_closed_at=bar.time+step,
            stop_loss=text(updated),atr=str(av),extreme=text(extreme),bar_close=text(bar.close)))
    validate(s)

@precise
def advance(old,bars,decision,now):
    """Already committed signal only; never build signals from catch-up candles."""
    s=deepcopy(old);validate(s);events=[];latest=now//STEP*STEP
    validate_bars(bars,now)
    if bars[-1].time+STEP!=latest:raise DemoError('STALE_DATA')
    watermark=s['watermark']
    if watermark is None:
        s.update(watermark=latest,last_bar_hash=digest(bars[-1].data()),pending=None,last_decision='ACTIVATION_BASELINE')
        mark(s,bars[-1],latest)
        return s,[event(s,'BASELINE',latest,now,dict(reason='ACTIVATION_BASELINE'))]
    prior=next((b for b in bars if b.time+STEP==watermark),None)
    if prior is None or digest(prior.data())!=s['last_bar_hash']:raise DemoError('SOURCE_CORRECTION_OR_HISTORY_MISSING')
    if latest==watermark:return s,[]
    future=[b for b in bars if b.time>=watermark]
    if not future or future[0].time!=watermark or any(b.time-a.time!=STEP for a,b in zip(future,future[1:])):raise DemoError('MISSING_CANDLES')
    if len(future)>32:raise DemoError('CATCHUP_LIMIT')
    if len(future)>1:
        s['missed_candles']+=len(future)-1;s['pending']=None
        events.append(event(s,'MISSED',latest,now,dict(count=len(future)-1,reason='MISSED_RUN_NO_RETROACTIVE_ENTRIES')))
    for b in future:
        roll_day(s,b.time)
        pending=s['pending'];s['pending']=None
        # Apply adverse opening mark before sizing another position.
        eq=liquidation_equity(s,b.open);s['equity']=text(eq);s['day_low_equity']=text(min(dec(s['day_low_equity']),eq))
        s['max_drawdown_pct']=text(max(dec(s['max_drawdown_pct']),money((dec(s['peak'])-eq)/dec(s['peak'])*100)))
        if pending and s['mode']=='ON' and not risk_reason(s) and pending['signal_at']==b.time:
            try:
                events.append(open_virtual(s,pending,b,now))
                s['position']['original_signal_at']=pending.get('original_signal_at',pending['signal_at'])
                s['position']['strategy_timeframe']=pending.get('strategy_timeframe','15m')
            except DemoError as exc:events.append(event(s,'REJECT',b.time,now,dict(reason=exc.code)))
        exit_event=protective(s,b,now)
        if exit_event:events.append(exit_event)
        mark(s,b,b.time+STEP)
        reason=risk_reason(s)
        if reason:
            if not s['emergency']:s['mode']='PAUSED'
            s['pending']=None;s['last_decision']=reason
    s.update(watermark=latest,last_bar_hash=digest(bars[-1].data()))
    reason=risk_reason(s)
    if s['mode']!='ON':reason=reason or 'AUTO_OFF'
    elif s['position']:reason='POSITION_ALREADY_OPEN'
    else:reason=reason or decision['reason']
    if reason==decision['reason'] and decision.get('direction') and s['mode']=='ON' and not s['position'] and not risk_reason(s):
        s['pending']=dict(decision,signal_at=latest,created_at=now);reason='SIGNAL_QUEUED_NEXT_OPEN'
    s['last_decision']=reason
    events.append(event(s,'DECISION',latest,now,dict(reason=reason,signal=decision,mode=s['mode'],closed_at=latest,
        balance=s['balance'],equity=s['equity'])))
    validate(s)
    return s,events
