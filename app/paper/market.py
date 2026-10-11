"""Injected public-market reads; no private exchange API or credentials."""
import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
import time

from .models import Bar, Window, PaperError, STEPS


class Market:
    def __init__(self, fetch, clock=None):
        self.fetch = fetch
        self.clock = clock or (lambda:int(time.time()*1000))
        self.lock = asyncio.Lock()

    async def window(self, symbol: str, timeframe: str) -> Window:
        if symbol != 'BTCUSDT' or timeframe not in STEPS:
            raise PaperError('UNSUPPORTED_MARKET')
        try:
            async with asyncio.timeout(25):
                async with self.lock:
                    data = await self.fetch(symbol,timeframe)
            now = self.clock()
            if not isinstance(data,dict) or (data.get('symbol'),data.get('timeframe')) != (symbol,timeframe):
                raise PaperError('INVALID_MARKET_DATA')
            if data.get('stale') is not False:
                raise PaperError('STALE_DATA')
            fetched = datetime.fromisoformat(data['fetched_at'])
            if fetched.tzinfo is None or not -1000 <= now-int(fetched.timestamp()*1000) <= 30000:
                raise PaperError('STALE_DATA')
            candles = data['candles']
            if not isinstance(candles,list) or not 1 <= len(candles) <= 500:
                raise PaperError('INVALID_MARKET_DATA')
            bars = []
            for candle in candles:
                prices = []
                if not isinstance(candle,dict) or type(candle.get('time')) is not int:
                    raise PaperError('INVALID_MARKET_DATA')
                volume = candle.get('volume')
                if type(volume) not in (int,float) or not math.isfinite(volume) or volume < 0:
                    raise PaperError('INVALID_MARKET_DATA')
                for field in ('open','high','low','close'):
                    raw = candle[field]
                    if type(raw) not in (int,float) or not math.isfinite(raw):
                        raise PaperError('INVALID_MARKET_DATA')
                    prices.append(Decimal(str(raw)))
                bars.append(Bar(candle['time'],*prices))
            window = Window(symbol,timeframe,data['source'],now,tuple(bars))
            window.validate(now)
            if data.get('last_closed_at') != bars[-1].time+STEPS[timeframe]:
                raise PaperError('INVALID_MARKET_DATA')
            return window
        except PaperError:
            raise
        except TimeoutError:
            raise PaperError('MARKET_TIMEOUT') from None
        except (KeyError,ValueError,TypeError,InvalidOperation,OverflowError):
            raise PaperError('INVALID_MARKET_DATA') from None
        except Exception:
            # Do not include upstream exception bodies/URLs in logs or responses.
            raise PaperError('MARKET_UNAVAILABLE') from None
