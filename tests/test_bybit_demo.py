"""Official V5 Demo GET protocol exercised offline using marked dummy credentials."""
import asyncio
import hashlib
import hmac
import json
import logging
import socket
import ssl
import time
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.bybit_demo.client import BASE_URL, READ_PATHS, Credentials, SafeFailure, BybitDemoReader as Reader

DUMMY = Credentials('DUMMY_BYBIT_DEMO_KEY_CANARY', 'dummy-bybit-demo-secret-never-real')
OWNER_PASSWORD = 'dummy-bybit-owner-password-for-tests'


def order(symbol='BTCUSDT', **extra):
    return dict(orderId='dummy-order-1', orderLinkId=DUMMY.secret, symbol=symbol, orderStatus='New', side='Buy',
                orderType='Limit', price='100.00000000', qty='2.00000000', cumExecQty='0.00000000',
                createdTime='1700000000000', **extra)


def trade(symbol='BTCUSDT', **extra):
    return dict(execId='dummy-exec-1', orderId='dummy-order-1', orderLinkId=DUMMY.key, symbol=symbol,
                side='Buy', execType='Trade', execPrice='100.00000000', execQty='1.00000000',
                execValue='100.00000000', execFee='-0.00001000', feeCurrency='BTC', execTime='1700000000000', **extra)


def payload(request):
    path = request.url.path
    if path == '/v5/market/time':
        return {'timeSecond': str(int(time.time())), 'timeNano': str(time.time_ns())}
    if path == '/v5/account/wallet-balance':
        return {'list': [{'accountType': 'UNIFIED', 'totalWalletBalance': '10000.12345678',
                         'totalEquity': '9999.00000000', 'totalAvailableBalance': '', 'uid': DUMMY.secret,
                         'coin': [{'coin': 'USDT', 'walletBalance': '10000.12345678', 'equity': '9999.00000000',
                                   'locked': '2.00000000', 'usdValue': '9999.00000000', 'spotBorrow': '1.00000000'},
                                  {'coin': 'BTC', 'walletBalance': '0.10000000', 'equity': '-0.00000001',
                                   'locked': '', 'usdValue': '', 'availableToWithdraw': '999999'}]}]}
    if path in ('/v5/order/realtime', '/v5/order/history', '/v5/execution/list'):
        symbol = request.url.params['symbol']
        rows = [trade(symbol)] if path == '/v5/execution/list' else [order(symbol)]
        return {'category': request.url.params['category'], 'list': rows, 'nextPageCursor': ''}
    raise AssertionError('Unexpected Demo read endpoint')


def response(result, **extra):
    return httpx.Response(200, json=dict(retCode=0, retMsg=DUMMY.secret, result=result, time=int(time.time()*1000), **extra))


def good(request):
    return response(payload(request))


async def scenario(callback, action, credentials=DUMMY):
    requests = []
    def handle(request):
        requests.append(request)
        assert request.method == 'GET' and not request.content
        assert request.url.scheme == 'https' and request.url.host == 'api-demo.bybit.com'
        assert request.url.path in READ_PATHS
        assert 'signature' not in request.url.params and 'api_key' not in request.url.params
        return callback(request)
    reader = Reader(credentials, transport=httpx.MockTransport(handle))
    try:
        return await action(reader, requests)
    finally:
        await reader.close()


def run(callback, action, credentials=DUMMY):
    return asyncio.run(scenario(callback, action, credentials))


@pytest.mark.parametrize('credentials', [Credentials(), Credentials('dummy-only-key'), Credentials(secret='dummy-only-secret')])
def test_not_configured_has_no_exchange_requests(credentials):
    async def action(reader, requests):
        data = await reader.read()
        assert data['status'] == 'Not configured' and data['provider'] == 'BYBIT_DEMO'
        assert data['demo'] and data['read_only'] and data['virtual_funds'] and not data['real_money']
        assert (await reader.read('history'))['status'] == 'Not configured' and not requests
    run(good, action, credentials)


def test_env_isolation_repr_no_override_host(monkeypatch):
    monkeypatch.setenv('BYBIT_DEMO_API_KEY', ' '+DUMMY.key+' ')
    monkeypatch.setenv('BYBIT_DEMO_API_SECRET', DUMMY.secret)
    monkeypatch.setenv('BINANCE_TESTNET_API_KEY', 'dummy-other-provider')
    monkeypatch.setenv('BYBIT_BASE_URL', 'https://api.bybit.com')
    assert Credentials.from_env() == DUMMY and BASE_URL == 'https://api-demo.bybit.com'
    assert DUMMY.key not in repr(DUMMY) and DUMMY.secret not in repr(DUMMY)
    reader = Reader(transport=httpx.MockTransport(good))
    assert reader._client.follow_redirects is False
    asyncio.run(reader.close())


