"""Dedicated public-only data reader for manual analysis; no ledger dependency."""
import asyncio
import time
from copy import deepcopy
from decimal import Decimal
from app.active43.bitget import Client,MarketError,number,IDENTITY,TIME
from app.models import Candle
from .aura_trader5_scenarios import STEPS,assess,wait


SAFE_CODES={'UPSTREAM_TIMEOUT','NETWORK_ERROR','RATE_LIMIT','REGION_OR_ACCESS_RESTRICTED',
    'UPSTREAM_CLOCK_OR_STALE_RESPONSE','HTTP_ERROR','UPSTREAM_API_ERROR','INVALID_DATA',
    'INVALID_TIMESTAMPS','INVALID_OHLCV','INVALID_RESPONSE','INCOMPLETE_HISTORY',
    'MISSING_CANDLES','SOURCE_MISMATCH','INVALID_RANGE','SNAPSHOT_EXPIRED',
    'RESPONSE_LIMIT','REDIRECT_BLOCKED','HISTORY_LIMIT','PAGE_LIMIT',
    'PAGINATION_STALLED','UNORDERED_CANDLES','CONFLICTING_DUPLICATE','INVALID_CONTRACT_METADATA','EXCHANGE_CLOSE_NOT_CONFIRMED'}


class AnalystService:
    def __init__(self,client=None,clock=time.time):
        self.clock=clock
        self.client=client
        self.closed=False
        self.lock=asyncio.Lock()
        self.cached=None
        self.cached_at=0
        self.retry_at=0

    async def close(self):
        self.closed=True
        if self.client is not None:await self.client.close()

    async def inspect(self):
        now=self.clock()
        if self.closed:return wait('ANALYST_UNAVAILABLE',now)
        if self.cached is not None and 0<=now-self.cached_at<30:
            value=deepcopy(self.cached)
            if now>=value['valid_until'] and value['scenario'] is not None:
                return wait('SCENARIO_EXPIRED',now)
            if value.get('asof_closed_at') is not None and int(now)//300*300!=value['asof_closed_at']:
                return wait('SNAPSHOT_EXPIRED',now)
            return value
        if now<self.retry_at:return wait('RATE_LIMIT_COOLDOWN',now)
        if self.lock.locked():return wait('ANALYSIS_BUSY',now)
        async with self.lock:
            try:
                if self.client is None:self.client=Client(clock=self.clock)
                async with asyncio.timeout(35):
                    response=await self.client.get(TIME,{})
                    server_ms=self.client.fresh_time(response['data']['serverTime'],check='serverTime',path=TIME)
                    at=min(self.clock(),server_ms/1000)
                    if int(at)//300!=int(self.clock())//300:
                        raise MarketError('EXCHANGE_CLOSE_NOT_CONFIRMED')
                    contract=await self.client.instrument()  # Public Futures identity + price tick.
                    places=contract.get('pricePlace')
                    if not isinstance(places,str) or not places.isascii() or not places.isdigit() or len(places)>2 or not 0<=int(places)<=12:
                        raise MarketError('INVALID_CONTRACT_METADATA')
                    tick=float(number(contract.get('priceEndStep'),True)*Decimal(10)**-int(places))
                    async def fetch(frame,step):
                        end=int(at)//step*step
                        raw=await self.client.candles(frame,end-200*step,end)
                        if raw.get('identity')!=IDENTITY:raise MarketError('SOURCE_MISMATCH')
                        bars=[Candle(b['time'],*[float(b[k]) for k in ('open','high','low','close','volume')]) for b in raw['bars']]
                        if len(bars)!=200:raise MarketError('INCOMPLETE_HISTORY')
                        return frame,bars
                    pairs=await asyncio.gather(*(fetch(f,s) for f,s in STEPS.items()),return_exceptions=True)
                    for value in pairs:
                        if isinstance(value,BaseException):raise value
                    received=self.clock()
                    if int(received)//300!=int(at)//300:raise MarketError('SNAPSHOT_EXPIRED')
                    result=assess(dict(pairs),received,tick)
                    result.update(received_at=received,request_duration_ms=round((received-now)*1000))
            except asyncio.CancelledError:
                raise
            except (MarketError,TimeoutError,ValueError,TypeError,KeyError,OverflowError) as exc:
                code=exc.code if isinstance(exc,MarketError) and exc.code in SAFE_CODES else 'UPSTREAM_TIMEOUT' if isinstance(exc,TimeoutError) else 'INVALID_CLOSED_HISTORY'
                result=wait(code,self.clock())
                if code=='RATE_LIMIT':self.retry_at=self.clock()+60
            self.cached=deepcopy(result);self.cached_at=self.clock()
            return result
