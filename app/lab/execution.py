"""One deterministic research-only Decimal engine shared by compatible strategies."""
from decimal import Decimal as D
import math
import time
from statistics import mean,stdev
from .models import Baseline,LabError,money,quantity,text,precise


def fee(price,size,rate):return money(price*size*rate,ceil=True)
def fill(raw,side,entry,slip):return raw*(1+(1 if (side=='LONG')==entry else -1)*slip)


@precise
def metrics(trades,curve,baseline):
    pnls=[D(t['realized_pnl']) for t in trades];wins=[p for p in pnls if p>0];losses=[-p for p in pnls if p<0]
    profit=sum(wins,D(0));loss=sum(losses,D(0));net=sum(pnls,D(0));start=D(baseline.starting_balance)
    peak=start;dd=D(0);dd_usdt=D(0)
    for point in curve:
        equity=D(point['equity']);peak=max(peak,equity);dd_usdt=max(dd_usdt,peak-equity);dd=max(dd,(peak-equity)/peak*100)
    daily=[p for p in curve if p['time']%86400==0]
    daily_returns=[]
    valid=True
    for a,b in zip(daily,daily[1:]):
        if D(a['equity'])<=0 or D(b['equity'])<=0:valid=False;break
        if b['time']-a['time']==86400:daily_returns.append(float(D(b['equity'])/D(a['equity'])-1))
    sharpe=None
    if valid and len(trades)>=baseline.min_trades and len(daily_returns)>=baseline.sharpe_min_daily_returns and stdev(daily_returns)>0:
        sharpe=mean(daily_returns)/stdev(daily_returns)*math.sqrt(365)
    return dict(net_profit=text(net),return_pct=text(money(net/start*100)),trades=len(trades),wins=len(wins),losses=len(losses),
                breakeven=len(pnls)-len(wins)-len(losses),win_rate=text(money(D(len(wins))/len(pnls)*100)) if pnls else None,
                profit_factor=text(money(profit/loss)) if loss else None,expectancy=text(money(net/len(pnls))) if pnls else None,
                max_drawdown_pct=text(money(dd)),max_drawdown_usdt=text(money(dd_usdt)),
                average_win=text(money(profit/len(wins))) if wins else None,average_loss=text(money(loss/len(losses))) if losses else None,
                realized_risk_reward=text(money((profit/len(wins))/(loss/len(losses)))) if wins and losses else None,
                total_fees=text(sum((D(t['fees']) for t in trades),D(0))),
                total_slippage_usdt=text(sum((D(t['slippage_usdt']) for t in trades),D(0))),
                sharpe=sharpe,sharpe_daily_returns=len(daily_returns),
                sharpe_assumptions='UTC full-day liquidation-equity returns; sample stdev; sqrt(365), crypto 24/7, zero risk-free rate. Undefined with <20 trades, <30 daily returns, nonpositive equity or zero variance.',
                sample_status='INCONCLUSIVE' if len(trades)<baseline.min_trades else 'DESCRIPTIVE_ONLY',
                sample_note='At least 20 trades required for numerical ranking; passing threshold is not statistical proof of profitability.',
                final_balance=curve[-1]['balance'])


