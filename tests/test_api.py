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


@pytest.mark.parametrize('symbol', ['BTCUSDT'])
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
        step = 900  # Default API timeframe is 15m, not 1m.
        end = int(time.time()) // step * step
        return [Candle(end - (500-i)*step, 100, 102, 99, 101, 10) for i in range(500)]
    monkeypatch.setattr(PROVIDERS['BTCUSDT'], 'fetch', recover)
    assert client.get('/api/market').status_code == 200


def test_partial_history_is_not_silently_accepted(client, monkeypatch):
    async def partial(*args):
        return [Candle(i * 60, 100, 102, 99, 101, 10) for i in range(50)]
    monkeypatch.setattr(PROVIDERS['BTCUSDT'], 'fetch', partial)
    assert client.get('/api/market').status_code == 503


def test_retired_gold_is_rejected_without_provider_request(client):
    assert 'XAUUSD' not in PROVIDERS
    assert client.get('/api/market?symbol=XAUUSD').status_code == 422


def test_bitget_source_preserved_in_api_and_cache(client, monkeypatch):
    from app.bitget_chart import SOURCE
    async def fetch(*args):
        step = 900
        end = int(time.time()) // step * step
        return [Candle(end-(500-i)*step,100,102,99,101,7) for i in range(500)]
    monkeypatch.setattr(PROVIDERS['BTCUSDT'],'fetch',fetch)
    first = client.get('/api/market').json()
    assert first['source'] == SOURCE
    assert first['candles'][0]['volume'] == 7
    assert client.get('/api/market').json() == first
