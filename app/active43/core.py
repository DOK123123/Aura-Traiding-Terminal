"""Network-free Active transitions using the existing production Decimal engine.

Engine ABI remains 4.2; scope/strategy identity and policy are independently pinned.
No global monkeypatching, account fallback or exchange client.
"""
from copy import deepcopy
from decimal import Decimal as D,ROUND_DOWN,ROUND_UP
from app.automated import engine as paper
from app.lab.execution import fee,fill
from app.lab.models import digest,money,text,precise,LabError
from .strategies import VERSION,STEPS,PARAMETERS,config as make_config

SCOPE='AURA43_ACTIVE_PAPER'
SOURCE='Bybit · USDT Perpetual / api.bybit.com'
IDENTITY=dict(exchange='BYBIT',market_type='USDT_PERPETUAL',category='linear',symbol='BTCUSDT',settlement='USDT')
FILTERS=dict(qty_step='0.001',min_qty='0.001',min_notional='5',price_tick='0.10')
POLICY=dict(paper.POLICY,classification='EXPERIMENTAL / UNVALIDATED_FUTURES',execution='CLOSED_SIGNAL_NEXT_OPEN',filters=FILTERS,source=SOURCE,identity=IDENTITY,funding='NOT_MODELED',
    cost_model='CONSERVATIVE_FIXED_10BPS_FEE_5BPS_SLIPPAGE_PER_SIDE')


def initial(now,config=None,epoch=None):
    cfg=config or make_config();s=paper.initial(now,epoch=epoch)
    s['epoch']='ACTIVE43_BYBIT_'+s['epoch']
    s.update(scope=SCOPE,market_source=SOURCE,market_identity=IDENTITY,strategy_version=VERSION,config=cfg,config_hash=digest(cfg),active_policy_hash=digest(POLICY),
             pending_exit=None,recovery_status='COLD_START',last_signal=None,last_check=None,last_close=None,last_price=None)
    return s


def validate(s):
    paper.validate(s)
    try:
        cfg=s['config']
        if (s['scope']!=SCOPE or not s['epoch'].startswith('ACTIVE43_BYBIT_') or s.get('market_source')!=SOURCE or s.get('market_identity')!=IDENTITY or s['strategy_version']!=VERSION
            or cfg!=make_config(cfg['strategy'],cfg['timeframe']) or s['config_hash']!=digest(cfg)
            or s['active_policy_hash']!=digest(POLICY)):raise ValueError()
        p=s['position']
        if s['pending'] and s['pending'].get('source')!=SOURCE:raise ValueError()
        if p and p.get('market_source')!=SOURCE:raise ValueError()
        if p:
            active=D(p.get('active_stop',p['stop_loss']));old=D(p['stop_loss']);target=D(p['take_profit'])
            if not active.is_finite() or active<=0 or not (old<=active<target if p['direction']=='LONG' else target<active<=old):raise ValueError()
        if s.get('pending_exit') is not None and (not p or s['pending_exit']!=p['id']):raise ValueError()
    except (KeyError,TypeError,ValueError,ArithmeticError):raise paper.DemoError('ACTIVE_SCOPE_OR_CONFIG_MISMATCH') from None


def event(s,kind,key,now,body):
    ev=paper.event(s,kind,key,now,body)
    ev['payload'].update(scope=SCOPE,strategy_version=VERSION,timeframe=s['config']['timeframe'],source=SOURCE)
    return ev


def plan(decision,bar,step,atr_value=None):
    side=decision.direction;value=dict(direction=side,reason=decision.reason,source=SOURCE,signal_at=bar.time+step,
        exit_long=decision.exit_long,exit_short=decision.exit_short,atr=None if atr_value is None else str(atr_value))
    if side:
        sign=1 if side=='LONG' else -1
        value.update(stop_loss=text(bar.close-sign*decision.stop_distance),take_profit=text(bar.close+sign*decision.target_distance))
    return value


