"""Offline tests of closed-candle quote guards."""
from copy import deepcopy
import pytest
from app.manual_paper.quotes import verified_close, QuoteRejected

NOW=1793007900
def snapshot():
    end=(NOW//900)*900
    return {"symbol":"BTCUSDT","source":"Bitget USDT-M Futures","timeframe":900,
            "candles":[{"time":end-1800,"open":"80000","high":"80100","low":"79900","close":"80050","volume":"20"},
                       {"time":end-900,"open":"80050","high":"80200","low":"80000","close":"80100","volume":"21"}]}

def test_matching_closed_history():
    a=snapshot()
    assert verified_close(a,deepcopy(a),now=NOW)["price"]==80100

@pytest.mark.parametrize("field,value", [
    ("close","80101"),("volume","22"),("high","80201")
])
def test_changed_history_fails(field,value):
    a=snapshot(); b=deepcopy(a);b["candles"][-1][field]=value
    with pytest.raises(QuoteRejected,match="HISTORY_CANDLE_CHANGED"):
        verified_close(a,b,now=NOW)

def test_stale_fails():
    a=snapshot()
    with pytest.raises(QuoteRejected,match="STALE_CANDLE"):
        verified_close(a,a,now=NOW+901)

def test_source_mismatch_fails():
    a=snapshot();a["source"]="Binance Spot"
    with pytest.raises(QuoteRejected,match="SOURCE_MISMATCH"):
        verified_close(a,a,now=NOW)

def test_gap_fails():
    a=snapshot();a["candles"][0]["time"]-=900
    with pytest.raises(QuoteRejected,match="HISTORY_GAP_OR_DUPLICATE"):
        verified_close(a,a,now=NOW)

def test_invalid_ohlc_fails():
    a=snapshot();a["candles"][-1]["low"]="90000"
    with pytest.raises(QuoteRejected,match="INVALID_CANDLE"):
        verified_close(a,a,now=NOW)
