"""Offline synthetic unit cases only; no fabricated historical performance."""
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
from app.lab.adaptive43 import propose as original,choose
from app.lab.adaptive43_profiles import propose,PROFILES
from app.lab import adaptive43_profiles_report as reports
from app.lab.api import router
from app.lab.models import Bar,canonical,digest,LabError
from app.automated.engine import advance,initial,mark
from scripts.aura43_profile_context import snapshot as projected
from scripts.replay_auto42_verification import PrefixCache,snapshot
from scripts.research_aura43_profiles import eligible,selected_rows,monthly_results,read_checkpoint
from scripts.aura43_history import load_history
from scripts.audit_aura43_profiles import verify_exit
from tests.test_adaptive43 import candidate
from tests.test_auto42 import bar
from tests.test_market_intelligence import bars

class Profiles(unittest.TestCase):
    def test_all_profiles_pullback_long_and_short_conservative_equivalence(self):
        for short in (False,True):
            bs,s,_=candidate()
            if short:
                bs=[replace(b,open=D(200)-b.open,close=D(200)-b.close,high=D(200)-b.low,low=D(200)-b.high) for b in bs]
                state=s['state'];state['trend_direction']=-1;state.update(high_leg='LH',low_leg='LL')
                state['trend_indicators'].update(ema20=100,ema50=101,rsi14=45)
                state['mtf']['h1']['direction']=-1;state['mtf']['h4']['direction']=-1
            expected=original(s,bs)
            for p in PROFILES:
                d=propose(s,bs,p)['TREND_PULLBACK'];self.assertEqual(d['direction'],'SHORT' if short else 'LONG')
                if p=='Conservative':
                    for key in ('direction','stop_loss','take_profit'):self.assertEqual(d[key],expected['TREND_PULLBACK'][key])

    def test_balanced_body_confirmation_increases_candidates_without_changing_risk(self):
        bs,s,_=candidate();prev=bs[-2];bs[-2]=replace(prev,high=D('103.5'))
        self.assertIsNone(propose(s,bs,'Conservative')['TREND_PULLBACK']['direction'])
        for p in ('Balanced','Active'):
            d=propose(s,bs,p)['TREND_PULLBACK'];self.assertEqual(d['direction'],'LONG')
            self.assertGreaterEqual(D(d['context']['expected_net_rr']),D('1.2'))
            self.assertLessEqual(bs[-1].close-D(d['stop_loss']),D(6))

    def test_volume_breakout_and_reversal_confirmation_profiles(self):
        bs,s,_=candidate();s['alignment_inputs']['1h']['trend_indicators']['adx14']=18
        s['state']['trend_indicators'].update(atr14=1,rsi14=60);s['state']['relative_volume']=1.3
        bs[-1]=bar(bs[-1].time,open='101',high='103',low='100.5',close='102.5')
        self.assertIsNone(propose(s,bs,'Conservative')['BREAKOUT']['direction'])
        for p in ('Balanced','Active'):self.assertEqual(propose(s,bs,p)['BREAKOUT']['direction'],'LONG')
        s['state']['trend_indicators']['rsi14']=50;s['state']['relative_volume']=2;s['state']['retest']='LONG'
        at=s['last_closed_at'];s['structure_events']=[dict(type='structure_event',value='CHoCH',confirmed_at=at-900),dict(type='breakout',value='LONG',confirmed_at=at-900)]
        bs[-1]=bar(bs[-1].time,open='99.8',high='100.5',low='99.5',close='100')
        history=[50]*len(bs);history[-3]=30;history[-2]=45
        for p in PROFILES:self.assertEqual(propose(s,bs,p,rsi_history=history)['REVERSAL']['direction'],'LONG')
        s['structure_events'][0]['confirmed_at']=at+900
        for p in PROFILES:self.assertIsNone(propose(s,bs,p,rsi_history=history)['REVERSAL']['direction'])

    def test_all_profiles_fail_closed_and_high_vol_protections(self):
        for change in ('stale','gap','future','source','shock','h1'):
            bs,s,_=candidate()
            if change=='stale':s['freshness']['status']='STALE'
            elif change=='gap':bs.pop(-3)
            elif change=='future':bs.append(bar(bs[-1].time+900))
            elif change=='source':s['source']='INVALID'
            elif change=='shock':bs[-1]=bar(bs[-1].time,high='120',low='90')
            else:s['state']['mtf']['h1']=None
            for p in PROFILES:self.assertTrue(all(d['direction'] is None for d in propose(s,bs,p).values()),(change,p))
        bs,s,_=candidate();s['state']['volatility_ratio']=2;s['state']['relative_volume']=1.99
        for p in PROFILES:self.assertTrue(all(d['direction'] is None for d in propose(s,bs,p).values()))

    def test_diagnostics_use_individual_gates_not_only_first_reason(self):
        bs,s,_=candidate();s['state']['relative_volume']=0
        d=propose(s,bs,'Balanced')['TREND_PULLBACK']['diagnostics']['LONG']
        self.assertFalse(d['gates']['volume']);self.assertTrue(d['gates']['entry_confirmation'])
        self.assertIsNone(d['plan'])

