"""Independent rational-arithmetic oracle: no production fee/PnL helpers."""
from decimal import Decimal as D
from fractions import Fraction as F
import pytest

from app.paper.models import Settings,Bar,Window
from app.paper.engine import Engine
from app.paper.storage import Store
from tests.test_paper_engine import ledger,window,payload

TICKS=100000000


def nearest_ticks(value):
    value*=TICKS
    base=value.numerator//value.denominator
    remainder=value-F(base)
    return base+int(remainder>F(1,2) or (remainder==F(1,2) and base%2))


def ceiling_ticks(value):
    value*=TICKS
    return -((-value.numerator)//value.denominator)


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('commission',['0','0.1373','2.5'])
@pytest.mark.parametrize('size',['1','1.123456789012','0.00000001','0.099999999999'])
def test_independent_fraction_pnl_fees_equity(ledger,direction,commission,size):
    engine,clock=ledger
    settings=engine.snapshot()['settings'];settings['commission_pct']=commission;engine.configure(settings)
    win=window(clock);body=payload(win,direction,size=size)
    trade=engine.open(body,win)
    entry,exit_,q,rate=F(100),F('112.3456789'),F(size),F(commission)/100
    entry_fee=ceiling_ticks(entry*q*rate);exit_fee=ceiling_ticks(exit_*q*rate)
    sign=1 if direction=='LONG' else -1
    gross=nearest_ticks(sign*(exit_-entry)*q)
    expected=gross-entry_fee-exit_fee
    s=engine.snapshot()['statistics']
    assert F(s['current_balance'])*TICKS==10000*TICKS-entry_fee
    assert F(s['equity'])*TICKS==10000*TICKS-2*entry_fee
    clock[0]+=60000
    close_body={'request_id':'11111111-1111-4111-8111-111111111111','exit_reason':'Rational oracle'}
    result=engine.close(trade['id'],close_body,window(clock,'112.3456789'))
    assert F(result['realized_pnl'])*TICKS==expected
    assert F(result['commissions'])*TICKS==entry_fee+exit_fee
    assert F(engine.snapshot()['statistics']['current_balance'])*TICKS==10000*TICKS+expected
    reserved=ceiling_ticks(entry*q)
    assert F(result['pnl_pct'])*TICKS==nearest_ticks(F(expected,reserved)*100)


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_independent_rational_position_risk_bound(ledger,direction):
    engine,clock=ledger;config=engine.snapshot()['settings']
    config.update(commission_pct='0.1373',risk_per_trade_pct='0.25',maximum_position_size_usdt='10000',stop_loss_pct='2')
    engine.configure(config);win=window(clock);trade=engine.open(payload(win,direction,size=None),win)
    price,stop,q,rate=F(trade['entry_price']),F(trade['stop_loss']),F(trade['position_size']),F('0.1373')/100
    risk=ceiling_ticks(abs(price-stop)*q)+ceiling_ticks(price*q*rate)+ceiling_ticks(stop*q*rate)
    assert risk<=25*TICKS
    assert F(trade['risk_usdt'])*TICKS==risk
    assert q.denominator<=10**12


def test_independent_reference_strategy_stats(ledger):
    engine,clock=ledger;outcomes=[('LONG','110'),('SHORT','110'),('SHORT','95'),('LONG','100')]
    for side,price in outcomes:
        win=window(clock);t=engine.open(payload(win,side),win)
        clock[0]+=60000
        engine.close(t['id'],{'request_id':__import__('uuid').uuid4().__str__(),'exit_reason':'Reference'},window(clock,price))
    s=engine.snapshot()['statistics']
    # Settled outcomes +10,-10,+5,0: independent closed-equity path 10000,10010,10000,10005,10005.
    assert F(s['net_pnl'])==5 and F(s['profit_factor'])==F(3,2)
    assert F(s['win_rate'])==50 and F(s['average_win'])==F(15,2) and F(s['average_loss'])==10
    assert F(s['maximum_drawdown_pct'])*TICKS==nearest_ticks(F(10,10010)*100)
    assert F(s['equity'])==10005 and F(s['return_pct'])==F(1,20)


def test_independent_indicator_reference_values():
    from app.indicators import ema,rsi,atr
    from app.models import Candle
    assert ema([10,12,14,16,18],3)==[None,None,12,14,16]
    values=rsi([10,12,11,13,12],2)
    assert values[:2]==[None,None]
    assert values[2:]==pytest.approx([float(F(200,3)),float(F(600,7)),float(F(600,11))])
    bars=[Candle(0,10,11,9,10,1),Candle(60,12,13,11,12,1),Candle(120,11,12,10,11,1)]
    assert atr(bars,2)==[None,2.5,2.25]