@pytest.mark.parametrize('category', ['spot', 'linear', 'inverse', 'option'])
def test_account_signature_scope_exact_amounts_and_cache(category, caplog):
    async def action(reader, requests):
        data = await reader.read(category=category)
        assert data['status'] == 'Connected' and data['read_only'] and data['demo'] and not data['real_money']
        assert data['demo_balance']['wallet_balance_usd'] == '10000.12345678'
        assert data['demo_balance']['available_balance_usd'] is None
        assert data['balances'][0]['equity'] == '-1E-8'
        assert data['balances'][0]['locked'] is None and 'free' not in data['balances'][0]
        assert data['available_assets'] == ['BTC', 'USDT']
        assert data['open_orders_scope'] == category.upper()+' / BTCUSDT'
        assert [r.url.path for r in requests] == ['/v5/market/time', '/v5/account/wallet-balance', '/v5/order/realtime']
        for request in requests:
            if request.url.path == '/v5/market/time':
                assert not any(name.startswith('x-bapi') for name in request.headers)
                continue
            timestamp = request.headers['X-BAPI-TIMESTAMP']
            assert abs(int(timestamp)-int(time.time()*1000)) < 2000
            assert request.headers['X-BAPI-RECV-WINDOW'] == '5000'
            assert request.headers['X-BAPI-API-KEY'] == DUMMY.key
            assert request.headers['X-BAPI-SIGN-TYPE'] == '2'
            signed = timestamp+DUMMY.key+'5000'+request.url.query.decode()
            expected = hmac.new(DUMMY.secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
            assert hmac.compare_digest(request.headers['X-BAPI-SIGN'], expected)
        assert requests[-1].url.params['category'] == category
        assert requests[-1].url.params['openOnly'] == '0'
        assert requests[1].url.params['accountType'] == 'UNIFIED'
        cached = await reader.read(category=category)
        assert cached['checked_at'] == data['checked_at'] and len(requests) == 3
        reader._cache[('account', category, 'BTCUSDT')] = (time.monotonic()-61, data)
        assert (await reader.read(category=category))['status'] == 'Connected' and len(requests) == 5
        assert DUMMY.secret not in json.dumps(data) and DUMMY.key not in json.dumps(data)
    run(good, action)
    assert DUMMY.secret not in caplog.text and DUMMY.key not in caplog.text


def test_wire_query_with_encoded_cursor_signed_exactly():
    async def action(reader, requests):
        params = {'category': 'spot', 'symbol': 'BTCUSDT', 'cursor': 'dummy/+= cursor:漢字'}
        await reader._signed_read('/v5/order/history', params)
        request = requests[-1]
        assert request.url.query.decode() == urlencode(params)
        signed = request.headers['X-BAPI-TIMESTAMP']+DUMMY.key+'5000'+urlencode(params)
        assert request.headers['X-BAPI-SIGN'] == hmac.new(DUMMY.secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    run(good, action)


@pytest.mark.parametrize('ret_code,category', [
    (10003, 'KEY_INVALID'), (10004, 'SIGNATURE_INVALID'), (10005, 'PERMISSION_DENIED'),
    (10007, 'AUTH_FAILED'), (10010, 'IP_RESTRICTED'), (-2015, 'KEY_EXPIRED'),
    (33004, 'KEY_EXPIRED'), (10008, 'ACCOUNT_MODE'), (10028, 'ACCOUNT_MODE'),
    (100028, 'ACCOUNT_MODE'), (10009, 'REGION_RESTRICTED'), (10024, 'REGION_RESTRICTED'),
    (10017, 'ENDPOINT_UNAVAILABLE'), (10029, 'INVALID_SYMBOL'), (10001, 'PARAMETER_ERROR'),
    (10000, 'TIMEOUT'), (10016, 'UPSTREAM_UNAVAILABLE'), (99999, 'API_ERROR'),
])
def test_ret_codes_do_not_echo_upstream_message_or_headers(ret_code, category, caplog):
    def callback(request):
        if request.url.path.endswith('/time'):
            return good(request)
        return httpx.Response(200, json={'retCode': ret_code, 'retMsg': DUMMY.secret, 'private': dict(request.headers)},
                              headers={'X-Private': DUMMY.key})
    async def action(reader, requests):
        data = await reader.read()
        assert data['code'] == category and data['status'] == 'Disconnected' and data['stale']
        assert data['diagnostics']['ret_code'] == ret_code and data['diagnostics']['http_status'] == 200
        assert data['diagnostics']['endpoint'] == '/v5/account/wallet-balance'
        assert 'balances' not in data
        await reader.read('history'); assert len(requests) == 2
        assert DUMMY.key not in json.dumps(data) and DUMMY.secret not in json.dumps(data)
    run(callback, action)
    assert DUMMY.key not in caplog.text and DUMMY.secret not in caplog.text and 'X-BAPI-SIGN' not in caplog.text


@pytest.mark.parametrize('status,category', [
    (401, 'AUTH_FAILED'), (403, 'HTTP_FORBIDDEN'), (451, 'REGION_RESTRICTED'),
    (404, 'ENDPOINT_UNAVAILABLE'), (405, 'ENDPOINT_UNAVAILABLE'),
    (503, 'UPSTREAM_UNAVAILABLE'), (500, 'UPSTREAM_UNAVAILABLE'),
    (302, 'REDIRECT_BLOCKED'), (400, 'HTTP_ERROR'), (200, 'INVALID_DATA'),
])
def test_http_errors_with_non_json_and_no_redirect(status, category, caplog):
    def callback(request):
        return httpx.Response(status, text='<html>'+DUMMY.secret+'</html>',
                              headers={'Location': 'https://api.bybit.com/?private=dummy-canary'})
    async def action(reader, requests):
        data = await reader.read()
        assert data['code'] == category and data['diagnostics']['http_status'] == status
        if status == 403:
            assert data['retry_after'] >= 600
        assert len(requests) == 1 and DUMMY.secret not in json.dumps(data)
    run(callback, action)
    assert DUMMY.secret not in caplog.text and 'private=dummy-canary' not in caplog.text


@pytest.mark.parametrize('status,ret_code', [(429, None), (418, None), (200, 10006), (200, 429)])
@pytest.mark.parametrize('retry', ['120', 'NaN', 'Infinity', 'invalid'])
def test_rate_limit_cooldown_for_all_scopes(status, ret_code, retry):
    def callback(request):
        return httpx.Response(status, json={'retCode': ret_code, 'retMsg': DUMMY.secret},
                              headers={'Retry-After': retry, 'X-Bapi-Limit-Reset-Timestamp': str(int(time.time()*1000)+90000)})
    async def action(reader, requests):
        data = await reader.read()
        assert data['code'] == 'RATE_LIMITED' and 89 <= data['retry_after'] <= 120
        if retry == '120':
            assert data['retry_after'] == 120
        assert (await reader.read('history', category='linear'))['code'] == 'RATE_LIMITED' and len(requests) == 1
    run(callback, action)


def test_exhausted_success_header_delays_the_next_read(monkeypatch):
    delays = []
    async def record_delay(value):
        delays.append(value)
    monkeypatch.setattr('app.bybit_demo.client.asyncio.sleep', record_delay)
    def callback(request):
        data = good(request)
        if request.url.path.endswith('/wallet-balance'):
            data.headers['X-Bapi-Limit-Status'] = '0'
            data.headers['X-Bapi-Limit-Reset-Timestamp'] = str(int(time.time()*1000)+1000)
        return data
    async def action(reader, requests):
        assert (await reader.read())['status'] == 'Connected'
        assert delays and 0 < delays[0] <= 2
    run(callback, action)


@pytest.mark.parametrize('error,category,detail', [
    (httpx.ConnectTimeout, 'TIMEOUT', ('timeout_phase', 'CONNECT')),
    (httpx.ReadTimeout, 'TIMEOUT', ('timeout_phase', 'READ')),
    (httpx.WriteTimeout, 'TIMEOUT', ('timeout_phase', 'WRITE')),
    (httpx.PoolTimeout, 'TIMEOUT', ('timeout_phase', 'POOL')),
    (httpx.ConnectError, 'NETWORK_ERROR', ('network_error', 'CONNECT')),
    (httpx.ReadError, 'NETWORK_ERROR', ('network_error', 'READ')),
    (httpx.RemoteProtocolError, 'NETWORK_ERROR', ('network_error', 'PROTOCOL')),
    (httpx.ProxyError, 'NETWORK_ERROR', ('network_error', 'PROXY')),
])
def test_transport_errors_recover_without_exception_leaks(error, category, detail, caplog):
    offline = True
    def callback(request):
        if offline:
            raise error(DUMMY.secret+str(request.headers), request=request)
        return good(request)
    async def action(reader, requests):
        nonlocal offline
        data = await reader.read()
        assert data['code'] == category and data['diagnostics'][detail[0]] == detail[1]
        assert 'http_status' not in data['diagnostics']
        offline = False
        assert (await reader.read())['status'] == 'Disconnected' and len(requests) == 1
        reader._retry_at = 0
        assert (await reader.read())['status'] == 'Connected'
    run(callback, action)
    assert DUMMY.secret not in caplog.text and 'x-bapi-sign' not in caplog.text.lower()


@pytest.mark.parametrize('cause,kind', [(socket.gaierror, 'DNS'), (ssl.SSLError, 'TLS')])
def test_dns_tls_types_are_safe(cause, kind):
    def callback(request):
        try:
            raise cause(DUMMY.secret)
        except cause as exc:
            raise httpx.ConnectError(DUMMY.key, request=request) from exc
    async def action(reader, requests):
        assert (await reader.read())['diagnostics']['network_error'] == kind
    run(callback, action)


@pytest.mark.parametrize('persistent', [False, True])
def test_clock_sync_and_single_retry(persistent):
    clock_calls = account_calls = 0
    def callback(request):
        nonlocal clock_calls, account_calls
        if request.url.path.endswith('/time'):
            clock_calls += 1
            return response({'timeNano': str(int((time.time()+60)*1000000000))})
        if request.url.path.endswith('/wallet-balance'):
            account_calls += 1
            assert abs(int(request.headers['X-BAPI-TIMESTAMP'])-int(time.time()*1000)-60000) < 2000
            if persistent or account_calls == 1:
                return httpx.Response(200, json={'retCode': 10002, 'retMsg': DUMMY.secret})
        return good(request)
    async def action(reader, requests):
        result = await reader.read()
        assert result['status'] == ('Disconnected' if persistent else 'Connected')
        if persistent:
            assert result['code'] == 'CLOCK_ERROR' and result['diagnostics']['ret_code'] == 10002
    run(callback, action)
    assert clock_calls == account_calls == 2


@pytest.mark.parametrize('bad', [None, {}, {'retCode': True, 'result': {}}, {'retCode': '0', 'result': {}},
                               {'retCode': 0, 'result': []}, {'retCode': 0, 'result': {'timeNano': 'NaN'}}])
def test_malformed_envelopes_and_clock(bad):
    async def action(reader, requests):
        assert (await reader.read())['code'] == 'INVALID_DATA'
    run(lambda request: httpx.Response(200, json=bad), action)


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '1e99', '<script>', '1.0 '+DUMMY.secret])
def test_malformed_wallet_amounts_rejected(bad):
    def callback(request):
        data = payload(request)
        if request.url.path.endswith('/wallet-balance'):
            data['list'][0]['coin'][0]['walletBalance'] = bad
        return response(data)
    async def action(reader, requests):
        assert (await reader.read())['code'] == 'INVALID_DATA' and len(requests) == 2
    run(callback, action)


