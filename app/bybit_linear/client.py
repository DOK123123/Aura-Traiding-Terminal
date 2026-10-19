"""Fixed official Bybit V5 public GETs. No account credentials or account methods."""
import asyncio,json,time
from dataclasses import dataclass,asdict
from decimal import Decimal,InvalidOperation
import httpx
from app.lab.models import Bar,LabError

BASE='https://api.bybit.com'
WS='wss://stream.bybit.com/v5/public/linear'
STEPS={'15m':900,'1h':3600,'4h':14400}
INTERVAL={'15m':'15','1h':'60','4h':'240'}
PATHS={'/v5/market/instruments-info','/v5/market/tickers','/v5/market/kline'}
MAX_BARS=13000

class MarketError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)

@dataclass(frozen=True)
class Identity:
    exchange:str='BYBIT'
    market_type:str='USDT_PERPETUAL'
    category:str='linear'
    symbol:str='BTCUSDT'
    settlement:str='USDT'
    def data(self):return asdict(self)
    def __post_init__(self):
        if tuple(asdict(self).values())!=('BYBIT','USDT_PERPETUAL','linear','BTCUSDT','USDT'):raise MarketError('SOURCE_MISMATCH')

IDENTITY=Identity()


def number(value,positive=False):
    if not isinstance(value,str) or len(value)>80:raise MarketError('INVALID_DATA')
    try:n=Decimal(value)
    except InvalidOperation:raise MarketError('INVALID_DATA') from None
    if not n.is_finite() or n<0 or positive and n<=0:raise MarketError('INVALID_DATA')
    if n.adjusted()>30 or n.as_tuple().exponent<-30 or positive and n>Decimal('1e12'):raise MarketError('INVALID_DATA')
    return n


def stamp(value):
    if type(value) is str and value.isascii() and value.isdigit() and len(value)<=16:value=int(value)
    if type(value) is not int or not 0<value<10**14:raise MarketError('INVALID_TIMESTAMPS')
    return value


def identity_result(data):
    result=data.get('result') if isinstance(data,dict) else None
    if not isinstance(result,dict) or result.get('category')!='linear':raise MarketError('SOURCE_MISMATCH')
    return result


def ticker(data,now):
    result=identity_result(data);rows=result.get('list')
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get('symbol')!='BTCUSDT':raise MarketError('SOURCE_MISMATCH')
    row=rows[0];at=stamp(data.get('time'))
    if at>now*1000+3000 or now*1000-at>10000:raise MarketError('STALE_DATA')
    return dict(identity=IDENTITY.data(),last_price=str(number(row.get('lastPrice'),True)),
        mark_price=str(number(row.get('markPrice'),True)),server_at_ms=at,received_at=now,
        transport='REST',status='LIVE',price_semantics='PUBLIC_TICKER_NOT_EXECUTION_AUTHORITY')


