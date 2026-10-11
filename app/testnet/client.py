"""Official Spot Testnet reads only. No order-writing methods or endpoints."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from email.utils import parsedate_to_datetime
import hashlib
import hmac
import json
import logging
import math
import os
import re
import time
import traceback
from urllib.parse import urlencode

import httpx

BASE_URL = 'https://testnet.binance.vision'
READ_PATHS = frozenset({'/api/v3/time', '/api/v3/account', '/api/v3/openOrders',
                        '/api/v3/allOrders', '/api/v3/myTrades'})
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Credentials:
    key: str = field(repr=False, default='')
    secret: str = field(repr=False, default='')

    @classmethod
    def from_env(cls):
        return cls(os.getenv('BINANCE_TESTNET_API_KEY', '').strip(),
                   os.getenv('BINANCE_TESTNET_API_SECRET', '').strip())

    @property
    def configured(self):
        return bool(self.key and self.secret)


class SafeFailure(Exception):
    """Only fixed safe codes are carried across the public API boundary."""
    def __init__(self, code, retry_after=30):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)


MESSAGES = {
    'AUTH_FAILED': 'Неверные Testnet credentials или отсутствует разрешение USER_DATA.',
    'TIMEOUT': 'Testnet не ответил вовремя. Повторим чтение автоматически.',
    'UNAVAILABLE': 'Testnet временно недоступен. Повторим чтение автоматически.',
    'RATE_LIMITED': 'Достигнут лимит запросов Testnet. Ожидаем разрешённого повтора.',
    'CLOCK_ERROR': 'Не удалось синхронизировать время с Testnet.',
    'INVALID_DATA': 'Testnet вернул некорректные данные.',
    'INVALID_SYMBOL': 'Эта торговая пара недоступна в Binance Spot Testnet.',
}


class CredentialLogFilter(logging.Filter):
    def __init__(self, credentials):
        super().__init__()
        self.credentials = credentials

    def filter(self, record):
        # httpx logs full URLs at INFO; never record signed Testnet URLs.
        message = record.getMessage()
        if record.exc_info:
            message += ''.join(traceback.format_exception(*record.exc_info))
        return ('testnet.binance.vision' not in message and not any(
            value and value in message for value in (self.credentials.key, self.credentials.secret)))


class TestnetReader:
    def __init__(self, credentials=None, *, transport=None):
        self._credentials = credentials if credentials is not None else Credentials.from_env()
        self._log_filter = CredentialLogFilter(self._credentials)
        self._filtered_loggers = [logging.getLogger('httpx'), logger]
        # Prevent low-level debug output containing transport details.
        self._core_levels = {}
        for name in ['httpcore', *list(logging.root.manager.loggerDict)]:
            if name == 'httpcore' or name.startswith('httpcore.'):
                log = logging.getLogger(name)
                self._core_levels[log] = log.level
                log.setLevel(logging.WARNING)
                self._filtered_loggers.append(log)
        for log in self._filtered_loggers:
            log.addFilter(self._log_filter)
        self._client = httpx.AsyncClient(timeout=8, follow_redirects=False, transport=transport)
        self._lock = asyncio.Lock()
        self._cache = {}
        self._retry_at = 0
        self._failure = None
        self._offset_ms = 0
        self._synced_at = None

    @property
    def configured(self):
        return self._credentials.configured

    async def close(self):
        await self._client.aclose()
        for log in self._filtered_loggers:
            log.removeFilter(self._log_filter)
        for log, level in self._core_levels.items():
            log.setLevel(level)

    @staticmethod
    def _retry_seconds(response):
        value = response.headers.get('Retry-After', '')
        try:
            delay = float(value) if value else 60
        except ValueError:
            try:
                delay = parsedate_to_datetime(value).timestamp()-time.time()
            except (ValueError, TypeError, OverflowError):
                delay = 60
        if not math.isfinite(delay):
            delay = 60
        return max(1, min(86400, math.ceil(delay)))

    async def _get(self, path, params=None, *, signed=False):
        if path not in READ_PATHS:
            raise ValueError('Only allowlisted Testnet reads are supported')
        query = dict(params or {})
        headers = {}
        if signed:
            query.update(recvWindow=5000, timestamp=int(time.time()*1000+self._offset_ms))
            payload = urlencode(query)
            signature = hmac.new(self._credentials.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            query_string = payload+'&signature='+signature
            headers['X-MBX-APIKEY'] = self._credentials.key
        else:
            query_string = urlencode(query)
        try:
            response = await self._client.get(BASE_URL+path, params=query_string, headers=headers)
        except httpx.TimeoutException:
            raise SafeFailure('TIMEOUT') from None
        except httpx.HTTPError:
            raise SafeFailure('UNAVAILABLE') from None
        if response.status_code in (418, 429):
            raise SafeFailure('RATE_LIMITED', self._retry_seconds(response))
        try:
            data = response.json()
        except (ValueError, UnicodeError):
            raise SafeFailure('INVALID_DATA') from None
        code = data.get('code') if isinstance(data, dict) else None
        if code == -1021:
            raise SafeFailure('CLOCK_ERROR')
        if response.status_code in (401, 403) or code in (-2014, -2015, -1022):
            raise SafeFailure('AUTH_FAILED', 60)
        if code == -1121:
            raise SafeFailure('INVALID_SYMBOL')
        # Redirects are never followed, even if sent by a compromised upstream.
        if not response.is_success or (isinstance(code, int) and code < 0):
            raise SafeFailure('UNAVAILABLE')
        return data

    async def _sync_clock(self, force=False):
        if not force and self._synced_at is not None and time.monotonic()-self._synced_at < 300:
            return
        before = time.time()*1000
        data = await self._get('/api/v3/time')
        after = time.time()*1000
        if not isinstance(data, dict) or type(data.get('serverTime')) is not int or data['serverTime'] <= 0:
            raise SafeFailure('INVALID_DATA')
        self._offset_ms = data['serverTime']-(before+after)/2
        self._synced_at = time.monotonic()

    async def _signed_read(self, path, params=None):
        await self._sync_clock()
        try:
            return await self._get(path, params, signed=True)
        except SafeFailure as exc:
            if exc.code != 'CLOCK_ERROR':
                raise
        await self._sync_clock(force=True)
        return await self._get(path, params, signed=True)

    @staticmethod
    def _amount(value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,32}(?:\.[0-9]{1,24})?', value):
            raise SafeFailure('INVALID_DATA')
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise SafeFailure('INVALID_DATA') from None
        if not number.is_finite() or number < 0:
            raise SafeFailure('INVALID_DATA')
        return number

    @staticmethod
    def _name(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9]{1,20}', value):
            raise SafeFailure('INVALID_DATA')
        return value

    @staticmethod
    def _integer(value):
        if type(value) is not int or value < 0:
            raise SafeFailure('INVALID_DATA')
        return value

    @staticmethod
    def _enum(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9_]{1,32}', value):
            raise SafeFailure('INVALID_DATA')
        return value

    def _balances(self, account):
        if not isinstance(account, dict) or not isinstance(account.get('balances'), list):
            raise SafeFailure('INVALID_DATA')
        result, seen = [], set()
        for row in account['balances']:
            if not isinstance(row, dict):
                raise SafeFailure('INVALID_DATA')
            asset = self._name(row.get('asset'))
            if asset in seen:
                raise SafeFailure('INVALID_DATA')
            seen.add(asset)
            free, locked = self._amount(row.get('free')), self._amount(row.get('locked'))
            with localcontext() as context:
                context.prec = 64  # Preserve account quantities, never round through float.
                total = str(free+locked)
            result.append(dict(asset=asset, free=str(free), locked=str(locked), total=total))
        return sorted(result, key=lambda row:row['asset'])

    def _orders(self, rows):
        if not isinstance(rows, list):
            raise SafeFailure('INVALID_DATA')
        result = []
        for row in rows:
            if not isinstance(row, dict):
                raise SafeFailure('INVALID_DATA')
            item = {key:self._enum(row.get(key)) for key in ('status','side','type')}
            item['symbol'] = self._name(row.get('symbol'))
            item.update(orderId=self._integer(row.get('orderId')), time=self._integer(row.get('time')))
            item.update({key:str(self._amount(row.get(key))) for key in ('price','origQty','executedQty')})
            result.append(item)
        return result

    def _trades(self, rows):
        if not isinstance(rows, list):
            raise SafeFailure('INVALID_DATA')
        result = []
        for row in rows:
            if not isinstance(row, dict) or type(row.get('isBuyer')) is not bool:
                raise SafeFailure('INVALID_DATA')
            item = {key:self._integer(row.get(key)) for key in ('id','orderId','time')}
            item.update(symbol=self._name(row.get('symbol')), commissionAsset=self._name(row.get('commissionAsset')),
                        side='BUY' if row['isBuyer'] else 'SELL')
            item.update({key:str(self._amount(row.get(key))) for key in ('price','qty','quoteQty','commission')})
            result.append(item)
        return result

    async def read(self, section='account', symbol='BTCUSDT'):
        if section not in ('account', 'history'):
            raise ValueError('Unsupported Testnet read section')
        if section == 'history' and (not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9]{5,20}', symbol)):
            raise ValueError('Unsupported history symbol')
        cache_key = 'account' if section == 'account' else ('history', symbol)
        if not self.configured:
            return dict(status='Not configured', testnet=True, read_only=True, stale=True,
                        message='Добавьте Testnet credentials в Environment Variables Render.')
        async with self._lock:
            if time.monotonic() < self._retry_at:
                return self._error(self._failure, max(1, int(self._retry_at-time.monotonic())+1))
            cached = self._cache.get(cache_key)
            if cached and time.monotonic()-cached[0] < 60:
                return dict(cached[1], cache_age_seconds=max(0, time.monotonic()-cached[0]))
            try:
                async with asyncio.timeout(20):
                    if section == 'account':
                        balances = self._balances(await self._signed_read('/api/v3/account'))
                        orders = self._orders(await self._signed_read('/api/v3/openOrders'))
                        result = dict(balances=balances, available_assets=[b['asset'] for b in balances if Decimal(b['free'])>0],
                                      open_orders=orders, open_orders_scope='ALL SYMBOLS')
                    else:
                        orders = self._orders(await self._signed_read('/api/v3/allOrders', dict(symbol=symbol,limit=100)))
                        trades = self._trades(await self._signed_read('/api/v3/myTrades', dict(symbol=symbol,limit=100)))
                        if any(row['symbol'] != symbol for row in orders+trades):
                            raise SafeFailure('INVALID_DATA')
                        result = dict(symbol=symbol, orders=orders, trades=trades, limit=100,
                                      message=f'Последние 100 ордеров и сделок {symbol}, доступных в Testnet.')
                result.update(status='Connected', testnet=True, read_only=True, stale=False,
                              checked_at=datetime.now(timezone.utc).isoformat())
                # Whitelisting is primary; this guard also rejects credential echoes.
                encoded = json.dumps(result)
                if any(value and value in encoded for value in (self._credentials.key,self._credentials.secret)):
                    raise SafeFailure('INVALID_DATA')
                self._cache[cache_key] = (time.monotonic(), result)
                self._failure = None
                return dict(result, cache_age_seconds=0)
            except TimeoutError:
                failure = SafeFailure('TIMEOUT')
            except SafeFailure as exc:
                failure = exc
            except (ValueError, TypeError, KeyError, OverflowError):
                failure = SafeFailure('INVALID_DATA')
            self._cache.clear()
            self._failure = failure
            self._retry_at = time.monotonic()+failure.retry_after
            logger.warning('Testnet read failed: %s; retry after %ss', failure.code, failure.retry_after)
            return self._error(failure, failure.retry_after)

    @staticmethod
    def _error(failure, retry_after):
        return dict(status='Disconnected', testnet=True, read_only=True, stale=True,
                    code=failure.code, message=MESSAGES[failure.code], retry_after=retry_after,
                    checked_at=datetime.now(timezone.utc).isoformat())