def test_duplicate_assets_and_deprecated_available_balance_are_not_used():
    reader = Reader(Credentials(), transport=httpx.MockTransport(good))
    data = {'list': [{'accountType': 'UNIFIED', 'coin': [dict(coin='BTC', walletBalance='1', equity='1',
                     availableToWithdraw='999', free='999')]}]}
    result = reader._wallet(data)
    assert 'free' not in result['balances'][0] and result['demo_balance']['available_balance_usd'] is None
    data['list'][0]['coin'].append(data['list'][0]['coin'][0])
    with pytest.raises(SafeFailure):
        reader._wallet(data)
    asyncio.run(reader.close())


def test_history_pages_use_stable_window_and_cursor_signature():
    def callback(request):
        data = payload(request)
        if request.url.path in ('/v5/order/history', '/v5/execution/list'):
            second = 'cursor' in request.url.params
            row = data['list'][0]
            row['orderId'] = 'dummy-order-2' if second else 'dummy-order-1'
            if request.url.path == '/v5/execution/list':
                row['execId'] = 'dummy-exec-2' if second else 'dummy-exec-1'
            data['nextPageCursor'] = '' if second else 'dummy/cursor+=&'
        return response(data)
    async def action(reader, requests):
        result = await reader.read('history', 'ETHUSDT', 'linear')
        assert result['status'] == 'Connected' and len(result['orders']) == len(result['trades']) == 2
        assert result['trades'][0]['fee'] == '-0.00001000'
        assert not result['orders_has_more'] and not result['trades_has_more']
        windows = set()
        for request in requests[1:]:
            params = request.url.params
            assert params['category'] == 'linear' and params['symbol'] == 'ETHUSDT'
            assert int(params['endTime'])-int(params['startTime']) == 7*86400000
            windows.add((params['startTime'], params['endTime']))
        assert len(windows) == 1
        await reader.read('history', 'ETHUSDT', 'linear'); assert len(requests) == 5
        await reader.read('history', 'ETHUSDT', 'spot'); assert len(requests) == 9
    run(callback, action)


