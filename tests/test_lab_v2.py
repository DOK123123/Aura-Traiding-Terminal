"""Synthetic fixtures only for invariant tests, never historical performance."""
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
from app.lab.models import digest,canonical,LabError
from app.lab.v2_strategies import prepare,decide,FAMILIES
from app.lab import v2_execution as lab
from app.automated import engine as native
from tests.test_adaptive43 import candidate
from tests.test_auto42 import bar
from tests.test_market_intelligence import bars


def data_case(short=False):
    bs,s,_=candidate();bs[-1]=replace(bs[-1],volume=D(1000))
    if short:bs=[replace(b,open=200-b.open,high=200-b.low,low=200-b.high,close=200-b.close) for b in bs]
    f=prepare(bs,900);i=len(bs)-1
    for k,v in dict(ema20=100,ema50=101 if short else 99,ema200=102 if short else 98,atr=2,adx=30,rsi=40 if short else 60,di_plus=10 if short else 30,di_minus=30 if short else 10).items():f[k][i]=float(v)
    f['rsi'][i-1]=50.;f['ema20'][i-1]=99. if short else 101.;f['ema50'][i-1]=101.1 if short else 98.9
    return bs,f,i

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ('original_signal_at','strategy_timeframe')}
    if isinstance(value,list):return [clean(v) for v in value]
    return value

class Rules(unittest.TestCase):
    def test_all_families_long_short_and_cost_aware_stops(self):
        for short in (False,True):
            bs,f,i=data_case(short)
            for family in FAMILIES:
                d=decide(f,i,family,closed_at=bs[-1].time+900)
                self.assertEqual(d['direction'],'SHORT' if short else 'LONG',(short,family,d))
                self.assertGreaterEqual(D(d['context']['expected_net_rr']),D('1.2'))
                stop,target=D(d['stop_loss']),D(d['take_profit'])
                self.assertTrue(target<bs[-1].close<stop if short else stop<bs[-1].close<target)

    def test_reject_unclosed_missing_invalid_indicators_volume_and_false_breakout(self):
        bs,f,i=data_case()
        for family in FAMILIES:self.assertIsNone(decide(f,i,family,closed_at=bs[-1].time)['direction'])
        f['adx'][i]=float('nan')
        for family in FAMILIES:self.assertIsNone(decide(f,i,family,closed_at=bs[-1].time+900)['direction'])
        bs,f,i=data_case();f['bars'][i-4]=replace(bs[i-4],time=bs[i-4].time-900)
        self.assertEqual(decide(f,i,'DONCHIAN',closed_at=bs[-1].time+900)['reason'],'MISSING_CANDLES')
        bs,f,i=data_case();f['bars'][i]=replace(bs[i],volume=D(0))
        self.assertIsNone(decide(f,i,'DONCHIAN',closed_at=bs[-1].time+900)['direction'])
        bs,f,i=data_case();f['bars'][i]=replace(bs[i],close=D('100.5'))
        self.assertFalse(decide(f,i,'DONCHIAN',closed_at=bs[-1].time+900)['gates']['LONG']['range_break'])

    def test_all_timeframes_future_perturbation_has_no_effect(self):
        bs=bars(4224);cut=bs[4175].time+900
        changed=[b if b.time<cut else replace(b,open=b.open*2,high=b.high*2,low=b.low*2,close=b.close*2) for b in bs]
        for step in (900,3600,14400):
            a,b=prepare(bs,step),prepare(changed,step);i=max(i for i,x in enumerate(a['bars']) if x.time+step<=cut);at=a['bars'][i].time+step
            for key in ('ema20','ema50','ema200','atr','rsi','adx','di_plus','di_minus'):self.assertEqual(a[key][i],b[key][i])
            for family in FAMILIES:self.assertEqual(decide(a,i,family,closed_at=at),decide(b,i,family,closed_at=at))
            self.assertTrue(all(x.time+step<=at for x in a['bars'][:i+1]))

