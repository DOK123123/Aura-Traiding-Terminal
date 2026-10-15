"""Public linear preview only. Offline fixtures are not real market evidence."""
import asyncio,json,unittest
from decimal import Decimal
from unittest.mock import AsyncMock,patch
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from app.bybit_linear.client import Client,Identity,IDENTITY,MarketError,ticker
from app.bybit_linear.feed import TickerState,Feed
from app.bybit_linear.api import router,configured
from app.automated.strategy import strategy
from tests.test_auto42 import fixture,DUMMY_OWNER

NOW=1800000900

def response(rows,category='linear',symbol='BTCUSDT',time=None):
    return dict(retCode=0,time=int((NOW if time is None else time)*1000),result=dict(category=category,symbol=symbol,list=rows))

def quote():return response([dict(symbol='BTCUSDT',lastPrice='100',markPrice='100.01')])
def row(at):return [str(at*1000),'100','102','99','101','2','202']
def event(kind='snapshot',at=None,**data):return dict(topic='tickers.BTCUSDT',type=kind,ts=int((NOW if at is None else at)*1000),data=dict(symbol='BTCUSDT',**(dict(lastPrice='100',markPrice='101') if kind=='snapshot' else {}),**data))

class ParseTests(unittest.TestCase):
    def test_identity_never_accepts_spot_or_other_symbol(self):
        self.assertEqual(IDENTITY.data()['market_type'],'USDT_PERPETUAL')
        for values in (dict(category='spot'),dict(exchange='BINANCE'),dict(symbol='ETHUSDT'),dict(settlement='BTC')):
            with self.assertRaisesRegex(MarketError,'SOURCE_MISMATCH'):Identity(**values)
    def test_ticker_last_mark_and_no_candle_close_substitution(self):
        v=ticker(quote(),NOW);self.assertEqual(v['last_price'],'100');self.assertEqual(v['mark_price'],'100.01')
        for change in ('lastPrice','markPrice'):
            d=quote();del d['result']['list'][0][change]
            with self.assertRaises(MarketError):ticker(d,NOW)
    def test_stale_future_and_malformed_ticker(self):
        for data in (response([None]),response([],time=NOW),response([dict(symbol='ETHUSDT')]),response([dict(symbol='BTCUSDT',lastPrice='NaN',markPrice='1')]),response([dict(symbol='BTCUSDT',lastPrice='1E999999999',markPrice='1')]),response([dict(symbol='BTCUSDT',lastPrice='1E-999999999',markPrice='1')])):
            with self.assertRaises(MarketError):ticker(data,NOW)
        for delta in (-11,4):
            d=quote();d['time']=int((NOW+delta)*1000)
            with self.assertRaisesRegex(MarketError,'STALE_DATA'):ticker(d,NOW)
    def test_delta_merge_duplicate_order_reset_and_stale(self):
        now=[NOW];s=TickerState(lambda:now[0]);s.apply(event());now[0]+=1
        s.apply(event('delta',now[0],lastPrice='102'));self.assertEqual(s.read()['mark_price'],'101')
        self.assertFalse(s.apply(event('delta',NOW,lastPrice='999')));self.assertEqual(s.read()['last_price'],'102')
        now[0]+=11;self.assertEqual(s.read()['status'],'STALE');s.reset()
        with self.assertRaisesRegex(MarketError,'SNAPSHOT_REQUIRED'):s.apply(event('delta',now[0],lastPrice='103'))
    def test_subscription_rejection_and_missing_snapshot_fields(self):
        s=TickerState(lambda:NOW)
        with self.assertRaisesRegex(MarketError,'SUBSCRIPTION_REJECTED'):s.apply({'op':'subscribe','success':False})
        d=event();del d['data']['markPrice']
        with self.assertRaises(MarketError):s.apply(d)
    def test_preview_cannot_become_existing_auto42_signal_source(self):
        bars,snap,now=fixture();snap['source']='Bybit · USDT Perpetual / linear'
        with self.assertRaisesRegex(Exception,'SNAPSHOT_MISMATCH'):strategy(snap,bars,now[0])

