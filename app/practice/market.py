"""Only fixed-host public GET; no keys, fallback provider or order endpoints."""
import asyncio
import json
import time
import httpx
from app.automated.engine import DemoError
from .core import SOURCE,quote_checked

class Quotes:
    def __init__(self,transport=None,clock=time.time):
        self.clock=clock;self.client=httpx.AsyncClient(timeout=3,follow_redirects=False,transport=transport)
        self.lock=asyncio.Lock();self.cached=None;self.cached_at=0
    async def close(self):await self.client.aclose()
    async def get(self):
        async with self.lock:
            if self.cached and time.monotonic()-self.cached_at<1:return dict(quote_checked(self.cached,self.clock()))
            try:
                async with asyncio.timeout(4):
                    async with self.client.stream('GET','https://data-api.binance.vision/api/v3/trades',params={'symbol':'BTCUSDT','limit':1}) as r:
                        if r.status_code!=200:raise DemoError('QUOTE_UNAVAILABLE')
                        raw=bytearray()
                        async for b in r.aiter_bytes():
                            raw.extend(b)
                            if len(raw)>8192:raise DemoError('INVALID_QUOTE')
                        rows=json.loads(raw)
                        if type(rows) is not list or len(rows)!=1:raise DemoError('INVALID_QUOTE')
                        row=rows[0];q=dict(price=row['price'],time_ms=row['time'],trade_id=row['id'],source=SOURCE)
                        quote_checked(q,self.clock())
                        if self.cached and (q['time_ms']<self.cached['time_ms'] or q['trade_id']<self.cached['trade_id'] or (q['trade_id']==self.cached['trade_id'] and q!=self.cached)):raise DemoError('QUOTE_REGRESSION')
                        self.cached=q;self.cached_at=time.monotonic();return dict(q)
            except (httpx.HTTPError,TimeoutError):raise DemoError('QUOTE_UNAVAILABLE') from None
            except (ValueError,KeyError,TypeError):raise DemoError('INVALID_QUOTE') from None
