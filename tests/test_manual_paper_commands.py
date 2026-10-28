"""End-to-end offline manual virtual trade accounting tests."""
import pytest
from app.manual_paper.commands import ManualCommands
from app.manual_paper.store import ManualStore

Q={"source":"Bitget USDT-M Futures","timeframe":900,"time":1793007000,"price":"80000"}
ID1="a"*32
ID2="b"*32

def test_open_close_persist_and_idempotency(tmp_path):
    store=ManualStore(str(tmp_path/"manual.sqlite"))
    svc=ManualCommands(store)
    opened=svc.open(ID1,"LONG","0.01","79500","81000",Q)
    assert opened["result"]["entry"]=="80000"
    assert svc.open(ID1,"LONG","0.01","79500","81000",Q)==opened
    state,version=store.load()
    assert version==1 and state.position is not None
    assert len(state.trades)==0
    with pytest.raises(ValueError,match="IDEMPOTENCY_CONFLICT"):
        svc.open(ID1,"SHORT","0.01","80500","79000",Q)
    assert store.load()[1]==1
    close_quote={**Q,"price":"81000","time":1793007900}
    closed=svc.close(ID2,close_quote)
    assert closed["result"]["net"]=="9.034000"
    assert svc.close(ID2,close_quote)==closed
    recovered,version=ManualStore(str(tmp_path/"manual.sqlite")).load()
    assert version==2 and recovered.position is None
    assert len(recovered.trades)==1

def test_rejected_trade_rolls_back(tmp_path):
    store=ManualStore(str(tmp_path/"manual.sqlite"))
    svc=ManualCommands(store)
    with pytest.raises(ValueError,match="RISK_LIMIT"):
        svc.open(ID1,"LONG","0.025","70000","81000",Q)
    assert store.load()==(None,0)
    svc.open(ID1,"LONG","0.01","79500","81000",Q)
    assert store.load()[1]==1

def test_source_rejected(tmp_path):
    svc=ManualCommands(ManualStore(str(tmp_path/"manual.sqlite")))
    with pytest.raises(ValueError,match="SOURCE_MISMATCH"):
        svc.open(ID1,"LONG","0.01","79500","81000",{**Q,"source":"Fake"})
