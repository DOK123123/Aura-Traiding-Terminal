"""Synthetic unit fixtures ONLY. Historical performance is never mocked here."""
import ast
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.lab.adaptive43 import propose,choose,SCENARIOS
from app.lab import adaptive43_report as reports
from app.lab.api import router
from app.lab.models import Bar,digest,canonical,LabError
from app.automated.engine import initial,advance,mark,DemoError
from scripts import research_aura43 as research
from scripts.replay_auto42_verification import PrefixCache,snapshot
from tests.test_auto42 import fixture,bar
from tests.test_market_intelligence import bars


def candidate():
    bs,s,now=fixture();at=s['last_closed_at']
    state=s['state'];state.update(trend_indicators=dict(ema20=100,ema50=99,adx14=30,atr14=2,rsi14=55),
        volatility_ratio=1,relative_volume=2,high_leg='HH',low_leg='HL',trend_direction=1)
    s['alignment_inputs']={'1h':dict(trend_indicators=dict(adx14=30))}
    bs[-1]=bar(bs[-1].time,open='101.5',high='103',low='101.4',close='102.5')
    s['history']['source_sha256']=digest([b.data() for b in bs])
    return bs,s,now


class Rules(unittest.TestCase):
    def test_trend_pullback_and_opposing_4h_is_context_not_alignment_gate(self):
        bs,s,_=candidate();a=propose(s,bs)['TREND_PULLBACK']
        self.assertEqual(a['direction'],'LONG');self.assertEqual(a['regime'],'TRENDING')
        self.assertEqual(a['context']['rr'],'2')
        s['state']['mtf']['h4']['direction']=-1;s['state']['mtf']['alignment']=False
        b=propose(s,bs)['TREND_PULLBACK']
        self.assertEqual(b['direction'],'LONG');self.assertEqual(b['context']['rr'],'1.75')
        self.assertEqual(a['stop_loss'],b['stop_loss'])

    def test_breakout_needs_volume_and_closed_range_break(self):
        bs,s,_=candidate();s['alignment_inputs']['1h']['trend_indicators']['adx14']=20
        s['state']['trend_indicators'].update(atr14=1,rsi14=60)
        bs[-1]=bar(bs[-1].time,open='101',high='103',low='100.5',close='102.5')
        d=propose(s,bs)['BREAKOUT'];self.assertEqual(d['direction'],'LONG')
        s['state']['relative_volume']=1.49;self.assertIsNone(propose(s,bs)['BREAKOUT']['direction'])

    def test_high_volatility_stricter_and_no_pullback_or_reversal(self):
        bs,s,_=candidate();s['state']['volatility_ratio']=2;s['state']['relative_volume']=1.9
        p=propose(s,bs)
        self.assertEqual(p['TREND_PULLBACK']['regime'],'HIGH_VOLATILITY')
        self.assertIsNone(p['TREND_PULLBACK']['direction']);self.assertIsNone(p['REVERSAL']['direction'])
        self.assertIsNone(p['BREAKOUT']['direction'])

    def test_reversal_requires_causal_choch_retest_and_exhaustion(self):
        bs,s,_=candidate();s['alignment_inputs']['1h']['trend_indicators']['adx14']=20
        s['state']['trend_indicators'].update(atr14=1,rsi14=50);s['state']['retest']='LONG'
        bs[-1]=bar(bs[-1].time,open='99.8',high='100.5',low='99.5',close='100')
        at=s['last_closed_at'];s['structure_events']=[dict(type='structure_event',value='CHoCH',confirmed_at=at-900),dict(type='breakout',value='LONG',confirmed_at=at-900)]
        history=[50]*len(bs);history[-3]=30;history[-2]=45
        d=propose(s,bs,rsi_history=history)['REVERSAL'];self.assertEqual(d['direction'],'LONG')
        s['structure_events'][0]['confirmed_at']=at+900
        self.assertIsNone(propose(s,bs,rsi_history=history)['REVERSAL']['direction'])

    def test_missing_h1_stale_forming_and_gap_never_signal(self):
        for case in ('h1','stale','forming','gap'):
            bs,s,_=candidate()
            if case=='h1':s['state']['mtf']['h1']=None
            elif case=='stale':s['freshness']['status']='STALE'
            elif case=='forming':bs.append(bar(bs[-1].time+900))
            else:bs.pop(-5)
            self.assertTrue(all(d['direction'] is None for d in propose(s,bs).values()),case)

    def test_future_h4_never_used_as_context(self):
        bs,s,_=candidate();s['state']['mtf']['h4']=None;unknown=propose(s,bs)
        s['state']['mtf']['h4']=dict(direction=-1,closed_at=s['last_closed_at']+14400)
        self.assertEqual(propose(s,bs),unknown)

    def test_priority_is_frozen_not_outcome_selected(self):
        d={k:dict(direction='LONG',reason=k) for k in SCENARIOS}
        self.assertEqual(choose(d)['reason'],'TREND_PULLBACK')
        self.assertEqual(choose(d,'REVERSAL')['reason'],'REVERSAL')

    def test_shock_bar_and_zero_atr_are_rejected(self):
        bs,s,_=candidate();s['state']['trend_indicators']['atr14']=0
        self.assertTrue(all(d['reason']=='INVALID_ATR' for d in propose(s,bs).values()))
        s['state']['trend_indicators']['atr14']=1;bs[-1]=bar(bs[-1].time,high='110',low='90')
        self.assertTrue(all(d['reason']=='SHOCK_CANDLE' for d in propose(s,bs).values()))


