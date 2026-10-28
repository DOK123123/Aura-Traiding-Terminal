"""Causality and reference execution checks for exploratory minute replay."""
from copy import deepcopy
from decimal import Decimal as D
import json
from pathlib import Path
import pytest
from app.models import Candle
from research.live_manual.replay import Book,Simulator

P=json.loads(Path('research/live_manual/protocol.json').read_text())

def test_partial_book_cannot_see_high_low_close_volume_of_uncompleted_minute():
    book=Book();first=Candle(1800000000,100,110,90,105,10)
    book.open(first)
    assert book.partial['5m']==Candle(first.time,100,100,100,100,0)
    book.finish(first)
    second=Candle(first.time+60,106,1000,1,900,9999)
    book.open(second)
    # Only the new minute's first observed price is known, not its future range.
    assert book.partial['5m']==Candle(first.time,100,110,90,106,10)
    assert book.closed['1m'][-1]==first
    prior=deepcopy(book.closed)
    book.finish(second)
    assert book.closed==prior

@pytest.mark.parametrize('side', ['LONG','SHORT'])
def test_model_latency_single_position_double_delivery_adverse_gap_and_reference_cash(side):
    sim=Simulator(P,1)
    long=side=='LONG';plan=dict(state=side,scenario=dict(entry_zone=dict(low=90,high=110),stop_loss=98 if long else 102,take_profit=104 if long else 96))
    sim.signal(plan,1800000001,'once');sim.signal(plan,1800000001,'once')
    sim.bar(Candle(1800000060,100,100.1,99.9,100,10))
    assert sim.position is None
    sim.bar(Candle(1800000120,100,100.1,99.9,100,10))
    assert sim.position is not None
    p=deepcopy(sim.position)
    sim.signal(plan,1800000121,'another');assert sim.pending is None
    gap=95 if long else 105
    sim.bar(Candle(1800000180,gap,gap+.1,gap-.1,gap,10))
    assert len(sim.trades)==1 and sim.trades[0]['reason']=='STOP_LOSS'
    e=D('100')*(D('1.0006') if long else D('.9994'));x=D(str(gap))*(D('.9994') if long else D('1.0006'));q=D(str(p['qty']))
    expected=(x-e)*q*(1 if long else -1)-(e+x)*q*D('.001')
    assert sim.cash==pytest.approx(float(D('10000')+expected),abs=1e-8)
    sim.signal(plan,1800000200,'once');assert sim.pending is None


def test_zero_volume_no_impossible_entry_and_ambiguous_sl_tp_uses_stop():
    sim=Simulator(P,1);plan=dict(state='LONG',scenario=dict(entry_zone=dict(low=90,high=110),stop_loss=98,take_profit=104))
    sim.signal(plan,1800000001,'x');sim.bar(Candle(1800000120,100,100,100,100,0))
    assert sim.position is None
    sim.signal(plan,1800000181,'y');sim.bar(Candle(1800000300,100,110,90,100,10))
    assert len(sim.trades)==1 and sim.trades[0]['reason']=='STOP_LOSS'
