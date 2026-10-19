"""Bounded fixed-host Spot data. No keys, exchange writes or source fallback."""
import asyncio,time
from decimal import Decimal as D
import httpx
from app.lab.data import public_page
from app.lab.models import Bar,number,validate_series,digest,LabError
from app.async_workers import run_in_slot
from app.automated.engine import DemoError
from .core import SOURCE,FILTERS,plan
from .strategies import STEPS,signals


def analyze(bars,cfg):
    value=signals(bars,cfg['strategy'])[-1]
    return plan(value,bars[-1],STEPS[cfg['timeframe']],value.stop_distance if cfg['strategy']=='TREND_ATR' else None)


class Market:
    def __init__(self,clock=time.time,transport=None):
        self.clock=clock;self.client=httpx.AsyncClient(timeout=5,follow_redirects=False,transport=transport)
        self.lock=asyncio.Lock();self.slots=asyncio.Semaphore(1);self.cache=None;self.cached_at=0
        self.specs_checked=0;self.specs_error=None
    async def close(self):await self.client.aclose()
    async def specs(self):
        if self.specs_checked and 0<=self.clock()-self.specs_checked<86400:return self.specs_error
        try:
            raw=bytearray()
            async with self.client.stream('GET','https://data-api.binance.vision/api/v3/exchangeInfo',params={'symbol':'BTCUSDT'}) as r:
                if r.status_code!=200:raise DemoError('SPOT_FILTERS_UNAVAILABLE')
                async for b in r.aiter_bytes():
                    raw.extend(b)
                    if len(raw)>65536:raise DemoError('SPOT_FILTERS_UNAVAILABLE')
            import json
            symbols=json.loads(raw)['symbols']
            if len(symbols)!=1 or symbols[0]['symbol']!='BTCUSDT' or symbols[0]['status']!='TRADING':raise DemoError('SPOT_FILTERS_CHANGED')
            filters={f['filterType']:f for f in symbols[0]['filters']}
            actual=dict(qty_step=filters['LOT_SIZE']['stepSize'],min_qty=filters['LOT_SIZE']['minQty'],
                min_notional=(filters.get('NOTIONAL') or filters['MIN_NOTIONAL'])['minNotional'],price_tick=filters['PRICE_FILTER']['tickSize'])
            if any(D(actual[k])!=D(FILTERS[k]) for k in FILTERS):raise DemoError('SPOT_FILTERS_CHANGED')
            self.specs_checked=self.clock();self.specs_error=None
        except DemoError as exc:self.specs_error=exc.code
        except (httpx.HTTPError,ValueError,KeyError,TypeError):self.specs_error='SPOT_FILTERS_UNAVAILABLE'
        return self.specs_error
    async def snapshot(self,cfg):
        async with self.lock:
            now=int(self.clock());step=STEPS[cfg['timeframe']];end=now//step*step
            if self.cache and self.cache[2]//step*step==end and time.monotonic()-self.cached_at<10:return self.cache
            start=end//86400*86400-1000*step;cursor=start;bars=[]
            try:
                async with asyncio.timeout(18):
                    for _ in range(2):
                        if cursor>=end:break
                        rows=await public_page(self.client,dict(symbol='BTCUSDT',interval=cfg['timeframe'],startTime=cursor*1000,endTime=end*1000-1,limit=min(1000,(end-cursor)//step)))
                        if not isinstance(rows,list) or not rows or len(rows)>1000:raise DemoError('INVALID_MARKET_DATA')
                        for row in rows:
                            if (not isinstance(row,list) or len(row)<7 or type(row[0]) is not int or row[0]%1000
                                or row[0]//1000<cursor or row[6]!=(row[0]//1000+step)*1000-1):raise DemoError('INVALID_MARKET_DATA')
                            bars.append(Bar(row[0]//1000,*[number(row[i]) for i in (1,2,3,4,5)]))
                        cursor=bars[-1].time+step
                    validate_series(bars,step,end)
                    if len(bars)!=(end-start)//step or len(bars)<1000 or bars[0].time!=start or bars[-1].time+step!=end:raise DemoError('INCOMPLETE_HISTORY')
                    decision=await run_in_slot(self.slots,analyze,bars,cfg)
                    err=await self.specs()
                    if err:decision.update(direction=None,reason=err,error=err)
                now=int(self.clock())
                if now//step*step!=end:raise DemoError('STALE_DATA')
                decision.update(source=SOURCE,source_sha256=digest([b.data() for b in bars]),evaluated_at=now)
                self.cache=(bars,decision,now);self.cached_at=time.monotonic();return self.cache
            except DemoError:raise
            except LabError as exc:raise DemoError(exc.code) from None
            except (httpx.HTTPError,TimeoutError):raise DemoError('MARKET_UNAVAILABLE') from None
            except (ValueError,TypeError,KeyError):raise DemoError('INVALID_MARKET_DATA') from None