class Client:
    steps=STEPS
    intervals=INTERVAL
    def __init__(self,transport=None,clock=time.time):
        self.clock=clock;self.http=httpx.AsyncClient(timeout=5,follow_redirects=False,transport=transport)
        self.slots=asyncio.Semaphore(2);self.cooldown=0
        self.instrument_lock=asyncio.Lock();self.verified_at=None
    async def close(self):await self.http.aclose()
    async def get(self,path,params):
        try:
            async with asyncio.timeout(12):return await self._get(path,params)
        except TimeoutError:raise MarketError('UPSTREAM_TIMEOUT') from None
    async def _get(self,path,params):
        if path not in PATHS or params.get('category')!='linear' or params.get('symbol')!='BTCUSDT':raise MarketError('SOURCE_MISMATCH')
        allowed={'category','symbol'}|({'interval','start','end','limit'} if path.endswith('/kline') else set())
        if set(params)-allowed:raise MarketError('UNSAFE_PARAMETERS')
        if self.clock()<self.cooldown:raise MarketError('RATE_LIMIT')
        async with asyncio.timeout(12):
            for attempt in range(2):
                try:
                    async with self.slots:
                        async with self.http.stream('GET',BASE+path,params=params) as r:
                            if r.status_code in (403,451):raise MarketError('REGION_OR_ACCESS_RESTRICTED')
                            if r.status_code in (418,429):
                                retry=r.headers.get('Retry-After','');delay=max(60,int(retry)) if retry.isdigit() and len(retry)<=6 else 60
                                self.cooldown=self.clock()+delay;raise MarketError('RATE_LIMIT')
                            if 300<=r.status_code<400:raise MarketError('REDIRECT_BLOCKED')
                            r.raise_for_status();raw=bytearray()
                            async for chunk in r.aiter_bytes():
                                if len(raw)+len(chunk)>1024*1024:raise MarketError('RESPONSE_LIMIT')
                                raw.extend(chunk)
                            data=json.loads(raw)
                            if not isinstance(data,dict) or type(data.get('retCode')) is not int:raise MarketError('INVALID_RESPONSE')
                            if data['retCode'] in (10006,10429):self.cooldown=self.clock()+60;raise MarketError('RATE_LIMIT')
                            if data['retCode']!=0:raise MarketError('UPSTREAM_API_ERROR')
                            return data
                except (httpx.RequestError,httpx.HTTPStatusError) as exc:
                    transient=not isinstance(exc,httpx.HTTPStatusError) or exc.response.status_code>=500
                    if attempt or not transient:raise MarketError('UPSTREAM_TIMEOUT' if isinstance(exc,httpx.TimeoutException) else 'NETWORK_ERROR' if isinstance(exc,httpx.RequestError) else 'HTTP_ERROR') from None
                    await asyncio.sleep(.25)
                except (ValueError,TypeError):raise MarketError('INVALID_RESPONSE') from None
        raise MarketError('UPSTREAM_TIMEOUT')
    async def verify_instrument(self):
        async with self.instrument_lock:
            if self.verified_at is not None and 0<=self.clock()-self.verified_at<300:return IDENTITY.data()
            result=await self._verify_instrument();self.verified_at=self.clock();return result
    async def _verify_instrument(self):
        result=identity_result(await self.get('/v5/market/instruments-info',dict(category='linear',symbol='BTCUSDT')))
        rows=result.get('list')
        if (not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or any(rows[0].get(k)!=v for k,v in
            dict(symbol='BTCUSDT',contractType='LinearPerpetual',quoteCoin='USDT',settleCoin='USDT',status='Trading').items())):raise MarketError('SOURCE_MISMATCH')
        return IDENTITY.data()
    async def quote(self):
        await self.verify_instrument()
        return ticker(await self.get('/v5/market/tickers',dict(category='linear',symbol='BTCUSDT')),self.clock())
    async def candles(self,timeframe,start,end):
        step=self.steps.get(timeframe)
        if (not step or type(start) is not int or type(end) is not int or start<0 or start%step or end%step or end<=start or end>self.clock()):raise MarketError('INVALID_RANGE')
        count=(end-start)//step
        if count>MAX_BARS:raise MarketError('HISTORY_LIMIT')
        bars={};cursor=end*1000-1;pages=duplicates=forming=0
        async with asyncio.timeout(60):
            while cursor>=start*1000:
                if pages>=15:raise MarketError('PAGE_LIMIT')
                data=await self.get('/v5/market/kline',dict(category='linear',symbol='BTCUSDT',interval=self.intervals[timeframe],start=start*1000,end=cursor,limit=min(1000,count)))
                result=identity_result(data)
                if result.get('symbol')!='BTCUSDT':raise MarketError('SOURCE_MISMATCH')
                rows=result.get('list');pages+=1
                if not isinstance(rows,list) or not rows or len(rows)>1000:raise MarketError('INCOMPLETE_HISTORY')
                previous=None;oldest=None
                for row in rows:
                    if not isinstance(row,list) or len(row)!=7:raise MarketError('INVALID_DATA')
                    at=stamp(row[0])
                    if at% (step*1000):raise MarketError('INVALID_TIMESTAMPS')
                    if previous is not None and at>previous:raise MarketError('UNORDERED_CANDLES')
                    previous=at;oldest=at
                    number(row[6])  # Turnover is quote currency; never use as BTC volume.
                    try:b=Bar(at//1000,*[number(row[i],i<5) for i in range(1,6)]);b.validate(step,at//1000+step)
                    except (ValueError,LabError):raise MarketError('INVALID_OHLCV') from None
                    if b.time+step>end or b.time+step>self.clock():forming+=1;continue
                    if b.time<start or at>cursor:raise MarketError('INVALID_RANGE')
                    if b.time in bars:
                        if bars[b.time]!=b:raise MarketError('CONFLICTING_DUPLICATE')
                        duplicates+=1
                    bars[b.time]=b
                if oldest is None or oldest>cursor:raise MarketError('PAGINATION_STALLED')
                cursor=oldest-1
                if len(bars)>MAX_BARS:raise MarketError('HISTORY_LIMIT')
        ordered=sorted(bars.values(),key=lambda b:b.time)
        if len(ordered)!=count or any(b.time!=start+i*step for i,b in enumerate(ordered)):raise MarketError('MISSING_CANDLES')
        return dict(identity=IDENTITY.data(),timeframe=timeframe,start=start,end_exclusive=end,
            received_at=self.clock(),count=len(ordered),pages=pages,duplicate_rows=duplicates,
            forming_excluded=forming,price_basis='LAST_TRADE_OHLC',bars=[b.data() for b in ordered])
