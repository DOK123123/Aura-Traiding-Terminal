"""Offline public probes: no credentials, portfolios or exchange orders."""
import asyncio
import json
import socket
import ssl
import time
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.exchange_diagnostics import probes as p
from app.exchange_diagnostics.api import router,configured,Diagnostics

NOW=1800000900

def quote(exchange='BITGET'):
    return [dict(symbol='BTCUSDT',lastPr='100',markPrice='101',ts=str(NOW*1000))] if exchange=='BITGET' else dict(symbol='BTC-USDT',lastPrice='100',closeTime=NOW*1000)
def payload(data,exchange='BITGET',code=None):return dict(code=code if code is not None else ('00000' if exchange=='BITGET' else 0),data=data)
def contract(exchange):
    return [dict(symbol='BTC-USDT',currency='USDT',asset='BTC',status=1)] if exchange=='BINGX' else [dict(symbol='BTCUSDT',quoteCoin='USDT',baseCoin='BTC',symbolType='perpetual',supportMarginCoins=['USDT'],symbolStatus='normal')]
def bars(exchange='BITGET'):
    start=NOW*1000//900000*900000
    return [[str(start-i*900000),'100','102','99','101','2','202'] for i in range(4,-1,-1)] if exchange=='BITGET' else [dict(time=start-i*900000,open='100',high='102',low='99',close='101',volume='2') for i in range(5)]

class Parsing(unittest.TestCase):
    def test_contract_identity(self):
        for ex in p.REST:
            self.assertEqual(p.contract(ex,contract(ex))['settlement'],'USDT')
            d=contract(ex);d[0]['symbol']='BTCUSD'
            with self.assertRaises(p.ProbeError):p.contract(ex,d)
        d=contract('BITGET');d[0]['symbolType']='delivery'
        with self.assertRaises(p.ProbeError):p.contract('BITGET',d)
    def test_ticker_freshness_and_missing_mark(self):
        self.assertEqual(p.ticker('BITGET',quote(),NOW)['mark_price'],'101')
        d=quote();del d[0]['markPrice'];self.assertIsNone(p.ticker('BITGET',d,NOW)['mark_price'])
        for at in (NOW-31,NOW+4):
            d=quote();d[0]['ts']=str(at*1000)
            with self.assertRaisesRegex(p.ProbeError,'STALE_DATA'):p.ticker('BITGET',d,NOW)
    def test_mark_timestamp_not_receipt_or_funding_substitution(self):
        d=dict(symbol='BTC-USDT',markPrice='100',updateTime=(NOW-3600)*1000)
        self.assertEqual(p.mark(d,NOW)['mark_freshness'],'UNVERIFIED')
    def test_candles_closed_chronological_gap_duplicates_ohlc(self):
        for ex in p.REST:self.assertEqual(p.candles(ex,bars(ex),'15m',NOW)['count'],4)
        for change in ('duplicate','gap','ohlc','timestamp','future','order'):
            d=bars()
            if change=='duplicate':d[1]=d[0]
            if change=='gap':del d[1]
            if change=='ohlc':d[0][2]='90'
            if change=='timestamp':d[0][0]=str(int(d[0][0])+1)
            if change=='future':d[-1][0]=str(NOW*1000+900000)
            if change=='order':d[0],d[1]=d[1],d[0]
            with self.assertRaises(p.ProbeError,msg=change):p.candles('BITGET',d,'15m',NOW)
    def test_invalid_numbers(self):
        for v in ('NaN','Infinity','1E999999','1E-999999',True,None,'-1','0'):
            with self.assertRaises(p.ProbeError):p.number(v)
    def test_ws_parsers(self):
        d=dict(arg=dict(instType='USDT-FUTURES',channel='ticker',instId='BTCUSDT'),data=quote())
        self.assertEqual(p.ws_message('BITGET',json.dumps(d),NOW)['last_price'],'100')
        for topic,key in [('lastPrice','c'),('markPrice','p')]:
            d=dict(dataType='BTC-USDT@'+topic,data=dict(s='BTC-USDT',E=NOW*1000,**{key:'100'}))
            self.assertIn('server_at_ms',p.ws_message('BINGX',json.dumps(d),NOW))
        self.assertEqual(p.ws_message('BINGX','Ping',NOW),{'heartbeat':'Ping'})
    def test_network_classification(self):
        for exc,code in [(socket.gaierror(),'DNS_ERROR'),(ssl.SSLError(),'TLS_ERROR'),(httpx.ReadTimeout('dummy'),'TIMEOUT')]:self.assertEqual(p.network_error(exc).code,code)

