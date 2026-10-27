"""Independent known answers and causal execution checks. No production clients."""
from dataclasses import replace
from decimal import Decimal as D, ROUND_CEILING
import pytest
from app.lab.execution import fee,fill,metrics
from research.manual_analyst_replay.config import Config
from research.manual_analyst_replay.dataset import Bar
from research.manual_analyst_replay.adapter import Signal
from research.manual_analyst_replay.execution import execute

T=1790812800


def bar(t=T,open='100',high='101',low='99',close='100',volume='10'):
    return Bar(t,*map(D,(open,high,low,close,volume)),t+62)


def signal(side='LONG',ident='a',at=T-58,until=T+2):
    return Signal(ident*64,T-60,at,until,side,D(99),D(101),D(95 if side=='LONG' else 105),D(115 if side=='LONG' else 85))


def cfg(**kw):
    return replace(Config(),**{'tick':'0.0001','lot':'0.0001',**kw})


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_legacy_helpers_match_independent_decimal_reference(side):
    # Separate algebra; no use of replay helpers to build expectations.
    sign=1 if side=='LONG' else -1
    for raw in (D('100'),D('95.1'),D('120.22')):
        expected=raw*(1+sign*D('.0005'))
        assert fill(raw,side,True,D('.0005'))==expected
        q=D('.1234');expected_fee=(expected*q*D('.001')).quantize(D('.00000001'),rounding=ROUND_CEILING)
        assert fee(expected,q,D('.001'))==expected_fee


@pytest.mark.parametrize('side,mode',[('LONG','TP'),('SHORT','TP'),('LONG','SL'),('SHORT','SL'),('LONG','BOTH'),('SHORT','BOTH')])
def test_long_short_protection_fees_and_balance_known_answer(side,mode):
    bars=[bar(),bar(T+60,high='116' if mode!='SL' else '101',low='84' if mode!='TP' else '99')]
    # SHORT SL requires the high; SHORT TP requires the low.
    if side=='SHORT':bars[1]=bar(T+60,high='116' if mode!='TP' else '101',low='84' if mode!='SL' else '99')
    r=execute(bars,60,[signal(side)],cfg())
    assert len(r['trades'])==1
    p=r['trades'][0];q=D(p['size']);sign=1 if side=='LONG' else -1
    expected_entry=D(100)*(1+sign*D('.0006'))
    raw=D(95 if side=='LONG' else 105) if mode!='TP' else D(115 if side=='LONG' else 85)
    expected_exit=raw*(1-sign*D('.0006'))
    ef=(expected_entry*q*D('.001')).quantize(D('.00000001'),rounding=ROUND_CEILING)
    xf=(expected_exit*q*D('.001')).quantize(D('.00000001'),rounding=ROUND_CEILING)
    expected_gross=(sign*(expected_exit-expected_entry)*q).quantize(D('.00000001'))
    assert D(p['entry_price'])==expected_entry and D(p['exit_price'])==expected_exit
    assert D(p['fees'])==ef+xf
    assert D(p['realized_pnl'])==expected_gross-ef-xf
    assert D(r['metrics']['final_balance'])==10000+D(p['realized_pnl'])
    assert D(p['risk_usdt'])<=50 and D(p['notional'])<=2000
    assert p['exit_reason']==('TAKE_PROFIT' if mode=='TP' else 'STOP_LOSS_AMBIGUOUS' if mode=='BOTH' else 'STOP_LOSS')


def test_adverse_gap_fills_worse_than_stop_and_favorable_gap_capped_at_target():
    for side,gap in [('LONG','80'),('SHORT','120')]:
        b=bar(T+60,open=gap,high=str(D(gap)+1),low=str(D(gap)-1),close=gap)
        r=execute([bar(),b],60,[signal(side)],cfg());p=r['trades'][0]
        assert p['exit_reason']=='STOP_GAP' and p['exit_raw_price']==gap
        assert D(p['realized_pnl'])< -D(p['risk_usdt'])
    r=execute([bar(),bar(T+60,open='125',high='126',low='124',close='125')],60,[signal()],cfg())
    assert r['trades'][0]['exit_raw_price']=='115'


def test_latency_expiry_zone_volume_one_position_and_dedup():
    r=execute([bar(),bar(T+60) ],60,[signal(),signal()],cfg())
    assert r['duplicate_signals_ignored']==1 and len(r['trades'])==1
    p=replace(signal(),id='b'*64,available_at=T+2,valid_until=T+62)
    r=execute([bar(),bar(T+60),bar(T+120)],60,[signal(),p],cfg())
    assert len(r['trades'])==1 and r['rejections']['POSITION_LIMIT']==1
    assert execute([bar()],60,[replace(signal(),valid_until=T)],cfg())['rejections']=={'SCENARIO_EXPIRED':1}
    assert execute([bar(volume='0')],60,[signal()],cfg())['rejections']=={'ZERO_VOLUME':1}
    assert not execute([bar(open='110',high='111',low='109',close='110')],60,[signal()],cfg())['trades']
    r=execute([bar()],60,[replace(signal(),available_at=T-1)],cfg())
    assert r['rejections']=={'NO_NEXT_EXECUTION_BAR':1}


