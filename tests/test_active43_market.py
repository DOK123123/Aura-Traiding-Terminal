"""Offline bounded-source and production/replay parity tests; fake prices only."""
import asyncio,json
from bisect import bisect_left
from decimal import Decimal as D
import httpx,pytest
from app.active43.market import Market,analyze
from app.active43.core import plan
from app.active43.strategies import config,STEPS,PARAMETERS
from app.lab.models import Bar
from app.automated.engine import DemoError
from scripts.research_active43 import rolling_signals

@pytest.mark.parametrize('tf',list(STEPS))
@pytest.mark.parametrize('failure',[None,'forming','gap','redirect','filters'])
def test_public_get_only_closed_candles_and_filters(tf,failure):
    async def run():
        step=STEPS[tf];now=1700000000//86400*86400+7*3600+30;end=now//step*step;start=end//86400*86400-1000*step
        calls=[]
        def handler(req):
            calls.append(req);assert req.method=='GET' and req.url.host=='data-api.binance.vision'
            if req.url.path=='/api/v3/exchangeInfo':
                return httpx.Response(200,json={'symbols':[{'symbol':'BTCUSDT','status':'TRADING','filters':[
                    {'filterType':'LOT_SIZE','stepSize':'0.00001','minQty':'0.00001'},
                    {'filterType':'NOTIONAL','minNotional':'10' if failure=='filters' else '5'},
                    {'filterType':'PRICE_FILTER','tickSize':'0.01'}]}]})
            assert req.url.path=='/api/v3/klines'
            if failure=='redirect':return httpx.Response(302,headers={'location':'https://evil.invalid/'})
            left=int(req.url.params['startTime'])//1000;limit=int(req.url.params['limit'])
            rows=[[t*1000,'100','101','99','100','100',(t+step)*1000-1] for t in range(left,min(end,left+step*limit),step)]
            if left==start and failure=='gap':rows.pop(4)
            if failure=='forming' and rows and rows[-1][0]//1000+step==end:rows.append([end*1000,'100','101','99','100','100',(end+step)*1000-1])
            return httpx.Response(200,json=rows)
        market=Market(clock=lambda:now,transport=httpx.MockTransport(handler))
        try:
            if failure in ('forming','gap','redirect'):
                with pytest.raises(DemoError):await market.snapshot(config('DONCHIAN',tf))
            else:
                bars,decision,at=await market.snapshot(config('DONCHIAN',tf))
                assert bars[0].time==start and bars[-1].time+step==end and at==now
                if failure=='filters':assert decision['error']=='SPOT_FILTERS_CHANGED' and decision['direction'] is None
                else:
                    assert decision['signal_at']==end
                    count=len(calls);await market.snapshot(config('DONCHIAN',tf));assert len(calls)==count
            assert all(r.url.path in ('/api/v3/klines','/api/v3/exchangeInfo') for r in calls)
        finally:await market.close()
    asyncio.run(run())

@pytest.mark.parametrize('tf',list(STEPS))
@pytest.mark.parametrize('name',list(PARAMETERS))
def test_rolling_day_research_equals_native_live_prefix(tf,name):
    step=STEPS[tf];start=1700000000//86400*86400;bars=[]
    for i in range(1800):
        price=D(100)+D(i%39)/10+D(i)/100
        bars.append(Bar(start+i*step,price,price+1,price-1,price+D('.1'),D(100+i%17)))
    times=[b.time for b in bars];decisions=rolling_signals(bars,name,step)
    for i in (1500,1559,1728):
        at=bars[i].time+step;left=bisect_left(times,at//86400*86400-1000*step)
        window=bars[left:i+1];d=decisions[i]
        # The live window anchors on CLOSED time, including the UTC-midnight
        # candle. This test intentionally includes such a boundary.
        assert analyze(window,config(name,tf))==plan(d,bars[i],step,d.stop_distance if name=='TREND_ATR' else None)

@pytest.mark.parametrize('tf',list(STEPS))
def test_research_rolls_window_on_closed_midnight_not_open_date(tf,monkeypatch):
    from app.lab.strategies import Decision
    import scripts.research_active43 as runner
    step=STEPS[tf];start=1700000000//86400*86400
    bars=[Bar(start+i*step,D(100),D(101),D(99),D(100),D(1)) for i in range(1400)]
    def prefix_lengths(window,name):return [Decision(stop_distance=D(i+1)) for i in range(len(window))]
    monkeypatch.setattr(runner,'signals',prefix_lengths)
    values=runner.rolling_signals(bars,'DONCHIAN',step)
    midnight_index=((1000*step)//86400+1)*86400//step-1
    assert values[midnight_index].stop_distance==D(1000)
    assert values[midnight_index+1].stop_distance==D(1001)