class Requests(unittest.IsolatedAsyncioTestCase):
    async def test_http_success_errors_api_codes_json_and_timeout(self):
        for status,body,expected in [(200,payload(quote()),'AVAILABLE'),(403,{},'BLOCKED_403'),(451,{},'BLOCKED_451'),(429,{},'RATE_LIMITED'),(200,payload([],code='40001'),'UNAVAILABLE'),(200,[],'INVALID_RESPONSE'),(200,'not-json','INVALID_RESPONSE')]:
            async def handler(request):
                self.assertEqual(request.method,'GET');self.assertEqual(request.url.host,'api.bitget.com');self.assertNotIn('authorization',request.headers)
                return httpx.Response(status,json=body) if not isinstance(body,str) else httpx.Response(status,text=body)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with patch.object(p.time,'time',return_value=NOW):r=await p.get(client,'BITGET','ticker')
            self.assertEqual(r['status'],expected,(status,body,r))
        async def timeout(request):raise httpx.ReadTimeout('dummy')
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:self.assertEqual((await p.get(client,'BITGET','ticker'))['status'],'TIMEOUT')
    async def test_ws_disconnect_bounded_clean_close(self):
        calls=[]
        @asynccontextmanager
        async def connector(*a,**kw):
            calls.append(1)
            class W:
                async def send(self,x):pass
                async def ping(self):
                    f=asyncio.get_running_loop().create_future();f.set_result(None);return f
                async def recv(self):raise OSError('dummy disconnect')
            try:yield W()
            finally:calls.append('closed')
        r=await p.websocket('BITGET',connector)
        self.assertEqual(r['status'],'UNAVAILABLE');self.assertEqual(calls,[1,'closed',1,'closed'])
    async def test_ws_success(self):
        @asynccontextmanager
        async def connector(*a,**kw):
            class W:
                async def send(self,x):pass
                async def ping(self):
                    f=asyncio.get_running_loop().create_future();f.set_result(None);return f
                async def recv(self):return json.dumps(dict(arg=dict(instType='USDT-FUTURES',channel='ticker',instId='BTCUSDT'),data=quote()))
            yield W()
        with patch.object(p.time,'time',return_value=NOW):r=await p.websocket('BITGET',connector)
        self.assertEqual(r['status'],'AVAILABLE');self.assertTrue(r['transport_pong'])
    async def test_feature_flag_auth_csrf_and_no_portfolio_access(self):
        with patch.dict('os.environ',{},clear=True):self.assertIsNone(configured())
        app=FastAPI();app.include_router(router);app.state.exchange_diagnostics=None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            with patch.dict('os.environ',{'AURA_TESTNET_VIEW_PASSWORD':'DUMMY_OWNER_DIAGNOSTICS_ONLY'}):
                self.assertEqual((await c.get('/api/exchange-diagnostics')).status_code,401)
                c.auth=('aura','DUMMY_OWNER_DIAGNOSTICS_ONLY')
                self.assertEqual((await c.get('/api/exchange-diagnostics')).json()['code'],'FEATURE_DISABLED')
                self.assertEqual((await c.post('/api/exchange-diagnostics/run')).status_code,403)
                self.assertEqual((await c.post('/api/exchange-diagnostics/run',headers={'X-Aura-Paper':'local-only'})).status_code,503)
                app.state.exchange_diagnostics=Diagnostics()
                async def probe(name,client):return dict(rest=dict(status='AVAILABLE'))
                with patch('app.exchange_diagnostics.api.exchange_probe',side_effect=probe):
                    r=await c.post('/api/exchange-diagnostics/run',headers={'X-Aura-Paper':'local-only'});self.assertEqual(r.status_code,200);self.assertFalse(r.json()['trading_enabled'])
                    self.assertEqual((await c.post('/api/exchange-diagnostics/run',headers={'X-Aura-Paper':'local-only'})).status_code,429)
                # No paper/auto42/account state exists: probe must never require one.
                self.assertFalse(hasattr(app.state,'paper'))
    async def test_blocked_ticker_stops_probe_and_preserves_status(self):
        calls=[]
        async def get(client,ex,kind,tf=None):
            calls.append(kind)
            return dict(status='AVAILABLE') if kind=='contract' else dict(status='BLOCKED_451',code='HTTP_451')
        for ex in p.REST:
            calls.clear()
            with patch.object(p,'get',side_effect=get):r=await p.exchange_probe(ex,None)
            self.assertEqual(r['rest']['status'],'BLOCKED_451');self.assertEqual(calls,['contract','ticker'])
            self.assertEqual(r['websocket']['status'],'NOT_TESTED')
    async def test_missing_mark_never_claimed_fully_available(self):
        async def get(client,ex,kind,tf=None):
            if kind=='ticker':return dict(status='AVAILABLE',last_price='100',mark_price=None)
            if kind=='mark':return dict(status='UNAVAILABLE',code='HTTP_ERROR')
            return dict(status='AVAILABLE')
        async def ws(ex):return dict(status='UNAVAILABLE')
        for ex in p.REST:
            with patch.object(p,'get',side_effect=get),patch.object(p,'websocket',side_effect=ws):r=await p.exchange_probe(ex,None)
            self.assertEqual(r['rest']['status'],'PARTIALLY_AVAILABLE');self.assertEqual(r['rest']['code'],'MISSING_MARK_PRICE')
    def test_ws_compression_and_stale_rejected(self):
        import gzip
        message=dict(dataType='BTC-USDT@markPrice',data=dict(s='BTC-USDT',E=NOW*1000,p='100'))
        self.assertEqual(p.ws_message('BINGX',gzip.compress(json.dumps(message).encode()),NOW)['mark_price'],'100')
        with self.assertRaisesRegex(p.ProbeError,'STALE_DATA'):p.ws_message('BINGX',json.dumps(message),NOW+31)
        with self.assertRaises(p.ProbeError):p.ws_message('BINGX',gzip.compress(b' '*70000),NOW)
    async def test_concurrent_run_rejected(self):
        s=Diagnostics()
        async with s.lock:self.assertEqual((await s.run())[0],409)
    def test_no_exchange_write_or_portfolio_dependency(self):
        import ast
        from pathlib import Path
        for path in Path('app/exchange_diagnostics').glob('*.py'):
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith(('app.automated','app.bybit_demo','app.testnet','app.paper.engine')))
        self.assertTrue(all('/market/' in path or '/quote/' in path for endpoints in p.PATHS.values() for path in endpoints.values()))
