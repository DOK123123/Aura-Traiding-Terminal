from copy import deepcopy
from dataclasses import replace
from math import nan
from unittest.mock import patch
import asyncio
import pytest
from app.models import Candle
from app.aura_trader5_scenarios import STEPS,assess,frame_analysis
from app.aura_trader5_analysis import ema,rsi,atr,risk_plan,Candle as HLC

NOW=1800000150


def windows(side='LONG'):
    data={}
    for tf,step in STEPS.items():
        end=NOW//step*step
        closes=[12000+i*15 for i in range(200)]
        if tf=='15m':closes=[12000+i*7 for i in range(139)]+[13000+i*50 for i in range(61)]
        if tf=='5m':closes=[14550+i*.75+[-8,5,-4,8][i%4] for i in range(200)]
        bars=[Candle(end-(200-i)*step,c-4,c+30,c-30,c,100) for i,c in enumerate(closes)]
        if side=='SHORT':bars=[Candle(b.time,30000-b.open,30000-b.low,30000-b.high,30000-b.close,b.volume) for b in bars]
        data[tf]=bars
    return data


def test_constant_history_waits_without_scenario():
    data=windows()
    for tf in data:data[tf]=[replace(b,open=100,high=101,low=99,close=100) for b in data[tf]]
    r=assess(data,NOW)
    assert r['state']=='WAIT' and r['scenario'] is None


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_confirmed_manual_scenario_and_cost_adjusted_geometry(side):
    r=assess(windows(side),NOW)
    assert r['state']==side,r
    p=r['scenario'];assert p['net_rr']>=1.5
    if side=='LONG':assert p['stop_loss']<p['entry_zone']['low']<p['entry_zone']['high']<p['take_profit']
    else:assert p['take_profit']<p['entry_zone']['low']<p['entry_zone']['high']<p['stop_loss']
    assert r['read_only'] and r['manual_only'] and not r['exchange_execution']
    assert r['fibonacci']['high_at']<=r['frames']['15m']['last_closed_at']-1800


@pytest.mark.parametrize('damage',['future','gap','duplicate','stale','missing_volume'])
def test_closed_history_invariants_fail(damage):
    data=windows();bars=data['5m']
    if damage=='future':bars.append(replace(bars[-1],time=bars[-1].time+300))
    elif damage=='gap':bars.pop(5)
    elif damage=='duplicate':bars[5]=bars[4]
    elif damage=='stale':bars.pop()
    else:bars[2]=replace(bars[2],volume=None)
    with pytest.raises(ValueError):assess(data,NOW)


def test_prefix_result_is_unchanged_by_later_market_data_and_future_bar_is_rejected():
    data=windows();before=deepcopy(data);first=assess(data,NOW)
    later=deepcopy(data);later['5m'].append(replace(data['5m'][-1],time=NOW//300*300))
    assert assess(data,NOW)==first and data==before
    with pytest.raises(ValueError):assess(later,NOW)


@pytest.mark.parametrize('fn',[ema,rsi])
@pytest.mark.parametrize('period',[True,0,-1,1.5])
def test_indicator_periods_are_strict(fn,period):
    with pytest.raises(ValueError):fn([1,2,3],period)


def test_nonfinite_short_warmup_is_rejected():
    with pytest.raises(ValueError):ema([nan],20)
    with pytest.raises(ValueError):rsi([nan],14)
    with pytest.raises(ValueError):atr([HLC(-1,-3,-2)])


@pytest.mark.parametrize('side',['long','short'])
def test_fee_slippage_reference_calculation(side):
    entry,stop,target=(100,95,112) if side=='long' else (100,105,88)
    fee=.001;slip=.0005
    r=risk_plan(entry,stop,target,side,10000,.5,fee,slip)
    sign=1 if side=='long' else -1
    a=entry*(1+sign*slip);b=stop*(1-sign*slip);c=target*(1-sign*slip)
    unit_loss=sign*(a-b)+(a+b)*fee
    unit_reward=sign*(c-a)-(a+c)*fee
    assert r['estimated_quantity']==pytest.approx(50/unit_loss)
    assert r['estimated_rr_after_costs']==pytest.approx(unit_reward/unit_loss)


def test_ui_fixture_tracks_current_closed_scenario_contract():
    import json
    from pathlib import Path
    fixture=json.loads(Path('tests/fixtures/aura_analyst_synthetic.json').read_text())
    assert fixture['scope']=='SYNTHETIC_OFFLINE_UI_ONLY'
    assert fixture['LONG']==assess(windows('LONG'),NOW)
    assert fixture['SHORT']==assess(windows('SHORT'),NOW)


def test_future_4h_and_conflicting_context_cannot_make_a_directional_plan():
    data=windows();data['4h']=windows('SHORT')['4h']
    result=assess(data,NOW)
    assert result['state']=='WAIT' and result['reasons']==['CONFLICTING_4H_CONTEXT']
    original=windows();original['4h'].append(replace(original['4h'][-1],time=NOW//14400*14400))
    with pytest.raises(ValueError):assess(original,NOW)


def test_manual_levels_follow_the_public_contract_price_tick():
    from decimal import Decimal
    for side in ('LONG','SHORT'):
        result=assess(windows(side),NOW,price_tick=.1)
        assert result['state']==side
        p=result['scenario']
        for value in [p['entry_zone']['low'],p['entry_zone']['high'],p['stop_loss'],p['take_profit']]:
            assert Decimal(str(value))%Decimal('.1')==0
        assert p['net_rr']>=1.5
