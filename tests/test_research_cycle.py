"""Standard-library offline regressions; synthetic fixtures are not PnL evidence."""
import ast
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.lab.models import Bar,Baseline
from app.lab.strategies import Decision
from app.lab.execution import simulate
from app.lab.local_csv import load_binance_csv
from app.lab.models import LabError
from scripts import research_candidates as candidates
from scripts import run_research_cycle as research


def bars(n=150):
    return [Bar(i*900,D(100+i%13),D(102+i%13),D(99+i%13),D(101+i%13),D(20)) for i in range(n)]


class ResearchCycleTests(unittest.TestCase):
    def setUp(self):
        self.protocol=research.load_protocol()
        self.strategies=candidates.registry(self.protocol)

    def test_all_candidates_ignore_future_prices(self):
        old=bars(100)
        future=[Bar(i*900,D(9999),D(20000),D(1),D(15000),D(99999)) for i in range(100,150)]
        for name,strategy in self.strategies.items():
            with self.subTest(strategy=name):
                self.assertEqual(strategy.generate(old),strategy.generate(old+future)[:100])

    def test_registry_and_nested_macd_parameters_immutable(self):
        with self.assertRaises(TypeError):self.strategies['E']=self.strategies['A']
        with self.assertRaises(TypeError):self.strategies['D'].parameters['rsi']=1
        self.assertIsInstance(self.strategies['D'].parameters['macd'],tuple)

    def test_donchian_current_high_excluded_and_atr_stops(self):
        rows=[Bar(i*900,D(100),D(101),D(99),D(100),D(20)) for i in range(51)]
        rows[-1]=Bar(50*900,D(100),D(103),D(99),D(102),D(20))
        decision=self.strategies['A'].generate(rows)[-1]
        self.assertEqual(decision.direction,'LONG')
        self.assertEqual(decision.stop_distance,D(str((2*13+4)/14))*2)

    def test_rsi_cross_requires_range_regime(self):
        rows=bars(70);fast=[100.]*70;slow=[100.]*70;rs=[50.]*70
        rs[59],rs[60]=29.,31.;at=[2.]*70;adx=[15.]*70;hist=[1.]*70
        with patch.object(candidates,'context',return_value=(fast,slow,rs,at,adx,hist)):
            self.assertEqual(self.strategies['C'].generate(rows)[60].direction,'LONG')
            adx[60]=30.
            self.assertIsNone(self.strategies['C'].generate(rows)[60].direction)

    def test_d_alternative_requires_real_volume_and_macd_confirmation(self):
        rows=[Bar(i*900,D(102),D(103),D(101),D(102),D(20)) for i in range(70)]
        values=([101.]*70,[100.]*70,[56.]*70,[2.]*70,[15.]*70,[1.]*70)
        with patch.object(candidates,'context',return_value=values):
            self.assertEqual(self.strategies['D'].generate(rows)[60].direction,'LONG')
            rows[60]=Bar(60*900,D(102),D(103),D(101),D(102),D(0))
            self.assertIsNone(self.strategies['D'].generate(rows)[60].direction)

    def test_missing_file_is_not_zero_profit_or_synthetic_run(self):
        with tempfile.TemporaryDirectory() as directory:
            result=research.run(Path(directory)/'missing.csv')
        self.assertEqual(result['status'],'BLOCKED_HISTORY')
        self.assertFalse(result['actual_backtest_performed'])
        for row in result['results']:
            self.assertIsNone(row['metrics']);self.assertIsNone(row['signals'])
            self.assertIsNone(row['trades']);self.assertIsNone(row['equity_curve'])

    def test_native_reference_serialized_config_and_source_guard(self):
        # A legitimate new API router changes app/main.py's source fingerprint.
        # The frozen native replay must then be refused, not silently blessed.
        import hashlib,json
        stored=json.loads((research.ROOT/'docs/FIXED_STRATEGY_RESULTS.json').read_bytes())['historical_pattern']
        changed=any(hashlib.sha256((research.ROOT/p).read_bytes()).hexdigest()!=h for p,h in stored['software_sha256'].items())
        if changed:
            with self.assertRaisesRegex(ValueError,'Native reference source version changed'):
                research.native_reference({'sha256':'cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07'})
        else:
            reference=research.native_reference({'sha256':'cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07'})
            self.assertEqual(reference['status'],'COMPLETE')
            self.assertFalse(reference['ranked'])
            self.assertIn('NOT REEXECUTED',reference['provenance'])
        with self.assertRaises(ValueError):research.native_reference({'sha256':'wrong'})

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'existing.json';output.write_bytes(b'preserve')
            with self.assertRaises(SystemExit):research.main(['missing.csv','--output',str(output)])
            self.assertEqual(output.read_bytes(),b'preserve')

    def test_next_open_ignores_signal_bar_extremes(self):
        rows=[Bar(0,D(100),D(200),D(1),D(100),D(20)),Bar(900,D(103),D(104),D(102),D(103),D(20))]
        result=simulate(rows,[Decision('LONG',D(2),D(4)),Decision()],0,2,900,Baseline())
        self.assertEqual(result['trades'][0]['entry_time'],900)
        self.assertEqual(result['trades'][0]['exit_reason'],'SEGMENT_END_CLOSE')

    def test_both_hits_are_stop_first_for_both_directions(self):
        rows=[Bar(0,D(100),D(101),D(99),D(100),D(20)),Bar(900,D(100),D(105),D(95),D(100),D(20))]
        for side in ('LONG','SHORT'):
            result=simulate(rows,[Decision(side,D(2),D(4)),Decision()],0,2,900,Baseline())
            self.assertEqual(result['trades'][0]['exit_reason'],'STOP_LOSS_AMBIGUOUS')
            self.assertLess(D(result['trades'][0]['realized_pnl']),0)

    def test_stop_gap_adverse(self):
        rows=[Bar(0,D(100),D(101),D(99),D(100),D(20)),
              Bar(900,D(100),D(101),D(99),D(100),D(20)),
              Bar(1800,D(90),D(91),D(89),D(90),D(20))]
        result=simulate(rows,[Decision('LONG',D(2),D(4)),Decision(),Decision()],0,3,900,Baseline())
        self.assertEqual(result['trades'][0]['exit_reason'],'STOP_GAP')
        self.assertEqual(result['trades'][0]['exit_raw_price'],'90')

    def test_rational_fee_slippage_oracle_and_decimal_context(self):
        rows=[Bar(0,D(100),D(101),D(99),D(100),D(20)),
              Bar(900,D(100),D(101),D(99),D(101),D(20))]
        signals=[Decision('LONG',D(20),D(40)),Decision()]
        original=simulate(rows,signals,0,2,900,Baseline())
        with localcontext() as ctx:
            ctx.prec=6
            self.assertEqual(original,simulate(rows,signals,0,2,900,Baseline()))
        trade=original['trades'][0];qty=F(trade['size'])
        entry=F(100)*F(2001,2000);exit_=F(101)*F(1999,2000)
        self.assertEqual(F(trade['entry_price']),entry)
        self.assertEqual(F(trade['exit_price']),exit_)
        def ceil_ticks(x):return -(-x.numerator//x.denominator)
        self.assertEqual(F(trade['entry_fee']),F(ceil_ticks(entry*qty*F(1,1000)*10**8),10**8))
        self.assertEqual(F(trade['exit_fee']),F(ceil_ticks(exit_*qty*F(1,1000)*10**8),10**8))
        self.assertLessEqual(D(trade['risk_usdt']),D(trade['risk_budget_usdt']))
        self.assertLessEqual(D(trade['notional']),D(2000))
        self.assertEqual(D(original['metrics']['final_balance']),D(10000)+D(trade['realized_pnl']))

    def test_split_and_replay_deterministic(self):
        rows=bars(100);signals=[Decision() for _ in rows];signals[49]=Decision('LONG',D(2),D(4))
        a=simulate(rows,signals,50,100,900,Baseline())
        self.assertEqual(a,simulate(rows,signals,50,100,900,Baseline()))
        self.assertEqual(a['trades'],[])
        self.assertIsNone(a['metrics']['expectancy'])
        self.assertIsNone(a['metrics']['profit_factor'])

    def test_no_private_exchange_dependency_or_live_activation(self):
        for module in (candidates,research):
            source=Path(module.__file__).read_text();tree=ast.parse(source)
            imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            self.assertFalse(any(x in ','.join(imports) for x in ('app.main','app.paper','bybit','testnet','httpx','requests')))
            self.assertNotIn('os.getenv',source)
            self.assertNotIn('create_order',source)
            self.assertNotIn('cancel_order',source)

    def test_month_end_open_exit_counts_carry_but_close_exit_does_not(self):
        cutoff=1788220800 # September UTC start
        rows=[Bar(cutoff-900,D(100),D(101),D(99),D(100),D(20))]
        trade=dict(entry_time=cutoff-1800,exit_time=cutoff,exit_reason='STRATEGY_EXIT_NEXT_OPEN')
        result=dict(monthly=[dict(month='2026-08')],trades=[trade])
        self.assertEqual(research.open_position_audit(result,rows,0,1)[0]['positions_carrying_next_month'],1)
        trade['exit_reason']='STOP_LOSS'
        self.assertEqual(research.open_position_audit(result,rows,0,1)[0]['positions_carrying_next_month'],0)

    def test_loader_rejects_missing_duplicate_and_malformed_prices(self):
        base=1699992000
        def row(i):
            stamp=(base+i*900)*1000
            return ','.join(map(str,[stamp,100,101,99,100,20,stamp+900000-1]))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'fixture.csv'
            for lines in ([row(0),row(2)],[row(0),row(0)],[row(0).replace(',101,',',98,')]):
                p.write_text('\n'.join(lines)+'\n')
                with self.assertRaises(LabError):load_binance_csv(p)

    def test_long_and_short_profit_loss_rational_pnl(self):
        def nearest(x):
            q,r=divmod(x.numerator,x.denominator)
            return q+int(2*r>x.denominator or (2*r==x.denominator and q%2==1))
        def ceiling(x):return -(-x.numerator//x.denominator)
        for side,last in (('LONG',110),('LONG',90),('SHORT',90),('SHORT',110)):
            with self.subTest(side=side,last=last):
                rows=[Bar(0,D(100),D(101),D(99),D(100),D(20)),
                      Bar(900,D(100),D(max(last,100)+1),D(min(last,100)-1),D(last),D(20))]
                run=simulate(rows,[Decision(side,D(20),D(40)),Decision()],0,2,900,Baseline())
                t=run['trades'][0];qty=F(t['size']);sign=1 if side=='LONG' else -1
                entry=F(100)*(1+sign*F(1,2000));exit_=F(last)*(1-sign*F(1,2000))
                gross=F(nearest(sign*(exit_-entry)*qty*10**8),10**8)
                ef=F(ceiling(entry*qty*F(1,1000)*10**8),10**8)
                xf=F(ceiling(exit_*qty*F(1,1000)*10**8),10**8)
                self.assertEqual(F(t['realized_pnl']),gross-ef-xf)


if __name__=='__main__':unittest.main()
