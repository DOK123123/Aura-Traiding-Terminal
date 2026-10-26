"""The manual-paper scaffold must fail closed, including POST routes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.manual_paper.api import router
from app.manual_paper.core import ManualPaper
import pytest

app=FastAPI()
app.include_router(router)
client=TestClient(app)

def test_capabilities_are_honest():
    r=client.get("/api/manual-paper/capabilities")
    assert r.status_code==200
    body=r.json()
    assert body["virtual_only"] is True
    assert body["ready"] is False
    assert body["manual_orders_enabled"] is False
    assert body["balance"] is None

def test_orders_are_blocked():
    assert client.post("/api/manual-paper/orders",json={
        "side":"LONG","quantity":"0.01","entry":"80000"
    }).status_code==503
    assert client.post("/api/manual-paper/positions/test/close").status_code==503

def test_invalid_candle_time_does_not_debit_balance():
    ledger=ManualPaper()
    with pytest.raises(ValueError,match="INVALID_CANDLE_TIME"):
        ledger.open("LONG","80000","79500","81000","0.01",candle_time=-1)
    assert ledger.balance==ledger.starting_balance
    assert ledger.position is None


def test_quote_requires_owner_auth(monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','long_test_password_123')
    response=client.get('/api/manual-paper/quote')
    assert response.status_code==401


def test_quote_is_read_only_even_when_owner_logged_in(monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','long_test_password_123')
    response=client.get('/api/manual-paper/quote',auth=('aura','long_test_password_123'))
    assert response.status_code==503  # No market client in isolated test app
    assert client.post('/api/manual-paper/orders',auth=('aura','long_test_password_123')).status_code==503