class CausalExecution(unittest.TestCase):
    def test_projection_native_equality_across_all_utc_boundaries_and_future_mutation(self):
        bs=bars(4175);cache=PrefixCache(bs)
        with cache.installed():
            for n in range(4160,4176):
                window=bs[:n];at=window[-1].time+900;a=snapshot(window,at);b=projected(cache,window,at)
                for key in b:self.assertEqual(b[key],a[key] if key!='history' else dict(source_sha256=a[key]['source_sha256']))
                for p in PROFILES:
                    x=propose(a,window,p);y=propose(b,window,p);self.assertEqual(x,y)
        n=4161;window=bs[:n];changed=window+[replace(b,open=b.open*3,close=b.close*3,high=b.high*3,low=b.low*3) for b in bs[n:]]
        self.assertEqual(projected(cache,window,window[-1].time+900),projected(PrefixCache(changed),window,window[-1].time+900))

    def test_two_execution_bars_equal_full_window_and_no_duplicate_or_state_leak(self):
        bs,s,now=candidate();at=s['last_closed_at'];state=initial(at,epoch='ISOLATED_PROFILE_TEST');state.update(mode='ON',watermark=at-900,last_bar_hash=digest(bs[-2].data()));mark(state,bs[-2],at-900)
        for n in range(4):
            d=choose(propose(s,bs,'Balanced')) if n==0 else dict(direction=None,reason='WAIT')
            full,events=advance(state,bs,d,bs[-1].time+930)
            small,ev=advance(state,bs[-2:],d,bs[-1].time+930)
            self.assertEqual(full,small);self.assertEqual(events,ev)
            again,empty=advance(small,bs[-2:],d,bs[-1].time+930);self.assertEqual(again,small);self.assertEqual(empty,[])
            state=full;bs.append(bar(bs[-1].time+900,open='103',high='110',low='95',close='102'))
        self.assertEqual(state['trades'],1);self.assertIsNone(state['position'])
        self.assertLessEqual(D(state['max_drawdown_pct']),10)

    def test_oracle_ambiguous_stop_first_and_gap_not_target_improvement(self):
        b=bar(900,open='100',high='120',low='80')
        t=dict(direction='LONG',entry_time=900,stop_loss='90',take_profit='110',exit_time=1800,exit_reason='STOP_LOSS_AMBIGUOUS',exit_raw_price='90')
        verify_exit(t,{900:b})
        t.update(exit_reason='TAKE_PROFIT',exit_raw_price='110')
        with self.assertRaises(AssertionError):verify_exit(t,{900:b})

    def test_selection_requires_development_evidence_not_validation(self):
        run=dict(metrics=dict(trades=19,net_profit='100',profit_factor='2',max_drawdown_pct='1',expectancy='1'),monthly={'x':dict(complete_calendar_month=True,net_profit='1')})
        self.assertFalse(eligible(run));run['metrics']['trades']=20;self.assertTrue(eligible(run))
        run['monthly']['x']['net_profit']='-1';self.assertFalse(eligible(run))
        run['monthly']['x']['net_profit']='1';run['metrics']['net_profit']='-1';self.assertFalse(eligible(run))

    def test_strict_csv_chunk_boundary_and_checkpoint_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'data.csv';start=1760000400//900*900
            def row(at):return f'{at*1000},100,101,99,100,5,{(at+900)*1000-1},500,1,2,200,0\n'
            p.write_text(''.join(row(start+i*900) for i in range(10001)))
            data,info=load_history(p);self.assertEqual(len(data),10001)
            p.write_text(''.join(row(start+i*900) for i in range(10000))+row(start+9999*900))
            with self.assertRaisesRegex(LabError,'MISSING_OR_DUPLICATE_BOUNDARY'):load_history(p)
            cp=Path(folder)/'checkpoint.gz';cp.write_bytes(gzip.compress(canonical(dict(fingerprint='wrong'))+b'\n'))
            with self.assertRaisesRegex(ValueError,'CHECKPOINT_IDENTITY'):read_checkpoint(cp,'correct',0,900)

class Reader(unittest.IsolatedAsyncioTestCase):
    async def test_owner_get_only_and_artifact_identity_no_production_access(self):
        app=FastAPI();app.include_router(router)
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_PROFILE_OWNER'):
            p=Path(folder)/'report.gz';r=dict(version='AURA43_PROFILES_1',symbol='BTCUSDT',research_only=True,activation_available=False,real_money_execution='DISABLED',code_hashes=reports.software(),development_selection={'winner':None},selection_hash=digest({'winner':None}),runs=[])
            r['checksum']=digest(r)
            with patch.object(reports,'REPORT',p):
                p.write_bytes(gzip.compress(canonical(r)));reports._load.cache_clear()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                    self.assertEqual((await c.get('/api/lab/profiles43')).status_code,401)
                    auth=('aura','DUMMY_PROFILE_OWNER');a=await c.get('/api/lab/profiles43',auth=auth)
                    self.assertEqual(a.status_code,200);self.assertIn('no-store',a.headers['cache-control']);self.assertIsNone(a.json()['development_selection']['winner'])
                    self.assertEqual((await c.post('/api/lab/profiles43',auth=auth)).status_code,405)
                    for query in ('variant=invalid','variant=Balanced%2F..','split=bad','limit=201','offset=-1'):
                        self.assertEqual((await c.get('/api/lab/profiles43/detail?'+query,auth=auth)).status_code,422)
                self.assertFalse(hasattr(app.state,'auto42'))
                r['checksum']='tampered';p.write_bytes(gzip.compress(canonical(r)));reports._load.cache_clear()
                with self.assertRaises(LabError):reports.summary()