class Execution(unittest.TestCase):
    def initial(self,bs):
        at=bs[-1].time+900;s=lab.initial(at,epoch='LAB_V2_UNIT_ONLY');s.update(mode='ON',watermark=at-900,last_bar_hash=digest(bs[-2].data()));lab.mark(s,bs[-2],at-900);return s

    def test_native_equivalence_without_trail_risk_fees_duplicate_and_no_signal_fill(self):
        bs,f,i=data_case();d=decide(f,i,'DONCHIAN',closed_at=bs[-1].time+900);s=self.initial(bs);n=deepcopy(s)
        opened=0
        for j in range(4):
            decision=d if j==0 else dict(direction=None,reason='WAIT');now=bs[-1].time+930
            s,events=lab.advance(s,bs[-2:],decision,now);n,expected=native.advance(n,bs[-2:],decision,now)
            self.assertEqual(clean(s),clean(n));self.assertEqual(clean(events),clean(expected))
            if j==0:self.assertIsNone(s['position']);self.assertTrue(s['pending'])
            for event in events:
                if event['kind']=='OPEN':
                    opened+=1;p=event['payload'];self.assertLessEqual(D(p['risk_usdt']),D(p['risk_budget_usdt']));self.assertLessEqual(D(p['notional']),2000)
            again,none=lab.advance(s,bs[-2:],decision,now);self.assertEqual(again,s);self.assertEqual(none,[])
            bs.append(bar(bs[-1].time+900,open='103',high='115',low='90',close='103'))
        self.assertEqual(opened,1);self.assertEqual(s['trades'],1);self.assertLess(D(s['balance']),10000)

    def test_profit_locking_trail_is_causal_never_loosens_and_does_not_hit_past_bar(self):
        bs,f,i=data_case();d=decide(f,i,'TREND_ATR',closed_at=bs[-1].time+900);s=self.initial(bs)
        s,_=lab.advance(s,bs[-2:],d,bs[-1].time+930)
        bs.append(bar(bs[-1].time+900,open='103',high='104',low='102',close='103'))
        s,_=lab.advance(s,bs[-2:],dict(direction=None,reason='WAIT'),bs[-1].time+930)
        lab.ratchet(s,bs[-1],1,step=900);first=D(s['position']['stop_loss'])
        bs.append(bar(bs[-1].time+900,open='103',high='107',low='102',close='106'))
        s,events=lab.advance(s,bs[-2:],dict(direction=None,reason='WAIT'),bs[-1].time+930)
        self.assertIsNotNone(s['position']);lab.ratchet(s,bs[-1],.5,step=900)
        p=s['position'];self.assertGreater(D(p['stop_loss']),D(p['entry_price']));self.assertGreater(D(p['stop_loss']),first)
        self.assertLess(bs[-1].low,D(p['stop_loss'])) # New stop cannot hit the just-completed bar.
        self.assertEqual(p['stop_history'][-1]['effective_from'],bs[-1].time+900)
        old_stop=p['stop_loss'];lab.ratchet(s,bs[-1],10,step=900);self.assertEqual(old_stop,s['position']['stop_loss'])
        bs.append(bar(bs[-1].time+900,open='106',high='107',low='105',close='106'))
        s,events=lab.advance(s,bs[-2:],dict(direction=None,reason='WAIT'),bs[-1].time+930)
        closes=[e['payload'] for e in events if e['kind']=='CLOSE'];self.assertEqual(len(closes),1);self.assertGreater(D(closes[0]['realized_pnl']),0)
        self.assertEqual(closes[0]['initial_stop_loss'],d['stop_loss']);self.assertIsNone(s['position'])

    def test_future_or_pre_entry_trail_and_risk_halt(self):
        bs,f,i=data_case();s=self.initial(bs);s['max_drawdown_pct']='10'
        s,e=lab.advance(s,bs[-2:],decide(f,i,'DONCHIAN',closed_at=bs[-1].time+900),bs[-1].time+930)
        self.assertEqual(s['mode'],'PAUSED');self.assertIsNone(s['pending']);self.assertIsNone(s['position'])
        bs.append(bar(bs[-1].time+900));s,e=lab.advance(s,bs[-2:],dict(direction='LONG',reason='TEST'),bs[-1].time+930)
        self.assertEqual(s['mode'],'PAUSED');self.assertFalse(any(x['kind']=='OPEN' for x in e))