@pytest.mark.parametrize('defect', ['wrong_category', 'wrong_symbol', 'duplicate', 'cursor_loop', 'credential_cursor', 'closed_order'])
def test_inconsistent_order_pages_fail_closed(defect):
    def callback(request):
        data = payload(request)
        if request.url.path == '/v5/order/realtime':
            if defect == 'wrong_category': data['category'] = 'inverse'
            if defect == 'wrong_symbol': data['list'][0]['symbol'] = 'ETHUSDT'
            if defect == 'duplicate': data['list'].append(data['list'][0])
            if defect == 'cursor_loop': data['nextPageCursor'] = 'dummy-repeated-cursor'
            if defect == 'credential_cursor': data['nextPageCursor'] = DUMMY.secret
            if defect == 'closed_order': data['list'][0]['orderStatus'] = 'Filled'
        return response(data)
    async def action(reader, requests):
        result = await reader.read()
        assert result['code'] == 'INVALID_DATA' and 'open_orders' not in result
    run(callback, action)


def test_bounded_pagination_reports_more_instead_of_claiming_complete():
    page = 0
    def callback(request):
        nonlocal page
        data = payload(request)
        if request.url.path == '/v5/order/realtime':
            page += 1
            data['list'][0]['orderId'] = 'dummy-page-'+str(page)
            data['nextPageCursor'] = 'dummy-cursor-'+str(page)
        return response(data)
    async def action(reader, requests):
        result = await reader.read()
        assert result['status'] == 'Connected' and result['open_orders_has_more']
        assert len(result['open_orders']) == 4 and len(requests) == 6
        assert 'cursor' not in json.dumps(result)
    run(callback, action)


