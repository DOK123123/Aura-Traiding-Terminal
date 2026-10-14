"""Offline transport/cache regressions; fixture prices are not market evidence."""
import asyncio
import unittest
from unittest.mock import patch
import httpx
from app.intelligence.market_context import MarketContext, fetch_window, retry_page
from tests.test_market_context import fixture, csv_row

class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_incremental_download_only_overlap_and_new_candle(self):
        bs=fixture(4161);now=bs[-1].time+950;calls=[]
        async def page(q):
            calls.append(q)
            return [csv_row(b) for b in bs if q['startTime']<=b.time*1000<=q['endTime']][:q['limit']]
        result,info=await fetch_window(page,now,bs[:-1])
        self.assertEqual(result,bs)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['limit'],2)
        self.assertTrue(info['complete'])

    async def test_retry_transient_then_success_and_no_retry_rate_limit(self):
        count=0
        async def page(q):
            nonlocal count
            count+=1
            if count==1:raise httpx.ReadTimeout('SENSITIVE_MARKER')
            return []
        with patch('app.intelligence.market_context.asyncio.sleep'):
            self.assertEqual(await retry_page(page,{}),[])
        self.assertEqual(count,2)
        request=httpx.Request('GET','https://invalid.example')
        response=httpx.Response(429,request=request)
        async def limited(q):raise httpx.HTTPStatusError('SENSITIVE_MARKER',request=request,response=response)
        with patch('app.intelligence.market_context.asyncio.sleep') as sleep:
            with self.assertRaises(httpx.HTTPStatusError):await retry_page(limited,{})
            sleep.assert_not_called()

    async def test_repeated_network_failure_has_exactly_two_attempts(self):
        count=0
        async def page(q):
            nonlocal count
            count+=1
            raise httpx.ConnectError('SENSITIVE_MARKER')
        with patch('app.intelligence.market_context.asyncio.sleep'):
            with self.assertRaises(httpx.ConnectError):await retry_page(page,{})
        self.assertEqual(count,2)

    async def test_failure_preserves_last_good_only_as_stale_display(self):
        bs=fixture();now=bs[-1].time+950;mono=[0]
        svc=MarketContext(None,clock=lambda:now,monotonic=lambda:mono[0])
        with patch('app.intelligence.market_context.fetch_window',return_value=(bs,{})):
            good=await svc.snapshot('15m')
        mono[0]=31
        with patch('app.intelligence.market_context.fetch_window',side_effect=TimeoutError()):
            bad=await svc.snapshot('15m')
        self.assertEqual(bad['status'],'UPSTREAM_TIMEOUT')
        self.assertIsNone(bad['state'])
        self.assertEqual(bad['last_successful_analysis']['state'],good['state'])
        self.assertEqual(bad['last_successful_analysis']['freshness']['status'],'STALE')
        self.assertEqual(bad['decision']['action'],'WAIT')
        self.assertFalse(bad['decision']['execution_enabled'])
        await svc.close()

    async def test_identical_verified_history_reuses_analysis(self):
        bs=fixture();now=bs[-1].time+950;mono=[0]
        svc=MarketContext(None,clock=lambda:now,monotonic=lambda:mono[0])
        from app.intelligence.market_context import analyze_window
        with patch('app.intelligence.market_context.fetch_window',return_value=(bs,{})),patch('app.intelligence.market_context.analyze_window',wraps=analyze_window) as compute:
            await svc.snapshot('15m');mono[0]=31
            await svc.snapshot('4h')
            self.assertEqual(compute.call_count,1)
        await svc.close()

    async def test_total_fetch_budget_reproduces_full_history_timeout(self):
        bs=fixture(4161);now=bs[-1].time+950
        async def page(q):
            await asyncio.sleep(0.025)
            return [csv_row(b) for b in bs if q['startTime']<=b.time*1000<=q['endTime']][:q['limit']]
        with patch('app.intelligence.market_context.FETCH_SECONDS',0.1):
            with self.assertRaises(TimeoutError):await fetch_window(page,now)
            result,_=await fetch_window(page,now,bs[:-1])
            self.assertEqual(result,bs)

    async def test_upstream_correction_rejected_and_seed_reset(self):
        from dataclasses import replace
        from app.lab.models import LabError
        bs=fixture();now=bs[-1].time+950
        async def page(q):
            return [csv_row(replace(bs[-1],volume=bs[-1].volume+1))]
        with self.assertRaises(LabError):await fetch_window(page,now,bs)
        svc=MarketContext(None,clock=lambda:now)
        svc.bars=bs
        with patch('app.intelligence.market_context.fetch_window',side_effect=LabError('INVALID_DATA')):
            await svc.snapshot('15m')
        self.assertEqual(svc.bars,[])
        await svc.close()

    async def test_per_attempt_timeout_is_bounded(self):
        calls=0
        async def page(q):
            nonlocal calls
            calls+=1
            await asyncio.Event().wait()
        with patch('app.intelligence.market_context.PAGE_SECONDS',0.01),patch('app.intelligence.market_context.asyncio.sleep'):
            with self.assertRaises(TimeoutError):await retry_page(page,{})
        self.assertEqual(calls,2)

    async def test_empty_incremental_response_cannot_replace_good_window(self):
        from app.lab.models import LabError
        bs=fixture();now=bs[-1].time+950
        async def page(q):return []
        with self.assertRaises(LabError):await fetch_window(page,now,bs)

    async def test_overlap_and_window_after_utc_four_hour_boundary(self):
        bs=fixture(4177);now=bs[-1].time+950
        async def page(q):return [csv_row(b) for b in bs if q['startTime']<=b.time*1000<=q['endTime']][:q['limit']]
        result,info=await fetch_window(page,now,bs[:-1])
        self.assertEqual(result,bs[16:])
        self.assertTrue(info['complete'])
        self.assertEqual(info['fetch_pages'],1)
