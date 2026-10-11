import httpx
import lzma
from fastapi.testclient import TestClient
import pytest
import time

from app.main import app, cache, locks, PROVIDERS
from app.models import Candle
from app.gold import CandleBatch


@pytest.fixture
def client():
    cache.clear()
    locks.clear()
    with TestClient(app) as test_client:
        yield test_client


def test_page_health_and_asset(client):
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.get('/static/app.js').status_code == 200


@pytest.mark.parametrize('query', ['symbol=ETHUSDT', 'timeframe=4h', 'limit=100', 'limit=oops'])
def test_query_validation(client, query):
    assert client.get('/api/market?' + query).status_code == 422


@pytest.mark.parametrize('symbol', ['BTCUSDT', 'XAUUSD'])
@pytest.mark.parametrize('timeframe', ['1m','5m','15m','1h'])
@pytest.mark.parametrize('limit', [500,2000])
def test_market_contract(client, monkeypatch, symbol, timeframe, limit):
    async def fetch(*args):
        from app.models import INTERVALS
        step = INTERVALS[timeframe]
        end = int(time.time()) // step * step - 4 * step
        return [Candle(end - (limit-i)*step, 100, 102, 99, 101, 10) for i in range(limit)]
    monkeypatch.setattr(PROVIDERS[symbol], 'fetch', fetch)
    response = client.get(f'/api/market?symbol={symbol}&timeframe={timeframe}&limit={limit}')
    assert response.status_code == 200
    data = response.json()
    assert len(data['candles']) == data['analysis']['count'] == limit
    assert data['stale']
    assert data['analysis']['signal_up'] + data['analysis']['signal_down'] == 100


def test_upstream_failure_and_recovery(client, monkeypatch):
    async def fail(*args):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(PROVIDERS['BTCUSDT'], 'fetch', fail)
    assert client.get('/api/market').status_code == 503
    assert not cache
    async def recover(*args):
        return [Candle(i * 60, 100, 102, 99, 101, 10) for i in range(500)]
    monkeypatch.setattr(PROVIDERS['BTCUSDT'], 'fetch', recover)
    assert client.get('/api/market').status_code == 200


def test_partial_history_is_not_silently_accepted(client, monkeypatch):
    async def partial(*args):
        return [Candle(i * 60, 100, 102, 99, 101, 10) for i in range(50)]
    monkeypatch.setattr(PROVIDERS['BTCUSDT'], 'fetch', partial)
    assert client.get('/api/market').status_code == 503


def test_corrupt_archive_returns_readable_error(client, monkeypatch):
    async def corrupt(*args):
        raise lzma.LZMAError('bad archive')
    monkeypatch.setattr(PROVIDERS['XAUUSD'], 'fetch', corrupt)
    response = client.get('/api/market?symbol=XAUUSD')
    assert response.status_code == 503
    assert 'Dukascopy' in response.json()['detail']


def test_fallback_source_preserved_in_api_and_cache(client, monkeypatch):
    async def fallback(*args):
        return CandleBatch([Candle(i*60,100,102,99,101,None) for i in range(500)],
                           'TradingView · OANDA:XAUUSD','Actual fallback note',True,'HTTP 429')
    monkeypatch.setattr(PROVIDERS['XAUUSD'],'fetch',fallback)
    first = client.get('/api/market?symbol=XAUUSD').json()
    assert first['source'] == 'TradingView · OANDA:XAUUSD'
    assert first['fallback'] and first['fallback_reason'] == 'HTTP 429'
    assert first['candles'][0]['volume'] is None
    assert client.get('/api/market?symbol=XAUUSD').json() == first