class ClientTests(unittest.IsolatedAsyncioTestCase):
    def client(self,fn):return Client(httpx.MockTransport(fn),clock=lambda:NOW)
    async def test_instrument_contract_settlement_and_no_auth_headers(self):
        def handle(r):
            self.assertEqual(r.method,'GET');self.assertEqual(r.url.host,'api.bybit.com');self.assertNotIn('authorization',r.headers);self.assertNotIn('X-BAPI-API-KEY',r.headers)
            return httpx.Response(200,json=response([dict(symbol='BTCUSDT',contractType='LinearPerpetual',quoteCoin='USDT',settleCoin='USDT',status='Trading')]))
        c=self.client(handle);self.assertEqual(await c.verify_instrument(),IDENTITY.data());await c.close()
    async def test_all_frames_reverse_pages_normalized_and_closed(self):
        for tf,step in [('15m',900),('1h',3600),('4h',14400)]:
            end=NOW//step*step;start=end-1001*step;calls=[]
            def handle(r):
                calls.append(r);cursor=int(r.url.params['end']);remaining=[t for t in range(start,end,step) if t*1000<=cursor]
                return httpx.Response(200,json=response([row(t) for t in reversed(remaining[-1000:])]))
            c=self.client(handle);v=await c.candles(tf,start,end)
            self.assertEqual(v['count'],1001);self.assertEqual(len(calls),2);self.assertEqual(v['bars'][0]['time'],start);self.assertEqual(v['bars'][-1]['time']+step,end);self.assertEqual(v['bars'][0]['volume'],'2');await c.close()
    async def test_forming_exclusion_and_identical_duplicates_counted(self):
        end=NOW//900*900;start=end-1800
        c=self.client(lambda r:httpx.Response(200,json=response([row(end),row(end-900),row(start),row(start)])))
        v=await c.candles('15m',start,end);self.assertEqual(v['count'],2);self.assertEqual(v['forming_excluded'],1);self.assertEqual(v['duplicate_rows'],1);await c.close()
    async def test_missing_order_conflict_and_invalid_ohlcv_rejected(self):
        end=NOW//900*900;start=end-1800
        bad=row(start);bad[2]='90'
        changed=row(start);changed[4]='100.5'
        for rows in ([row(start)],[row(start),row(end-900)],[row(end-900),row(start),changed],[row(end-900),bad]):
            c=self.client(lambda r:httpx.Response(200,json=response(rows)))
            with self.assertRaises(MarketError):await c.candles('15m',start,end)
            await c.close()
    async def test_page_limits_and_timeframe_range_validation(self):
        c=self.client(lambda r:(_ for _ in ()).throw(AssertionError('network must not run')))
        for tf,start,end in [('15m',0,13001*900),('15m',NOW-901,NOW),('5m',0,900),('15m',NOW,NOW+900)]:
            with self.assertRaises(MarketError):await c.candles(tf,start,end)
        with self.assertRaisesRegex(MarketError,'SOURCE_MISMATCH'):await c.get('/v5/order/create',dict(category='linear',symbol='BTCUSDT'))
        await c.close()
    async def test_region_rate_limit_and_redirect_fail_closed(self):
        for status,code in [(403,'REGION_OR_ACCESS_RESTRICTED'),(451,'REGION_OR_ACCESS_RESTRICTED'),(429,'RATE_LIMIT'),(302,'REDIRECT_BLOCKED')]:
            calls=[];c=self.client(lambda r:(calls.append(r) or httpx.Response(status)))
            with self.assertRaisesRegex(MarketError,code):await c.quote()
            self.assertEqual(len(calls),1)
            if status==429:
                with self.assertRaisesRegex(MarketError,'RATE_LIMIT'):await c.quote()
                self.assertEqual(len(calls),1)
            await c.close()
    async def test_timeout_network_api_and_malformed_json(self):
        for exc,code in [(httpx.ReadTimeout('dummy-sensitive-marker'),'UPSTREAM_TIMEOUT'),(httpx.ConnectError('dummy-sensitive-marker'),'NETWORK_ERROR')]:
            calls=[]
            def handle(r):calls.append(r);raise exc
            c=self.client(handle)
            with patch('app.bybit_linear.client.asyncio.sleep'):
                with self.assertRaisesRegex(MarketError,code):await c.quote()
            self.assertEqual(len(calls),2);await c.close()
        for data in [{'retCode':10001},{'retCode':True},[]]:
            c=self.client(lambda r:httpx.Response(200,json=data))
            with self.assertRaises(MarketError):await c.quote()
            await c.close()
    async def test_rest_fallback_is_singleflight_and_rate_bounded(self):
        c=self.client(lambda r:httpx.Response(200,json=quote()));c.quote=AsyncMock(return_value=ticker(quote(),NOW));f=Feed(c,clock=lambda:NOW)
        values=await asyncio.gather(*(f.quote() for _ in range(8)));self.assertTrue(all(v['status']=='LIVE' for v in values));self.assertEqual(c.quote.await_count,1);await f.close()
    async def test_reconnect_requires_new_snapshot_and_uses_fixed_host(self):
        c=self.client(lambda r:httpx.Response(403));c.verify_instrument=AsyncMock(return_value=IDENTITY.data());connections=[]
        class Socket:
            def __init__(self,n):self.n=n;self.receives=0
            async def send(self,s):self.message=json.loads(s)
            async def recv(self):
                self.receives+=1
                if self.receives==1:return json.dumps(event() if self.n==1 else event('delta',lastPrice='102'))
                raise ConnectionError('dummy-sensitive-marker')
        @asynccontextmanager
        async def connector(url,**options):
            self.assertEqual(url,'wss://stream.bybit.com/v5/public/linear');connections.append(url);yield Socket(len(connections))
        f=Feed(c,connector,clock=lambda:NOW);f.start()
        try:
            async with asyncio.timeout(3):
                while len(connections)<2 or f.error!='SNAPSHOT_REQUIRED':await asyncio.sleep(.01)
            self.assertEqual(f.ticker.read()['status'],'DISCONNECTED')
        finally:await f.close()
    async def test_flag_default_off_and_owner_auth(self):
        with patch.dict('os.environ',{},clear=True):self.assertIsNone(configured())
        app=FastAPI();app.include_router(router);app.state.bybit_linear_preview=None
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                self.assertEqual((await c.get('/api/bybit-linear/ticker')).status_code,401)
                r=await c.get('/api/bybit-linear/ticker',auth=('aura',DUMMY_OWNER));self.assertEqual(r.status_code,503);self.assertEqual(r.json()['code'],'FEATURE_DISABLED');self.assertFalse(r.json()['execution_enabled'])

    async def test_wrong_perpetual_contract_blocks_ticker_before_fetch(self):
        calls=[]
        def handle(r):
            calls.append(r.url.path)
            return httpx.Response(200,json=response([dict(symbol='BTCUSDT',contractType='LinearFutures',quoteCoin='USDT',settleCoin='USDT',status='Trading')]))
        c=self.client(handle)
        with self.assertRaisesRegex(MarketError,'SOURCE_MISMATCH'):await c.quote()
        self.assertEqual(calls,['/v5/market/instruments-info']);await c.close()

    async def test_import_restricted_source_creates_no_dataset_or_paper_state(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from scripts.import_bybit_linear_history import download
        fake=AsyncMock();fake.verify_instrument.side_effect=MarketError('REGION_OR_ACCESS_RESTRICTED')
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'history.json'
            with patch('scripts.import_bybit_linear_history.Client',return_value=fake):
                with self.assertRaisesRegex(MarketError,'REGION_OR_ACCESS_RESTRICTED'):await download(SimpleNamespace(output=out,timeframe='15m',days=30))
            self.assertFalse(out.exists());fake.close.assert_awaited_once();fake.candles.assert_not_awaited()
