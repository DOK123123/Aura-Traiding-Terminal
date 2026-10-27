"""Availability-aware, single-position offline execution. No order transport.

Only audited currency-neutral fee/fill/metrics helpers are reused from Lab.
Full Lab.simulate is incompatible with absolute levels, latency, TTL and guards.
"""
from collections import Counter
from decimal import Decimal as D, localcontext, ROUND_FLOOR, ROUND_CEILING
import time
from app.lab.execution import fee, fill, metrics
from app.lab.models import money, text
from .adapter import Signal
from .config import Config
from .dataset import Bar, validate


def rounded(value: D, tick: D, up: bool) -> D:
    return (value/tick).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR)*tick


def execute(bars, step: int, signals: list[Signal], config: Config, *, cost_multiplier: D = D(1),
            close_at_end: bool = True, deadline: float | None = None) -> dict:
    config.validate();validate(bars,step)
    if cost_multiplier not in (D(1),D('1.5'),D(2)):raise ValueError('COST_MULTIPLIER')
    known={};unique=[];duplicates=0
    for s in signals:
        s.validate()
        if s.id in known:
            if s!=known[s.id]:raise ValueError('SIGNAL_ID_COLLISION')
            duplicates+=1;continue
        known[s.id]=s;unique.append(s)
    if any(b.available_at<a.available_at for a,b in zip(unique,unique[1:])):raise ValueError('UNORDERED_SIGNALS')
    with localcontext() as ctx:
        ctx.prec=64
        return _execute(bars,step,unique,config,cost_multiplier,close_at_end,deadline,duplicates)