@precise
def open_position(s,decision,bar,now):
    # Reuse production sizing/risk; floor to frozen Bybit linear lot step, then use the
    # same production fee/fill functions to reconcile the smaller virtual fill.
    decision=deepcopy(decision);long=decision['direction']=='LONG';tick=D(FILTERS['price_tick'])
    # Virtual trigger prices obey the same contract tick. Round a stop outward
    # and a target toward entry; the existing fee-inclusive risk is recomputed.
    for key in ('stop_loss','take_profit'):
        rounding=ROUND_DOWN if long else ROUND_UP
        decision[key]=text((D(decision[key])/tick).to_integral_value(rounding=rounding)*tick)
    ev=paper.open_virtual(s,decision,bar,now);p=s['position'];old=deepcopy(p);q=D(p['size'])
    q=(q/D(FILTERS['qty_step'])).to_integral_value(rounding=ROUND_DOWN)*D(FILTERS['qty_step'])
    px=D(p['entry_price']);cost=money(px*q,ceil=True)
    if q<D(FILTERS['min_qty']) or cost<D(FILTERS['min_notional']):raise paper.DemoError('MINIMUM_SIZE_OR_NOTIONAL')
    ef=fee(px,q,paper.RATE);stop=fill(D(p['stop_loss']),p['direction'],False,paper.SLIP)
    risk=money(abs(px-stop)*q,ceil=True)+ef+fee(stop,q,paper.RATE)
    target=fill(D(p['take_profit']),p['direction'],False,paper.SLIP);sign=1 if p['direction']=='LONG' else -1
    if risk>D(p['risk_budget_usdt']) or money(sign*(target-px)*q)-ef-fee(target,q,paper.RATE)<=0:raise paper.DemoError('RISK_OR_COST_FILTER')
    s['balance']=text(money(D(s['balance'])+D(old['entry_fee'])-ef))
    s['fees']=text(money(D(s['fees'])-D(old['entry_fee'])+ef))
    s['slippage']=text(money(D(s['slippage'])-money(abs(px-bar.open)*D(old['size']))+money(abs(px-bar.open)*q)))
    p.update(size=text(q),notional=text(cost),entry_fee=text(ef),risk_usdt=text(risk),timeframe=s['config']['timeframe'],
             active_stop=p['stop_loss'],trailing_extreme=p['entry_price'],market_source=SOURCE)
    return event(s,'OPEN',decision['signal_at'],now,deepcopy(p))


def close(s,raw,at,reason):
    ev=paper.close_virtual(s,raw,at,reason);s['pending_exit']=None
    result=event(s,'CLOSE',ev['payload']['signal_at'],at,ev['payload']);s['last_close']=deepcopy(result['payload'])
    return result


def protect(s,b,step):
    p=s['position']
    if not p:return None
    long=p['direction']=='LONG';stop=D(p['active_stop']);target=D(p['take_profit'])
    if (b.open<=stop if long else b.open>=stop):return close(s,b.open,b.time,'STOP_GAP')
    if (b.open>=target if long else b.open<=target):return close(s,target,b.time,'TAKE_PROFIT_GAP_CONSERVATIVE')
    sl=b.low<=stop if long else b.high>=stop;tp=b.high>=target if long else b.low<=target
    if sl:return close(s,stop,b.time+step,'STOP_LOSS_AMBIGUOUS' if tp else 'STOP_LOSS')
    if tp:return close(s,target,b.time+step,'TAKE_PROFIT')
    return None


def ratchet(s,b,distance,closed_at):
    p=s['position']
    if not p or distance is None:return None
    distance=D(str(distance))
    if not distance.is_finite() or distance<=0:raise paper.DemoError('INVALID_ANALYSIS')
    long=p['direction']=='LONG';old=D(p['active_stop']);tick=D(FILTERS['price_tick']);target=D(p['take_profit'])
    extreme=max(D(p['trailing_extreme']),b.high) if long else min(D(p['trailing_extreme']),b.low)
    candidate=min(extreme-distance,b.close-tick,target-tick) if long else max(extreme+distance,b.close+tick,target+tick)
    new=max(old,candidate) if long else min(old,candidate)
    new=(new/tick).to_integral_value(rounding=ROUND_DOWN if long else ROUND_UP)*tick
    p.update(active_stop=text(new),trailing_extreme=text(extreme))
    return dict(effective_from=closed_at,old_stop=text(old),active_stop=text(new)) if new!=old else None