@precise
def simulate(bars,signals,begin,end,step,baseline:Baseline,deadline=None,*,trailing_atr=None,close_at_end=True):
    baseline.validate()
    if not 0<=begin<end<=len(bars) or len(signals)!=len(bars):raise LabError('INVALID_RANGE')
    # Optional research-only distances. Existing callers/output remain unchanged.
    if trailing_atr is not None:
        if len(trailing_atr)!=len(bars) or any(v is not None and (not isinstance(v,D) or not v.is_finite() or v<=0) for v in trailing_atr):
            raise LabError('INVALID_TRAILING_STOP')
    balance=D(baseline.starting_balance);rate=D(baseline.fee_bps)/10000;slip=D(baseline.slippage_bps)/10000
    position=None;pending_entry=None;pending_exit=False;trades=[];rejected={};curve=[dict(time=bars[begin].time,balance=text(balance),equity=text(balance))]

    def reject(code):rejected[code]=rejected.get(code,0)+1
    def equity(price):
        if position is None:return balance
        sign=1 if position['direction']=='LONG' else -1
        exit_fill=fill(price,position['direction'],False,slip)
        return money(balance+money(sign*(exit_fill-D(position['entry_price']))*D(position['size']))-fee(exit_fill,D(position['size']),rate))
    def close(raw,stamp,reason):
        nonlocal position,balance
        p=position;size=D(p['size']);exit_price=fill(raw,p['direction'],False,slip);sign=1 if p['direction']=='LONG' else -1
        exit_fee=fee(exit_price,size,rate);gross=money(sign*(exit_price-D(p['entry_price']))*size)
        pnl=money(gross-D(p['entry_fee'])-exit_fee);balance=money(balance+gross-exit_fee)
        p.update(exit_raw_price=text(raw),exit_price=text(exit_price),exit_time=stamp,exit_reason=reason,exit_fee=text(exit_fee),
                 fees=text(D(p['entry_fee'])+exit_fee),gross_price_pnl=text(gross),realized_pnl=text(pnl),
                 pnl_pct=text(money(pnl/D(p['notional'])*100)),status='CLOSED',
                 slippage_usdt=text(money((abs(D(p['entry_price'])-D(p['entry_raw_price']))+abs(exit_price-raw))*size)))
        trades.append(p);position=None
    def open_position(decision,bar):
        nonlocal position,balance
        side=decision.direction
        if side not in ('LONG','SHORT'):reject('INVALID_SIGNAL');return
        entry=fill(bar.open,side,True,slip);sign=1 if side=='LONG' else -1
        distances=(decision.stop_distance,decision.target_distance)
        if any(not isinstance(v,D) or not v.is_finite() or v<=0 for v in distances):reject('INVALID_STOPS');return
        stop=entry-sign*decision.stop_distance;target=entry+sign*decision.target_distance
        if min(stop,target)<=0:reject('INVALID_STOPS');return
        planned_stop=fill(stop,side,False,slip);planned_target=fill(target,side,False,slip)
        if balance<=0:reject('INSUFFICIENT_BALANCE');return
        budget=balance*D(baseline.risk_pct)/100
        unit_risk=abs(entry-planned_stop)+rate*(entry+planned_stop)
        if unit_risk<=0:reject('INVALID_STOPS');return
        size=quantity(min((budget-D('0.00000003'))/unit_risk,D(baseline.max_notional)/entry,(balance-D('0.00000002'))/(entry*(1+rate))))
        if size<=0:reject('INSUFFICIENT_BALANCE');return
        notional=money(entry*size,ceil=True);entry_fee=fee(entry,size,rate)
        risk=money(abs(entry-planned_stop)*size,ceil=True)+entry_fee+fee(planned_stop,size,rate)
        reward=money(sign*(planned_target-entry)*size)-entry_fee-fee(planned_target,size,rate)
        if notional>D(baseline.max_notional):reject('NOTIONAL_LIMIT');return
        if notional+entry_fee>balance:reject('INSUFFICIENT_BALANCE');return
        if risk>budget:reject('RISK_LIMIT');return
        if reward<=0:reject('TARGET_AFTER_COSTS');return
        balance=money(balance-entry_fee)
        position=dict(direction=side,signal_time=bars[bar_index-1].time+step,entry_time=bar.time,entry_raw_price=text(bar.open),
                      entry_price=text(entry),size=text(size),notional=text(notional),stop_loss=text(stop),take_profit=text(target),
                      entry_fee=text(entry_fee),risk_usdt=text(risk),risk_budget_usdt=text(money(budget)),planned_risk_reward=text(money(reward/risk)),
                      entry_reason=decision.reason,status='OPEN')
        if trailing_atr is not None:
            position.update(initial_stop_loss=text(stop),trailing_extreme=text(entry),stop_history=[])

    for bar_index in range(begin,end):
        if deadline is not None and time.monotonic()>deadline:raise LabError('COMPUTE_TIMEOUT')
        b=bars[bar_index]
        # A protective opening gap has priority over a scheduled strategy exit.
        if position is not None:
            p=position;long=p['direction']=='LONG';stop=D(p['stop_loss']);target=D(p['take_profit'])
            if (b.open<=stop if long else b.open>=stop):close(b.open,b.time,'STOP_GAP')
            elif (b.open>=target if long else b.open<=target):close(target,b.time,'TAKE_PROFIT_GAP_CONSERVATIVE')
            elif pending_exit:close(b.open,b.time,'STRATEGY_EXIT_NEXT_OPEN')
        pending_exit=False
        if pending_entry is not None and position is None:open_position(pending_entry,b)
        pending_entry=None
        if position is not None:
            p=position;long=p['direction']=='LONG';stop=D(p['stop_loss']);target=D(p['take_profit'])
            stop_hit=b.low<=stop if long else b.high>=stop;target_hit=b.high>=target if long else b.low<=target
            if stop_hit:close(stop,b.time+step,'STOP_LOSS_AMBIGUOUS' if target_hit else 'STOP_LOSS')
            elif target_hit:close(target,b.time+step,'TAKE_PROFIT')
        if bar_index==end-1:
            if position is not None and close_at_end:close(b.close,b.time+step,'SEGMENT_END_CLOSE')
        else:
            # Ratchet only after the CLOSED bar was executed with the old stop.
            # Clamp to close: never retrospectively fill a newly computed stop.
            if position is not None and trailing_atr is not None and trailing_atr[bar_index] is not None:
                p=position;long=p['direction']=='LONG';old=D(p['stop_loss']);distance=trailing_atr[bar_index]
                extreme=max(D(p['trailing_extreme']),b.high) if long else min(D(p['trailing_extreme']),b.low)
                candidate=min(extreme-distance,b.close) if long else max(extreme+distance,b.close)
                updated=max(old,candidate) if long else min(old,candidate)
                p['trailing_extreme']=text(extreme)
                if updated!=old:
                    p['stop_loss']=text(updated)
                    p['stop_history'].append(dict(effective_from=b.time+step,stop_loss=text(updated)))
            decision=signals[bar_index]
            if position is None and decision.direction is not None:pending_entry=decision
            elif position is not None:pending_exit=decision.exit_long if position['direction']=='LONG' else decision.exit_short
        curve.append(dict(time=b.time+step,balance=text(balance),equity=text(equity(b.close))))
    unfinished_fee=D(position['entry_fee']) if position is not None else D(0)
    if balance!=money(D(baseline.starting_balance)+sum((D(t['realized_pnl']) for t in trades),D(0))-unfinished_fee):raise LabError('ACCOUNTING_ERROR')
    result=dict(status='OK',metrics=metrics(trades,curve,baseline),trades=trades,equity_curve=curve,rejections=rejected,
                decision_start=bars[begin].time,decision_end_exclusive=bars[end-1].time+step,
                entry_model='SIGNAL_AT_CLOSE_ENTRY_NEXT_OPEN',positions_max=1,
                execution_scope='RESEARCH_ONLY',real_money_execution='DISABLED')
    if not close_at_end:result['open_position']=position
    return result
