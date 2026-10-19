"""Fixed Bitget USDT perpetual public data. No keys, writes, redirects or fallback."""
import asyncio
import time
from decimal import Decimal as D

from app.async_workers import run_in_slot
from app.automated.engine import DemoError
from .bitget import Client, MarketError, number
from app.lab.models import Bar, digest, LabError
from .core import SOURCE, FILTERS, IDENTITY, plan
from .strategies import STEPS, signals


def analyze(bars, cfg):
    value = signals(bars, cfg['strategy'])[-1]
    return plan(value, bars[-1], STEPS[cfg['timeframe']], value.stop_distance if cfg['strategy'] == 'TREND_ATR' else None)


def quote_checked(value, now):
    """Active43 accepts only Bitget quotes, never the Practice/Spot validator."""
    try:
        if not isinstance(value, dict) or value.get('source') != SOURCE or value.get('identity') != IDENTITY:
            raise DemoError('QUOTE_SOURCE_MISMATCH')
        at = value['time_ms']
        if type(at) is not int or not -3000 <= now * 1000 - at <= 10000:
            raise DemoError('STALE_QUOTE')
        number(value['price'], True)
        return value
    except (KeyError, TypeError, MarketError):
        raise DemoError('INVALID_QUOTE') from None


PublicClient = Client


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
            row = await self.client.instrument()
            for key in ('pricePlace','volumePlace'):
                if type(row.get(key)) is not str or not row[key].isdigit() or not 0<=int(row[key])<=12:
                    raise DemoError('FUTURES_FILTERS_UNAVAILABLE')
            actual = dict(qty_step=row['sizeMultiplier'], min_qty=row['minTradeNum'], min_notional=row['minTradeUSDT'],
                          price_tick=str(number(row['priceEndStep'],True)*D(10)**-int(row['pricePlace'])))
            if any(number(actual[k],True)!=D(FILTERS[k]) for k in FILTERS):
                raise DemoError('FUTURES_FILTERS_CHANGED')
            if D(FILTERS['qty_step']) < D(10)**-int(row['volumePlace']):
                raise DemoError('FUTURES_FILTERS_CHANGED')
            self.max_market_qty = number(row['maxMarketOrderQty'],True)
            self.specs_checked = self.clock()
            self.client.verified_at = self.clock()
            self.specs_error = None
        except MarketError as exc:
            self.specs_error = exc.code
        except DemoError as exc:
            self.specs_error = exc.code
        except (ValueError, KeyError, TypeError, ArithmeticError):
            self.specs_error = 'FUTURES_FILTERS_UNAVAILABLE'
        if self.specs_error=='SOURCE_MISMATCH':raise DemoError('SOURCE_MISMATCH')
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
                    await self.client.check_time()
                    err = await self.specs()
                    raw = await self.client.candles(cfg['timeframe'], start, end)
                    if raw['identity'] != IDENTITY:
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
                                config_hash=digest(cfg), market_identity=IDENTITY)
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
