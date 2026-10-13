"""Context algorithm fixtures and independent research safety/causality tests."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from app.lab.models import Bar,Baseline,digest
from app.lab.execution import simulate
from app.lab.strategies import Decision
from research.market_intelligence.structure import segment_states,prepare,VERSION,VECTOR_NAMES,zones
from research.market_intelligence.similarity import fit_normalizer,normalized,nearest,evidence,route,explain
from research.market_intelligence.strategies import candidates,decision
from research.market_intelligence.pipeline import protocol,hypotheses,classify
from scripts.run_market_intelligence import serialize_streams,restore_streams,cached


def bars(n=1200):
    return [Bar(1577836800+i*900,D(100)+D(i%7)/10,D(102)+D(i%7)/10,D(98)+D(i%7)/10,D(100)+D(i%7)/10,D(10)) for i in range(n)]


def pivots():
    xs=[Bar(1577836800+i*900,D(100),D(101),D(99),D(100),D(10)) for i in range(266)]
    for i,h in ((251,110),(257,112)):xs[i]=replace(xs[i],high=D(h))
    for i,l in ((254,95),(260,97)):xs[i]=replace(xs[i],low=D(l))
    return xs


def row():
    return dict(timestamp=1600000000,vector=[0.]*len(VECTOR_NAMES),trend_direction=1,trend_strength=30,breakout='LONG',failed_breakout=None,retest=None,volume_confirmed=True,mtf=dict(alignment=True,known_mask=3),relative_volume=2,pullback_depth_atr=1,range_detected=False,range_position=.5,rsi=55,regime='TREND_UP',volatility='EXPANSION',atr=2)


def scaler():return dict(fit_closed_through=100,means=[0.]*len(VECTOR_NAMES),scales=[1.]*len(VECTOR_NAMES))
def event(i,**kwargs):
    result=dict(timestamp=1000+i*345600,resolved_at=1000+i*345600+900,vector=[0.]*len(VECTOR_NAMES),regime='TREND_UP',mtf_mask=3,volume_known=True,family='BREAKOUT_CONTINUATION',direction='LONG',net_pnl='10',target_first=True)
    result.update(kwargs);return result


class MarketIntelligenceTests(unittest.TestCase):
    def test_fixed_budget_and_no2025_period(self):
        p=protocol(Path('.'));self.assertEqual(len(hypotheses(p)),42)
        self.assertEqual(p['selection']['known_comparison_family_minimum'],869)
        self.assertNotIn('2025',json.dumps(p['periods']).split('validation')[0])
    def test_future_prices_do_not_change_past_structure(self):
        xs=bars(400);prefix=segment_states(xs[:330]);changed=xs[:330]+[replace(b,open=D(200),high=D(300),low=D(150),close=D(250)) for b in xs[330:]]
        self.assertEqual(prefix,segment_states(changed)[:330])
    def test_confirmed_pivot_timestamp_separate_from_confirmation(self):
        rs=segment_states(pivots());p=next(p for p in rs[253]['confirmed_pivots'] if p['kind']=='HIGH')
        self.assertEqual(p['pivot_time'],pivots()[251].time);self.assertEqual(p['confirmation_time'],pivots()[253].time+900)
        self.assertFalse(rs[252]['confirmed_pivots'])
    def test_hh_hl_and_bos(self):
        xs=pivots();xs[263]=replace(xs[263],open=D(112),high=D(114),low=D(111),close=D(113))
        rs=segment_states(xs);self.assertEqual(rs[262]['high_leg'],'HH');self.assertEqual(rs[262]['low_leg'],'HL')
        self.assertEqual(rs[263]['breakout'],'LONG');self.assertEqual(rs[263]['structure_event'],'BOS')
    def test_failed_breakout_and_choch(self):
        xs=pivots();xs[263]=replace(xs[263],open=D(112),high=D(114),low=D(111),close=D(113))
        xs[264]=replace(xs[264],open=D(113),high=D(114),low=D(110),close=D(111))
        xs[265]=replace(xs[265],open=D(100),high=D(101),low=D(94),close=D(95))
        rs=segment_states(xs);self.assertEqual(rs[264]['failed_breakout'],'SHORT');self.assertEqual(rs[265]['structure_event'],'CHoCH')
    def test_retest_requires_later_confirmed_bar(self):
        xs=pivots();xs[263]=replace(xs[263],open=D(112),high=D(114),low=D(111),close=D(113))
        xs[264]=replace(xs[264],open=D('112.1'),high=D(114),low=D('111.95'),close=D('112.9'))
        rs=segment_states(xs);self.assertIsNone(rs[263]['retest']);self.assertEqual(rs[264]['retest'],'LONG')
    def test_liquidity_sweep_no_fake_direction_when_both_sides(self):
        xs=pivots();xs[263]=replace(xs[263],high=D(114),low=D(94))
        r=segment_states(xs)[263];self.assertEqual(r['liquidity_sweep'],'AMBIGUOUS');self.assertEqual(r['vector'][7],0)
    def test_equal_levels_and_order_block_operational(self):
        xs=pivots();xs[257]=replace(xs[257],high=D(110));self.assertTrue(segment_states(xs)[262]['equal_highs'])
        xs=pivots();xs[262]=replace(xs[262],open=D(101),close=D(100));xs[263]=replace(xs[263],open=D(112),high=D(114),low=D(111),close=D(113))
        ob=segment_states(xs)[263]['order_block'];self.assertEqual(ob['origin_time'],xs[262].time);self.assertEqual(ob['confirmation_time'],xs[263].time+900)
    def test_fvg_uses_real_three_bar_gap(self):
        xs=pivots();xs[263]=replace(xs[263],open=D(104),high=D(106),low=D(103),close=D(105))
        fvg=segment_states(xs)[263]['fvg'];self.assertEqual(fvg['side'],'LONG');self.assertEqual(fvg['lower'],'101')
    def test_forming_unordered_duplicate_and_gap_rejected(self):
        xs=bars(270)
        with self.assertRaises(Exception):segment_states(xs[:260]+xs[261:])
        with self.assertRaises(Exception):segment_states(xs[:260]+[xs[259]])
        #Closed candle validation is reused, including exact timestamp boundary.
        with self.assertRaises(Exception):xs[-1].validate(900,xs[-1].time+899)
    def test_gap_resets_context_and_mtf(self):
        xs=bars(3000);xs=xs[:1500]+xs[1501:];ps=prepare(xs)
        self.assertEqual(len(ps),2);self.assertTrue(all(r is None for r in ps[1][1][:249]))
        self.assertEqual(ps[1][1][249]['mtf']['known_mask'],0)
    def test_higher_timeframe_future_candle_cannot_align(self):
        xs=bars(4100);rs=prepare(xs[:4090]);changed=xs[:4090]+[replace(b,open=D(200),high=D(300),low=D(150),close=D(250)) for b in xs[4090:]]
        other=prepare(changed);self.assertEqual(rs[0][1],other[0][1][:4090])
        for r in other[0][1]:
            if r:
                for k in ('h1','h4'):
                    if r['mtf'][k]:self.assertLessEqual(r['mtf'][k]['closed_at'],r['timestamp'])
    def test_normalizer_ignores_future_rows_and_not_available_early(self):
        rs=[dict(timestamp=i,vector=[float(i%3)]*len(VECTOR_NAMES)) for i in range(2000)]
        a=fit_normalizer(rs,1200);rs[1300:]=[dict(timestamp=i,vector=[999.]*len(VECTOR_NAMES)) for i in range(1300,2000)]
        self.assertEqual(a,fit_normalizer(rs,1200))
        with self.assertRaises(ValueError):normalized([0.]*len(VECTOR_NAMES),a,1200)
    def test_invalid_vector_refused(self):
        with self.assertRaises(ValueError):normalized([float('nan')]*len(VECTOR_NAMES),scaler(),1000)
    def test_unresolved_future_event_excluded(self):
        q=dict(timestamp=10000000,vector=[0.]*len(VECTOR_NAMES),regime='TREND_UP',mtf_mask=3,family='BREAKOUT_CONTINUATION',direction='LONG')
        events=[event(1,resolved_at=q['timestamp']+1)]
        self.assertEqual(nearest(q,events,scaler()),[])
    def test_purge_and_similarity_regime_side_mask(self):
        q=dict(timestamp=10000000,vector=[0.]*len(VECTOR_NAMES),regime='TREND_UP',mtf_mask=3,family='BREAKOUT_CONTINUATION',direction='LONG')
        es=[event(1),event(1,timestamp=event(1)['timestamp']+900,resolved_at=event(1)['resolved_at']+900),event(2,regime='RANGE')]
        es.sort(key=lambda e:e['resolved_at']);found=nearest(q,es,scaler());self.assertEqual(len(found),1)
    def test_no_analogs_edge_router_waits(self):
        r=row();out=route(bars(1)[0],r,{},scaler(),'PCT_2_4');self.assertEqual(out['strategy'],'WAIT')
        self.assertTrue(any(x['reason']=='INSUFFICIENT_ANALOGS' for x in out['options']))
    def test_no_historical_edge_and_uncertainty(self):
        es=[dict(event(i),distance=0,net_pnl='-1') for i in range(40)]
        self.assertEqual(evidence(es)['status'],'NO_EDGE')
        self.assertEqual(evidence([])['status'],'INSUFFICIENT_DATA')
    def test_rule_and_nearest_are_explicit_baselines_not_live_permission(self):
        r=row();v=route(bars(1)[0],r,{},scaler(),'PCT_2_4','RULE');self.assertEqual(v['strategy'],'BREAKOUT_CONTINUATION')
        self.assertEqual(explain(bars(1)[0],r,{},scaler())['strategy'],'WAIT')
    def test_protective_sides_commission_risk_and_next_open(self):
        xs=bars(5);r=row()
        for side in ('LONG','SHORT'):
            ds=[decision(xs[0],r,'ALL',side,'PCT_2_4')]+[Decision()]*4
            out=simulate(xs,ds,0,5,900,Baseline());t=out['trades'][0]
            self.assertEqual(t['entry_time'],xs[1].time)
            self.assertLessEqual(D(t['risk_usdt']),D(100));self.assertLessEqual(D(t['notional']),D(2000));self.assertGreater(D(t['fees']),0)
            ep,sl,tp=map(D,(t['entry_price'],t['stop_loss'],t['take_profit']))
            self.assertTrue(sl<ep<tp if side=='LONG' else tp<ep<sl)
    def test_all_router_does_not_invalidate_by_new_entry_family(self):
        r=row();ds=decision(bars(1)[0],r,'ALL',None,'PCT_2_4')
        self.assertFalse(ds.exit_long);self.assertFalse(ds.exit_short)
    def test_stream_roundtrip_and_checkpoint_corruption(self):
        ds=[Decision('LONG',D(2),D(4))];value=serialize_streams(([(ds,None)],{},[]))
        self.assertEqual(restore_streams(value['streams'])[0][0],ds)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'state.gz';self.assertEqual(cached(p,'x',lambda:{'a':1}),cached(p,'x',lambda:{'a':2}))
            with self.assertRaises(ValueError):cached(p,'changed',lambda:{})
            p.write_bytes(b'bad')
            with self.assertRaises(ValueError):cached(p,'x',lambda:{})
    def test_insufficient_sample_cannot_pass(self):
        base=dict(metrics=dict(trades=0),full_period_execution_valid=True)
        self.assertEqual(classify(base,base,protocol(Path('.')))[0],'INSUFFICIENT_EVIDENCE')
    def test_rolling_breakout_is_not_claimed_as_confirmed_bos(self):
        xs=[Bar(1577836800+i*900,D(100)+D(i)/10,D('100.1')+D(i)/10,D('99.9')+D(i)/10,D(100)+D(i)/10,D(10)) for i in range(270)]
        xs[-1]=replace(xs[-1],high=xs[-1].high+2,close=xs[-1].close+2)
        r=segment_states(xs)[-1];self.assertEqual(r['breakout'],'LONG');self.assertIsNone(r['structure_event'])
    def test_positive_historical_evidence_never_authorizes_execution(self):
        r=row();es=[event(i,net_pnl='-1' if i%10==0 else '10') for i in range(50)]
        bank={('PCT_2_4','BREAKOUT_CONTINUATION','LONG','UNIVERSAL'):es}
        value=route(bars(1)[0],r,bank,scaler(),'PCT_2_4')
        self.assertEqual(value['strategy'],'BREAKOUT_CONTINUATION');self.assertEqual(value['execution'],'DISABLED')
        self.assertEqual(explain(bars(1)[0],r,bank,scaler())['strategy'],'WAIT')
    def test_absent_archive_is_blocked_without_compact_replay_fallback(self):
        from types import SimpleNamespace
        from scripts.run_market_intelligence import run
        with tempfile.TemporaryDirectory() as t:
            args=SimpleNamespace(output=Path(t)/'out',archive=Path(t)/'absent.zip',report=Path(t)/'report.json')
            with patch('scripts.run_market_intelligence.load_years',side_effect=AssertionError('Must not import fallback')):value=run(args)
            self.assertEqual(value['status'],'BLOCKED_DATA_REQUIRED');self.assertEqual(value['results'],[])
    def test_lh_ll_mirror_structure(self):
        xs=[replace(b,open=D(200)-b.open,high=D(200)-b.low,low=D(200)-b.high,close=D(200)-b.close) for b in pivots()]
        r=segment_states(xs)[262];self.assertEqual(r['high_leg'],'LH');self.assertEqual(r['low_leg'],'LL')
    def test_all_six_formal_setups_and_range_detection(self):
        b=replace(bars(1)[0],open=D(99),close=D(100))
        r=row();r.update(failed_breakout='SHORT',retest='LONG')
        found=candidates(b,r)
        self.assertTrue({'BREAKOUT_CONTINUATION','FAILED_BREAKOUT_REVERSAL','BREAKOUT_RETEST','TREND_PULLBACK','VOLATILITY_EXPANSION'}<=set(found))
        r.update(trend_strength=15,range_detected=True,range_position=.1,rsi=35,breakout=None,failed_breakout=None,retest=None)
        self.assertEqual(candidates(b,r)['RANGE_MEAN_REVERSION'],'LONG')
        self.assertTrue(segment_states(bars(300))[-1]['range_detected'])
    def test_analog_label_grid_matches_signal_grid_and_cost_refusal_is_not_gap(self):
        from research.market_intelligence.pipeline import build_banks
        xs=bars(1100);rows=[dict(row(),timestamp=b.time+900) for b in xs]
        p=protocol(Path('.'))
        with patch('research.market_intelligence.pipeline.candidates',return_value={'BREAKOUT_CONTINUATION':'LONG'}),patch('research.market_intelligence.pipeline.simulate',return_value={'trades':[],'rejections':{'TARGET_AFTER_COSTS':1},'open_position':None}) as mocked:
            bank,stats=build_banks([(xs,rows)],p)
            self.assertEqual(mocked.call_args_list[0].args[0][0].time,xs[1008].time)
            self.assertEqual(bank,{});self.assertGreater(stats['label_rejected:TARGET_AFTER_COSTS'],0)
            self.assertEqual(stats.get('unresolved_gap_labels',0),0)
    def test_invalid_router_and_normalizer_configuration_refused(self):
        with self.assertRaises(ValueError):route(bars(1)[0],row(),{},scaler(),'PCT_2_4','unknown')
        s=scaler();s['scales'][0]=0
        with self.assertRaises(ValueError):normalized([0.]*len(VECTOR_NAMES),s,1000)
    def test_real_execution_and_credentials_architecturally_absent(self):
        for p in Path('research').rglob('*.py'):
            text=p.read_text()
            for token in ('app.paper','app.bybit','app.testnet','httpx','requests','create_order','cancel_order','amend_order','os.environ','register('):self.assertNotIn(token,text)

if __name__=='__main__':unittest.main()
