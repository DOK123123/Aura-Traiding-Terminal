"""Disabled deployments fail closed and require owner/CSRF on every write."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.manual_paper.api import router


def test_disabled_contract(monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-password-for-testing')
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        r=client.get('/api/manual-paper/capabilities')
        assert r.status_code==200 and r.json()['balance'] is None
        assert r.json()['manual_orders_enabled'] is False
        body=dict(request_id='a'*32,side='LONG',quantity='0.01',stop='79500',target='81000')
        assert client.post('/api/manual-paper/orders',json=body).status_code==401
        assert client.post('/api/manual-paper/orders',json=body,auth=('aura','dummy-password-for-testing')).status_code==403
        r=client.post('/api/manual-paper/orders',json=body,auth=('aura','dummy-password-for-testing'),headers={'X-Aura-Paper':'local-only'})
        assert r.status_code==503 and r.json()['code']=='MANUAL_PAPER_DISABLED'
        assert client.get('/api/manual-paper/quote').status_code==401
