"""Hypothetical observations only: no account balances, positions or order writers."""
from bisect import bisect_left, bisect_right
from decimal import Decimal, localcontext
import math

D = lambda x: Decimal(str(x))


def cashflow(plan, entry, exit_price, entry_time, exit_time, bars, funding, *, multiplier=1):
    """1 BTC research PnL. Public funding rates with explicitly conservative OHLC notional proxy."""
    from .engine import RULES
    sign = 1 if plan['direction']=='LONG' else -1
    with localcontext() as ctx:
        ctx.prec = 40
        fee = D(RULES['costs']['fee_bps_per_side'])*D(multiplier)/D(10000)
        fees = (D(entry)+D(exit_price))*fee
        funding_cost = D(0)
        at = [x[0] for x in funding]
        selected = funding[bisect_left(at,entry_time):bisect_right(at,exit_time+plan['step'])]
        actual_times={x[0] for x in selected}
        missing=[]
        # Missing historical funding is a disclosed debit model, never fake observed rates.
        first_settlement=int(math.ceil(entry_time/28800))*28800
        for timestamp in range(first_settlement,int(exit_time+plan['step'])+1,28800):
            if timestamp not in actual_times:missing.append(timestamp)
        selected=sorted([*selected,*[[t,sign*.0001] for t in missing]])
        bar_times = [b[0] for b in bars]
        for timestamp, rate in selected:
            index = bisect_right(bar_times,timestamp)-1
            if index < 0:
                raise ValueError('FUNDING_PRICE_COVERAGE')
            b = bars[index]
            if not b[0] <= timestamp <= b[0]+plan['step']:
                raise ValueError('FUNDING_PRICE_GAP')
            debit = sign*rate
            boundary = timestamp==entry_time or timestamp>=exit_time
            if debit < 0 and boundary:
                continue  # Uncertain boundary credit never manufactures profit.
            proxy = b[2] if debit>=0 else b[3]
            value = D(sign)*D(rate)*D(proxy)
            funding_cost += value*D(multiplier) if value>=0 else value
        pnl = D(sign)*(D(exit_price)-D(entry))-fees-funding_cost
        risk = abs(D(plan['entry'])-D(plan['sl']))
        return {'fees_usdt': str(fees), 'funding_usdt': str(funding_cost), 'pnl_usdt': str(pnl),
                'r': float(pnl/risk), 'missing_funding_settlements':len(missing), 'funding_model': 'MODELED_MISSING_1BP_PER_8H_DEBIT' if missing else 'ACTUAL_RATES_OHLC_NOTIONAL_PROXY; BOUNDARY_CREDITS_EXCLUDED'}


def simulate(plan, bars, funding, *, multiplier=1, delay=1):
    from .engine import RULES
    sign = 1 if plan['direction']=='LONG' else -1
    step = plan['step']
    record = {**plan, 'outcome':'UNKNOWN','entered':False,'entry_time':None,'exit_time':None,
              'entry_fill':None,'exit_fill':None,'pnl_usdt':None,'r':None,'ambiguous':False,
              'note':'END_OF_DATA','cost_multiplier':multiplier,'last_time':plan['signal_time']}
    if not bars:
        return record
    first_time = plan['signal_time']+(delay-1)*step
    first = bisect_left([b[0] for b in bars],first_time)
    if first >= len(bars) or bars[first][0] != first_time:
        record['note']='ENTRY_DATA_GAP';return record
    b=bars[first]
    half=RULES['costs']['full_spread_bps']/2e4*multiplier
    slip=RULES['costs']['slippage_bps_per_side']/1e4*multiplier
    reference=b[1]*(1+sign*half)
    if not plan['zone'][0]<=reference<=plan['zone'][1] or sign*(reference-plan['sl'])<=0 or sign*(plan['tp']-reference)<=0:
        record.update(outcome='NO_FILL',note='NEXT_OPEN_OUTSIDE_ZONE_OR_LEVELS',last_time=b[0]);return record
    record.update(entered=True,entry_time=b[0],entry_fill=reference*(1+sign*slip))
    for j in range(first,min(len(bars),first+plan['hold_bars'])):
        b=bars[j];record['last_time']=b[0]
        if b[0] != first_time+(j-first)*step:
            record['note']='OUTCOME_DATA_GAP';return record
        q=1-sign*half
        op,high,low,close=b[1]*q,b[2]*q,b[3]*q,b[4]*q
        sl=low<=plan['sl'] if sign==1 else high>=plan['sl']
        tp=high>=plan['tp'] if sign==1 else low<=plan['tp']
        exit_price=None;outcome=None;note=None
        if sign*(op-plan['sl'])<=0:
            exit_price,outcome,note=op,'SL','ADVERSE_STOP_GAP'
        elif sign*(op-plan['tp'])>=0:
            exit_price,outcome,note=plan['tp'],'TP','TARGET_GAP_CAPPED'
        elif sl:
            exit_price,outcome,note=plan['sl'],'SL','BOTH_TOUCHED_SL_FIRST' if tp else 'STOP_TOUCHED'
            record['ambiguous']=bool(tp)
        elif tp:
            exit_price,outcome,note=plan['tp'],'TP','TARGET_TOUCHED'
        elif j==first+plan['hold_bars']-1:
            exit_price,outcome,note=close,'TIMEOUT','HOLD_LIMIT'
        if outcome:
            fill=exit_price*(1-sign*slip)
            record.update(outcome=outcome,note=note,exit_time=b[0],exit_fill=fill)
            record.update(cashflow(plan,record['entry_fill'],fill,record['entry_time'],record['exit_time'],bars[first:j+1],funding,multiplier=multiplier))
            return record
    return record
