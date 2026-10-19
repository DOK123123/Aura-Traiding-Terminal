"""Synthetic TEST ONLY fixtures; no source/API injection into the application.

Used solely by offline unit/PostgreSQL CLI verification. Production imports none
of this module. Natural historical tests use real closed-prefix analysis instead.
"""
from copy import deepcopy
from decimal import Decimal as D
from app.lab.models import Bar,digest
from app.automated.engine import DemoError
from app.active43.core import SOURCE
from app.active43.strategies import STEPS

class FixtureMarket:
    def __init__(self,side='LONG',timeframe='15m'):
        self.side=side;self.step=STEPS[timeframe];self.signal=True;self.failure=None
        start=1700000000//86400*86400-1000*self.step
        self.bars=[Bar(start+i*self.step,D(100),D(101),D(99),D(100),D(100)) for i in range(1000)]
    async def close(self):pass
    async def snapshot(self,cfg):
        if self.failure:raise DemoError(self.failure)
        at=self.bars[-1].time+self.step
        decision=dict(direction=self.side if self.signal else None,reason='TEST_ONLY_SYNTHETIC' if self.signal else 'NO_SIGNAL',
            source=SOURCE,source_sha256=digest([b.data() for b in self.bars]),signal_at=at,
            stop_loss='98' if self.side=='LONG' else '102',take_profit='104' if self.side=='LONG' else '96',
            exit_long=False,exit_short=False,atr='2')
        return self.bars,decision,at+30
    def add(self,open='100',high='101',low='99',close='100'):
        self.bars.append(Bar(self.bars[-1].time+self.step,*map(D,(open,high,low,close,'100'))))
        if len(self.bars)>1290:self.bars=self.bars[-1290:]

class PublicFixture:
    """TEST ONLY public Bitget V2-shaped market, native indicators (no forced decision)."""
    def __init__(self, side='LONG'):
        self.side=side;self.step=900;self.at=1700000000//86400*86400
        self.now=[self.at+30];self.failure=None;self.requests=[]
        self.bars=[Bar(self.at-(1000-i)*900,D(68000),D(68100),D(67900),D(68000),D(100)) for i in range(1000)]
    def add(self,kind):
        sign=1 if self.side=='LONG' else -1
        if kind=='signal':o,c,h,l=68000,68000+sign*300,68400 if sign==1 else 68100,67900 if sign==1 else 67600
        elif kind=='fill':o,c,h,l=68000+sign*300,68000+sign*320,68400 if sign==1 else 67800,68200 if sign==1 else 67600
        elif kind=='update':o,c,h,l=68000+sign*320,68000+sign*330,68400 if sign==1 else 67800,68200 if sign==1 else 67600
        else:o,c,h,l=68000+sign*330,68000+sign*400,70000 if sign==1 else 67800,68200 if sign==1 else 66000
        self.bars.append(Bar(self.at,*map(D,(o,h,l,c,100))));self.at+=900;self.now[0]=self.at+30
    def handler(self,request):
        import httpx
        self.requests.append(request)
        assert request.method=='GET' and request.url.host=='api.bitget.com'
        path=request.url.path
        if path!='/api/v2/public/time':
            assert request.url.params['productType']=='USDT-FUTURES' and request.url.params['symbol']=='BTCUSDT'
        if self.failure:return httpx.Response(self.failure,text='OFFLINE_TEST_ONLY_FAILURE')
        if path.endswith('/time'):
            data={'serverTime':str(self.now[0]*1000)}
        elif path.endswith('/contracts'):
            data=[dict(symbol='BTCUSDT',baseCoin='BTC',quoteCoin='USDT',symbolType='perpetual',symbolStatus='normal',supportMarginCoins=['USDT'],
                minTradeNum='0.0001',sizeMultiplier='0.0001',minTradeUSDT='5',priceEndStep='1',pricePlace='1',volumePlace='4',maxMarketOrderQty='220')]
        elif path.endswith('/ticker'):
            data=[dict(symbol='BTCUSDT',lastPr=str(self.bars[-1].close),markPrice=str(self.bars[-1].close),ts=str(self.now[0]*1000))]
        else:
            assert path=='/api/v2/mix/market/history-candles'
            start=int(request.url.params['startTime']);end=int(request.url.params['endTime']);limit=int(request.url.params['limit'])
            bars=[b for b in self.bars if start<=b.time*1000<end][-limit:]
            data=[[str(b.time*1000),*[str(v) for v in (b.open,b.high,b.low,b.close,b.volume)],str(b.close*b.volume)] for b in bars]
        return httpx.Response(200,json=dict(code='00000',requestTime=self.now[0]*1000,data=data))
