from dataclasses import replace
import pytest
from app.models import Candle
from app.aura_trader5_technical import macd, ema_series, confirmed_swings, technical_context
from app.aura_trader5_scenarios import assess
from tests.test_aura_trader5_scenarios import windows, NOW


def bars(values):
    return [Candle(300*(i+1),v,v+1,v-1,v,100) for i,v in enumerate(values)]


def test_macd_linear_ramp_independent_analytic_value():
    # For a linear ramp SMA-seeded EMA_n(i) = i - (n-1)/2.
    # EMA12-EMA26=7, signal9=7 and histogram=0, not 7/9.
    result=macd(list(range(1,101)))
    assert result==dict(line=7.0,signal=7.0,histogram=0.0,bias='NEUTRAL')
    assert macd([100.]*100)==dict(line=0.,signal=0.,histogram=0.,bias='NEUTRAL')
    assert macd([100.]*33)['bias']=='UNAVAILABLE'
    assert ema_series([1,2,3,4,5],3)==[None,None,2.,3.,4.]


def test_macd_matches_independent_decimal_reference_on_nontrivial_series():
    from decimal import Decimal as D
    values=[100+i*.2+(i%7-3)*2 for i in range(100)]
    def reference(v,n):
        r=[None]*(n-1);a=sum(v[:n])/n;r.append(a)
        for x in v[n:]:a+=(x-a)*D(2)/D(n+1);r.append(a)
        return r
    ds=list(map(lambda n:D(str(n)),values))
    fast=reference(ds,12);slow=reference(ds,26)
    line=[a-b for a,b in zip(fast,slow) if a is not None and b is not None]
    expected=reference(line,9)[-1];result=macd(values)
    assert result['signal']==pytest.approx(float(expected))
    assert result['histogram']==pytest.approx(float(line[-1]-expected))


def test_pivot_is_visible_only_after_two_right_candles_close_and_no_repaint():
    data=bars([100,102,109,103,101,100,99])
    assert not any(p['time']==900 for p in confirmed_swings(data[:4],300))
    pivot=next(p for p in confirmed_swings(data[:5],300) if p['time']==900)
    assert pivot==dict(kind='HIGH',price=110,time=900,index=2,confirmed_at=1800)
    assert pivot in confirmed_swings(data,300)
    flat=bars([100]*20);assert confirmed_swings(flat,300)==[]


@pytest.mark.parametrize('kind',['LONG','SHORT'])
def test_confirmed_rsi_divergence_uses_past_pivots_and_delayed_confirmation(kind):
    # First selloff is abrupt; second lower low follows a slower drift => higher RSI.
    values=[100.]*18+[98,94,88,94,99,101,100,99,98,97,96,95,94,93,92,90,89,87,90,93]
    if kind=='SHORT':values=[200-v for v in values]
    data=bars(values)
    context=technical_context(data,300)
    d=next(d for d in context['rsi_divergences'] if d['side']==kind)
    assert d['second_at']==data[-3].time
    assert d['confirmed_at']==data[-1].time+300
    assert not technical_context(data[:-1],300)['rsi_divergences']
    # Changing inaccessible future bars cannot change a calculation on this prefix.
    assert technical_context((data+bars([1000]*10))[:len(data)],300)==context


def test_volume_baseline_excludes_current_bar_and_zero_volume_does_not_create_a_direction():
    data=bars([100.]*40);data[-1]=replace(data[-1],volume=1000)
    result=technical_context(data,300)
    assert result['volume']==dict(last=1000,previous20_mean=100,ratio=10,directional=False)
    zero=[replace(b,volume=0) for b in data]
    assert technical_context(zero,300)['volume']['ratio'] is None


def test_enrichment_keeps_stage_one_direction_and_cannot_control_execution():
    for side in ('LONG','SHORT'):
        result=assess(windows(side),NOW)
        assert result['state']==side
        assert result['evidence']['context_only']
        assert result['evidence']['invalidation']['stop_loss']==result['scenario']['stop_loss']
        assert not result['exchange_execution']
        for tf,frame in result['frames'].items():
            assert all(p['confirmed_at']<=frame['last_closed_at'] for p in frame['technical']['swings'])
    # Bad/future windows still fail before any extra context can be emitted.
    data=windows();data['5m'].append(replace(data['5m'][-1],time=NOW//300*300))
    with pytest.raises(ValueError):assess(data,NOW)
