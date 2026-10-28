"""Additional integration risk gates for manual-only live inputs. Offline SQLite."""
import asyncio
from decimal import Decimal as D
from unittest.mock import AsyncMock
import pytest
from app.manual_paper.core import ManualPaper
from app.manual_paper.commands import ManualCommands
from app.manual_paper.store import ManualStore
from app.manual_paper.service import Service

STAMP=1800000000000

def q(bid='80000',ask='80001',at=STAMP):
    return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',time=at,
                bid=D(bid),ask=D(ask),price=D(bid),bid_size=D('1'),ask_size=D('1'))

@pytest.mark.parametrize('side,stop,target,exitbid,exitask',[
    ('LONG','79500','81000','81000','81001'),('SHORT','80500','79000','78999','79000')])
def test_independent_bid_ask_slippage_fees_restart(side,stop,target,exitbid,exitask,tmp_path):
    svc=Service(ManualStore(tmp_path/'manual-paper.sqlite3'),clock=lambda:STAMP/1000)
    svc.quote=AsyncMock(return_value=q());body=dict(request_id='a'*32,side=side,quantity='.01',stop=stop,target=target)
    opened=asyncio.run(svc.open(body));p=svc.store.load()[0].position
    entry=D('80001' if side=='LONG' else '80000')*(D('1.0005') if side=='LONG' else D('.9995'))
    assert p.entry==entry
    restored=Service(ManualStore(svc.store.path),clock=lambda:STAMP/1000+1)
    restored.quote=AsyncMock(return_value=q(exitbid,exitask,STAMP+1000))
    receipt=asyncio.run(restored.close_position('a'*32,'b'*32))
    exit=D(exitbid if side=='LONG' else exitask)*(D('.9995') if side=='LONG' else D('1.0005'))
    net=(exit-entry)*D('.01')*(1 if side=='LONG' else -1)-(entry+exit)*D('.01')*D('.0006')
    assert D(receipt['balance'])==D('10000')+net
    assert D(receipt['result']['net'])==net
    assert asyncio.run(restored.open(body))==opened
    assert asyncio.run(restored.close_position('a'*32,'b'*32))==receipt
    assert len(restored.store.load()[0].trades)==1


def test_daily_loss_budget_is_reconstructed_on_restart_and_does_not_reset_balance(tmp_path):
    store=ManualStore(tmp_path/'manual-paper.sqlite3');ledger=ManualPaper()
    # Four known adverse fills, each within per-entry .5% but cumulative >2%.
    # Gap loss is not clipped to planned risk. Daily guard must then block.
    ledger.open('LONG','80000','79500','81000','.02',candle_time=STAMP,position_id='a'*32)
    ledger.close('69000',closed_at=STAMP+1)
    store.save(ledger,0);restored,_=ManualStore(store.path).load()
    assert restored.balance<D('9800')
    with pytest.raises(ValueError,match='DAILY_LOSS_LIMIT'):
        restored.open('LONG','80000','79500','81000','.01',candle_time=STAMP+1000)
    # Next UTC day the guard uses the new opening balance, not a deposit reset.
    restored.open('LONG','80000','79500','81000','.01',candle_time=STAMP+86400000)
    assert restored.balance<D('9800')


def test_fee_and_adverse_stop_fill_both_consume_risk_budget():
    ledger=ManualPaper()
    # Raw SL distance 49 USDT is inside 50, but fills and fees exceed it.
    with pytest.raises(ValueError,match='RISK_LIMIT'):
        ledger.open('LONG','80000','78040','81000','.025',exit_slippage='.0005')
    assert ledger.position is None and ledger.balance==D('10000')


def test_live_analyst_has_no_authority_to_open(tmp_path):
    svc=Service(ManualStore(tmp_path/'manual-paper.sqlite3'),clock=lambda:STAMP/1000)
    svc.quote=AsyncMock(return_value=q())
    for _ in range(3):asyncio.run(svc.protect())
    assert svc.store.load()==(None,0)
    svc.quote.assert_not_called()

@pytest.mark.parametrize('field,value',[('quantity','0.000001'),('quantity','0.00011'),('stop','79500.01'),('target','81000.03')])
def test_conservative_bitget_paper_size_and_price_steps(field,value,tmp_path):
    svc=Service(ManualStore(tmp_path/'manual-paper.sqlite3'),clock=lambda:STAMP/1000)
    svc.quote=AsyncMock(return_value=q())
    body=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000');body[field]=value
    with pytest.raises(ValueError,match='MINIMUM_SIZE_OR_PRECISION'):asyncio.run(svc.open(body))
    assert svc.store.load()==(None,0)


def test_manual_protection_failure_still_closes_all_isolated_services(monkeypatch):
    import app.main as main
    from fastapi import FastAPI
    events=[]
    class Public:
        async def close(self):events.append('analyst')
    class Auto:
        async def close(self):events.append('active43')
    class Manual:
        store=object()
        async def run_protection(self):raise ValueError('DUMMY_PROTECTION_FAILURE')
        async def close(self):events.append('manual')
    monkeypatch.setattr(main,'AnalystService',Public)
    monkeypatch.setattr(main,'configured_active43',lambda:Auto())
    monkeypatch.setattr(main,'configured_manual_paper',lambda client:Manual())
    async def exercise():
        async with main.lifespan(FastAPI()):await asyncio.sleep(0)
    with pytest.raises(ValueError,match='DUMMY_PROTECTION_FAILURE'):asyncio.run(exercise())
    assert events==['manual','analyst','active43']
