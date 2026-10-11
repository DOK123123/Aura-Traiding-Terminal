"""Offline regressions for safe Testnet error diagnosis; never exchange orders."""
import asyncio
import json
import logging
import socket
import ssl

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.testnet.client import Credentials, SafeFailure, TestnetReader as Reader
from tests.test_testnet import DUMMY, OWNER_PASSWORD, good, run


@pytest.mark.parametrize('status,upstream_code,category', [
    (400, -1002, 'PERMISSION_DENIED'),
    (400, -1007, 'TIMEOUT'),
    (400, -1003, 'RATE_LIMITED'),
    (400, -1015, 'RATE_LIMITED'),
    (403, -2015, 'KEY_REJECTED'),
    (401, -2014, 'KEY_INVALID'),
    (401, -1022, 'SIGNATURE_INVALID'),
    (401, None, 'AUTH_FAILED'),
    (403, None, 'WAF_BLOCKED'),
    (451, 0, 'REGION_RESTRICTED'),
    (404, None, 'ENDPOINT_UNAVAILABLE'),
    (405, None, 'ENDPOINT_UNAVAILABLE'),
    (410, None, 'ENDPOINT_UNAVAILABLE'),
    (400, -1016, 'ENDPOINT_UNAVAILABLE'),
    (400, -1020, 'ENDPOINT_UNAVAILABLE'),
    (500, -1000, 'UPSTREAM_UNAVAILABLE'),
    (400, -1008, 'UPSTREAM_UNAVAILABLE'),
    (400, -1102, 'HTTP_ERROR'),
    (200, -1102, 'BINANCE_ERROR'),
])
@pytest.mark.parametrize('endpoint', ['/api/v3/time', '/api/v3/account', '/api/v3/openOrders'])
def test_http_and_binance_codes_survive_without_upstream_text(status, upstream_code, category, endpoint, caplog):
    signed_urls = []
    def callback(request):
        if 'signature' in request.url.params:
            signed_urls.append(str(request.url))
        if request.url.path != endpoint:
            return good(request)
        # Deliberately poisonous fields: none may escape through API or logging.
        body = {'msg': DUMMY.secret, 'url': str(request.url), 'key': DUMMY.key}
        if upstream_code is not None:
            body['code'] = upstream_code
        return httpx.Response(status, json=body, headers={'X-Private': DUMMY.secret})
    async def action(reader, requests):
        data = await reader.read()
        assert data['code'] == category and data['status'] == 'Disconnected'
        expected = {'endpoint': endpoint, 'http_status': status}
        if upstream_code is not None:
            expected['binance_code'] = upstream_code
        if upstream_code == -1007:
            expected['timeout_phase'] = 'UPSTREAM'
        assert data['diagnostics'] == expected
        assert 'balances' not in data and 'open_orders' not in data
        assert (await reader.read())['diagnostics'] == expected
        reader._retry_at = 0
        encoded = json.dumps(data)
        for sensitive in [DUMMY.key, DUMMY.secret, 'signature=', *signed_urls]:
            assert sensitive not in encoded and sensitive not in caplog.text
        assert endpoint in caplog.text and category in caplog.text
    run(callback, action)


@pytest.mark.parametrize('status,category', [
    (200, 'INVALID_DATA'), (401, 'AUTH_FAILED'), (403, 'WAF_BLOCKED'),
    (404, 'ENDPOINT_UNAVAILABLE'), (451, 'REGION_RESTRICTED'),
    (502, 'UPSTREAM_UNAVAILABLE'), (503, 'UPSTREAM_UNAVAILABLE'),
    (429, 'RATE_LIMITED'), (418, 'RATE_LIMITED'), (307, 'REDIRECT_BLOCKED'),
])
def test_html_errors_preserve_http_status_and_do_not_follow_redirect(status, category, caplog):
    def callback(request):
        return httpx.Response(status, text='<html>'+DUMMY.secret+'</html>', headers={
            'Location': 'https://api.binance.com/?signature=never-follow', 'Retry-After': '120'})
    async def action(reader, requests):
        result = await reader.read()
        assert result['code'] == category
        assert result['diagnostics'] == {'endpoint': '/api/v3/time', 'http_status': status}
        assert len(requests) == 1
        if category == 'RATE_LIMITED':
            assert result['retry_after'] == 120
        assert DUMMY.secret not in json.dumps(result) and DUMMY.secret not in caplog.text
        assert 'never-follow' not in caplog.text
    run(callback, action)


