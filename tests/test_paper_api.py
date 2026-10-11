"""Offline FastAPI ownership/CSRF, gateway, monitor and safe failure tests."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock
import uuid

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.paper.market import Market
from app.paper.models import PaperError
from app.paper.service import Service
from tests.test_paper_engine import ledger,window,payload

PASSWORD='dummy-paper-owner-password'
HEADERS={'X-Aura-Paper':'local-only','Origin':'http://testserver','Sec-Fetch-Site':'same-origin'}


def raw(clock):
    win=window(clock)
    return dict(symbol=win.symbol,timeframe=win.timeframe,source=win.source,stale=False,
                fetched_at=datetime.fromtimestamp(clock[0]/1000,timezone.utc).isoformat(),last_closed_at=win.bars[-1].time+60,
                candles=[dict(time=b.time,open=float(b.open),high=float(b.high),low=float(b.low),close=float(b.close),volume=10.0) for b in win.bars])


@pytest.fixture
def client(monkeypatch,ledger):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',PASSWORD)
    for name in ('BINANCE_TESTNET_API_KEY','BINANCE_TESTNET_API_SECRET','BYBIT_DEMO_API_KEY','BYBIT_DEMO_API_SECRET'):
        monkeypatch.delenv(name,raising=False)
    with TestClient(app) as client:
        engine,clock=ledger
        app.state.paper.engine=engine
        app.state.paper.market=Market(AsyncMock(return_value=raw(clock)),lambda:clock[0])
        yield client,engine,clock


def test_owner_required_even_when_exchange_not_configured(client):
    c,_,_=client
    assert c.get('/api/paper/state').status_code==401
    assert c.get('/api/paper/export').status_code==401
    assert c.get('/api/paper/state',auth=('aura','incorrect-dummy')).status_code==401
    assert c.get('/api/bybit-demo/account').json()['status']=='Not configured'
    assert c.get('/api/health').json()=={'status':'ok'}
    assert 'PAPER TRADING' in c.get('/').text


def test_missing_owner_password_does_not_affect_markets(client,monkeypatch):
    c,_,_=client;monkeypatch.delenv('AURA_TESTNET_VIEW_PASSWORD')
    assert c.get('/api/paper/state').status_code==403
    assert c.get('/api/health').status_code==200


def test_quote_open_close_state_backup(client):
    c,engine,clock=client;auth=('aura',PASSWORD)
    quote=c.get('/api/paper/quote?timeframe=1m',auth=auth)
    assert quote.status_code==200 and quote.json()['automatic_signal_execution'] is False
    body=payload(window(clock))
    response=c.post('/api/paper/positions/open',auth=auth,headers=HEADERS,json=body)
    assert response.status_code==200
    trade=response.json();assert trade['signal_source']=='MANUAL'
    assert c.post('/api/paper/positions/open',auth=auth,headers=HEADERS,json=body).json()['id']==trade['id']
    close=dict(request_id=str(uuid.uuid4()),exit_reason='Offline owner')
    assert c.post('/api/paper/positions/'+trade['id']+'/close',auth=auth,headers=HEADERS,json=close).status_code==200
    state=c.get('/api/paper/state',auth=auth)
    assert state.headers['cache-control']=='no-store'
    assert state.json()['statistics']['total_trades']==1
    backup=c.get('/api/paper/export',auth=auth)
    assert backup.content.startswith(b'SQLite format 3\x00')


@pytest.mark.parametrize('headers',[{}, {'X-Aura-Paper':'bad'},
 {'X-Aura-Paper':'local-only','Origin':'https://attacker.example'},
 {'X-Aura-Paper':'local-only','Sec-Fetch-Site':'cross-site'},
 {'X-Aura-Paper':'local-only','Origin':'http://testserver@attacker.example'},
 {'X-Aura-Paper':'local-only','Origin':'null'},
 {'X-Aura-Paper':'local-only','Origin':'http://testserver/path'}])
def test_csrf_rejected(client,headers):
    c,_,clock=client
    response=c.post('/api/paper/positions/open',auth=('aura',PASSWORD),headers=headers,json=payload(window(clock)))
    assert response.status_code==403


@pytest.mark.parametrize('change',[{'expected_price':100.0},{'automatic_execution':True},{'symbol':'XAUUSD'},
 {'direction':'BUY'},{'exchange_url':'https://api.bybit.com'},{'position_size':True},{'expected_candle_time':True}])
def test_strict_dtos(client,change):
    c,_,clock=client;body=payload(window(clock));body.update(change)
    assert c.post('/api/paper/positions/open',auth=('aura',PASSWORD),headers=HEADERS,json=body).status_code==422


def test_invalid_decimal_and_no_secret_in_error(client):
    c,_,clock=client;body=payload(window(clock));body['position_size']='dummy-sensitive-invalid-value'
    response=c.post('/api/paper/positions/open',auth=('aura',PASSWORD),headers=HEADERS,json=body)
    assert response.status_code==409
    assert 'dummy-sensitive-invalid-value' not in response.text and PASSWORD not in response.text
    assert response.json()['code']=='INVALID_DATA'


def test_success_replay_does_not_need_market(client):
    c,engine,clock=client;body=payload(window(clock));auth=('aura',PASSWORD)
    first=c.post('/api/paper/positions/open',auth=auth,headers=HEADERS,json=body).json()
    app.state.paper.market.fetch=AsyncMock(side_effect=RuntimeError('dummy-sensitive-exception'))
    second=c.post('/api/paper/positions/open',auth=auth,headers=HEADERS,json=body)
    assert second.status_code==200 and second.json()['id']==first['id']
    assert not app.state.paper.market.fetch.called


@pytest.mark.parametrize('field,value,code',[
 ('symbol','XAUUSD','INVALID_MARKET_DATA'),('stale',True,'STALE_DATA'),('stale',None,'STALE_DATA'),
 ('fetched_at','bad','INVALID_MARKET_DATA'),('fetched_at','2020-01-01T00:00:00+00:00','STALE_DATA'),
 ('last_closed_at',1,'INVALID_MARKET_DATA'),('candles',[], 'INVALID_MARKET_DATA'),('source','', 'INVALID_MARKET_DATA')])
def test_gateway_rejects_invalid_snapshot(ledger,field,value,code):
    _,clock=ledger;data=raw(clock);data[field]=value
    async def run():
        market=Market(AsyncMock(return_value=data),lambda:clock[0])
        with pytest.raises(PaperError,match=code):await market.window('BTCUSDT','1m')
    asyncio.run(run())


@pytest.mark.parametrize('field,value',[('volume',-1),('volume',float('nan')),('close',float('inf')),('time',True),('low',110)])
def test_gateway_bad_ohlcv(ledger,field,value):
    _,clock=ledger;data=raw(clock);data['candles'][0][field]=value
    async def run():
        with pytest.raises(PaperError,match='INVALID_MARKET_DATA'):
            await Market(AsyncMock(return_value=data),lambda:clock[0]).window('BTCUSDT','1m')
    asyncio.run(run())


@pytest.mark.parametrize('exception,code',[(TimeoutError('dummy-sensitive-url'),'MARKET_TIMEOUT'),(RuntimeError('dummy-sensitive-url'),'MARKET_UNAVAILABLE')])
def test_gateway_failures_no_leak(ledger,exception,code,caplog):
    _,clock=ledger
    async def run():
        with pytest.raises(PaperError,match=code) as error:
            await Market(AsyncMock(side_effect=exception),lambda:clock[0]).window('BTCUSDT','1m')
        assert 'dummy-sensitive-url' not in str(error.value)
    asyncio.run(run());assert 'dummy-sensitive-url' not in caplog.text


def test_monitor_idle_no_network_and_failed_data_pauses_equity(ledger):
    engine,clock=ledger;fetch=AsyncMock(return_value=raw(clock));service=Service(Market(fetch,lambda:clock[0]),engine)
    async def run():
        await service.refresh();fetch.assert_not_called()
        win=window(clock);engine.open(payload(win),win)
        fetch.side_effect=RuntimeError('dummy-sensitive-exception')
        state=await service.refresh()
        assert state['statistics']['equity'] is None
        assert state['open_positions'][0]['data_status']=='MARKET_UNAVAILABLE'
        fetch.side_effect=None
        state=await service.refresh();assert state['statistics']['equity'] is not None
    asyncio.run(run())


def test_storage_failed_lifespan_does_not_break_health(monkeypatch,tmp_path):
    monkeypatch.setenv('PAPER_DB_PATH',str(tmp_path/'corrupt.sqlite3'))
    (tmp_path/'corrupt.sqlite3').write_text('not a SQLite database')
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',PASSWORD)
    with TestClient(app) as c:
        assert c.get('/api/health').status_code==200
        response=c.get('/api/paper/state',auth=('aura',PASSWORD))
        assert response.status_code==503 and response.json()['code']=='STORAGE_UNAVAILABLE'
        assert str(tmp_path) not in response.text


def test_no_exchange_order_routes_added():
    routes=app.openapi()['paths']
    assert not any('order' in path and set(methods)-{'get','head'} for path,methods in routes.items())
    allowed={'/api/paper/positions/open','/api/paper/positions/{trade_id}/close','/api/paper/settings','/api/paper/refresh'}
    assert {path for path,methods in routes.items() if 'post' in methods and path.startswith('/api/paper/')}==allowed
