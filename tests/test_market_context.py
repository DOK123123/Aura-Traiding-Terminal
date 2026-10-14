"""Offline adapter tests: fixtures prove logic, never historical profitability."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.intelligence import api
from app.intelligence.market_context import (MarketContext, analyze_window,
    fetch_window, error_code, unavailable, MAX_BARS, VERSION)
from app.lab.models import LabError
from app.lab.series import higher, split_parts
from research.market_intelligence.structure import segment_states
from tests.test_market_intelligence import bars, pivots


def csv_row(b):
    return [b.time*1000,*[str(getattr(b,k)) for k in ('open','high','low','close','volume')],(b.time+900)*1000-1,'0',0,'0','0','0']


def fixture(n=4160):
    return bars(n)


class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bs=fixture();cls.now=cls.bs[-1].time+950
        cls.snapshots=analyze_window(cls.bs,cls.now)

    def test_all_frames_warmed_closed_and_real_snapshot(self):
        for tf,step in [('15m',900),('1h',3600),('4h',14400)]:
            v=self.snapshots[tf]
            self.assertEqual(v['status'],'OK');self.assertEqual(v['state']['version'],VERSION)
            self.assertEqual(v['last_closed_at']%step,0);self.assertLessEqual(v['last_closed_at'],self.now)
            self.assertEqual(v['decision']['action'],'WAIT');self.assertFalse(v['decision']['execution_enabled'])
        self.assertEqual(self.snapshots['15m']['mtf']['known_mask'],3)

    def test_reuse_exact_research_algorithm_primary(self):
        v=analyze_window(pivots(),pivots()[-1].time+950)['15m']['state']
        old=segment_states(pivots())[-1]
        for k in old:
            if k not in ('mtf','vector'):self.assertEqual(v[k],old[k])
        self.assertEqual(v['vector'][:-3],old['vector'][:-3])

    def test_forming_candle_not_analyzed(self):
        with self.assertRaises(LabError) as c:analyze_window(self.bs,self.bs[-1].time+899)
        self.assertEqual(c.exception.code,'INVALID_TIMESTAMPS')

    def test_incomplete_utc_buckets(self):
        xs=self.bs[:-1];v=analyze_window(xs,xs[-1].time+950)
        for tf,step in [('1h',3600),('4h',14400)]:
            self.assertEqual(v[tf]['last_closed_at'],xs[-1].time//step*step)
        self.assertNotEqual(v['15m']['last_closed_at'],v['4h']['last_closed_at'])
        self.assertFalse(higher(self.bs[:15],14400))

    def test_no_lookahead_or_future_pivot(self):
        prefix=fixture(300);future=[replace(b,open=D(200),high=D(300),low=D(190),close=D(250)) for b in fixture(330)[300:]]
        self.assertEqual(segment_states(prefix),segment_states(prefix+future)[:300])
        states=segment_states(pivots());self.assertFalse(states[252]['confirmed_pivots'])
        self.assertEqual(states[253]['confirmed_pivots'][0]['confirmation_time'],pivots()[253].time+900)

    def test_insufficient_primary_and_higher_warmup_nulls(self):
        v=analyze_window(self.bs[:249],self.bs[248].time+950)['15m']
        self.assertEqual(v['status'],'INSUFFICIENT_HISTORY');self.assertIsNone(v['state']);self.assertIsNone(v['levels'])
        v=analyze_window(self.bs[:2000],self.bs[1999].time+950)
        self.assertEqual(v['15m']['status'],'OK');self.assertEqual(v['4h']['status'],'INSUFFICIENT_HISTORY')
        self.assertIsNone(v['15m']['mtf']['h4'])

    def test_gap_resets_all_indicators_no_synthetic_fill(self):
        xs=self.bs[:4000]+self.bs[4001:]
        v=analyze_window(xs,self.now)
        self.assertEqual(v['15m']['history']['missing_candles'],1)
        for value in v.values():self.assertEqual(value['status'],'INSUFFICIENT_HISTORY');self.assertIsNone(value['state'])
        self.assertEqual(v['15m']['history']['base_count'],4159)

    def test_later_primary_can_recover_but_mtf_must_warm_again(self):
        xs=self.bs[:2000]+self.bs[2001:]
        v=analyze_window(xs,self.now)
        self.assertEqual(v['15m']['status'],'OK');self.assertEqual(v['4h']['status'],'INSUFFICIENT_HISTORY')
        self.assertIsNone(v['15m']['mtf']['h4'])
        self.assertLessEqual(v['15m']['state']['segment_start'],v['15m']['last_closed_at'])

    def test_duplicates_order_and_invalid_ohlcv_rejected(self):
        for xs in [self.bs[:20]+self.bs[19:],list(reversed(self.bs)),self.bs[:-1]+[replace(self.bs[-1],close=D('NaN'))]]:
            with self.assertRaises(LabError):analyze_window(xs,self.now)

    def test_max_window_and_deadline(self):
        with self.assertRaises(LabError):analyze_window(fixture(MAX_BARS+1),fixture(MAX_BARS+1)[-1].time+950)
        with self.assertRaises(TimeoutError):segment_states(self.bs,deadline=0)

    def test_v1_analogs_not_reused_unknown_not_zero(self):
        for v in self.snapshots.values():
            ev=v['analog_availability'];self.assertEqual(ev['status'],'ANALOG_DATA_UNAVAILABLE')
            self.assertEqual(ev['reason'],'INCOMPATIBLE_V1_PACK')
            for k in ('sample_count','coverage','sha256','exit_model'):self.assertIsNone(ev[k])
            self.assertIsNone(v['research_evidence']['live_expectancy'])

    def test_pure_helpers_are_reexported_not_duplicated(self):
        from scripts.lab3_strategies import higher as old_higher
        from scripts.pattern_research import split_parts as old_split
        self.assertIs(higher,old_higher);self.assertIs(split_parts,old_split)

    def test_network_and_http_classification_no_leak(self):
        self.assertEqual(error_code(LabError('DO_NOT_SHOW')),'UNAVAILABLE')
        self.assertEqual(error_code(httpx.ConnectError('DO_NOT_SHOW')),'NETWORK_ERROR')
        self.assertEqual(error_code(httpx.ReadTimeout('DO_NOT_SHOW')),'TIMEOUT')
        for status,code in [(429,'RATE_LIMIT'),(451,'REGION_RESTRICTED'),(403,'REGION_RESTRICTED'),(500,'UPSTREAM_HTTP_ERROR')]:
            r=httpx.Response(status,request=httpx.Request('GET','https://invalid.example'))
            self.assertEqual(error_code(httpx.HTTPStatusError('DO_NOT_SHOW',request=r.request,response=r)),code)

    def test_no_offline_runner_private_client_or_storage_in_adapter(self):
        src=Path('app/intelligence/market_context.py').read_text()
        for token in ('Service(', 'sqlite', 'os.environ', 'getenv', 'app.paper', 'app.bybit', 'app.testnet','simulate(', 'run_market_intelligence', 'lab3_history', 'create_order', 'cancel_order', 'amend_order'):
            self.assertNotIn(token,src)
        root=Path('research/market_intelligence/structure.py').read_text()
        self.assertNotIn('from scripts.',root)


class AsyncContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_exact_closed_window_in_bounded_pages(self):
        calls=[];now=fixture()[-1].time+950
        async def page(query):
            calls.append(query);start=query['startTime']//1000
            xs=[replace(b,time=start+i*900) for i,b in enumerate(bars(query['limit']))]
            return [csv_row(b) for b in xs]
        bs,info=await fetch_window(page,now)
        self.assertLessEqual(len(calls),5);self.assertEqual(len(bs),4160)
        self.assertTrue(info['complete']);self.assertEqual(bs[-1].time+900,int(now)//900*900)

    async def test_unexpected_forming_is_excluded_not_confirmed(self):
        now=fixture()[-1].time+950;end=int(now)//900*900
        async def page(query):
            row=csv_row(replace(bars(1)[0],time=end))
            return [row]
        bs,info=await fetch_window(page,now)
        self.assertFalse(bs);self.assertEqual(info['forming_excluded'],1)

    async def test_fetch_duplicates_missing_invalid_close(self):
        now=fixture()[-1].time+950
        for mode in ('duplicate','close','unordered','ohlcv'):
            async def page(query):
                start=query['startTime']//1000
                a=csv_row(replace(bars(1)[0],time=start));b=csv_row(replace(bars(1)[0],time=start+900))
                if mode=='duplicate':b=a
                elif mode=='close':a[6]+=1
                elif mode=='unordered':a,b=b,a
                else:a[2]='1'
                return [a,b]
            with self.assertRaises(LabError):await fetch_window(page,now)

    async def test_fetch_missing_is_explicit_not_sorted_or_filled(self):
        calls=0;now=fixture()[-1].time+950
        async def page(q):
            nonlocal calls
            calls+=1
            if calls>1:return []
            start=q['startTime']//1000
            return [csv_row(replace(b,time=start+i*900)) for i,b in enumerate(bars(300)) if i!=20]
        bs,info=await fetch_window(page,now)
        out=analyze_window(bs,now,info)['15m']
        self.assertEqual(out['history']['missing_candles'],1)
        self.assertFalse(info['complete']);self.assertEqual(len(bs),299)

    async def test_single_flight_ttl_and_failure_clears_cache(self):
        gate=asyncio.Event();clock=[0.];now=[fixture()[-1].time+950]
        async def work(*args):await gate.wait();return fixture(),{}
        svc=MarketContext(None,clock=lambda:now[0],monotonic=lambda:clock[0])
        with patch('app.intelligence.market_context.fetch_window',side_effect=work) as fetch:
            tasks=[asyncio.create_task(svc.snapshot(tf)) for tf in ('15m','1h','4h')]
            await asyncio.sleep(0);gate.set();values=await asyncio.gather(*tasks)
            self.assertEqual(fetch.call_count,1);self.assertTrue(all(v['freshness']['status']=='FRESH' for v in values))
            await svc.snapshot('15m');self.assertEqual(fetch.call_count,1)
        clock[0]=31
        with patch('app.intelligence.market_context.fetch_window',side_effect=httpx.ConnectError('PRIVATE_MARKER')):
            with self.assertLogs('app.intelligence.market_context',level='WARNING') as logs:v=await svc.snapshot('15m')
            self.assertEqual(v['status'],'NETWORK_ERROR');self.assertIsNone(v['state']);self.assertNotIn('PRIVATE_MARKER',json.dumps(v)+str(logs.output))
        await svc.close()

    async def test_stale_base_feed_invalidates_every_timeframe(self):
        xs=fixture();at=xs[-1].time+950
        svc=MarketContext(None,clock=lambda:at)
        svc.cache=analyze_window(xs,at);svc.at=svc.monotonic()
        for v in svc.cache.values():v['fetched_at']=at
        at+=1000
        for tf in ('15m','1h','4h'):
            v=await svc.snapshot(tf);self.assertEqual(v['status'],'STALE');self.assertIsNone(v['state']);self.assertEqual(v['decision']['action'],'WAIT')

    async def test_failed_compute_and_rate_cooldown(self):
        now=fixture()[-1].time+950;mono=[0.]
        svc=MarketContext(None,clock=lambda:now,monotonic=lambda:mono[0])
        r=httpx.Response(429,headers={'Retry-After':'120'},request=httpx.Request('GET','https://invalid.example'))
        e=httpx.HTTPStatusError('PRIVATE_MARKER',request=r.request,response=r)
        with patch('app.intelligence.market_context.fetch_window',side_effect=e) as fetch:
            self.assertEqual((await svc.snapshot('15m'))['status'],'RATE_LIMIT')
            mono[0]=60;await svc.snapshot('4h');self.assertEqual(fetch.call_count,1)
        svc=MarketContext(None)
        with patch('app.intelligence.market_context.fetch_window',return_value=(fixture(),{})),patch('app.intelligence.market_context.analyze_window',side_effect=TimeoutError()):
            self.assertEqual((await svc.snapshot('15m'))['status'],'ANALYSIS_TIMEOUT')

    async def test_restart_without_data_and_close_never_resurrects_cache(self):
        svc=MarketContext(None)
        await svc.close()
        self.assertEqual((await svc.snapshot('15m'))['status'],'UNAVAILABLE')
        with self.assertRaises(ValueError):await svc.snapshot('5m')

    async def test_main_app_endpoint_health_static_and_fresh_snapshot(self):
        from app.main import app
        bs=fixture();now=bs[-1].time+950
        svc=MarketContext(None,clock=lambda:now)
        svc.cache=analyze_window(bs,now);svc.at=svc.monotonic()
        for value in svc.cache.values():value['fetched_at']=now
        with patch.object(app.state,'market_context',svc,create=True),patch.dict(os.environ,{'AURA_TESTNET_VIEW_PASSWORD':'dummy-only-test-password'}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                r=await c.get('/api/intelligence/market-context',auth=('aura','dummy-only-test-password'))
                self.assertEqual(r.status_code,200);self.assertEqual(r.json()['freshness']['status'],'FRESH')
                self.assertEqual(r.json()['decision']['action'],'WAIT')
                self.assertEqual((await c.get('/api/health')).json()['status'],'ok')
                index=await c.get('/');self.assertEqual(index.status_code,200)
                self.assertIn('id="mc-panel"',index.text);self.assertIn('id="ai-confirm"',index.text)
                self.assertEqual((await c.get('/static/market_context.js')).status_code,200)
                self.assertEqual((await c.get('/static/market_context.css')).status_code,200)
                from app.bybit_demo.client import BybitDemoReader, Credentials
                def no_network(request):raise AssertionError('Account read must remain unconfigured')
                reader=BybitDemoReader(Credentials('',''),transport=httpx.MockTransport(no_network))
                try:
                    with patch.object(app.state,'bybit_demo',reader,create=True):
                        account=await c.get('/api/bybit-demo/account')
                        self.assertEqual(account.status_code,200);self.assertEqual(account.json()['status'],'Not configured')
                finally:await reader.close()
        path=app.openapi()['paths']['/api/intelligence/market-context']
        self.assertEqual(set(path),{'get'})

    async def test_owner_asgi_read_only_api_without_archive_or_portfolio(self):
        app=FastAPI();app.include_router(api.router)
        svc=MarketContext(None);svc.cache={tf:dict(unavailable('INSUFFICIENT_HISTORY','INSUFFICIENT_HISTORY'),timeframe=tf) for tf in ('15m','1h','4h')};svc.at=svc.monotonic()
        app.state.market_context=svc
        with patch.dict(os.environ,{'AURA_TESTNET_VIEW_PASSWORD':'dummy-only-test-password'}),patch.object(api,'service',side_effect=AssertionError('Portfolio must not be touched')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                url='/api/intelligence/market-context'
                self.assertEqual((await c.get(url)).status_code,401)
                c.auth=('aura','dummy-only-test-password')
                r=await c.get(url);self.assertEqual(r.status_code,200);self.assertEqual(r.headers['cache-control'],'no-store')
                self.assertIsNone(r.json()['state']);self.assertEqual(r.json()['decision']['mode'],'READ_ONLY')
                self.assertEqual((await c.get(url+'?timeframe=5m')).status_code,422)
                self.assertEqual((await c.post(url)).status_code,405)
                del app.state.market_context
                r=await c.get(url);self.assertEqual(r.status_code,503);self.assertEqual(r.json()['status'],'UNAVAILABLE')
        with patch.dict(os.environ,{'AURA_TESTNET_VIEW_PASSWORD':''}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:self.assertEqual((await c.get('/api/intelligence/market-context')).status_code,403)


if __name__=='__main__':unittest.main()