def test_failed_read_clears_all_cached_balances():
    offline = False
    def callback(request):
        if offline:
            return httpx.Response(503, text=DUMMY.secret)
        return good(request)
    async def action(reader, requests):
        nonlocal offline
        data = await reader.read()
        reader._cache[('account', 'spot', 'BTCUSDT')] = (time.monotonic()-61, data)
        offline = True
        result = await reader.read()
        assert result['status'] == 'Disconnected' and 'balances' not in result and not reader._cache
    run(callback, action)


def test_no_writing_endpoints_methods_or_wrong_authentication():
    async def action(reader, requests):
        for path in ['/v5/order/create', '/v5/order/amend', '/v5/order/cancel', '/v5/order/cancel-all',
                     '/v5/asset/withdraw/create', '/v5/asset/transfer/inter-transfer', '/v5/account/demo-apply-money',
                     'https://api.bybit.com/v5/account/wallet-balance']:
            with pytest.raises(ValueError): await reader._get(path)
        with pytest.raises(ValueError): await reader._get('/v5/account/wallet-balance', signed=False)
        for name in ['create_order', 'cancel_order', 'amend_order', 'place_order', 'withdraw', 'transfer']:
            assert not hasattr(reader, name)
        assert not requests
    run(good, action)


def test_safe_diagnostics_and_logs_never_include_auth_headers(caplog):
    failure = SafeFailure('NETWORK_ERROR', endpoint=DUMMY.secret, ret_code=DUMMY.secret,
                          http_status=True, network_error=DUMMY.key)
    assert failure.diagnostics == {}
    reader = Reader(DUMMY, transport=httpx.MockTransport(good))
    with caplog.at_level(logging.DEBUG):
        for text in ['HTTP GET '+BASE_URL+'/v5/order/history?cursor=dummy', 'X-BAPI-SIGN: dummy-signature',
                     'X-BAPI-API-KEY: '+DUMMY.key, 'Authorization: Basic dummy-basic', DUMMY.secret]:
            logging.getLogger('httpx').warning(text)
        try:
            raise ValueError(DUMMY.secret)
        except ValueError:
            logging.getLogger('httpcore.http11').warning('failed', exc_info=True)
        asyncio.run(reader.read())
    asyncio.run(reader.close())
    for text in [DUMMY.secret, DUMMY.key, 'dummy-signature', 'dummy-basic', BASE_URL]:
        assert text not in caplog.text


