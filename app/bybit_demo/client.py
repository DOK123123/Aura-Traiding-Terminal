"""Fixed official Demo endpoint, HMAC V5 and a GET-only read allowlist."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import hashlib
import hmac
import json
import logging
import math
import os
import re
import socket
import ssl
import time
import traceback
from urllib.parse import urlencode

import httpx

BASE_URL = 'https://api-demo.bybit.com'
READ_PATHS = frozenset({'/v5/market/time', '/v5/account/wallet-balance',
                        '/v5/order/realtime', '/v5/order/history', '/v5/execution/list'})
CATEGORIES = frozenset({'spot', 'linear', 'inverse', 'option'})
MAX_PAGES = 4
PAGE_SIZE = 50
logger = logging.getLogger(__name__)

MESSAGES = {
    'KEY_INVALID': 'Bybit отклонил Demo API Key. Нужен HMAC-ключ именно Demo Trading, не Testnet или реального аккаунта.',
    'KEY_EXPIRED': 'Срок действия Demo API Key истёк. Обновите ключ в Demo Trading.',
    'SIGNATURE_INVALID': 'Bybit отклонил HMAC-подпись. Проверьте парный Demo Secret.',
    'PERMISSION_DENIED': 'Нет разрешения на чтение Demo account. Проверьте read-only permissions; торговые операции Aura не нужны.',
    'IP_RESTRICTED': 'IP сервиса не входит в разрешённые IP Demo API Key. Проверьте исходящие IP Render.',
    'AUTH_FAILED': 'Bybit отклонил авторизацию Demo account.',
    'CLOCK_ERROR': 'Не удалось синхронизировать время с Bybit Demo.',
    'RATE_LIMITED': 'Лимит запросов Bybit Demo. Повтор после разрешённого cooldown.',
    'REGION_RESTRICTED': 'Bybit ограничил доступ для региона/IP сервиса. Проверьте допустимость региона Render.',
    'HTTP_FORBIDDEN': 'HTTP 403 Bybit: возможны регион/IP restriction или IP rate limit. Пауза не менее 10 минут; это не доказательство неверного Secret.',
    'ENDPOINT_UNAVAILABLE': 'Demo endpoint или категория недоступны для этого аккаунта.',
    'ACCOUNT_MODE': 'Нужен Bybit Demo Unified Trading Account (UNIFIED) с поддержкой выбранной категории.',
    'INVALID_SYMBOL': 'Пара недоступна в выбранной категории Bybit Demo.',
    'PARAMETER_ERROR': 'Bybit отклонил параметры. Проверьте категорию и пару Demo account.',
    'HTTP_ERROR': 'Bybit Demo вернул HTTP error. Числовой status доступен в diagnostics.',
    'API_ERROR': 'Bybit Demo вернул ошибку API. Числовой retCode доступен в diagnostics.',
    'UPSTREAM_UNAVAILABLE': 'Bybit Demo временно недоступен. Повторим чтение автоматически.',
    'REDIRECT_BLOCKED': 'Перенаправление Demo-запроса заблокировано для защиты credentials.',
    'NETWORK_ERROR': 'Сетевая ошибка Bybit Demo. Проверьте DNS/TLS и исходящий доступ Render.',
    'TIMEOUT': 'Bybit Demo не ответил вовремя. Повторим чтение автоматически.',
    'INVALID_DATA': 'Bybit Demo вернул некорректные или несогласованные данные.',
}


@dataclass(frozen=True)
class Credentials:
    key: str = field(repr=False, default='')
    secret: str = field(repr=False, default='')

    @classmethod
    def from_env(cls) -> 'Credentials':
        return cls(os.getenv('BYBIT_DEMO_API_KEY', '').strip(),
                   os.getenv('BYBIT_DEMO_API_SECRET', '').strip())

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret)


class SafeFailure(Exception):
    def __init__(self, code, retry_after=30, *, endpoint=None, http_status=None,
                 ret_code=None, network_error=None, timeout_phase=None):
        if code not in MESSAGES:
            raise ValueError('Unsupported safe Demo failure category')
        self.code, self.retry_after = code, retry_after
        self.diagnostics = {}
        if endpoint in READ_PATHS:
            self.diagnostics['endpoint'] = endpoint
        if type(http_status) is int and 100 <= http_status <= 599:
            self.diagnostics['http_status'] = http_status
        if type(ret_code) is int and -1000000 <= ret_code <= 1000000:
            self.diagnostics['ret_code'] = ret_code
        if network_error in {'DNS', 'TLS', 'CONNECT', 'READ', 'WRITE', 'PROTOCOL', 'PROXY', 'NETWORK'}:
            self.diagnostics['network_error'] = network_error
        if timeout_phase in {'CONNECT', 'READ', 'WRITE', 'POOL', 'UPSTREAM', 'SNAPSHOT'}:
            self.diagnostics['timeout_phase'] = timeout_phase
        super().__init__(code)


class CredentialLogFilter(logging.Filter):
    def __init__(self, credentials):
        super().__init__()
        self.credentials = credentials

    def filter(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += ''.join(traceback.format_exception(*record.exc_info))
        sensitive = ('api-demo.bybit.com', 'x-bapi-sign', 'x-bapi-api-key',
                     'authorization:', 'authorization=', 'signature=')
        return not any(token in message.lower() for token in sensitive) and not any(
            value and value in message for value in (self.credentials.key, self.credentials.secret))


class BybitDemoReader:
    def __init__(self, credentials: Credentials | None = None, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._credentials = credentials if credentials is not None else Credentials.from_env()
        self._log_filter = CredentialLogFilter(self._credentials)
        self._filtered_loggers = [logging.getLogger('httpx'), logger]
        self._core_levels = {}
        for name in ['httpcore', *list(logging.root.manager.loggerDict)]:
            if name == 'httpcore' or name.startswith('httpcore.'):
                log = logging.getLogger(name)
                self._core_levels[log] = log.level
                log.setLevel(logging.WARNING)
                self._filtered_loggers.append(log)
        for log in self._filtered_loggers:
            log.addFilter(self._log_filter)
        # Logger filters do not propagate to children created after startup.
        # Guard output handlers too, including warnings/tracebacks from new leaves.
        self._filtered_handlers = set(logging.getLogger().handlers)
        for log in self._filtered_loggers:
            self._filtered_handlers.update(log.handlers)
        for handler in self._filtered_handlers:
            handler.addFilter(self._log_filter)
        self._client = httpx.AsyncClient(timeout=8, follow_redirects=False, transport=transport)
        self._lock = asyncio.Lock()
        self._cache = {}
        self._failure = None
        self._retry_at = self._request_at = 0
        self._offset_ms = 0
        self._synced_at = None
        self._active_endpoint = None

    @property
    def configured(self) -> bool:
        return self._credentials.configured

    async def close(self) -> None:
        await self._client.aclose()
        for log in self._filtered_loggers:
            log.removeFilter(self._log_filter)
        for handler in self._filtered_handlers:
            handler.removeFilter(self._log_filter)
        for log, level in self._core_levels.items():
            log.setLevel(level)

    @staticmethod
    def _network_kind(exc):
        current, seen = exc, set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, socket.gaierror):
                return 'DNS'
            if isinstance(current, ssl.SSLError):
                return 'TLS'
            current = current.__cause__ or current.__context__
        for kind, cls in [('PROXY', httpx.ProxyError), ('CONNECT', httpx.ConnectError),
                          ('READ', httpx.ReadError), ('WRITE', httpx.WriteError),
                          ('PROTOCOL', httpx.ProtocolError)]:
            if isinstance(exc, cls):
                return kind
        return 'NETWORK'

    @staticmethod
    def _timeout_phase(exc):
        for phase, cls in [('CONNECT', httpx.ConnectTimeout), ('READ', httpx.ReadTimeout),
                           ('WRITE', httpx.WriteTimeout), ('POOL', httpx.PoolTimeout)]:
            if isinstance(exc, cls):
                return phase
        return None

    def _retry_seconds(self, response, default=60):
        delays = []
        value = response.headers.get('Retry-After', '')
        if value:
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = parsedate_to_datetime(value).timestamp()-time.time()
                except (ValueError, TypeError, OverflowError):
                    delay = float('nan')
            if math.isfinite(delay):
                delays.append(delay)
        reset = response.headers.get('X-Bapi-Limit-Reset-Timestamp', '')
        if re.fullmatch(r'[0-9]{1,16}', reset):
            delays.append((int(reset)-(time.time()*1000+self._offset_ms))/1000)
        return max(1, min(86400, math.ceil(max(delays) if delays else default)))

    async def _get(self, path, params=None, *, signed=True):
        if path not in READ_PATHS or signed != (path != '/v5/market/time'):
            raise ValueError('Only allowlisted Demo GET reads with correct authentication are supported')
        self._active_endpoint = path
        delay = self._request_at-time.monotonic()
        if delay > 5:
            raise SafeFailure('RATE_LIMITED', math.ceil(delay), endpoint=path)
        if delay > 0:
            await asyncio.sleep(delay)
        query_string = urlencode(params or {})
        headers = {}
        if signed:
            if not self.configured or not re.fullmatch(r'[!-~]+', self._credentials.key):
                raise SafeFailure('KEY_INVALID', 60, endpoint=path)
            timestamp = str(int(time.time()*1000+self._offset_ms))
            recv_window = '5000'
            payload = timestamp+self._credentials.key+recv_window+query_string
            signature = hmac.new(self._credentials.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            headers = {'X-BAPI-API-KEY': self._credentials.key, 'X-BAPI-TIMESTAMP': timestamp,
                       'X-BAPI-RECV-WINDOW': recv_window, 'X-BAPI-SIGN': signature, 'X-BAPI-SIGN-TYPE': '2'}
        try:
            # No JSON body on GET; signed bytes match the query sent to the server.
            response = await self._client.get(BASE_URL+path, params=query_string, headers=headers)
        except httpx.TimeoutException as exc:
            raise SafeFailure('TIMEOUT', endpoint=path, timeout_phase=self._timeout_phase(exc)) from None
        except httpx.HTTPError as exc:
            raise SafeFailure('NETWORK_ERROR', endpoint=path, network_error=self._network_kind(exc)) from None
        try:
            data = response.json()
        except (ValueError, UnicodeError):
            data = None
        ret_code = data.get('retCode') if isinstance(data, dict) else None
        if type(ret_code) is not int or not -1000000 <= ret_code <= 1000000:
            ret_code = None
        details = dict(endpoint=path, http_status=response.status_code, ret_code=ret_code)
        if response.status_code in (418, 429) or ret_code in (10006, 10018, 429):
            raise SafeFailure('RATE_LIMITED', self._retry_seconds(response), **details)
        if ret_code in (10002, -1):
            raise SafeFailure('CLOCK_ERROR', **details)
        mapping = {10003:'KEY_INVALID', 10004:'SIGNATURE_INVALID', 10005:'PERMISSION_DENIED',
                   10007:'AUTH_FAILED', 10010:'IP_RESTRICTED', -2015:'KEY_EXPIRED', 33004:'KEY_EXPIRED',
                   10008:'ACCOUNT_MODE', 10028:'ACCOUNT_MODE', 100028:'ACCOUNT_MODE',
                   10009:'REGION_RESTRICTED', 10024:'REGION_RESTRICTED',
                   10017:'ENDPOINT_UNAVAILABLE', 10029:'INVALID_SYMBOL', 10001:'PARAMETER_ERROR'}
        if ret_code in mapping:
            category = mapping[ret_code]
            raise SafeFailure(category, 600 if category == 'REGION_RESTRICTED' else 60, **details)
        if ret_code == 10000:
            raise SafeFailure('TIMEOUT', timeout_phase='UPSTREAM', **details)
        status = response.status_code
        if 300 <= status < 400:
            raise SafeFailure('REDIRECT_BLOCKED', **details)
        if status == 451:
            raise SafeFailure('REGION_RESTRICTED', 600, **details)
        if status == 403:
            raise SafeFailure('HTTP_FORBIDDEN', max(600, self._retry_seconds(response)), **details)
        if status == 401:
            raise SafeFailure('AUTH_FAILED', 60, **details)
        if status in (404, 405, 410):
            raise SafeFailure('ENDPOINT_UNAVAILABLE', **details)
        if status >= 500 or ret_code == 10016:
            raise SafeFailure('UPSTREAM_UNAVAILABLE', **details)
        if not response.is_success:
            raise SafeFailure('HTTP_ERROR', **details)
        if ret_code is None:
            raise SafeFailure('INVALID_DATA', **details)
        if ret_code != 0:
            raise SafeFailure('API_ERROR', **details)
        if not isinstance(data.get('result'), dict):
            raise SafeFailure('INVALID_DATA', **details)
        if response.headers.get('X-Bapi-Limit-Status') == '0':
            self._request_at = time.monotonic()+self._retry_seconds(response, default=1)
        return data['result']

    async def _sync_clock(self, force=False):
        if not force and self._synced_at is not None and time.monotonic()-self._synced_at < 300:
            return
        before = time.time()*1000
        data = await self._get('/v5/market/time', signed=False)
        after = time.time()*1000
        nano = data.get('timeNano')
        if not isinstance(nano, str) or not re.fullmatch(r'[0-9]{1,22}', nano) or int(nano) <= 0:
            raise SafeFailure('INVALID_DATA')
        self._offset_ms = int(nano)//1000000-(before+after)/2
        self._synced_at = time.monotonic()

    async def _signed_read(self, path, params):
        await self._sync_clock()
        try:
            return await self._get(path, params)
        except SafeFailure as exc:
            if exc.code != 'CLOCK_ERROR':
                raise
        await self._sync_clock(force=True)
        return await self._get(path, params)

    @staticmethod
    def _amount(value, *, signed=False, optional=False):
        if optional and (value is None or value == ''):
            return None
        pattern = r'-?[0-9]{1,32}(?:\.[0-9]{1,24})?' if signed else r'[0-9]{1,32}(?:\.[0-9]{1,24})?'
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise SafeFailure('INVALID_DATA')
        return str(Decimal(value))

    @staticmethod
    def _text(value, pattern):
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise SafeFailure('INVALID_DATA')
        return value

    def _wallet(self, data):
        rows = data.get('list')
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise SafeFailure('INVALID_DATA')
        account = rows[0]
        if account.get('accountType') != 'UNIFIED' or not isinstance(account.get('coin'), list):
            raise SafeFailure('INVALID_DATA')
        balances, seen = [], set()
        for row in account['coin']:
            if not isinstance(row, dict):
                raise SafeFailure('INVALID_DATA')
            asset = self._text(row.get('coin'), r'[A-Z0-9]{1,20}')
            if asset in seen:
                raise SafeFailure('INVALID_DATA')
            seen.add(asset)
            balances.append(dict(asset=asset, wallet_balance=self._amount(row.get('walletBalance'), signed=True),
                                 equity=self._amount(row.get('equity'), signed=True),
                                 locked=self._amount(row.get('locked'), optional=True),
                                 usd_value=self._amount(row.get('usdValue'), signed=True, optional=True),
                                 spot_borrow=self._amount(row.get('spotBorrow'), optional=True)))
        totals = {name:self._amount(account.get(field), signed=True, optional=True) for name, field in [
            ('wallet_balance_usd', 'totalWalletBalance'), ('equity_usd', 'totalEquity'),
            ('available_balance_usd', 'totalAvailableBalance')]}
        return dict(account_type='UNIFIED', demo_balance=totals, balances=sorted(balances, key=lambda row:row['asset']),
                    available_assets=sorted(row['asset'] for row in balances if Decimal(row['wallet_balance']) > 0))

    def _order(self, row):
        result = {name:self._text(row.get(field), pattern) for name, field, pattern in [
            ('order_id', 'orderId', r'[A-Za-z0-9-]{1,64}'), ('symbol', 'symbol', r'[A-Z0-9-]{3,64}'),
            ('status', 'orderStatus', r'[A-Za-z0-9_]{1,40}'), ('side', 'side', r'Buy|Sell'),
            ('type', 'orderType', r'Market|Limit')]}
        result.update({name:self._amount(row.get(field)) for name, field in [
            ('price', 'price'), ('quantity', 'qty'), ('executed_quantity', 'cumExecQty')]})
        result['time'] = int(self._text(row.get('createdTime'), r'[0-9]{1,15}'))
        return result

    def _trade(self, row):
        result = {name:self._text(row.get(field), pattern) for name, field, pattern in [
            ('id', 'execId', r'[A-Za-z0-9-]{1,64}'), ('order_id', 'orderId', r'[A-Za-z0-9-]{1,64}'),
            ('symbol', 'symbol', r'[A-Z0-9-]{3,64}'), ('side', 'side', r'Buy|Sell'),
            ('exec_type', 'execType', r'[A-Za-z0-9_]{1,32}') ]}
        result.update({name:self._amount(row.get(field), optional=optional, signed=signed) for name, field, optional, signed in [
            ('price', 'execPrice', False, False), ('quantity', 'execQty', False, False),
            ('value', 'execValue', True, False), ('fee', 'execFee', True, True)]})
        currency = row.get('feeCurrency')
        result['fee_asset'] = self._text(currency, r'[A-Z0-9]{1,20}') if currency else None
        result['time'] = int(self._text(row.get('execTime'), r'[0-9]{1,15}'))
        return result

    async def _pages(self, path, params, *, trades=False, open_orders=False):
        rows, ids, cursors = [], set(), set()
        query = dict(params, limit=PAGE_SIZE)
        cursor = ''
        for _ in range(MAX_PAGES):
            data = await self._signed_read(path, query)
            if data.get('category') != params['category'] or not isinstance(data.get('list'), list):
                raise SafeFailure('INVALID_DATA')
            if len(data['list']) > PAGE_SIZE:
                raise SafeFailure('INVALID_DATA')
            for row in data['list']:
                if not isinstance(row, dict):
                    raise SafeFailure('INVALID_DATA')
                item = self._trade(row) if trades else self._order(row)
                ident = item['id'] if trades else item['order_id']
                if ident in ids or item['symbol'] != params['symbol']:
                    raise SafeFailure('INVALID_DATA')
                if open_orders and item['status'] not in {'New', 'PartiallyFilled', 'Untriggered', 'Triggered'}:
                    raise SafeFailure('INVALID_DATA')
                ids.add(ident)
                rows.append(item)
            cursor = data.get('nextPageCursor', '')
            if not isinstance(cursor, str) or len(cursor) > 2048:
                raise SafeFailure('INVALID_DATA')
            if not cursor:
                break
            if cursor in cursors or any(value and value in cursor for value in (self._credentials.key, self._credentials.secret)):
                raise SafeFailure('INVALID_DATA')
            cursors.add(cursor)
            query['cursor'] = cursor
        return rows, bool(cursor)

    async def read(self, section: str = 'account', symbol: str = 'BTCUSDT', category: str = 'spot') -> dict:
        if section not in {'account', 'history'} or category not in CATEGORIES or not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9-]{3,64}', symbol):
            raise ValueError('Unsupported Demo read scope')
        identity = dict(provider='BYBIT_DEMO', demo=True, virtual_funds=True, real_money=False, read_only=True,
                        symbol=symbol, category=category)
        if not self.configured:
            return dict(identity, status='Not configured', stale=True,
                        message='Добавьте BYBIT_DEMO_API_KEY и BYBIT_DEMO_API_SECRET в Environment Variables Render.')
        cache_key = (section, category, symbol)
        async with self._lock:
            if time.monotonic() < self._retry_at:
                return self._error(self._failure, max(1, math.ceil(self._retry_at-time.monotonic())), identity)
            cached = self._cache.get(cache_key)
            if cached and time.monotonic()-cached[0] < 60:
                return dict(cached[1], cache_age_seconds=max(0, time.monotonic()-cached[0]))
            try:
                async with asyncio.timeout(25):
                    params = dict(category=category, symbol=symbol)
                    if section == 'account':
                        result = self._wallet(await self._signed_read('/v5/account/wallet-balance', dict(accountType='UNIFIED')))
                        orders, more = await self._pages('/v5/order/realtime', dict(params, openOnly=0), open_orders=True)
                        result.update(open_orders=orders, open_orders_has_more=more, open_orders_scope=f'{category.upper()} / {symbol}')
                    else:
                        await self._sync_clock()
                        end_time = int(time.time()*1000+self._offset_ms)
                        params.update(startTime=end_time-7*86400000, endTime=end_time)
                        orders, more_orders = await self._pages('/v5/order/history', params)
                        trades, more_trades = await self._pages('/v5/execution/list', params, trades=True)
                        result = dict(orders=orders, trades=trades, orders_has_more=more_orders, trades_has_more=more_trades,
                                      limit=MAX_PAGES*PAGE_SIZE, window_days=7,
                                      message='История Bybit Demo выбранной категории/пары за доступные последние 7 дней; максимум 200 записей каждого типа.')
                result.update(identity, status='Connected', stale=False, checked_at=datetime.now(timezone.utc).isoformat())
                encoded = json.dumps(result)
                if any(value and value in encoded for value in (self._credentials.key, self._credentials.secret)):
                    raise SafeFailure('INVALID_DATA')
                if len(self._cache) >= 32 and cache_key not in self._cache:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[cache_key] = (time.monotonic(), result)
                self._failure = None
                return dict(result, cache_age_seconds=0)
            except TimeoutError:
                failure = SafeFailure('TIMEOUT', timeout_phase='SNAPSHOT')
            except SafeFailure as exc:
                failure = exc
            except (ValueError, TypeError, KeyError, OverflowError):
                failure = SafeFailure('INVALID_DATA')
            self._cache.clear()
            if 'endpoint' not in failure.diagnostics and self._active_endpoint in READ_PATHS:
                failure.diagnostics['endpoint'] = self._active_endpoint
            self._failure = failure
            self._retry_at = time.monotonic()+failure.retry_after
            logger.warning('Bybit Demo read failed: %s; diagnostics=%s; retry after %ss',
                           failure.code, json.dumps(failure.diagnostics, sort_keys=True), failure.retry_after)
            return self._error(failure, failure.retry_after, identity)

    @staticmethod
    def _error(failure, retry_after, identity):
        return dict(identity, status='Disconnected', stale=True, code=failure.code,
                    message=MESSAGES[failure.code], diagnostics=dict(failure.diagnostics), retry_after=retry_after,
                    checked_at=datetime.now(timezone.utc).isoformat())