class Reader(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_owner_summary_full_reasons_pagination_and_side_filter(self):
        from app.lab import v2_report as reports
        from app.lab.api import router
        app=FastAPI();app.include_router(router)
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_V2_OWNER'):
            directory=Path(folder);log=directory/'decisions_DONCHIAN_1h_validation.jsonl.gz'
            raw=b''.join(canonical(dict(closed_at=i*3600,reason='WAIT',direction=None))+b'\n' for i in range(3));compressed=gzip.compress(raw,mtime=0);log.write_bytes(compressed)
            import hashlib
            row=dict(variant='DONCHIAN_1h',split='validation',trades=[dict(direction='LONG'),dict(direction='SHORT')],equity_curve=[],daily_equity=[],metrics={},decision_artifact=log.name,decision_sha256=hashlib.sha256(compressed).hexdigest(),decision_total=3)
            r=dict(version='AURA_STRATEGY_LAB_2.0',symbol='BTCUSDT',research_only=True,activation_available=False,real_money_execution='DISABLED',code_hashes=reports.software(),development_selection={'winner':None},selection_hash=digest({'winner':None}),runs=[row]);r['checksum']=digest(r)
            (directory/'report.json.gz').write_bytes(gzip.compress(canonical(r)))
            with patch.object(reports,'DIRECTORY',directory):
                reports._load.cache_clear()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                    self.assertEqual((await c.get('/api/lab/v2')).status_code,401);auth=('aura','DUMMY_V2_OWNER')
                    a=await c.get('/api/lab/v2',auth=auth);self.assertEqual(a.status_code,200);self.assertIn('no-store',a.headers['cache-control']);self.assertNotIn('trades',a.json()['runs'][0])
                    a=await c.get('/api/lab/v2/detail?variant=DONCHIAN_1h&split=validation&side=SHORT&offset=0&limit=1',auth=auth)
                    self.assertEqual(a.status_code,200);self.assertEqual(a.json()['trades'],[dict(direction='SHORT')]);self.assertEqual(a.json()['decision_total'],3)
                    self.assertEqual((await c.post('/api/lab/v2',auth=auth)).status_code,405)
                    for q in ('variant=invalid','side=invalid','split=bad','offset=-1','limit=201'):
                        self.assertEqual((await c.get('/api/lab/v2/detail?'+q,auth=auth)).status_code,422)
                self.assertFalse(hasattr(app.state,'auto42'))
                log.write_bytes(compressed+b'tampered')
                with self.assertRaises(LabError):reports.detail('DONCHIAN_1h','validation',0,1)
                row['decision_artifact']='../../other';r.pop('checksum');r['checksum']=digest(r)
                (directory/'report.json.gz').write_bytes(gzip.compress(canonical(r)));reports._load.cache_clear()
                with self.assertRaises(LabError):reports.detail('DONCHIAN_1h','validation',0,1)

class Protocol(unittest.TestCase):
    def test_delayed_execution_has_original_timestamp_and_no_boundary_carry(self):
        from scripts.research_lab_v2 import decisions,eligible
        bs,f,i=data_case();start=bs[-1].time-900;end=bs[-1].time+900
        rows=[dict(closed_at=start+900,decision=dict(direction='LONG',reason='TEST',signal_at=start+900),original={})]
        d=list(decisions(bs,'AURA42',rows,{},start,end,1))
        self.assertEqual(d[0]['decision']['reason'],'NO_NEW_CLOSED_TIMEFRAME')
        self.assertEqual(d[1]['decision']['original_signal_at'],start+900)
        self.assertTrue(all(r['closed_at']>start for r in d))
        r=dict(metrics=dict(trades=29,net_profit='100',profit_factor='2',max_drawdown_pct='1'),monthly={'x':dict(complete_calendar_month=True,net_profit='1')})
        self.assertFalse(eligible(r,30));r['metrics']['trades']=30;self.assertTrue(eligible(r,30))
        r['monthly']['x']['net_profit']='-1';self.assertFalse(eligible(r,30))