class Causality(unittest.TestCase):
    def test_native_cache_future_mutation_does_not_change_adaptive_prefix(self):
        bs=bars(4175);at=bs[4160].time+900;window=bs[:4161]
        expected=propose(snapshot(window,at),window)
        changed=window+[replace(b,open=b.open*2,high=b.high*2,low=b.low*2,close=b.close*2) for b in bs[4161:]]
        with PrefixCache(changed).installed():self.assertEqual(propose(snapshot(window,at),window),expected)

    def test_pure_native_engine_limits_and_duplicate_watermark_unchanged(self):
        bs,s,now=candidate();d=choose(propose(s,bs));state=initial(now[0],epoch='TEST_LAB_ONLY');state['mode']='ON'
        state,_=advance(state,bs,d,now[0]);bs.append(bar(bs[-1].time+900));now[0]+=900
        state,_=advance(state,bs,d,now[0]);bs.append(bar(bs[-1].time+900));now[0]+=900
        state,events=advance(state,bs,dict(direction=None,reason='WAIT'),now[0])
        self.assertEqual(sum(e['kind']=='OPEN' for e in events),1)
        self.assertLessEqual(D(state['position']['risk_usdt']),D(state['position']['risk_budget_usdt']))
        self.assertEqual(D(state['position']['risk_budget_usdt']),D(50))
        repeat,rows=advance(state,bs,d,now[0]);self.assertEqual(state,repeat);self.assertEqual(rows,[])

    def test_research_modules_cannot_import_controller_storage_or_private_clients(self):
        for path in ('app/lab/adaptive43.py','scripts/research_aura43.py'):
            for n in ast.walk(ast.parse(Path(path).read_text())):
                if isinstance(n,ast.ImportFrom):
                    self.assertFalse(any(x in (n.module or '') for x in ('automated.service','automated.storage','paper','bybit','testnet')))


class Artifact(unittest.IsolatedAsyncioTestCase):
    def report(self):
        r=dict(symbol='BTCUSDT',research_only=True,activation_available=False,real_money_execution='DISABLED',
            code_hashes=reports.software(),runs=[dict(variant='AURA42',split='validation',trades=[],decisions=[],equity_curve=[],metrics={})])
        return dict(r,checksum=digest(r))

    async def test_owner_only_reader_missing_and_valid_artifact_no_compute(self):
        app=FastAPI();app.include_router(router)
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_RESEARCH_OWNER_ONLY'):
            p=Path(folder)/'report.gz'
            with patch.object(reports,'REPORT',p):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                    self.assertEqual((await c.get('/api/lab/adaptive43')).status_code,401)
                    self.assertEqual((await c.get('/api/lab/adaptive43',auth=('aura','DUMMY_RESEARCH_OWNER_ONLY'))).status_code,404)
                    p.write_bytes(gzip.compress(canonical(self.report()),mtime=0));reports._load.cache_clear()
                    r=await c.get('/api/lab/adaptive43',auth=('aura','DUMMY_RESEARCH_OWNER_ONLY'))
                    self.assertEqual(r.status_code,200);self.assertIn('no-store',r.headers['cache-control'])
                    self.assertFalse(r.json()['activation_available']);self.assertFalse(hasattr(app.state,'auto42'))
                    self.assertEqual((await c.get('/api/lab/adaptive43/detail?limit=201',auth=('aura','DUMMY_RESEARCH_OWNER_ONLY'))).status_code,422)

    def test_tampered_or_stale_report_never_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'r.gz';value=self.report();value['symbol']='OTHER'
            with patch.object(reports,'REPORT',p):
                p.write_bytes(gzip.compress(canonical(value)));reports._load.cache_clear()
                with self.assertRaises(LabError):reports.summary()
                value=self.report();value['code_hashes']['app/lab/adaptive43.py']='wrong';value.pop('checksum');value['checksum']=digest(value)
                p.write_bytes(gzip.compress(canonical(value)));reports._load.cache_clear()
                with self.assertRaisesRegex(LabError,'SOFTWARE_MISMATCH'):reports.summary()