def _execute(bars,step,signals,cfg,multiplier,close_at_end,deadline,duplicates):
    rate=D(cfg.fee_bps)/10000*multiplier
    impact=(D(cfg.slippage_bps)+D(cfg.spread_bps)/2)/10000*multiplier
    tick=D(cfg.tick);lot=D(cfg.lot);balance=D(cfg.starting_balance)
    position=None;pending_guard=None;trades=[];events=[];curve=[];rejections=Counter();i=0
    peak=guard_peak=last_equity=balance;day=bars[0].time//86400;day_start=balance;daily_halt=False;drawdown_halt=False
    maximum_dd=D(0)

    def price(raw,side,entry):
        buy=(side=='LONG')==entry
        return rounded(fill(raw,side,entry,impact),tick,buy)

    def equity(raw):
        if position is None:return balance
        p=position;q=D(p['size']);x=price(raw,p['direction'],False);sign=1 if p['direction']=='LONG' else -1
        return money(balance+sign*(x-D(p['entry_price']))*q-fee(x,q,rate))

    def event(kind,stamp,**values):events.append(dict(event=kind,time=stamp,**values))

    def close(raw,stamp,reason):
        nonlocal position,balance,pending_guard
        p=position;q=D(p['size']);x=price(raw,p['direction'],False);sign=1 if p['direction']=='LONG' else -1
        exit_fee=fee(x,q,rate);gross=money(sign*(x-D(p['entry_price']))*q)
        pnl=money(gross-D(p['entry_fee'])-exit_fee);balance=money(balance+gross-exit_fee)
        p.update(exit_time=stamp,exit_price=text(x),exit_raw_price=text(raw),exit_fee=text(exit_fee),
                 fees=text(D(p['entry_fee'])+exit_fee),realized_pnl=text(pnl),gross_price_pnl=text(gross),
                 exit_reason=reason,status='CLOSED',funding='NOT_INCLUDED',
                 execution_impact_usdt=text(money((abs(D(p['entry_price'])-D(p['entry_raw_price']))+abs(x-raw))*q)),
                 slippage_usdt=text(money((abs(D(p['entry_price'])-D(p['entry_raw_price']))+abs(x-raw))*q)))
        trades.append(p);event('CLOSE',stamp,trade_id=p['id'],reason=reason,balance=text(balance));position=None;pending_guard=None

    def guards(raw,stamp):
        nonlocal peak,guard_peak,maximum_dd,drawdown_halt,daily_halt,pending_guard
        eq=equity(raw);peak=max(peak,eq);maximum_dd=max(maximum_dd,(peak-eq)/peak*100)
        guard_peak=max(guard_peak,eq);dd=(guard_peak-eq)/guard_peak*100
        why=None
        if eq<=day_start*(1-D(cfg.daily_loss_pct)/100):
            if not daily_halt:event('DAILY_LOSS_HALT',stamp,equity=text(eq))
            daily_halt=True;why='DAILY_LOSS_EXIT'
        if eq<=0 or dd>=D(cfg.drawdown_pct):
            if not drawdown_halt:event('DRAWDOWN_HALT',stamp,equity=text(eq))
            drawdown_halt=True;why='DRAWDOWN_EXIT'
        if why and position is not None and pending_guard is None:pending_guard=(stamp+cfg.latency_seconds,why)
        return eq

    def opening(s,b):
        nonlocal position,balance
        def reject(code):rejections[code]+=1;event('ENTRY_REJECTED',b.time,signal_id=s.id,reason=code)
        if b.volume==0:reject('ZERO_VOLUME');return
        if b.time>=s.valid_until:reject('SCENARIO_EXPIRED');return
        if b.time<s.available_at+cfg.latency_seconds:reject('SIGNAL_LATENCY');return
        if position is not None:reject('POSITION_LIMIT');return
        if drawdown_halt:reject('DRAWDOWN_HALT');return
        if daily_halt:reject('DAILY_LOSS_HALT');return
        if balance<=0:reject('INSUFFICIENT_MARGIN');return
        x=price(b.open,s.side,True);sign=1 if s.side=='LONG' else -1
        if not s.low<=b.open<=s.high or not s.low<=x<=s.high:reject('ENTRY_OUTSIDE_ZONE');return
        if not (s.stop<x<s.target if sign==1 else s.target<x<s.stop):reject('GAP_INVALID_GEOMETRY');return
        if s.stop%tick or s.target%tick:reject('OFF_TICK_LEVEL');return
        stop_fill=price(s.stop,s.side,False);target_fill=price(s.target,s.side,False)
        unit_loss=sign*(x-stop_fill)+rate*(x+stop_fill)
        if unit_loss<=0:reject('INVALID_RISK');return
        budget=min(balance*D(cfg.risk_pct)/100,balance-day_start*(1-D(cfg.daily_loss_pct)/100),
                   balance-guard_peak*(1-D(cfg.drawdown_pct)/100))
        if budget<=D('.00000004'):reject('LOSS_BUDGET_EXHAUSTED');return
        size=rounded(min((budget-D('.00000004'))/unit_loss,D(cfg.max_notional)/x,
                         max(D(0),balance-D('.00000004'))/(x*(1+rate))),lot,False)
        if size<D(cfg.min_quantity):reject('INSUFFICIENT_MARGIN_OR_MIN_QUANTITY');return
        notional=money(x*size,ceil=True);entry_fee=fee(x,size,rate)
        risk=money(sign*(x-stop_fill)*size,ceil=True)+entry_fee+fee(stop_fill,size,rate)
        reward=money(sign*(target_fill-x)*size)-entry_fee-fee(target_fill,size,rate)
        if notional<D(cfg.min_notional):reject('MIN_NOTIONAL');return
        if notional>D(cfg.max_notional) or notional+entry_fee>balance:reject('INSUFFICIENT_MARGIN');return
        if risk>budget:reject('RISK_LIMIT');return
        if reward<=0 or reward/risk<D('1.5'):reject('RR_AFTER_COSTS');return
        balance=money(balance-entry_fee)
        position=dict(id=s.id,direction=s.side,signal_time=s.candle_close,signal_available_at=s.available_at,
            entry_time=b.time,entry_raw_price=text(b.open),entry_price=text(x),size=text(size),notional=text(notional),
            stop_loss=text(s.stop),take_profit=text(s.target),entry_fee=text(entry_fee),risk_usdt=text(risk),
            risk_budget_usdt=text(money(budget)),planned_risk_reward=text(money(reward/risk)),status='OPEN')
        event('OPEN',b.time,trade_id=s.id,balance=text(balance),available_margin=text(balance-notional))

    curve.append(dict(time=bars[0].time,balance=text(balance),equity=text(balance)))
    for index,b in enumerate(bars):
        if deadline is not None and time.monotonic()>deadline:raise ValueError('COMPUTE_TIMEOUT')
        if b.time//86400!=day:
            day=b.time//86400;day_start=equity(b.open);daily_halt=False
        had_position=position is not None
        if position is not None and b.volume>0:
            p=position;long=p['direction']=='LONG';stop=D(p['stop_loss']);target=D(p['take_profit'])
            if (b.open<=stop if long else b.open>=stop):close(b.open,b.time,'STOP_GAP')
            elif (b.open>=target if long else b.open<=target):close(target,b.time,'TAKE_PROFIT_GAP_CONSERVATIVE')
            elif pending_guard is not None and b.time>=pending_guard[0]:close(b.open,b.time,pending_guard[1])
        opening_equity=guards(b.open,b.time)
        curve.append(dict(time=b.time,phase="OPEN_MARK",balance=text(balance),equity=text(opening_equity)))
        eligible=[]
        while i<len(signals) and signals[i].available_at+cfg.latency_seconds<=b.time:
            eligible.append(signals[i]);i+=1
        for s in eligible[:-1]:
            rejections['SUPERSEDED_SIGNAL']+=1;event('ENTRY_REJECTED',b.time,signal_id=s.id,reason='SUPERSEDED_SIGNAL')
        if eligible:
            if had_position:
                rejections['POSITION_LIMIT']+=1;event('ENTRY_REJECTED',b.time,signal_id=eligible[-1].id,reason='POSITION_LIMIT')
            else:opening(eligible[-1],b)
        if position is not None and b.volume>0:
            p=position;long=p['direction']=='LONG';stop=D(p['stop_loss']);target=D(p['take_profit'])
            sh=b.low<=stop if long else b.high>=stop;th=b.high>=target if long else b.low<=target
            if sh:close(stop,b.time+step,'STOP_LOSS_AMBIGUOUS' if th else 'STOP_LOSS')
            elif th:close(target,b.time+step,'TAKE_PROFIT')
        if index==len(bars)-1 and position is not None and close_at_end:
            # Explicit terminal accounting estimate, not a tradable historical close.
            close(b.close,b.available_at,'SEGMENT_END_LIQUIDATION_ESTIMATE')
        # Closing marks are reporting-only. Risk actions use known execution OPEN
        # prices, never a not-yet-published candle close to block an earlier open.
        last_equity=equity(b.close);peak=max(peak,last_equity)
        maximum_dd=max(maximum_dd,(peak-last_equity)/peak*100)
        curve.append(dict(time=b.time+step,available_at=b.available_at,balance=text(balance),equity=text(last_equity)))
    if i<len(signals):rejections['NO_NEXT_EXECUTION_BAR']+=len(signals)-i
    open_fee=D(position['entry_fee']) if position else D(0)
    if balance!=money(D(cfg.starting_balance)+sum((D(t['realized_pnl']) for t in trades),D(0))-open_fee):
        raise ValueError('ACCOUNTING_IDENTITY_FAILED')
    result_metrics=metrics(trades,curve,cfg)
    # Preserve both closing and subsequent opening marks for drawdown. Daily
    # returns use only the latest mark at each timestamp, not duplicate boundaries.
    daily_metrics=metrics(trades,list({p['time']:p for p in curve}.values()),cfg)
    for key in ('sharpe','sharpe_daily_returns'):
        result_metrics[key]=daily_metrics[key]
    result_metrics['max_drawdown_pct']=text(money(maximum_dd))
    result_metrics['final_liquidation_equity']=text(last_equity)
    result_metrics['long_trades']=sum(t['direction']=='LONG' for t in trades)
    result_metrics['average_holding_minutes']=text(money(sum((D(t['exit_time']-t['entry_time'])/60 for t in trades),D(0))/len(trades))) if trades else None
    result_metrics['trades_per_day']=text(money(D(len(trades))*86400/D(bars[-1].time+step-bars[0].time)))
    result_metrics['short_trades']=sum(t['direction']=='SHORT' for t in trades)
    return dict(metrics=result_metrics,trades=trades,equity_curve=curve,events=events,rejections=dict(rejections),
        open_position=position,duplicate_signals_ignored=duplicates,drawdown_halted=drawdown_halt,
        status='TECHNICAL_REPLAY_ONLY',real_money_execution='DISABLED',funding='NOT_INCLUDED',
        benchmark=buy_hold(bars,cfg,rate,impact),cost_multiplier=str(multiplier))


def buy_hold(bars,cfg,rate,impact):
    """Two passive LONG baselines: full unlevered capital and capped 2000 USDT."""
    live=[b for b in bars if b.volume>0]
    if not live:return {'status':'NO_LIQUID_BARS'}
    first,last=live[0],live[-1];tick=D(cfg.tick);lot=D(cfg.lot)
    entry=rounded(fill(first.open,'LONG',True,impact),tick,True)
    exit=rounded(fill(last.close,'LONG',False,impact),tick,False)
    result={}
    for label,cap in [('full_capital',D(cfg.starting_balance)),('notional_2000',D(cfg.max_notional))]:
        q=rounded(min(cap/entry,D(cfg.starting_balance)/(entry*(1+rate))),lot,False)
        costs=fee(entry,q,rate)+fee(exit,q,rate);net=money((exit-entry)*q-costs)
        result[label]=dict(net_profit=text(net),return_pct=text(money(net/D(cfg.starting_balance)*100)),fees=text(costs),
                           starting_balance=cfg.starting_balance,quantity=text(q),funding='NOT_INCLUDED')
    result['cash']={'net_profit':'0','return_pct':'0'}
    return result