@pytest.fixture
def protected_client(monkeypatch):
    monkeypatch.delenv('BINANCE_TESTNET_API_KEY', raising=False)
    monkeypatch.delenv('BINANCE_TESTNET_API_SECRET', raising=False)
    monkeypatch.setenv('BYBIT_DEMO_API_KEY', DUMMY.key)
    monkeypatch.setenv('BYBIT_DEMO_API_SECRET', DUMMY.secret)
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD', OWNER_PASSWORD)
    monkeypatch.setattr('app.main.BybitDemoReader', lambda: Reader(DUMMY, transport=httpx.MockTransport(good)))
    with TestClient(app) as client:
        yield client


def test_owner_api_ui_binance_retained_and_health(protected_client):
    client = protected_client
    page = client.get('/')
    assert page.status_code == 200 and 'BYBIT DEMO / READ ONLY' in page.text
    assert 'REAL MONEY IS NOT USED' in page.text and '/static/bybit_demo.js' in page.text
    assert '/static/testnet.js' not in page.text
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.get('/api/bybit-demo/account').status_code == 401
    assert client.get('/api/bybit-demo/history', auth=('aura', 'wrong-password')).status_code == 401
    result = client.get('/api/bybit-demo/account', auth=('aura', OWNER_PASSWORD))
    assert result.headers['cache-control'] == 'no-store' and result.json()['status'] == 'Connected'
    assert DUMMY.key not in result.text and DUMMY.secret not in result.text and OWNER_PASSWORD not in result.text
    assert client.get('/api/bybit-demo/history?category=linear&symbol=ETHUSDT', auth=('aura', OWNER_PASSWORD)).json()['category'] == 'linear'
    login = client.get('/api/bybit-demo/login', auth=('aura', OWNER_PASSWORD), follow_redirects=False)
    assert login.status_code == 303 and login.headers['location'] == '/'
    assert client.get('/api/testnet/account').status_code in (200, 401, 403)


@pytest.mark.parametrize('password', ['', 'short'])
def test_owner_password_missing_fails_closed(protected_client, monkeypatch, password):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD', password)
    assert protected_client.get('/api/bybit-demo/account', auth=('aura', OWNER_PASSWORD)).status_code == 403


def test_missing_keys_does_not_break_public_terminal(monkeypatch):
    monkeypatch.delenv('BYBIT_DEMO_API_KEY', raising=False)
    monkeypatch.delenv('BYBIT_DEMO_API_SECRET', raising=False)
    with TestClient(app) as client:
        assert client.get('/api/bybit-demo/account').json()['status'] == 'Not configured'
        assert client.get('/').status_code == 200 and client.get('/api/health').status_code == 200


@pytest.mark.parametrize('method', ['post', 'put', 'patch', 'delete'])
def test_routes_are_get_only(protected_client, method):
    for path in ['account', 'history', 'login']:
        assert getattr(protected_client, method)('/api/bybit-demo/'+path).status_code == 405
    assert protected_client.post('/api/bybit-demo/order').status_code == 404


@pytest.mark.parametrize('query', ['category=real', 'symbol=BTC/USDT', 'symbol=https://api.bybit.com'])
def test_scope_input_validation(protected_client, query):
    assert protected_client.get('/api/bybit-demo/account?'+query, auth=('aura', OWNER_PASSWORD)).status_code == 422


def test_concurrent_reads_are_serialized_and_share_cache():
    async def action(reader, requests):
        first, second = await asyncio.gather(reader.read(), reader.read())
        assert first['status'] == second['status'] == 'Connected' and len(requests) == 3
    run(good, action)


def test_snapshot_timeout_is_safe(monkeypatch):
    real_timeout = asyncio.timeout
    monkeypatch.setattr('app.bybit_demo.client.asyncio.timeout', lambda _: real_timeout(.005))
    async def slow(request):
        await asyncio.sleep(.1)
        return good(request)
    async def action(reader, requests):
        result = await reader.read()
        assert result['code'] == 'TIMEOUT' and result['diagnostics']['timeout_phase'] == 'SNAPSHOT'
        assert 'balances' not in result
    run(slow, action)
