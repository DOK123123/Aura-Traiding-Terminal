"""Independent exact Fraction oracle. No engine/risk/fill/storage imports."""
from fractions import Fraction as F

SCALE=10**8
QTY_SCALE=10**12

def quantize(value,ceil=False):
    value=F(value);q,r=divmod(value.numerator*SCALE,value.denominator)
    if (r and ceil) or (not ceil and (2*r>value.denominator or 2*r==value.denominator and q%2)):q+=1
    return F(q,SCALE)

def check(condition,label):
    if not condition:raise AssertionError('ORACLE_'+label)

def audit_position(p,starting='10000'):
    sign=1 if p['direction']=='LONG' else -1;q=F(p['size']);raw=F(p['entry_raw_price'])
    entry=raw*(1+sign*F(5,10000));stop_fill=F(p['stop_loss'])*(1-sign*F(5,10000));capital=F(starting)
    rate=F(1,1000);budget=capital/F(200);unit=abs(entry-stop_fill)+rate*(entry+stop_fill)
    cap=min((budget-F(3,10**8))/unit,F(2000)/entry,(capital-F(2,10**8))/(entry*(1+rate)))
    size=F(cap.numerator*QTY_SCALE//cap.denominator,QTY_SCALE)
    ef=quantize(entry*q*rate,True)
    risk=quantize(abs(entry-stop_fill)*q,True)+ef+quantize(stop_fill*q*rate,True)
    check(q==size,'SIZE');check(F(p['entry_price'])==entry,'ENTRY_FILL');check(F(p['entry_fee'])==ef,'ENTRY_FEE')
    check(F(p['notional'])==quantize(entry*q,True),'NOTIONAL');check(F(p['notional'])<=2000,'NOTIONAL_CAP')
    check(F(p['risk_usdt'])==risk and risk<=budget,'FEE_INCLUSIVE_RISK');check(F(p['risk_budget_usdt'])==quantize(budget),'BUDGET')
    return dict(sign=sign,q=q,entry=entry,entry_fee=ef,capital=capital)

def audit_mark(p,state,bar,view):
    a=audit_position(p);price=F(bar.close)*(1-a['sign']*F(5,10000));gross=quantize(a['sign']*(price-a['entry'])*a['q']);fee=quantize(price*a['q']/1000,True)
    balance=a['capital']-a['entry_fee'];equity=quantize(balance+gross-fee)
    check(F(state['balance'])==balance,'OPEN_BALANCE');check(F(state['equity'])==equity,'MARK_EQUITY')
    check(F(view['position']['net_pnl_including_entry_fee'])==gross-fee-a['entry_fee'],'MONITOR_NET_MARK')
    return True

def audit_close(p,t,state,bar):
    a=audit_position(p)
    check(all(t[k]==p[k] for k in ('id','direction','size','entry_price','entry_raw_price','stop_loss','take_profit','entry_fee','signal_at','entry_time','notional','risk_usdt','risk_budget_usdt')),'POSITION_IDENTITY')
    long=p['direction']=='LONG';stop=F(p['stop_loss']);target=F(p['take_profit'])
    o,h,l=map(F,(bar.open,bar.high,bar.low));raw=reason=None
    if (o<=stop if long else o>=stop):raw,reason=o,'STOP_GAP'
    elif (o>=target if long else o<=target):raw,reason=target,'TAKE_PROFIT_GAP_CONSERVATIVE'
    else:
        sl=l<=stop if long else h>=stop;tp=h>=target if long else l<=target
        if sl:raw,reason=stop,'STOP_LOSS_AMBIGUOUS' if tp else 'STOP_LOSS'
        elif tp:raw,reason=target,'TAKE_PROFIT'
    check(raw is not None and F(t['exit_raw_price'])==raw and t['exit_reason']==reason,'FIRST_TOUCH_FILL')
    check(t['exit_time']==bar.time+(0 if 'GAP' in reason else 900),'EXIT_TIMESTAMP')
    price=raw*(1-a['sign']*F(5,10000));xf=quantize(price*a['q']/1000,True)
    gross=quantize(a['sign']*(price-a['entry'])*a['q']);net=quantize(gross-a['entry_fee']-xf)
    slip=quantize(quantize(abs(a['entry']-F(p['entry_raw_price']))*a['q'])+abs(price-raw)*a['q'])
    check(F(t['exit_price'])==price,'EXIT_FILL');check(F(t['exit_fee'])==xf,'EXIT_FEE')
    check(F(t['gross_price_pnl'])==gross,'GROSS');check(F(t['fees'])==a['entry_fee']+xf,'TRADE_FEES')
    check(F(t['realized_pnl'])==net and F(state['realized_pnl'])==net,'NET')
    check(F(state['balance'])==a['capital']+net and F(state['equity'])==F(state['balance']),'FINAL_BALANCE')
    check(F(state['fees'])==a['entry_fee']+xf,'ACCOUNT_FEES');check(F(state['slippage'])==slip,'SLIPPAGE')
    check(state['position'] is None and state['trades']==1,'FINAL_POSITION_COUNT')
    return True
