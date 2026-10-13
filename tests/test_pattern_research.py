"""Independent offline research causality, execution and lock regression cases."""
from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from app.intelligence.patterns import detect
from app.lab.models import Bar,Baseline,digest
from app.lab.execution import simulate
from app.lab.strategies import Decision
from scripts.lab3_strategies import higher
from scripts.pattern_research import (protocol,hypotheses,prepare,side_for,streams,split_parts,
    period_run,blocked_bootstrap,lock_finalists,classify,write_artifact)


def bars(n=270,start=1577836800):
    return [Bar(start+i*900,D(100)+D(i)/100,D(102)+D(i)/100,D(98)+D(i)/100,D(100)+D(i)/100,D(20)) for i in range(n)]


class PatternResearchTests(unittest.TestCase):
    def test_budget_statuses_and_no_planned_models(self):
        p=protocol();grid=hypotheses(p)
        self.assertEqual(len(grid),810);self.assertEqual(len({x['id'] for x in grid}),810)
        self.assertEqual(len(p['patterns']),30)
        self.assertEqual(sum(x['status']=='PLANNED' for x in p['catalogue']),43)
    def test_past_only_prefix_reproducibility(self):
        xs=bars();a=prepare(xs[:260],'15m')[0][1]
        xs[260:]=[replace(b,open=D(500),high=D(600),low=D(400),close=D(500)) for b in xs[260:]]
        b=prepare(xs,'15m')[0][1]
        self.assertEqual(a,b[:260])
    def test_closed_candle_boundary(self):
        xs=bars(6)
        with self.assertRaises(Exception):detect(xs,cutoff=xs[-1].time+899)
        detect(xs,cutoff=xs[-1].time+900)
    def test_gap_warmup_reset(self):
        xs=bars(600);xs=xs[:260]+xs[261:]
        parts=prepare(xs,'15m');self.assertEqual(len(parts),2)
        self.assertTrue(all(r is None for r in parts[1][1][:249]))
        self.assertIsNotNone(parts[1][1][249])
    def test_higher_frames_complete_blocks_only(self):
        xs=bars(32);self.assertEqual(len(higher(xs,3600)),8)
        self.assertEqual(len(higher(xs[:7],3600)),1)
        self.assertEqual(len(higher(xs[:15],14400)),0)
        self.assertEqual(len(higher(xs[:2]+xs[3:],3600)),7)
    def test_confirmed_pivot_waits_for_second_right_bar(self):
        xs=bars(5);xs[2]=replace(xs[2],high=D(120))
        self.assertNotIn('swing_high',[p['pattern_id'] for p in detect(xs[:4])])
        p=next(p for p in detect(xs) if p['pattern_id']=='swing_high')
        self.assertEqual(p['timestamp'],xs[-1].time+900)
    def test_hammer_context_and_engulfing_direction(self):
        from tests.test_intelligence import trend,b
        candle=b(5,130,131.1,125,131)
        self.assertIn('hammer',[p['pattern_id'] for p in detect(trend(False)+[candle])])
        self.assertNotIn('hammer',[p['pattern_id'] for p in detect(trend(True)+[candle])])
        ps=detect(trend(False)+[b(5,130,131,123,124),b(6,123,132,122,131)])
        self.assertEqual(next(p['direction'] for p in ps if p['pattern_id']=='bullish_engulfing'),'LONG')
    def test_neutral_needs_explicit_direction(self):
        row=dict(patterns={'doji':None},direction=None,adx=30,rsi=60,volume=2,vol=1,near_low=True,near_high=False)
        h=dict(pattern='doji',context='NONE')
        self.assertIsNone(side_for(row,h));row['direction']='LONG';self.assertEqual(side_for(row,h),'LONG')
    def test_next_open_fee_slippage_and_accounting(self):
        xs=bars(4);ds=[Decision('LONG',D(5),D(10)),Decision(),Decision(),Decision()]
        out=simulate(xs,ds,0,4,900,Baseline());t=out['trades'][0]
        self.assertEqual(t['entry_time'],xs[1].time)
        self.assertEqual(D(t['entry_price']),xs[1].open*D('1.0005'))
        self.assertLessEqual(D(t['risk_usdt']),D(100));self.assertLessEqual(D(t['notional']),D(2000))
        self.assertEqual(D(t['gross_price_pnl'])-D(t['fees']),D(t['realized_pnl']))
        self.assertGreater(D(t['slippage_usdt']),0)
    def test_gap_stop_and_ambiguous_stop_first(self):
        xs=bars(4);xs[1]=replace(xs[1],high=D(112),low=D(94));ds=[Decision('LONG',D(5),D(10))]+[Decision()]*3
        t=simulate(xs,ds,0,4,900,Baseline())['trades'][0]
        self.assertEqual(t['exit_reason'],'STOP_LOSS_AMBIGUOUS')
        xs=bars(4);xs[2]=replace(xs[2],open=D(90),high=D(91),low=D(88),close=D(90))
        t=simulate(xs,ds,0,4,900,Baseline())['trades'][0]
        self.assertEqual(t['exit_reason'],'STOP_GAP');self.assertEqual(t['exit_raw_price'],'90')
    def test_overlap_one_position_only(self):
        xs=bars(20);ds=[Decision('LONG',D(10),D(20)) for _ in xs]
        out=simulate(xs,ds,0,len(xs),900,Baseline())
        self.assertEqual(len(out['trades']),1)
    def test_gap_open_position_censored_not_fake_fill(self):
        xs=bars(260);prepared=prepare(xs,'15m');rows=prepared[0][1]
        for r in rows:
            if r:r['patterns']={'doji':'LONG'}
        h=dict(id='test',pattern='doji',context='NONE',exit='PCT_2_4')
        # Wide stops to ensure genuinely unresolved exposure at a missing next bar.
        h['exit']='ATR_2_4'
        for r in rows:
            if r:r['atr']=20
        out=period_run(prepared,h,xs[0].time,xs[-1].time+1800,Baseline(),900)
        self.assertFalse(out['full_period_execution_valid']);self.assertEqual(len(out['censored_positions']),1)
        self.assertEqual(out['metrics']['net_profit'],'0');self.assertEqual(out['metrics']['final_balance'],'10000.00000000')
    def test_period_balance_isolation(self):
        xs=bars();prepared=prepare(xs,'15m');h=dict(id='test',pattern='doji',context='NONE',exit='PCT_2_4')
        a=period_run(prepared,h,xs[250].time,xs[-1].time+900,Baseline(),900)
        b=period_run(prepared,h,xs[250].time,xs[-1].time+900,Baseline(),900)
        self.assertEqual(a,b);self.assertEqual(a['equity_curve'][0]['balance'],'10000')
    def test_block_bootstrap_deterministic_and_not_iid(self):
        curve=[dict(time=i*86400,equity=str(10000+i+(i%14)*3)) for i in range(100)]
        a=blocked_bootstrap(curve,reps=99);self.assertEqual(a,blocked_bootstrap(curve,reps=99));self.assertEqual(a['block_days'],14)
    def test_holdout_lock_and_checkpoint_reproducible(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'lock.json';f=protocol();sha=lock_finalists(path,f,[])
            self.assertEqual(sha,lock_finalists(path,f,[]))
            with self.assertRaises(ValueError):lock_finalists(path,f,[dict(id='changed')])
            a=Path(t)/'a.gz';b=Path(t)/'b.gz';self.assertEqual(write_artifact(a,{'x':1}),write_artifact(b,{'x':1}))
    def test_positive_pnl_alone_never_passes_multiplicity(self):
        p=protocol();r=dict(metrics=dict(net_profit='100',trades=150,max_drawdown_pct='1'),full_period_execution_valid=True,by_year={'2020':dict(net_pnl='100')},bootstrap=dict(p_value=.001,lower95_mean_daily=1))
        label,reasons=classify(r,r,p);self.assertEqual(label,'INSUFFICIENT_EVIDENCE');self.assertIn('MULTIPLE_COMPARISON_UNCERTAINTY',reasons)
    def test_feasible_strong_candidate_and_missing_year_rejection(self):
        p=protocol();r=dict(metrics=dict(net_profit='100',trades=150,max_drawdown_pct='1'),full_period_execution_valid=True,by_year={str(y):dict(net_pnl='30') for y in (2020,2021,2022)},bootstrap=dict(p_value=.00005,lower95_mean_daily=1))
        self.assertEqual(classify(r,r,p)[0],'RESEARCH_CANDIDATE')
        del r['by_year']['2021'];self.assertIn('YEAR_UNSTABLE',classify(r,r,p)[1])
    def test_matched_random_control_count_and_seed_reproducibility(self):
        from scripts.pattern_research_controls import control_rows
        xs=bars();prepared=prepare(xs,'15m');h=dict(pattern='ema_alignment',context='NONE')
        a=control_rows(prepared,'RANDOM_MATCHED',xs[0].time,xs[-1].time+900,h,42)
        self.assertEqual(a,control_rows(prepared,'RANDOM_MATCHED',xs[0].time,xs[-1].time+900,h,42))
        self.assertEqual(sum(side_for(r,h) is not None for r in prepared[0][1]),sum(r is not None and bool(r['patterns']) for r in a[0][1]))
    def test_independent_math_auditor_accepts_and_catches_tampering(self):
        from scripts.audit_pattern_research import check
        xs=bars(4);ds=[Decision('SHORT',D(5),D(10))]+[Decision()]*3
        run=simulate(xs,ds,0,4,900,Baseline())
        self.assertEqual(check(run,'10','5',{b.time:b.data() for b in xs},900),1)
        run['trades'][0]['exit_fee']='0'
        with self.assertRaises(ValueError):check(run,'10','5',{b.time:b.data() for b in xs},900)
    def test_resume_canonical_protocol_and_changed_config_refused(self):
        from scripts.run_pattern_research import compatible_protocol
        p=protocol();saved=json.loads(json.dumps(p))
        self.assertTrue(compatible_protocol(saved,p))
        saved['baseline']['risk_pct']='2';self.assertFalse(compatible_protocol(saved,p))
        saved=json.loads(json.dumps(p));saved['source_hash']='0'*64
        self.assertFalse(compatible_protocol(saved,p))
    def test_every_qualified_candidate_gets_validation_even_below_top10(self):
        from scripts.run_pattern_research import validation_targets,selection_result
        ranked=[dict(hypothesis=dict(id=str(i)),full_period_execution_valid=True) for i in range(12)]
        targets=validation_targets(ranked,[ranked[-1]])
        self.assertIn(ranked[-1],targets);self.assertEqual(len(targets),11)
        empty=dict(metrics=dict(trades=0),full_period_execution_valid=True)
        self.assertEqual(selection_result(empty,empty,protocol()),('INSUFFICIENT_EVIDENCE',['NO_TRADES']))
    def test_artifact_corruption_refused(self):
        from scripts.run_pattern_research import artifact_read
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'data.gz';sha=write_artifact(p,{'x':1});p.write_bytes(b'bad')
            with self.assertRaises(ValueError):artifact_read(p,sha)
    def test_isolated_no_private_clients_or_runtime_registration(self):
        for name in ('pattern_research.py','run_pattern_research.py'):
            s=(Path('scripts')/name).read_text()
            for token in ('app.paper','app.bybit_demo','app.testnet','httpx','requests','create_order','cancel_order','register('):self.assertNotIn(token,s)

if __name__=='__main__':unittest.main()