@precise
def advance(old,bars,decision,now):
    s=deepcopy(old);validate(s);step=STEPS[s['config']['timeframe']];latest=now//step*step;events=[]
    if not bars or len(bars)>1300:raise paper.DemoError('INVALID_MARKET_DATA')
    try:
        for b in bars:b.validate(step,now)
    except LabError:raise paper.DemoError('INVALID_MARKET_DATA') from None
    if any(b.time-a.time!=step for a,b in zip(bars,bars[1:])):raise paper.DemoError('MISSING_CANDLES')
    if bars[-1].time+step!=latest:raise paper.DemoError('STALE_DATA')
    if decision.get('signal_at')!=latest or decision.get('source')!=SOURCE:raise paper.DemoError('SNAPSHOT_MISMATCH')
    if s['watermark'] is None:
        s.update(watermark=latest,last_bar_hash=digest(bars[-1].data()),pending=None,last_decision='ACTIVATION_BASELINE')
        paper.mark(s,bars[-1],latest);s['last_price']=text(bars[-1].close)
        return s,[event(s,'BASELINE',latest,now,dict(reason='ACTIVATION_BASELINE'))]
    prior=next((b for b in bars if b.time+step==s['watermark']),None)
    if prior is None or digest(prior.data())!=s['last_bar_hash']:raise paper.DemoError('SOURCE_CORRECTION_OR_HISTORY_MISSING')
    if latest==s['watermark']:return s,[]
    future=[b for b in bars if b.time>=s['watermark']]
    if not future or future[0].time!=s['watermark']:raise paper.DemoError('MISSING_CANDLES')
    missed=len(future)>1
    if missed:
        s['missed_candles']+=len(future)-1;s['pending']=None;s['pending_exit']=None
        events.append(event(s,'MISSED',latest,now,dict(reason='NO_RETROACTIVE_ENTRIES_OR_STRATEGY_EXITS',count=len(future)-1)))
    for b in future:
        paper.roll_day(s,b.time);pending=s['pending'];s['pending']=None
        eq=paper.liquidation_equity(s,b.open);s['equity']=text(eq);s['day_low_equity']=text(min(D(s['day_low_equity']),eq))
        s['max_drawdown_pct']=text(max(D(s['max_drawdown_pct']),money((D(s['peak'])-eq)/D(s['peak'])*100)))
        # Opening gaps precede queued strategy exits; full candle protection uses
        # the old stop. A newly calculated trailing stop is never back-filled.
        p=s['position']
        if p and s['pending_exit']:
            long=p['direction']=='LONG';stop=D(p['active_stop']);target=D(p['take_profit'])
            if (b.open<=stop if long else b.open>=stop):events.append(close(s,b.open,b.time,'STOP_GAP'))
            elif (b.open>=target if long else b.open<=target):events.append(close(s,target,b.time,'TAKE_PROFIT_GAP_CONSERVATIVE'))
            else:events.append(close(s,b.open,b.time,'STRATEGY_EXIT_NEXT_OPEN'))
        s['pending_exit']=None
        if pending and s['mode']=='ON' and not paper.risk_reason(s) and pending['signal_at']==b.time:
            before=deepcopy(s)
            try:events.append(open_position(s,pending,b,now))
            except paper.DemoError as exc:
                s=before;events.append(event(s,'REJECT',b.time,now,dict(reason=exc.code)))
        ev=protect(s,b,step)
        if ev:events.append(ev)
        paper.mark(s,b,b.time+step)
        if paper.risk_reason(s):
            if not s['emergency']:s['mode']='PAUSED'
            s['pending']=None
    # After an outage no intermediate strategy values or retroactive trails are
    # invented: old stop protects missed candles, current closed bar ratchets.
    if s['position'] and s['config']['strategy']=='TREND_ATR':
        change=ratchet(s,bars[-1],decision.get('atr'),latest)
        if change:events.append(event(s,'STOP_UPDATE',latest,now,change))
    s.update(watermark=latest,last_bar_hash=digest(bars[-1].data()),last_price=text(bars[-1].close))
    if s['position']:
        p=s['position'];exit_flag=decision.get('exit_long') if p['direction']=='LONG' else decision.get('exit_short')
        if exit_flag:s['pending_exit']=p['id']
        events.append(event(s,'POSITION_UPDATE',latest,now,dict(position=deepcopy(p),equity=s['equity'])))
    reason=paper.risk_reason(s) or ('AUTO_OFF' if s['mode']!='ON' else 'POSITION_ALREADY_OPEN' if s['position'] else decision['reason'])
    if decision.get('direction'):
        s['last_signal']=deepcopy(decision)
        events.append(event(s,'SIGNAL',latest,now,deepcopy(decision)))
        if s['mode']=='ON' and not s['position'] and not paper.risk_reason(s):
            s['pending']=deepcopy(decision);reason='SIGNAL_QUEUED_NEXT_OPEN'
    s['last_decision']=reason;s['last_check']=deepcopy(decision)
    events.append(event(s,'DECISION',latest,now,dict(reason=reason,signal=deepcopy(decision),closed_at=latest)))
    validate(s);return s,events
