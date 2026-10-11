"""All Testnet tests are offline. Dummy credentials and MockTransport only."""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.testnet.client import BASE_URL, Credentials, SafeFailure, TestnetReader as Reader

DUMMY = Credentials('DUMMY_TEST_KEY_CANARY', 'dummy-secret-test-canary-never-real')
OWNER_PASSWORD = 'dummy-owner-password-for-tests'


def order(**extra):
    return dict(symbol='BTCUSDT', orderId=1, clientOrderId=DUMMY.secret,
                status='PARTIALLY_FILLED', side='BUY', type='STOP_LOSS_LIMIT',
                time=1700000000000, price='100.00000000', origQty='2.00000000',
                executedQty='1.00000000', **extra)


def trade():
    return dict(symbol='BTCUSDT', id=7, orderId=1, time=1700000000000,
                price='100.00000000', qty='1.00000000', quoteQty='100.00000000',
                commission='0.00001000', commissionAsset='BTC', isBuyer=True,
                privateField=DUMMY.secret)


def payload(path):
    if path == '/api/v3/time':
        return {'serverTime': int(time.time()*1000)}
    if path == '/api/v3/account':
        return {'uid':123, 'privateField':DUMMY.secret, 'balances':[
            {'asset':'USDT', 'free':'10000.12345678', 'locked':'2.00000000'},
            {'asset':'BTC', 'free':'0.50000000', 'locked':'0.00000000'},
            {'asset':'ETH', 'free':'0.00000000', 'locked':'0.00000000'}]}
    if path in ('/api/v3/openOrders','/api/v3/allOrders'):
        return [order()]
    if path == '/api/v3/myTrades':
        return [trade()]
    raise AssertionError('Unexpected endpoint')


