"""Offline integrity/security checks; synthetic transport data is never signal evidence."""
import asyncio
import copy
import time
import httpx
import pytest
from app.manual_preview.history import archive_history, public_history, bounds, validate

START=1790812800
END=1790899200


def test_real_archive_complete_warmup_and_cost_labels():
    for frame in ('15m','1h','4h'):
        result=archive_history(frame,START,END,time.time())
        assert result['source'].startswith('BITGET_SAVED_REAL_ARCHIVE')
        assert len(result['bars'])==200+(END-START)//{'15m':900,'1h':3600,'4h':14400}[frame]
        assert result['quote_model']['historical_bid_ask'] is False
        assert result['statistical_result']=='NOT_EVALUATED'
        assert len(result['sha256'])==64


@pytest.mark.parametrize('frame,start,end',[
    ('1m',START,END),('15m',START+1,END),('15m',START,START),
    ('15m',START,START+6001*900),('4h',True,END),('15m',START,999999999999)])
def test_period_rejected_before_network(frame,start,end):
    with pytest.raises(ValueError):bounds(frame,start,end,time.time())


def test_archive_does_not_fake_missing_dates():
    with pytest.raises(ValueError,match='INCOMPLETE'):
        archive_history('15m',START-86400*150,START-86400*149,time.time())


def test_public_history_bounded_pagination_and_fixed_public_get():
    calls=[];first=START-200*900
    rows=[[str(t*1000),'100','102','99','101','1','0'] for t in range(first,END+900,900)]
    def handler(req):
        calls.append(req)
        cursor=int(req.url.params['endTime'])
        data=[r for r in rows if int(r[0])<=cursor][-200:]
        return httpx.Response(200,json={'code':'00000','data':list(reversed(data))})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await public_history(client,'15m',START,END,time.time())
    result=asyncio.run(run())
    assert len(result['bars'])==296 and len(calls)==2
    assert all(r.method=='GET' and r.url.host=='api.bitget.com' and r.url.path=='/api/v2/mix/market/history-candles' for r in calls)
    assert all(r.url.params['symbol']=='BTCUSDT' and r.url.params['productType']=='USDT-FUTURES' for r in calls)
    assert int(calls[1].url.params['endTime'])<int(calls[0].url.params['endTime'])


@pytest.mark.parametrize('bad',[
    {'code':'00000','data':[]}, {'code':'ERROR','data':[]}, {'code':'00000','data':[['nan','1','1','1','1','1']]},
    {'code':'00000','data':[[str((END+900)*1000),'1','1','1','1','1']]}])
def test_malformed_or_future_public_history_fails_closed(bad):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=bad))) as client:
            await public_history(client,'15m',START,END,time.time())
    with pytest.raises(ValueError):asyncio.run(run())


def test_public_response_size_limit():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*200001))) as client:
            await public_history(client,'15m',START,END,time.time())
    with pytest.raises(ValueError,match='RESPONSE_LIMIT'):asyncio.run(run())


def test_history_conflicting_duplicate_is_rejected():
    first=START-200*900
    rows=[[str(t*1000),'100','102','99','101','1'] for t in range(first,END,900)]
    calls=[]
    def handler(req):
        cursor=int(req.url.params['endTime']);data=copy.deepcopy([r for r in rows if int(r[0])<=cursor][-200:])
        if calls:data[-1][4]='100.5'
        calls.append(1)
        return httpx.Response(200,json={'code':'00000','data':data})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await public_history(client,'15m',START,END,time.time())
    with pytest.raises(ValueError,match='CONFLICT'):asyncio.run(run())
