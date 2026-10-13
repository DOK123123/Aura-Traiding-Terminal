"""Manual intelligence safety, real-data replay and deterministic detector fixtures."""
import asyncio,json,os,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from app.lab.models import Bar
from app.intelligence import api,patterns
from app.intelligence.service import Service,IntelligenceError,DATA_SHA
from app.intelligence.analysis import analyze


def b(i,o,h,l,c):return Bar(i*900,D(str(o)),D(str(h)),D(str(l)),D(str(c)),D(20))
def trend(up):return [b(i,120+i if up else 140-i,122+i if up else 142-i,118+i if up else 138-i,120+i if up else 140-i) for i in range(5)]


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.clock=[1000.];self.s=Service(Path(self.temp.name)/'replay.sqlite3',clock=lambda:self.clock[0])
    def tearDown(self):self.temp.cleanup()
    def create(self,manual=True):return self.s.create('15m',1672531200,manual)
    def test_real_pipeline_wait_manual_confirmation_and_net_pnl(self):
        state=self.create();sid=state['session_id'];self.assertEqual(state['analysis']['strategy'],'WAIT')
        self.assertEqual(state['analysis']['evidence']['count'],64)
        self.assertEqual(state['portfolio']['trades'],[])
        state=self.s.proposal(sid,True);pid=state['proposal']['id'];self.assertTrue(state['proposal']['hypothetical_manual'])
        state=self.s.decide(sid,pid,True);self.assertEqual(state['proposal']['status'],'CONFIRMED')
        self.assertEqual(state['portfolio']['trades'],[]);self.assertIsNone(state['portfolio']['open_position'])
        for _ in range(12):
            state=self.s.advance(sid,32)
            if state['portfolio']['trades']:break
        t=state['portfolio']['trades'][0];self.assertEqual(t['entry_time'],1672532100)
        self.assertEqual(t['exit_reason'],'STOP_LOSS');self.assertEqual(t['realized_pnl'],'-45.07967723')
        self.assertEqual(t['fees'],'4.04103864');self.assertEqual(len(state['portfolio']['trades']),1)
        self.assertEqual(state['proposal']['status'],'PAPER_EXECUTED')
    def test_no_confirmation_never_executes(self):
        v=self.create();sid=v['session_id'];self.s.proposal(sid,True);v=self.s.advance(sid,32)
        self.assertEqual(v['proposal']['status'],'EXPIRED');self.assertEqual(v['portfolio']['trades'],[])
        self.assertIsNone(v['portfolio']['open_position'])
    def test_no_edge_cannot_silently_propose(self):
        sid=self.create(False)['session_id']
        for manual in (False,True):
            with self.assertRaises(IntelligenceError):self.s.proposal(sid,manual)
    def test_risk_refusal_and_server_config_no_edit_endpoint(self):
        sid=self.create()['session_id']
        with self.s.db() as db:tiny=self.s.portfolio(self.s.load(db,sid))
        tiny['equity_curve'][-1]['balance']='0.00000001'
        with patch.object(self.s,'portfolio',return_value=tiny):
            with self.assertRaises(IntelligenceError):self.s.proposal(sid,True)
        self.assertEqual(self.s.state(sid)['config']['risk_pct'],'1')
    def test_future_replay_prices_do_not_affect_current_analysis(self):
        initial=self.create();sid=initial['session_id']
        with self.s.db() as db:i=self.s.load(db,sid)['cursor']
        self.s.frames['15m']=self.s.frames['15m'][:i+1]+[replace(x,open=D(9999),high=D(20000),low=D(1),close=D(15000)) for x in self.s.frames['15m'][i+1:]]
        self.assertEqual(initial['analysis'],self.s.state(sid)['analysis'])
    def test_indicators_volume_pivots_and_fvg_are_actual_detectors(self):
        bs=self.s.bars[3000:3250]
        bs=list(bs);bs[-1]=replace(bs[-1],volume=sum(x.volume for x in bs[-21:-1]))
        ids=[p['pattern_id'] for p in patterns.detect(bs)]
        self.assertIn('ema_alignment',ids);self.assertIn('adx_strength',ids);self.assertIn('volume_spike',ids)
        xs=[b(0,100,101,99,100),b(1,100,101,99,100),b(2,110,115,105,111),b(3,100,102,99,100),b(4,100,101,99,100)]
        self.assertIn('swing_high',[p['pattern_id'] for p in patterns.detect(xs)])
        xs[-1]=b(4,120,122,119,121)
        self.assertIn('fvg',[p['pattern_id'] for p in patterns.detect(xs)])
    def test_concurrent_duplicate_confirmation_exactly_one_signal(self):
        sid=self.create()['session_id'];pid=self.s.proposal(sid,True)['proposal']['id']
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:self.s.decide(sid,pid,True),range(4)))
        with self.s.db() as db:self.assertEqual(len(self.s.load(db,sid)['confirmed']),1)
        self.assertIsNotNone(self.s.advance(sid)['portfolio']['open_position'])
    def test_expired_and_wrong_id_never_execute(self):
        sid=self.create()['session_id'];pid=self.s.proposal(sid,True)['proposal']['id'];self.clock[0]+=301
        with self.assertRaises(IntelligenceError):self.s.decide(sid,pid,True)
        self.assertIsNone(self.s.advance(sid)['portfolio']['open_position'])
    def test_restart_recovers_same_journal(self):
        sid=self.create()['session_id'];pid=self.s.proposal(sid,True)['proposal']['id'];self.s.decide(sid,pid,True);v=self.s.advance(sid,32)
        restarted=Service(self.s.path,clock=lambda:self.clock[0]);self.assertEqual(v,restarted.state(sid))
    def test_missing_history_fails_closed(self):
        with patch('app.intelligence.service.DATA',Path(self.temp.name)/'missing'):
            with self.assertRaises(OSError):Service(self.s.path)
    def test_future_events_are_excluded_and_small_samples_wait(self):
        bars=self.s.bars[3000:3250];cutoff=bars[-1].time+900
        events=[dict(r,resolved_at=cutoff+1) for r in self.s.pack['index']]
        result=analyze(bars,events,'15m');self.assertEqual(result['strategy'],'WAIT');self.assertEqual(result['evidence']['count'],0)
    def test_forming_and_gap_candles_rejected(self):
        bs=trend(True)+[b(5,125,126,124,125)]
        with self.assertRaises(Exception):patterns.detect(bs,cutoff=bs[-1].time+899)
        with self.assertRaises(ValueError):patterns.detect(bs[:2]+bs[3:])
    def test_context_hammer_and_hanging_man_are_distinct(self):
        candle=b(5,130,131.1,125,131)
        self.assertIn('hammer',[p['pattern_id'] for p in patterns.detect(trend(False)+[candle])])
        ids=[p['pattern_id'] for p in patterns.detect(trend(True)+[candle])]
        self.assertIn('hanging_man',ids);self.assertNotIn('hammer',ids)
    def test_shapes_doji_marubozu_spinning_inverted_context(self):
        fixtures=[('doji',b(5,100,103,97,100)),('long_legged_doji',b(5,100,103,97,100)),('dragonfly_doji',b(5,100,100.1,96,100)),('gravestone_doji',b(5,100,104,99.9,100)),('marubozu',b(5,100,110,100,110)),('spinning_top',b(5,100,103,98,101)),('inverted_hammer',b(5,130,136,129.9,131))]
        for name,bar in fixtures:
            with self.subTest(name=name):self.assertIn(name,[p['pattern_id'] for p in patterns.detect(trend(False)+[bar])])
        self.assertIn('shooting_star',[p['pattern_id'] for p in patterns.detect(trend(True)+[fixtures[-1][1]])])
    def test_engulf_harami_context_and_inside_outside(self):
        cases=[('bullish_engulfing',False,b(5,130,131,123,124),b(6,123,132,122,131)),('bearish_engulfing',True,b(5,130,137,129,136),b(6,137,138,128,129)),('bullish_harami',False,b(5,135,136,123,124),b(6,127,129,126,128)),('bearish_harami',True,b(5,125,137,124,136),b(6,132,133,130,131)),('harami_cross',False,b(5,135,136,123,124),b(6,129,131,127,129)),('inside_bar',True,b(5,130,138,124,136),b(6,131,135,126,132)),('outside_bar',True,b(5,130,137,125,136),b(6,130,139,124,133))]
        for name,up,a,c in cases:
            with self.subTest(name=name):self.assertIn(name,[p['pattern_id'] for p in patterns.detect(trend(up)+[a,c])])
    def test_morning_evening_and_doji_star(self):
        for up,name in [(False,'morning'),(True,'evening')]:
            xs=[b(i,140-i*5 if not up else 100+i*5,142-i*5 if not up else 102+i*5,138-i*5 if not up else 98+i*5,140-i*5 if not up else 100+i*5) for i in range(4)]
            extra=[b(4,128,129,117,118),b(5,118,120,116,118),b(6,118,127,117,126)] if not up else [b(4,118,129,117,128),b(5,128,130,126,128),b(6,128,129,117,118)]
            ids=[p['pattern_id'] for p in patterns.detect(xs+extra)]
            self.assertIn(name+'_star',ids);self.assertIn(name+'_doji_star',ids)
    def test_catalogue_never_claims_planned_detection(self):
        self.assertGreater(len(patterns.catalogue()),30)
        self.assertTrue(all(p['algorithm'] is None for p in patterns.catalogue() if p['status']=='PLANNED'))
    def test_no_exchange_write_imports(self):
        for p in Path('app/intelligence').glob('*.py'):
            source=p.read_text()
            for forbidden in ('create_order','cancel_order','amend_order','api-demo.bybit','app.bybit','app.testnet'):
                self.assertNotIn(forbidden,source)
    def test_owner_and_csrf_api_end_to_end(self):
        async def run():
            app=FastAPI();app.include_router(api.router)
            with patch.object(api,'service',return_value=self.s),patch.dict(os.environ,{'AURA_TESTNET_VIEW_PASSWORD':'dummy-only-test-password'}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                    self.assertEqual((await c.get('/api/intelligence/manifest')).status_code,401)
                    c.auth=('aura','dummy-only-test-password')
                    self.assertEqual((await c.post('/api/intelligence/sessions',json={'timeframe':'15m','candle_time':1672531200})).status_code,403)
                    h={'X-Aura-Paper':'local-only','Origin':'http://test'}
                    v=(await c.post('/api/intelligence/sessions',headers=h,json={'timeframe':'15m','candle_time':1672531200,'manual_research':True})).json()
                    sid=v['session_id'];r=await c.post('/api/intelligence/sessions/'+sid+'/proposal',headers=h,json={'manual':True});pid=r.json()['proposal']['id']
                    r=await c.post('/api/intelligence/sessions/'+sid+'/decision',headers=h,json={'proposal_id':pid,'confirm':True});self.assertEqual(r.status_code,200)
                    r=await c.post('/api/intelligence/sessions/'+sid+'/advance',headers=h,json={'steps':32});self.assertIsNotNone(r.json()['portfolio']['open_position'])
                    self.assertEqual((await c.post('/api/intelligence/sessions',headers=dict(h,Origin='https://foreign'),json={'timeframe':'15m','candle_time':1672531200})).status_code,403)
        asyncio.run(run())


if __name__=='__main__':unittest.main()
