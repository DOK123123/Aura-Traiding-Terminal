"""Independent offline inverse, execution and money regressions (not performance data)."""
import ast
from dataclasses import replace
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest

from app.lab.execution import simulate
from app.lab.models import Bar, Baseline
from app.lab.strategies import Decision
from scripts import research_inverse as research
from scripts.research_candidates import registry
from scripts.run_research_cycle import load_protocol


def candles(values):
    return [Bar(i*900,D(str(p)),D(str(p+1)),D(str(p-1)),D(str(p)),D(20)) for i,p in enumerate(values)]


class InverseResearchTests(unittest.TestCase):
    def test_mapping_wait_and_exit_contract(self):
        original=[Decision('LONG',D(2),D(4),True,False),Decision('SHORT',D(3),D(6),False,True),Decision()]
        one=research.invert(original,'I');two=research.invert(original,'II')
        self.assertEqual([d.direction for d in one],['SHORT','LONG',None])
        self.assertEqual([(d.exit_long,d.exit_short) for d in one],[(True,False),(False,True),(False,False)])
        self.assertEqual([(d.exit_long,d.exit_short) for d in two],[(False,True),(True,False),(False,False)])
        self.assertEqual(two[0].stop_distance,D(2));self.assertEqual(two[0].target_distance,D(4))
        self.assertEqual(original[0].direction,'LONG')

    def test_invalid_variants_and_directions_rejected(self):
        with self.assertRaises(ValueError):research.invert([], 'OPTIMIZED')
        with self.assertRaises(ValueError):research.invert([Decision('BUY')], 'I')

    def test_involution_directions_exits_not_history(self):
        ds=[Decision('LONG',D(2),D(4),True,False),Decision('SHORT'),Decision()]
        for v in ('I','II'):
            twice=research.invert(research.invert(ds,v),v)
            self.assertEqual([replace(d,reason='') for d in ds],[replace(d,reason='') for d in twice])

    def test_each_candidate_inversion_causal_on_prefix(self):
        prefix=candles([100+i%13 for i in range(100)])
        future=[Bar(i*900,D(10000),D(20000),D(1),D(15000),D(999)) for i in range(100,150)]
        for strategy in registry(load_protocol()).values():
            for v in ('I','II'):
                with self.subTest(strategy=strategy.identifier,variant=v):
                    self.assertEqual(research.invert(strategy.generate(prefix),v),research.invert(strategy.generate(prefix+future),v)[:100])

    def test_signal_only_and_mirrored_are_distinct_executions(self):
        bars=candles([100,100,101,102])
        ds=[Decision('LONG',D(10),D(20)),Decision(None,None,None,False,True),Decision(),Decision()]
        one=simulate(bars,research.invert(ds,'I'),0,4,900,Baseline())
        two=simulate(bars,research.invert(ds,'II'),0,4,900,Baseline())
        self.assertEqual(one['trades'][0]['exit_reason'],'STRATEGY_EXIT_NEXT_OPEN')
        self.assertEqual(one['trades'][0]['exit_time'],1800)
        self.assertEqual(two['trades'][0]['exit_reason'],'SEGMENT_END_CLOSE')
        self.assertEqual(two['trades'][0]['exit_time'],3600)

    def test_next_open_not_signal_extremes(self):
        bars=candles([100,103]);bars[0]=Bar(0,D(100),D(200),D(1),D(100),D(20))
        ds=research.invert([Decision('LONG',D(10),D(20)),Decision()],'II')
        outcome=simulate(bars,ds,0,2,900,Baseline())
        self.assertEqual(outcome['trades'][0]['entry_time'],900)
        self.assertEqual(outcome['trades'][0]['entry_raw_price'],'103')
        self.assertEqual(outcome['trades'][0]['exit_reason'],'SEGMENT_END_CLOSE')

    def test_zero_cost_symmetry_and_symmetric_risk(self):
        bars=candles([100,100,105])
        base=replace(Baseline(),fee_bps='0',slippage_bps='0')
        decisions=[Decision('LONG',D(20),D(40)),Decision(),Decision()]
        long=simulate(bars,decisions,0,3,900,base)
        short=simulate(bars,research.invert(decisions,'II'),0,3,900,base)
        lt,st=long['trades'][0],short['trades'][0]
        self.assertEqual(lt['size'],st['size']);self.assertEqual(lt['risk_usdt'],st['risk_usdt'])
        self.assertEqual(D(lt['realized_pnl']),-D(st['realized_pnl']))
        self.assertEqual(D(lt['entry_price'])-D(lt['stop_loss']),D(st['stop_loss'])-D(st['entry_price']))

    def test_nonzero_cost_inverse_is_not_negated_net(self):
        bars=candles([100,100,105]);ds=[Decision('LONG',D(20),D(40)),Decision(),Decision()]
        long=simulate(bars,ds,0,3,900,Baseline())
        short=simulate(bars,research.invert(ds,'II'),0,3,900,Baseline())
        self.assertNotEqual(D(long['metrics']['net_profit']),-D(short['metrics']['net_profit']))
        self.assertLess(D(long['metrics']['net_profit'])+D(short['metrics']['net_profit']),0)

    def test_both_side_protective_touch_stop_first(self):
        bars=candles([100,100]);bars[-1]=Bar(900,D(100),D(110),D(90),D(100),D(20))
        for side in ('LONG','SHORT'):
            r=simulate(bars,[Decision(side,D(2),D(4)),Decision()],0,2,900,Baseline())
            self.assertEqual(r['trades'][0]['exit_reason'],'STOP_LOSS_AMBIGUOUS')
            self.assertEqual(research.verify_accounting(r,bars,Baseline()),1)

    def test_gap_adverse_and_target_gap_capped_both_sides(self):
        for side,gap,reason,raw in [('LONG',90,'STOP_GAP',90),('SHORT',110,'STOP_GAP',110),
                                   ('LONG',110,'TAKE_PROFIT_GAP_CONSERVATIVE',D('104.05')),
                                   ('SHORT',90,'TAKE_PROFIT_GAP_CONSERVATIVE',D('95.95'))]:
            with self.subTest(side=side,gap=gap):
                bars=candles([100,100,gap])
                result=simulate(bars,[Decision(side,D(2),D(4)),Decision(),Decision()],0,3,900,Baseline())
                t=result['trades'][0]
                self.assertEqual(t['exit_reason'],reason);self.assertEqual(D(t['exit_raw_price']),D(raw))
                research.verify_accounting(result,bars,Baseline())

    def test_fee_and_pnl_rational_oracle_all_directions(self):
        for side,last in [('LONG',110),('LONG',90),('SHORT',90),('SHORT',110)]:
            with self.subTest(side=side,last=last):
                bars=candles([100,100,last]);ds=[Decision(side,D(20),D(40)),Decision(),Decision()]
                r=simulate(bars,ds,0,3,900,Baseline());t=r['trades'][0]
                sign=1 if side=='LONG' else -1;q=F(t['size'])
                ep=F(100)*(1+sign*F(1,2000));xp=F(last)*(1-sign*F(1,2000))
                self.assertEqual(F(t['entry_price']),ep);self.assertEqual(F(t['exit_price']),xp)
                for price,key in ((ep,'entry_fee'),(xp,'exit_fee')):
                    exact=price*q/1000*10**8
                    ceil=-(-exact.numerator//exact.denominator)
                    self.assertEqual(F(t[key]),F(ceil,10**8))
                research.verify_accounting(r,bars,Baseline())

    def test_break_even_and_no_double_slippage(self):
        bars=candles([100,100,110]);r=simulate(bars,[Decision('LONG',D(20),D(40)),Decision(),Decision()],0,3,900,Baseline())
        e=research.economy(r['trades'])
        self.assertEqual(D(e['net_pnl']),D(e['gross_filled_price_pnl'])-D(e['fees']))
        self.assertLessEqual(abs(D(e['rounding_residual'])),D('.00000001'))
        t=r['trades'][0];turn=(D(t['entry_price'])+D(t['exit_price']))*D(t['size'])
        self.assertEqual(D(e['fixed_path_fee_break_even_bps']), (D(t['gross_price_pnl'])/turn*10000).quantize(D('.00000001')))

    def test_zero_trades_undefined_not_fake_positive(self):
        e=research.economy([])
        self.assertIsNone(e['fixed_path_fee_break_even_bps'])
        self.assertFalse(e['nonnegative_break_even_fee_exists'])
        self.assertIsNone(e['holding_seconds']['mean'])

    def test_entry_and_exit_follow_previous_closed_decision(self):
        bars=candles([100,100,102]);ds=[Decision('LONG',D(20),D(40)),Decision(None,None,None,True,False),Decision()]
        result=simulate(bars,ds,0,3,900,Baseline())
        research.verify_signal_execution(result,bars,ds)
        with self.assertRaises(ValueError):research.verify_signal_execution(result,bars,research.invert(ds,'I'))
        wrong=[ds[0],Decision(),ds[2]]
        with self.assertRaises(ValueError):research.verify_signal_execution(result,bars,wrong)

    def test_test_split_does_not_execute_development_signal(self):
        bars=candles([100]*6);ds=[Decision() for _ in bars]
        ds[2]=Decision('LONG',D(20),D(40))
        for v in ('ORIGINAL','I','II'):
            result=simulate(bars,research.invert(ds,v),3,6,900,Baseline())
            self.assertEqual(result['trades'],[])
            self.assertEqual(result['metrics']['final_balance'],'10000')

    def test_auditor_detects_corrupted_money_and_dd(self):
        bars=candles([100,100,99]);ds=[Decision('LONG',D(20),D(40)),Decision(),Decision()]
        r=simulate(bars,ds,0,3,900,Baseline());r['metrics']['max_drawdown_pct']='0'
        with self.assertRaises(ValueError):research.verify_accounting(r,bars,Baseline())
        r=simulate(bars,ds,0,3,900,Baseline());r['trades'][0]['realized_pnl']='123'
        with self.assertRaises(ValueError):research.verify_accounting(r,bars,Baseline())

    def test_replay_decimal_context_restart_consistency_and_one_position(self):
        bars=candles([100,101,102,103,104]);ds=[Decision('LONG',D(20),D(40)) for _ in bars]
        first=simulate(bars,ds,0,5,900,Baseline())
        with localcontext() as ctx:
            ctx.prec=6
            self.assertEqual(first,simulate(bars,ds,0,5,900,Baseline()))
        self.assertEqual(len(first['trades']),1);research.verify_accounting(first,bars,Baseline())
        self.assertLessEqual(D(first['trades'][0]['notional']),2000)
        self.assertLessEqual(D(first['trades'][0]['risk_usdt']),100)

    def test_missing_history_blocks_and_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'missing.csv';r=research.run(p)
            self.assertFalse(r['actual_backtest_performed']);self.assertIsNone(r['results'])
            out=Path(folder)/'exists.json';out.write_text('preserve')
            with self.assertRaises(SystemExit):research.main([str(p),'--output',str(out)])
            self.assertEqual(out.read_text(),'preserve')

    def test_no_private_exchange_write_or_credentials_or_db(self):
        source=Path(research.__file__).read_text();tree=ast.parse(source)
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(any(x in ','.join(imports) for x in ('app.main','app.paper','bybit','testnet','httpx','requests')))
        for token in ('create_order','cancel_order','amend_order','withdraw','transfer','getenv','sqlite','API_SECRET'):
            self.assertNotIn(token,source)


if __name__=='__main__':unittest.main()