def test_no_signal_or_unaffordable_lot_never_opens_and_no_fills_on_zero_volume():
    assert not execute([bar()],60,[],cfg())['trades']
    r=execute([bar()],60,[signal()],cfg(lot='1000',min_quantity='1000'))
    assert not r['trades'] and 'INSUFFICIENT_MARGIN_OR_MIN_QUANTITY' in r['rejections']
    r=execute([bar(),bar(T+60,high='120',low='80',volume='0'),bar(T+120)],60,[signal()],cfg(),close_at_end=False)
    assert not r['trades'] and r['open_position'] is not None


def test_prefix_causality_and_restart_rerun_no_hidden_state():
    data=[bar(T+i*60) for i in range(5)];s=signal()
    prefix=execute(data[:3],60,[s],cfg(),close_at_end=False)
    full=execute(data,60,[s],cfg(),close_at_end=False)
    assert full['equity_curve'][:len(prefix['equity_curve'])]==prefix['equity_curve']
    assert execute(data,60,[s],cfg(),close_at_end=False)==full
    assert prefix['open_position']==full['open_position']


def test_guard_halts_after_loss_without_reading_future_close():
    # Small explicit test guard; strategy parameters remain fixed.
    g=cfg(daily_loss_pct='0.01',drawdown_pct='0.02')
    s2=replace(signal(),id='b'*64,available_at=T+62,candle_close=T+60,valid_until=T+122)
    r=execute([bar(),bar(T+60,open='80',high='81',low='79',close='80'),bar(T+120)],60,[signal(),s2],g)
    assert len(r['trades'])==1 and r['drawdown_halted']
    assert r['rejections'].get('DRAWDOWN_HALT')==1
    # Different future intrabar range cannot influence the OPEN preceding it.
    a=execute([bar()],60,[signal()],cfg(),close_at_end=False)
    b=execute([bar(high='150',low='50')],60,[signal()],cfg(),close_at_end=False)
    assert [e for e in a['events'] if e['event']=='OPEN']==[e for e in b['events'] if e['event']=='OPEN']


def test_config_caps_and_signal_collision():
    for c in [replace(Config(),risk_pct='0.6'),replace(Config(),daily_loss_pct='3'),replace(Config(),drawdown_pct='11'),replace(Config(),max_notional='2001')]:
        with pytest.raises(ValueError):c.validate()
    with pytest.raises(ValueError,match='SIGNAL_ID_COLLISION'):
        execute([bar()],60,[signal(),replace(signal(),high=D(102))],cfg())

def test_full_legacy_simulator_is_not_a_drop_in_for_absolute_levels():
    from types import SimpleNamespace
    from app.lab.execution import simulate
    from app.lab.models import Baseline
    from app.lab.strategies import Decision
    oldbars=[SimpleNamespace(time=T+i*60,open=D(p),high=D(p)+1,low=D(p)-1,close=D(p),volume=D(10)) for i,p in enumerate(['100','110','110'])]
    old=simulate(oldbars,[Decision('LONG',D(5),D(10)),Decision(),Decision()],0,3,60,Baseline(risk_pct='0.5',slippage_bps='0',fee_bps='0'))
    assert old['trades'][0]['stop_loss']=='105'  # Re-anchored from next open.
    s=replace(signal(),low=D(109),high=D(111),stop=D(95),target=D(140))
    new=execute([bar(open='110',high='111',low='109',close='110')],60,[s],cfg())
    assert new['trades'][0]['stop_loss']=='95'  # Immutable analyst level.

def test_five_minute_open_cannot_silently_extend_analyst_ttl():
    s=replace(signal(),candle_close=T,available_at=T+2,valid_until=T+62)
    minute=execute([bar(),bar(T+60)],60,[s],cfg())
    coarse=execute([replace(bar(),available_at=T+302),replace(bar(T+300),available_at=T+602)],300,[s],cfg())
    assert len(minute['trades'])==1
    assert coarse['rejections']=={'SCENARIO_EXPIRED':1} and not coarse['trades']

def test_slippage_cannot_manufacture_an_entry_zone_touch():
    # The paid fill would be 100.0600 in the zone, but raw market 100 is below it.
    s=replace(signal(),low=D('100.03'),high=D('101'),stop=D('100.02'))
    r=execute([bar()],60,[s],cfg())
    assert not r['trades'] and r['rejections']=={'ENTRY_OUTSIDE_ZONE':1}


def test_metrics_match_independent_known_trade_totals_and_drawdown():
    trades=[dict(realized_pnl=x,fees='0',slippage_usdt='0') for x in ('10','-5','0')]
    curve=[dict(time=T+i*86400,balance=str(v),equity=str(v)) for i,v in enumerate((10000,10010,10005))]
    r=metrics(trades,curve,Config())
    assert D(r['net_profit'])==5 and D(r['profit_factor'])==2
    assert D(r['expectancy'])==D('1.66666667') and D(r['win_rate'])==D('33.33333333')
    assert D(r['max_drawdown_pct'])==(D(5)/10010*100).quantize(D('.00000001'))

def test_boundary_close_peak_is_not_lost_from_drawdown_money():
    data=[bar(),bar(T+60,open='101',high='104',low='100',close='104'),bar(T+120,open='90',high='91',low='89',close='90')]
    r=execute(data,60,[signal()],cfg())
    eq=[D(p['equity']) for p in r['equity_curve']];peak=eq[0];dd=D(0)
    for value in eq:peak=max(peak,value);dd=max(dd,peak-value)
    assert D(r['metrics']['max_drawdown_usdt'])==dd.quantize(D('.00000001'))
    assert r['trades'][0]['exit_reason']=='STOP_GAP'