async def scenario(callback, action, credentials=DUMMY):
    requests=[]
    def handle(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.url.scheme == 'https' and request.url.host == 'testnet.binance.vision'
        return callback(request)
    reader=Reader(credentials, transport=httpx.MockTransport(handle))
    try:
        return await action(reader, requests)
    finally:
        await reader.close()


def good(request):
    return httpx.Response(200, json=payload(request.url.path))


def run(callback, action, credentials=DUMMY):
    return asyncio.run(scenario(callback, action, credentials))


@pytest.mark.parametrize('credentials', [Credentials(), Credentials('dummy-only-key'), Credentials(secret='dummy-only-secret')])
def test_not_configured_makes_no_requests(credentials):
    async def action(reader, requests):
        assert (await reader.read())['status'] == 'Not configured'
        assert (await reader.read('history'))['status'] == 'Not configured'
        assert not requests
    run(lambda req: pytest.fail('No network allowed'), action, credentials)


def test_env_credentials_repr_and_isolated_client(monkeypatch):
    monkeypatch.setenv('BINANCE_TESTNET_API_KEY', DUMMY.key)
    monkeypatch.setenv('BINANCE_TESTNET_API_SECRET', DUMMY.secret)
    credentials=Credentials.from_env()
    assert credentials == DUMMY
    assert DUMMY.key not in repr(credentials) and DUMMY.secret not in repr(credentials)
    reader=Reader(transport=httpx.MockTransport(good))
    assert reader._client.follow_redirects is False
    asyncio.run(reader.close())


def test_account_signature_precision_whitelist_and_cache():
    async def action(reader, requests):
        data=await reader.read()
        assert data['status']=='Connected' and data['read_only'] and data['testnet'] and not data['stale']
        assert data['balances'][2] == {'asset':'USDT','free':'10000.12345678','locked':'2.00000000','total':'10002.12345678'}
        assert data['available_assets']==['BTC','USDT']
        assert data['open_orders'][0]['status']=='PARTIALLY_FILLED'
        assert data['open_orders'][0]['type']=='STOP_LOSS_LIMIT'
        assert data['open_orders_scope']=='ALL SYMBOLS'
        assert 'uid' not in data and 'clientOrderId' not in data['open_orders'][0]
        assert DUMMY.secret not in json.dumps(data) and DUMMY.key not in json.dumps(data)
        assert [r.url.path for r in requests]==['/api/v3/time','/api/v3/account','/api/v3/openOrders']
        for request in requests:
            if request.url.path.endswith('/time'):
                assert 'X-MBX-APIKEY' not in request.headers
                continue
            raw=request.url.query.decode()
            signed, signature=raw.rsplit('&signature=',1)
            expected=hmac.new(DUMMY.secret.encode(),signed.encode(),hashlib.sha256).hexdigest()
            assert hmac.compare_digest(signature,expected)
            assert request.headers['X-MBX-APIKEY']==DUMMY.key
            params=dict(parse_qsl(signed))
            assert params['recvWindow']=='5000'
            assert abs(int(params['timestamp'])-int(time.time()*1000))<2000
        cached=await reader.read()
        assert cached['checked_at']==data['checked_at'] and len(requests)==3
        assert cached['cache_age_seconds']>=0
        reader._cache['account']=(time.monotonic()-61,data)
        assert (await reader.read())['status']=='Connected' and len(requests)==5
    run(good,action)


def test_history_support_is_symbol_scoped_read_only():
    async def action(reader, requests):
        data=await reader.read('history')
        assert data['status']=='Connected' and data['symbol']=='BTCUSDT' and data['limit']==100
        assert data['orders'][0]['orderId']==1 and data['trades'][0]['side']=='BUY'
        assert DUMMY.secret not in json.dumps(data)
        assert len(requests)==3
        for request in requests[1:]:
            assert request.url.params['symbol']=='BTCUSDT' and request.url.params['limit']=='100'
    run(good,action)


@pytest.mark.parametrize('status,body,code', [
    (401,{'code':-2015,'msg':DUMMY.secret},'AUTH_FAILED'),
    (400,{'code':-2014,'msg':DUMMY.key},'AUTH_FAILED'),
    (400,{'code':-1022,'msg':DUMMY.secret},'AUTH_FAILED'),
    (403,{'msg':DUMMY.secret},'AUTH_FAILED'),
    (503,{'msg':DUMMY.secret},'UNAVAILABLE'),
    (302,{'msg':DUMMY.secret},'UNAVAILABLE'),
])
def test_failures_hide_upstream_credentials_and_no_redirect(status, body, code, caplog):
    def callback(request):
        if request.url.path.endswith('/time'): return good(request)
        return httpx.Response(status, json=body, headers={'Location':'https://api.binance.com/api/v3/account'})
    async def action(reader, requests):
        data=await reader.read()
        assert data['status']=='Disconnected' and data['code']==code and data['stale']
        assert 'balances' not in data and 'open_orders' not in data
        await reader.read(); assert len(requests)==2
        assert DUMMY.secret not in json.dumps(data) and DUMMY.key not in json.dumps(data)
    run(callback,action)
    assert DUMMY.secret not in caplog.text and DUMMY.key not in caplog.text


@pytest.mark.parametrize('error,code', [(httpx.ReadTimeout,'TIMEOUT'),(httpx.ConnectError,'UNAVAILABLE')])
def test_transport_errors_sanitized_and_recovered(error,code,caplog):
    offline=True
    def callback(request):
        if offline: raise error(DUMMY.secret,request=request)
        return good(request)
    async def action(reader,requests):
        nonlocal offline
        failure=await reader.read(); assert failure['code']==code
        offline=False
        assert (await reader.read())['status']=='Disconnected' and len(requests)==1
        reader._retry_at=0
        assert (await reader.read())['status']=='Connected'
    run(callback,action)
    assert DUMMY.secret not in caplog.text


@pytest.mark.parametrize('status', [418,429])
@pytest.mark.parametrize('retry_after', ['120','NaN','infinity','Wed, 01 Jan 2099 00:00:00 GMT','invalid'])
def test_rate_limits_respect_cooldown_globally(status,retry_after):
    def callback(request):
        return httpx.Response(status, json={'msg':DUMMY.secret}, headers={'Retry-After':retry_after})
    async def action(reader,requests):
        data=await reader.read()
        assert data['code']=='RATE_LIMITED' and 1<=data['retry_after']<=86400
        if retry_after=='120': assert data['retry_after']==120
        assert (await reader.read('history'))['code']=='RATE_LIMITED' and len(requests)==1
    run(callback,action)


def test_clock_skew_is_corrected_and_only_retried_once():
    time_calls=account_calls=0
    def callback(request):
        nonlocal time_calls,account_calls
        if request.url.path.endswith('/time'):
            time_calls+=1
            return httpx.Response(200,json={'serverTime':int(time.time()*1000)+60000})
        if request.url.path.endswith('/account'):
            account_calls+=1
            assert abs(int(request.url.params['timestamp'])-int(time.time()*1000)-60000)<2000
            if account_calls==1: return httpx.Response(400,json={'code':-1021,'msg':DUMMY.secret})
        return good(request)
    async def action(reader,requests):
        assert (await reader.read())['status']=='Connected'
    run(callback,action)
    assert time_calls==2 and account_calls==2


def test_persistent_clock_skew_stops_without_retry_loop():
    def callback(request):
        if request.url.path.endswith('/time'): return good(request)
        return httpx.Response(400,json={'code':-1021})
    async def action(reader,requests):
        assert (await reader.read())['code']=='CLOCK_ERROR'
        assert len(requests)==4
    run(callback,action)


@pytest.mark.parametrize('bad', ['NaN','Infinity','-1','1e99999999','<script>','0.1 '+DUMMY.secret])
def test_bad_balances_rejected(bad):
    def callback(request):
        if request.url.path.endswith('/account'):
            data=payload(request.url.path); data['balances'][0]['free']=bad
            return httpx.Response(200,json=data)
        return good(request)
    async def action(reader,requests):
        assert (await reader.read())['code']=='INVALID_DATA'
        assert len(requests)==2
    run(callback,action)


def test_decimal_total_is_not_rounded_by_float_or_decimal_context():
    reader=Reader(Credentials(),transport=httpx.MockTransport(good))
    data=reader._balances({'balances':[{'asset':'BTC','free':'12345678901234567890123456789012.123456789012345678901234',
                                       'locked':'0.000000000000000000000001'}]})
    assert data[0]['total']=='12345678901234567890123456789012.123456789012345678901235'
    asyncio.run(reader.close())


def test_failed_snapshot_does_not_return_cached_balance():
    offline=False
    def callback(request):
        if offline: return httpx.Response(503,json={'msg':'offline'})
        return good(request)
    async def action(reader,requests):
        nonlocal offline
        data=await reader.read(); reader._cache['account']=(time.monotonic()-61,data)
        offline=True
        failure=await reader.read()
        assert failure['status']=='Disconnected' and 'balances' not in failure
        assert not reader._cache
    run(callback,action)


def test_no_order_writing_endpoints_or_methods():
    async def action(reader,requests):
        for path in ['/api/v3/order','/api/v3/order/test','/api/v3/order/cancelReplace','/sapi/v1/account']:
            with pytest.raises(ValueError): await reader._get(path,signed=True)
        for name in ['create_order','cancel_order','modify_order','place_order']:
            assert not hasattr(reader,name)
        assert not requests
    run(good,action)


def test_malformed_and_credential_echo_responses_are_safe():
    for response in [httpx.Response(200,text=DUMMY.secret),httpx.Response(200,json={'serverTime':DUMMY.secret})]:
        async def action(reader,requests):
            data=await reader.read(); assert data['code']=='INVALID_DATA'
            assert DUMMY.secret not in json.dumps(data)
        run(lambda request:response,action)


def test_signed_urls_and_credentials_do_not_appear_in_logs(caplog):
    reader=Reader(DUMMY,transport=httpx.MockTransport(good))
    with caplog.at_level(logging.DEBUG):
        logging.getLogger('httpx').info('HTTP GET %s/api/v3/account?signature=canary',BASE_URL)
        logging.getLogger('httpcore.http11').warning('header X-MBX-APIKEY: %s',DUMMY.key)
        logging.getLogger('app.testnet.client').warning('bad upstream %s',DUMMY.secret)
        asyncio.run(reader.read())
    asyncio.run(reader.close())
    assert DUMMY.secret not in caplog.text and DUMMY.key not in caplog.text and 'signature=' not in caplog.text


@pytest.fixture
def protected_client(monkeypatch):
    monkeypatch.setenv('BINANCE_TESTNET_API_KEY',DUMMY.key)
    monkeypatch.setenv('BINANCE_TESTNET_API_SECRET',DUMMY.secret)
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',OWNER_PASSWORD)
    monkeypatch.setattr('app.main.TestnetReader',lambda:Reader(DUMMY,transport=httpx.MockTransport(good)))
    with TestClient(app) as client:
        yield client


def test_owner_protection_and_public_market_survives(protected_client):
    client=protected_client
    assert client.get('/').status_code==200
    assert client.get('/api/health').json()=={'status':'ok'}
    response=client.get('/api/testnet/account')
    assert response.status_code==401 and response.headers['cache-control']=='no-store'
    assert 'Aura Testnet' in response.headers['www-authenticate']
    assert client.get('/api/testnet/history',auth=('aura','wrong-password')).status_code==401
    response=client.get('/api/testnet/account',auth=('aura',OWNER_PASSWORD))
    assert response.json()['status']=='Connected' and response.headers['cache-control']=='no-store'
    assert DUMMY.key not in response.text and DUMMY.secret not in response.text and OWNER_PASSWORD not in response.text
    assert client.get('/api/testnet/history',auth=('aura',OWNER_PASSWORD)).json()['symbol']=='BTCUSDT'
    login=client.get('/api/testnet/login',auth=('aura',OWNER_PASSWORD),follow_redirects=False)
    assert login.status_code==303 and login.headers['location']=='/'


@pytest.mark.parametrize('password', ['','short'])
def test_configured_account_fails_closed_without_owner_password(protected_client,monkeypatch,password):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD',password)
    assert protected_client.get('/api/testnet/account',auth=('aura',OWNER_PASSWORD)).status_code==403


@pytest.mark.parametrize('method',['post','put','patch','delete'])
def test_api_exposes_no_account_mutations(protected_client,method):
    for endpoint in ['account','history','login']:
        response=getattr(protected_client,method)('/api/testnet/'+endpoint)
        assert response.status_code==405
    assert protected_client.post('/api/testnet/order').status_code==404


def test_missing_credentials_returns_not_configured_without_login(monkeypatch):
    monkeypatch.delenv('BINANCE_TESTNET_API_KEY',raising=False)
    monkeypatch.delenv('BINANCE_TESTNET_API_SECRET',raising=False)
    with TestClient(app) as client:
        response=client.get('/api/testnet/account')
        assert response.status_code==200 and response.json()['status']=='Not configured'
        assert client.get('/api/health').status_code==200


def test_history_pair_is_validated_and_cache_is_separate():
    def callback(request):
        rows=payload(request.url.path)
        if isinstance(rows,list):
            rows=[dict(row,symbol=request.url.params['symbol']) for row in rows]
        return httpx.Response(200,json=rows)
    async def action(reader,requests):
        assert (await reader.read('history','ETHUSDT'))['symbol']=='ETHUSDT'
        assert (await reader.read('history','BTCUSDT'))['symbol']=='BTCUSDT'
        assert len(requests)==5
        await reader.read('history','ETHUSDT'); assert len(requests)==5
        with pytest.raises(ValueError): await reader.read('history','https://api.binance.com')
    run(callback,action)


def test_wrong_pair_history_is_rejected():
    async def action(reader,requests):
        assert (await reader.read('history','ETHUSDT'))['code']=='INVALID_DATA'
    run(good,action)


def test_unsupported_pair_returns_safe_error():
    def callback(request):
        if request.url.path.endswith('/time'): return good(request)
        return httpx.Response(400,json={'code':-1121,'msg':DUMMY.secret})
    async def action(reader,requests):
        data=await reader.read('history','ETHUSDT')
        assert data['code']=='INVALID_SYMBOL' and DUMMY.secret not in json.dumps(data)
    run(callback,action)


def test_exception_logs_cannot_echo_credentials(caplog):
    reader=Reader(DUMMY,transport=httpx.MockTransport(good))
    try:
        raise ValueError(DUMMY.secret)
    except ValueError:
        logging.getLogger('httpcore.http11').warning('failed',exc_info=True)
    asyncio.run(reader.close())
    assert DUMMY.secret not in caplog.text


def test_history_query_rejects_non_symbol_input(protected_client):
    response=protected_client.get('/api/testnet/history?symbol=ETH/USDT',auth=('aura',OWNER_PASSWORD))
    assert response.status_code==422


def test_concurrent_reads_share_single_snapshot():
    async def action(reader,requests):
        first,second=await asyncio.gather(reader.read(),reader.read())
        assert first['status']==second['status']=='Connected' and len(requests)==3
    run(good,action)


def test_overall_snapshot_timeout_is_safe(monkeypatch):
    real_timeout=asyncio.timeout
    monkeypatch.setattr('app.testnet.client.asyncio.timeout',lambda _:real_timeout(.005))
    async def slow(request):
        await asyncio.sleep(.1)
        return good(request)
    async def action(reader,requests):
        result=await reader.read()
        assert result['code']=='TIMEOUT' and result['status']=='Disconnected'
        assert 'balances' not in result
    run(slow,action)


def test_duplicate_balances_do_not_create_false_totals():
    def callback(request):
        if request.url.path.endswith('/account'):
            data=payload(request.url.path); data['balances'].append(data['balances'][0])
            return httpx.Response(200,json=data)
        return good(request)
    async def action(reader,requests):
        assert (await reader.read())['code']=='INVALID_DATA'
    run(callback,action)
