"""Fixed Bybit USDT perpetual public data. No keys, writes, redirects or fallback."""
import asyncio
import time
from decimal import Decimal as D

from app.async_workers import run_in_slot
from app.automated.engine import DemoError
from app.bybit_linear.client import Client, MarketError, IDENTITY as BYBIT_IDENTITY, number, stamp, identity_result
from app.lab.models import Bar, digest, LabError
from .core import SOURCE, FILTERS, plan
from .strategies import STEPS, signals


def analyze(bars, cfg):
    value = signals(bars, cfg['strategy'])[-1]
    return plan(value, bars[-1], STEPS[cfg['timeframe']], value.stop_distance if cfg['strategy'] == 'TREND_ATR' else None)


def quote_checked(value, now):
    """Active43 accepts only Bybit quotes, never the Practice/Spot validator."""
    try:
        if not isinstance(value, dict) or value.get('source') != SOURCE or value.get('identity') != BYBIT_IDENTITY.data():
            raise DemoError('QUOTE_SOURCE_MISMATCH')
        at = value['time_ms']
        if type(at) is not int or not -3000 <= now * 1000 - at <= 10000:
            raise DemoError('STALE_QUOTE')
        number(value['price'], True)
        return value
    except (KeyError, TypeError, MarketError):
        raise DemoError('INVALID_QUOTE') from None


class PublicClient(Client):
    """Add response-clock validation to the existing closed V5 GET allowlist."""
    steps={'5m':300,**Client.steps}
    intervals={'5m':'5',**Client.intervals}

    async def get(self, path, params):
        data = await super().get(path, params)
        at = stamp(data.get('time'))
        if not -3000 <= self.clock() * 1000 - at <= 10000:
            raise MarketError('UPSTREAM_CLOCK_OR_STALE_RESPONSE')
        return data


class Market:
    def __init__(self, clock=time.time, transport=None):
        self.clock = clock
        self.client = PublicClient(transport=transport, clock=clock)
        self.lock = asyncio.Lock()
        self.slots = asyncio.Semaphore(1)
        self.cache = None
        self.cached_at = 0
        self.specs_checked = None
        self.specs_error = None

    async def close(self):
        await self.client.close()

    async def specs(self):
        # Recheck at most five minutes after a successful check. A failed check
        # is never cached as success and cannot authorize a new position.
        if self.specs_checked is not None and 0 <= self.clock() - self.specs_checked < 300:
            return None
        try:
            result = identity_result(await self.client.get('/v5/market/instruments-info', dict(category='linear', symbol='BTCUSDT')))
            rows = result.get('list')
            expected = dict(symbol='BTCUSDT', contractType='LinearPerpetual', quoteCoin='USDT', settleCoin='USDT', status='Trading')
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or any(rows[0].get(k) != v for k, v in expected.items()):
                raise DemoError('SOURCE_MISMATCH')
            row = rows[0]
            lot = row['lotSizeFilter']
            actual = dict(qty_step=lot['qtyStep'], min_qty=lot['minOrderQty'], min_notional=lot['minNotionalValue'], price_tick=row['priceFilter']['tickSize'])
            if any(number(actual[k], True) != D(FILTERS[k]) for k in FILTERS):
                raise DemoError('FUTURES_FILTERS_CHANGED')
            # Verify that the frozen notional cap fits the published market
            # quantity bound at the current closed price (checked below).
            self.max_market_qty = number(lot['maxMktOrderQty'], True)
            self.specs_checked = self.clock()
            self.client.verified_at = self.clock()
            self.specs_error = None
        except MarketError as exc:
            self.specs_error = exc.code
        except DemoError as exc:
            self.specs_error = exc.code
        except (ValueError, KeyError, TypeError, ArithmeticError):
            self.specs_error = 'FUTURES_FILTERS_UNAVAILABLE'
        return self.specs_error

    async def snapshot(self, cfg):
        async with self.lock:
            now = int(self.clock())
            step = STEPS[cfg['timeframe']]
            end = now // step * step
            if (self.cache and self.cache[1].get('config_hash') == digest(cfg)
                    and self.cache[0][-1].time + step == end and 0 <= now - self.cache[2] < 10
                    and time.monotonic() - self.cached_at < 10):
                return self.cache
            start = end // 86400 * 86400 - 1000 * step
            try:
                async with asyncio.timeout(32):
                    err = await self.specs()
                    raw = await self.client.candles(cfg['timeframe'], start, end)
                    if raw['identity'] != BYBIT_IDENTITY.data():
                        raise DemoError('SOURCE_MISMATCH')
                    bars = [Bar.restore(b) for b in raw['bars']]
                    if len(bars) < 1000 or bars[0].time != start or bars[-1].time + step != end:
                        raise DemoError('INCOMPLETE_HISTORY')
                    decision = await run_in_slot(self.slots, analyze, bars, cfg)
                    if not err and D('2000') / bars[-1].close > self.max_market_qty:
                        err = 'FUTURES_FILTERS_CHANGED'
                    if err:
                        # Data can still close an existing position. A contract
                        # filter failure blocks entries, not virtual protection.
                        decision.update(direction=None, reason=err, error=err)
                now = int(self.clock())
                if now // step * step != end:
                    raise DemoError('STALE_DATA')
                decision.update(source=SOURCE, source_sha256=digest([b.data() for b in bars]), evaluated_at=now,
                                config_hash=digest(cfg), market_identity=BYBIT_IDENTITY.data())
                self.cache = (bars, decision, now)
                self.cached_at = time.monotonic()
                return self.cache
            except (MarketError, LabError) as exc:
                raise DemoError(exc.code) from None
            except TimeoutError:
                raise DemoError('MARKET_UNAVAILABLE') from None
            except (ValueError, KeyError, TypeError, ArithmeticError):
                raise DemoError('INVALID_MARKET_DATA') from None


class Quotes:
    """Read-only same-source display; never drives a financial transition."""
    def __init__(self, transport=None, clock=time.time):
        self.clock = clock
        self.client = PublicClient(transport=transport, clock=clock)
        self.lock = asyncio.Lock()
        self.cached = None
        self.cached_at = 0

    async def close(self):
        await self.client.close()

    async def get(self):
        async with self.lock:
            if self.cached and time.monotonic() - self.cached_at < 1:
                return dict(quote_checked(self.cached, self.clock()))
            try:
                async with asyncio.timeout(4):
                    q = await self.client.quote()
                value = dict(price=q['last_price'], mark_price=q['mark_price'], time_ms=q['server_at_ms'],
                             source=SOURCE, identity=q['identity'], price_basis='LAST_TRADE')
                quote_checked(value, self.clock())
                if self.cached and value['time_ms'] < self.cached['time_ms']:
                    raise DemoError('QUOTE_REGRESSION')
                self.cached = value
                self.cached_at = time.monotonic()
                return dict(value)
            except MarketError as exc:
                raise DemoError(exc.code) from None
            except TimeoutError:
                raise DemoError('QUOTE_UNAVAILABLE') from None
