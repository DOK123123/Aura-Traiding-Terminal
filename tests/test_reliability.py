"""Offline reliability regression tests; also runnable without pytest."""
import asyncio
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app, cache, locks, PROVIDERS
from app.models import Candle, validate_candles, data_fresh
from app.providers import aggregate, BinanceProvider, DataUnavailable
from app.market_state import LiveWindow
from app.live import btc_messages, parse_binance, envelope
from app.patterns.history import Dataset, HistoryService


def bars(count=500, end=None):
    end = int(time.time())//60*60 if end is None else end
    return [Candle(end-(count-i)*60, 100, 102, 99, 101, 5) for i in range(count)]


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        cache.clear()
        locks.clear()

    def test_timestamp_rejects_invalid_values(self):
        for stamp in (-1, True, 1.5, float('nan')):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                Candle(stamp, 100, 102, 99, 101, 5)

    def test_invalid_prices_ranges_and_volumes_rejected(self):
        for values in ((100,102,99,float('nan'),5), (100,102,99,101,float('inf')),
                       (100,102,99,101,-1), (100,100,99,101,5), (0,1,0,1,5)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Candle(0,*values)

    def test_window_rejects_duplicates_reordering_future_and_alignment(self):
        rows = bars()
        now = rows[-1].time+60
        for invalid in (rows+[rows[-1]], list(reversed(rows)),
                        rows[:-1]+[replace(rows[-1],time=now)],
                        rows[:-1]+[replace(rows[-1],time=rows[-1].time+1)]):
            with self.subTest(), self.assertRaises(ValueError):
                validate_candles(invalid, '1m', now=now, contiguous=True)

    def test_bitcoin_gaps_rejected_gold_market_breaks_allowed(self):
        rows=bars(10); del rows[4]
        with self.assertRaises(ValueError):
            validate_candles(rows,'1m',now=time.time(),contiguous=True)
        validate_candles(rows,'1m',now=time.time())

    def test_incomplete_internal_gold_bucket_is_not_published(self):
        rows=[Candle(i*60,100,102,99,101,1) for i in (0,1,3,4,5)]
        self.assertEqual(aggregate(rows,300,60,600),[])

    def test_complete_gold_bucket_and_identical_duplicates(self):
        rows=[Candle(i*60,100,102,99,101,1) for i in range(5)]
        self.assertEqual(aggregate(rows+[rows[0]],300,60,600),[Candle(0,100,102,99,101,5)])

    def test_conflicting_gold_duplicate_rejected(self):
        rows=bars(5)
        with self.assertRaises(ValueError):
            aggregate(rows+[replace(rows[0],close=100)],300,60,int(time.time()))

    def test_freshness_boundary(self):
        c=bars(1,end=600)[0]
        self.assertTrue(data_fresh(c,'1m',720))
        self.assertFalse(data_fresh(c,'1m',721))
        self.assertFalse(data_fresh(c,'1m',599))

    def test_live_bootstrap_checks_history(self):
        rows=bars(); invalid=rows.copy(); invalid[5]=invalid[4]
        with self.assertRaises(ValueError):LiveWindow(invalid,'1m',500)
        with self.assertRaises(DataUnavailable):LiveWindow(bars(end=int(time.time())//60*60-600),'1m',500)

    def test_live_duplicate_and_old_events_do_not_roll_back(self):
        rows=bars(); window=LiveWindow(rows,'1m',500)
        c=replace(rows[-1],time=rows[-1].time+60)
        self.assertTrue(window.apply(c,False,1))
        self.assertIsNone(window.apply(replace(c,close=100),False,1))
        self.assertEqual(window.candles[-1],c)
        self.assertFalse(window.apply(c,True,2))
        self.assertIsNone(window.apply(c,False,3))
        self.assertEqual(len(window.candles),500)

    def test_live_regressing_high_low_open_volume_rejected(self):
        rows=bars(); c=replace(rows[-1],time=rows[-1].time+60)
        for bad in (replace(c,open=100.5),replace(c,high=101),replace(c,low=100),replace(c,volume=4)):
            window=LiveWindow(rows,'1m',500); window.apply(c,False,1)
            with self.subTest(bad=bad), self.assertRaises(DataUnavailable):window.apply(bad,False,2)

    def test_gap_requires_bootstrap(self):
        rows=bars(); window=LiveWindow(rows,'1m',500)
        with self.assertRaises(DataUnavailable):
            window.apply(replace(rows[-1],time=rows[-1].time+120),False,1)

    def test_stale_and_malformed_binance_events_rejected(self):
        now=time.time(); stamp=int(now)//60*60
        event={'e':'kline','s':'BTCUSDT','E':int((now-30)*1000),
               'k':{'s':'BTCUSDT','i':'1m','t':stamp*1000,'o':'100','h':'102','l':'99','c':'101','v':'5','x':False}}
        for invalid in (event,[],{'e':'kline','k':None}):
            with self.subTest(), self.assertRaises(DataUnavailable):parse_binance(invalid,'1m')

    def test_envelope_old_gold_stream_is_stale(self):
        c=bars(end=int(time.time())//60*60-600)[-1]
        self.assertTrue(envelope('XAUUSD','1m','OANDA','source_stream',c)['stale'])

    def test_binance_rest_gap_rejected(self):
        async def run():
            now=60000*1000+30000
            rows=[[i*60000,'100','102','99','101','5',(i+1)*60000-1] for i in (995,996,998,999)]
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=rows))) as client:
                with self.assertRaises(ValueError):
                    await BinanceProvider().fetch(client,'1m',4,now_ms=now)
        asyncio.run(run())

    def test_rest_bad_window_returns_503_and_logs(self):
        rows=bars(); rows[10]=rows[9]
        with patch.object(PROVIDERS['BTCUSDT'],'fetch',AsyncMock(return_value=rows)), TestClient(app) as client:
            with self.assertLogs('app.main',level='WARNING'):
                self.assertEqual(client.get('/api/market?timeframe=1m').status_code,503)

    def test_rest_cached_freshness_is_recomputed(self):
        rows=bars(); end=rows[-1].time+60
        with patch.object(PROVIDERS['BTCUSDT'],'fetch',AsyncMock(return_value=rows)), TestClient(app) as client:
            with patch('app.main.time.time',return_value=end+119):
                self.assertFalse(client.get('/api/market?timeframe=1m').json()['stale'])
            with patch('app.main.time.time',return_value=end+121):
                self.assertTrue(client.get('/api/market?timeframe=1m').json()['stale'])

    def test_pattern_source_match_mismatch_missing_and_delayed(self):
        rows=bars(); dataset=Dataset(rows,'Binance · Spot',time.time(),500,'fixture')
        prediction=lambda *args:dict(status='OK',signal='LONG',confidence=80,explanation={'risks':[]})
        with patch('app.patterns.api.history_service.get',AsyncMock(return_value=dataset)), \
             patch('app.patterns.api.evaluate',side_effect=prediction), TestClient(app) as client:
            for source in (None,'Dukascopy · XAUUSD BID','Binance · Spot'):
                body={'symbol':'BTCUSDT','timeframe':'1m','chart_source':source}
                data=client.post('/api/patterns/analyze',json=body).json()
                self.assertEqual(data['signal'],'LONG' if source==dataset.source else 'WAIT')
                self.assertEqual(data['source_verified'],source==dataset.source)
            dataset.candles=[replace(c,time=c.time-600) for c in rows]
            data=client.post('/api/patterns/analyze',json=body).json()
            self.assertEqual((data['status'],data['signal']),('DELAYED','WAIT'))

    def test_bitcoin_archive_excludes_old_disk_gap(self):
        class Archive:
            def save(self,*args):pass
            def read(self,*args):return bars(10,end=rows[0].time-600)+rows
        rows=bars()
        service=HistoryService(Archive()); service.binance=AsyncMock(return_value=rows)
        with self.assertLogs('app.patterns.history',level='WARNING'):
            data=asyncio.run(service.get(None,'BTCUSDT','1m'))
        self.assertEqual(data.candles,rows)
        self.assertIn('gap excluded',data.note)

    def test_bitcoin_stream_reconnects_and_rebootstraps(self):
        rows=bars(); now=int(time.time()*1000); stamp=rows[-1].time+60
        event={'e':'kline','s':'BTCUSDT','E':now,
               'k':{'s':'BTCUSDT','i':'1m','t':stamp*1000,'o':'100','h':'102','l':'99','c':'101','v':'5','x':False}}
        class Socket:
            def __init__(self,fail):self.fail=fail
            async def __aenter__(self):
                if self.fail:raise OSError('connection interrupted')
                return self
            async def __aexit__(self,*args):pass
            async def recv(self):return json.dumps(event)
        class Provider:
            name='Binance · Spot'
            fetch=AsyncMock(return_value=rows)
        provider=Provider()
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'serverTime':now}))) as client:
                stream=btc_messages(client,provider,'1m',500)
                try:
                    status=await anext(stream); seed=await anext(stream); update=await anext(stream)
                    self.assertEqual(status['state'],'reconnecting')
                    self.assertEqual(seed['type'],'snapshot')
                    self.assertEqual(update['mode'],'streaming')
                finally:await stream.aclose()
        with patch('app.live.connect',side_effect=[Socket(True),Socket(False)]), \
             patch('app.live.asyncio.sleep',new_callable=AsyncMock) as sleep, \
             self.assertLogs('app.live',level='WARNING'):
            asyncio.run(run())
            sleep.assert_awaited_once_with(2)
        provider.fetch.assert_awaited_once()

    def test_page_and_assets_still_available(self):
        with TestClient(app) as client:
            for url in ('/','/api/health','/static/live.js','/static/patterns.js'):
                self.assertEqual(client.get(url).status_code,200)


if __name__=='__main__':unittest.main()