@pytest.mark.parametrize('error,phase', [
    (httpx.ConnectTimeout, 'CONNECT'), (httpx.ReadTimeout, 'READ'),
    (httpx.WriteTimeout, 'WRITE'), (httpx.PoolTimeout, 'POOL'),
])
def test_transport_timeouts_are_not_binance_errors(error, phase, caplog):
    def callback(request):
        raise error(str(request.url)+DUMMY.secret, request=request)
    async def action(reader, requests):
        result = await reader.read()
        assert result['code'] == 'TIMEOUT'
        assert result['diagnostics'] == {'endpoint': '/api/v3/time', 'timeout_phase': phase}
        assert DUMMY.secret not in caplog.text
    run(callback, action)


@pytest.mark.parametrize('error,kind', [
    (httpx.ConnectError, 'CONNECT'), (httpx.ReadError, 'READ'),
    (httpx.WriteError, 'WRITE'), (httpx.RemoteProtocolError, 'PROTOCOL'),
    (httpx.ProxyError, 'PROXY'),
])
def test_network_errors_have_safe_type_only(error, kind, caplog):
    def callback(request):
        raise error(DUMMY.key+DUMMY.secret, request=request)
    async def action(reader, requests):
        result = await reader.read()
        assert result['code'] == 'NETWORK_ERROR'
        assert result['diagnostics'] == {'endpoint': '/api/v3/time', 'network_error': kind}
        assert DUMMY.key not in caplog.text and DUMMY.secret not in caplog.text
    run(callback, action)


@pytest.mark.parametrize('cause,kind', [(socket.gaierror, 'DNS'), (ssl.SSLError, 'TLS')])
def test_dns_tls_exception_chains_do_not_leak_details(cause, kind, caplog):
    def callback(request):
        try:
            raise cause(DUMMY.secret)
        except cause as exc:
            raise httpx.ConnectError(str(request.url)+DUMMY.key, request=request) from exc
    async def action(reader, requests):
        result = await reader.read()
        assert result['diagnostics']['network_error'] == kind
        assert DUMMY.secret not in caplog.text and DUMMY.key not in caplog.text
    run(callback, action)


def test_diagnostic_fields_are_allowlisted_not_arbitrary_strings():
    failure = SafeFailure('NETWORK_ERROR', endpoint='https://host/?signature=bad',
                          http_status=True, binance_code='-2015 '+DUMMY.secret,
                          network_error=DUMMY.key, timeout_phase=DUMMY.secret)
    assert failure.diagnostics == {}
    with pytest.raises(ValueError):
        SafeFailure(DUMMY.secret)


def test_poisonous_binance_code_is_not_echoed():
    async def action(reader, requests):
        result = await reader.read()
        assert result['code'] == 'HTTP_ERROR'
        assert 'binance_code' not in result['diagnostics']
        assert DUMMY.secret not in json.dumps(result)
    run(lambda request: httpx.Response(400, json={'code': DUMMY.secret}), action)


def test_protected_api_exposes_only_sanitized_diagnostics(monkeypatch):
    monkeypatch.setenv('BINANCE_TESTNET_API_KEY', DUMMY.key)
    monkeypatch.setenv('BINANCE_TESTNET_API_SECRET', DUMMY.secret)
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD', OWNER_PASSWORD)
    def callback(request):
        if request.url.path.endswith('/time'):
            return good(request)
        return httpx.Response(451, json={'code': 0, 'msg': str(request.url)+DUMMY.secret})
    monkeypatch.setattr('app.main.TestnetReader', lambda: Reader(DUMMY, transport=httpx.MockTransport(callback)))
    with TestClient(app) as client:
        assert client.get('/api/testnet/account').status_code == 401
        response = client.get('/api/testnet/account', auth=('aura', OWNER_PASSWORD))
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        assert response.json()['diagnostics'] == {'endpoint': '/api/v3/account', 'http_status': 451, 'binance_code': 0}
        for sensitive in [DUMMY.key, DUMMY.secret, OWNER_PASSWORD, 'signature=', 'Authorization']:
            assert sensitive not in response.text
        assert client.get('/').status_code == 200
        assert client.get('/api/health').json() == {'status': 'ok'}


def test_log_filter_blocks_authentication_headers_even_without_key_echo(caplog):
    reader = Reader(Credentials(), transport=httpx.MockTransport(good))
    with caplog.at_level(logging.DEBUG):
        for message in ['Authorization: Basic dummy-canary', 'X-MBX-APIKEY: dummy-canary',
                        'request signature=dummy-canary']:
            logging.getLogger('httpx').warning(message)
    asyncio.run(reader.close())
    assert 'dummy-canary' not in caplog.text
