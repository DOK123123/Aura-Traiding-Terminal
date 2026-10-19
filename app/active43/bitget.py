"""Bitget public USDT-M perpetual GET allowlist; no credentials or order methods."""
import asyncio
import json
import time
from decimal import Decimal, InvalidOperation

import httpx
from app.lab.models import Bar, LabError
from .core import IDENTITY

BASE = 'https://api.bitget.com'
STEPS = {'5m':300, '15m':900, '1h':3600, '4h':14400}
INTERVAL = {'5m':'5m', '15m':'15m', '1h':'1H', '4h':'4H'}
TIME = '/api/v2/public/time'
CONTRACTS = '/api/v2/mix/market/contracts'
TICKER = '/api/v2/mix/market/ticker'
HISTORY = '/api/v2/mix/market/history-candles'
PATHS = {TIME, CONTRACTS, TICKER, HISTORY}


class MarketError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def number(value, positive=False):
    if not isinstance(value, str) or len(value)>80:
        raise MarketError('INVALID_DATA')
    try:
        n = Decimal(value)
    except InvalidOperation:
        raise MarketError('INVALID_DATA') from None
    if not n.is_finite() or n<0 or positive and (n<=0 or n>Decimal('1e12')) or n.adjusted()>30 or n.as_tuple().exponent<-30:
        raise MarketError('INVALID_DATA')
    return n


def stamp(value):
    if type(value) is str and value.isascii() and value.isdigit() and len(value)<=16:
        value = int(value)
    if type(value) is not int or not 0<value<10**14:
        raise MarketError('INVALID_TIMESTAMPS')
    return value


