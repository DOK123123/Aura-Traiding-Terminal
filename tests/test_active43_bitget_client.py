"""Bitget public REST contract tests. All HTTP data here are synthetic/offline."""
import asyncio
import json
import httpx
import pytest
from app.active43.bitget import Client,MarketError,PATHS,TIME,CONTRACTS,TICKER,HISTORY
from scripts.verify_active43 import PublicFixture


def test_no_private_spot_or_source_override_requests():
    async def run():
        calls=[]
        c=Client(clock=lambda:1700000030,transport=httpx.MockTransport(lambda r:calls.append(r)))
        for path,params in [('/api/v2/mix/order/place-order',{}),('/api/v2/spot/market/tickers',{}),
            (TICKER,dict(symbol='ETHUSDT',productType='USDT-FUTURES')),
            (TICKER,dict(symbol='BTCUSDT',productType='COIN-FUTURES')),
            (TICKER,dict(symbol='BTCUSDT',productType='USDT-FUTURES',host='https://evil.invalid'))]:
            with pytest.raises(MarketError,match='SOURCE_MISMATCH'):await c.get(path,params)
        assert calls==[] and PATHS=={TIME,CONTRACTS,TICKER,HISTORY}
        await c.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure',['code_type','business_error','request_stale','server_stale','ticker_stale','ticker_future','symbol','spot','margin','json','redirect'])
def test_malformed_clock_contract_ticker_and_business_errors_fail_closed(failure):
    async def run():
        f=PublicFixture()
        def handler(r):
            if failure=='json':return httpx.Response(200,text='not-json')
            if failure=='redirect':return httpx.Response(302,headers={'location':'https://evil.invalid'})
            d=f.handler(r).json();path=r.url.path
            if failure=='code_type':d['code']=0
            if failure=='business_error':d['code']='40017'
            if failure=='request_stale':d['requestTime']-=11000
            if failure=='server_stale' and path==TIME:d['data']['serverTime']=str(f.now[0]*1000-11000)
            if failure=='ticker_stale' and path==TICKER:d['data'][0]['ts']=str(f.now[0]*1000-11000)
            if failure=='ticker_future' and path==TICKER:d['data'][0]['ts']=str(f.now[0]*1000+3001)
            if failure=='symbol' and path==TICKER:d['data'][0]['symbol']='ETHUSDT'
            if failure=='spot' and path==CONTRACTS:d['data'][0]['symbolType']='spot'
            if failure=='margin' and path==CONTRACTS:d['data'][0]['supportMarginCoins']=['BTC']
            return httpx.Response(200,json=d)
        c=Client(clock=lambda:f.now[0],transport=httpx.MockTransport(handler))
        with pytest.raises(MarketError):await c.quote()
        await c.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure',[None,'duplicate','conflict','unordered','gap','forming'])
def test_candle_utc_end_boundary_volume_duplicates_and_order(failure):
    async def run():
        f=PublicFixture();start=f.at-3*900;end=f.at
        def handler(r):
            assert int(r.url.params['endTime'])%900000==0
            d=f.handler(r).json();rows=d['data']
            if failure in ('duplicate','conflict'):
                other=list(rows[0]);rows.insert(1,other)
                if failure=='conflict':other[4]='68001'
            if failure=='unordered':rows.reverse()
            if failure=='gap':rows.pop(1)
            if failure=='forming':rows.append([str(end*1000),'68000','68100','67900','68000','10','680000'])
            return httpx.Response(200,json=d)
        c=Client(clock=lambda:f.now[0],transport=httpx.MockTransport(handler))
        if failure in ('conflict','unordered','gap'):
            with pytest.raises(MarketError):await c.candles('15m',start,end)
        else:
            d=await c.candles('15m',start,end)
            assert [b['time'] for b in d['bars']]==[start,start+900,start+1800]
            assert d['bars'][0]['volume']=='100' # not quote turnover 6800000
            assert d['duplicate_rows']==(1 if failure=='duplicate' else 0)
            assert d['forming_excluded']==(1 if failure=='forming' else 0)
        await c.close()
    asyncio.run(run())


def test_rate_limit_uses_cooldown_and_has_no_fallback():
    async def run():
        calls=[]
        def handler(r):calls.append(r);return httpx.Response(429,headers={'Retry-After':'120'})
        c=Client(clock=lambda:1700000030,transport=httpx.MockTransport(handler))
        for _ in range(2):
            with pytest.raises(MarketError,match='RATE_LIMIT'):await c.check_time()
        assert len(calls)==1 and c.cooldown==1700000150
        await c.close()
    asyncio.run(run())


@pytest.mark.parametrize('price',['0','-1','NaN','Infinity','1e30',True])
def test_invalid_current_prices_never_become_actionable_quotes(price):
    async def run():
        f=PublicFixture()
        def handler(r):
            d=f.handler(r).json()
            if r.url.path==TICKER:d['data'][0]['lastPr']=price
            return httpx.Response(200,json=d)
        c=Client(clock=lambda:f.now[0],transport=httpx.MockTransport(handler))
        with pytest.raises(MarketError):await c.quote()
        await c.close()
    asyncio.run(run())