class Client:
    def __init__(self, transport=None, clock=time.time):
        self.clock = clock
        self.http = httpx.AsyncClient(timeout=5, follow_redirects=False, transport=transport)
        self.slots = asyncio.Semaphore(2)
        self.cooldown = 0
        self.instrument_lock = asyncio.Lock()
        self.verified_at = None
        self.contract = None

    async def close(self):
        await self.http.aclose()

    def fresh_time(self, value):
        at = stamp(value)
        if not -3000 <= self.clock()*1000-at <= 10000:
            raise MarketError('UPSTREAM_CLOCK_OR_STALE_RESPONSE')
        return at

    async def get(self, path, params):
        if path not in PATHS:
            raise MarketError('SOURCE_MISMATCH')
        expected = {} if path==TIME else dict(symbol='BTCUSDT',productType='USDT-FUTURES')
        allowed = set(expected) | ({'granularity','startTime','endTime','limit'} if path==HISTORY else set())
        if set(params)-allowed or any(params.get(k)!=v for k,v in expected.items()):
            raise MarketError('SOURCE_MISMATCH')
        if path==TIME and params:
            raise MarketError('SOURCE_MISMATCH')
        if self.clock()<self.cooldown:
            raise MarketError('RATE_LIMIT')
        try:
            async with asyncio.timeout(12):
                for attempt in range(2):
                    try:
                        async with self.slots:
                            async with self.http.stream('GET',BASE+path,params=params) as r:
                                if r.status_code in (403,451):raise MarketError('REGION_OR_ACCESS_RESTRICTED')
                                if r.status_code in (418,429):
                                    retry=r.headers.get('Retry-After','')
                                    self.cooldown=self.clock()+(max(60,int(retry)) if retry.isdigit() and len(retry)<=6 else 60)
                                    raise MarketError('RATE_LIMIT')
                                if 300<=r.status_code<400:raise MarketError('REDIRECT_BLOCKED')
                                r.raise_for_status()
                                raw=bytearray()
                                async for chunk in r.aiter_bytes():
                                    if len(raw)+len(chunk)>1024*1024:raise MarketError('RESPONSE_LIMIT')
                                    raw.extend(chunk)
                                data=json.loads(raw)
                                if not isinstance(data,dict) or type(data.get('code')) is not str:raise MarketError('INVALID_RESPONSE')
                                if data['code']=='429':self.cooldown=self.clock()+60;raise MarketError('RATE_LIMIT')
                                if data['code']!='00000':raise MarketError('UPSTREAM_API_ERROR')
                                self.fresh_time(data.get('requestTime'))
                                if 'symbol' in data and data['symbol']!='BTCUSDT':raise MarketError('SOURCE_MISMATCH')
                                if 'productType' in data and data['productType']!='USDT-FUTURES':raise MarketError('SOURCE_MISMATCH')
                                return data
                    except (httpx.RequestError,httpx.HTTPStatusError) as exc:
                        transient=not isinstance(exc,httpx.HTTPStatusError) or exc.response.status_code>=500
                        if attempt or not transient:
                            raise MarketError('UPSTREAM_TIMEOUT' if isinstance(exc,httpx.TimeoutException) else 'NETWORK_ERROR' if isinstance(exc,httpx.RequestError) else 'HTTP_ERROR') from None
                        await asyncio.sleep(.25)
                    except (ValueError,TypeError):raise MarketError('INVALID_RESPONSE') from None
        except TimeoutError:
            raise MarketError('UPSTREAM_TIMEOUT') from None
        raise MarketError('UPSTREAM_TIMEOUT')

    async def check_time(self):
        data=await self.get(TIME,{})
        try:self.fresh_time(data['data']['serverTime'])
        except (KeyError,TypeError):raise MarketError('INVALID_RESPONSE') from None

    async def instrument(self):
        async with self.instrument_lock:
            if self.verified_at is not None and 0<=self.clock()-self.verified_at<300:
                return self.contract
            data=await self.get(CONTRACTS,dict(productType='USDT-FUTURES',symbol='BTCUSDT'))
            rows=data.get('data')
            expected=dict(symbol='BTCUSDT',baseCoin='BTC',quoteCoin='USDT',symbolType='perpetual',symbolStatus='normal')
            if (not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict)
                    or any(rows[0].get(k)!=v for k,v in expected.items()) or rows[0].get('supportMarginCoins')!=['USDT']):
                raise MarketError('SOURCE_MISMATCH')
            self.contract=rows[0];self.verified_at=self.clock()
            return self.contract

    async def quote(self):
        await self.check_time()
        await self.instrument()
        data=await self.get(TICKER,dict(productType='USDT-FUTURES',symbol='BTCUSDT'))
        rows=data.get('data')
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get('symbol')!='BTCUSDT':
            raise MarketError('SOURCE_MISMATCH')
        row=rows[0]
        return dict(identity=dict(IDENTITY),last_price=str(number(row.get('lastPr'),True)),
                    mark_price=str(number(row.get('markPrice'),True)),server_at_ms=self.fresh_time(row.get('ts')))

    async def candles(self, timeframe, start, end):
        step=STEPS.get(timeframe)
        if (not step or type(start) is not int or type(end) is not int or start<0 or start%step or end%step
                or end<=start or end>self.clock()):raise MarketError('INVALID_RANGE')
        count=(end-start)//step
        if count>1300:raise MarketError('HISTORY_LIMIT')
        cursor=end;bars={};pages=forming=duplicates=0
        while cursor>start:
            if pages>=8:raise MarketError('PAGE_LIMIT')
            left=max(start,cursor-200*step)
            # Bitget rounds endTime DOWN to a candle boundary and excludes that
            # boundary. Exactly cursor*1000 is required; minus 1 loses a closed bar.
            data=await self.get(HISTORY,dict(productType='USDT-FUTURES',symbol='BTCUSDT',granularity=INTERVAL[timeframe],
                                           startTime=left*1000,endTime=cursor*1000,limit=min(200,(cursor-left)//step)))
            rows=data.get('data');pages+=1
            if not isinstance(rows,list) or not rows or len(rows)>200:raise MarketError('INCOMPLETE_HISTORY')
            previous=None;oldest=None
            for row in rows:
                if not isinstance(row,list) or len(row)!=7:raise MarketError('INVALID_DATA')
                at=stamp(row[0])
                if at%(step*1000):raise MarketError('INVALID_TIMESTAMPS')
                if previous is not None and at<previous:raise MarketError('UNORDERED_CANDLES')
                previous=at;oldest=at if oldest is None else min(oldest,at)
                number(row[6]) # quote turnover; row[5] is base BTC volume
                try:
                    b=Bar(at//1000,*[number(row[i],i<5) for i in range(1,6)])
                    b.validate(step,b.time+step)
                except LabError:raise MarketError('INVALID_OHLCV') from None
                if b.time+step>end or b.time+step>self.clock():forming+=1;continue
                if b.time<left or b.time>=cursor:raise MarketError('INVALID_RANGE')
                if b.time in bars:
                    if bars[b.time]!=b:raise MarketError('CONFLICTING_DUPLICATE')
                    duplicates+=1
                bars[b.time]=b
            if oldest is None or oldest>=cursor*1000:raise MarketError('PAGINATION_STALLED')
            cursor=oldest//1000
        ordered=sorted(bars.values(),key=lambda b:b.time)
        if len(ordered)!=count or any(b.time!=start+i*step for i,b in enumerate(ordered)):raise MarketError('MISSING_CANDLES')
        return dict(identity=dict(IDENTITY),bars=[b.data() for b in ordered],pages=pages,forming_excluded=forming,duplicate_rows=duplicates)
