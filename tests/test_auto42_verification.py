"""Proof isolation and replay adapter equivalence; fixtures are not market results."""
import asyncio
from copy import deepcopy
from pathlib import Path
import ast
import unittest
from unittest.mock import patch

from scripts.verify_auto42_execution import run
from scripts.replay_auto42_verification import PrefixCache,snapshot
import app.intelligence.market_context as mc
from tests.test_market_intelligence import bars

class ExecutionVerification(unittest.IsolatedAsyncioTestCase):
    async def test_production_controller_open_persist_restart_close_and_controls(self):
        result=await run();self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['cases']),5)
        self.assertEqual(result['live_autonomy'],'NOT_TESTED');self.assertEqual(result['supabase_integration'],'NOT_TESTED')
        for case in result['cases']:
            self.assertEqual((case['opened'],case['closed']),(1,1));self.assertTrue(case['restart_restored'])
            self.assertIn('TEST_ONLY',case['closed_trade']['id'])
    async def test_no_runtime_configuration_or_private_exchange_calls(self):
        def forbidden(*args,**kwargs):raise AssertionError('Forbidden runtime client')
        with patch('app.automated.storage.SupabaseStore',side_effect=forbidden),patch('app.automated.service.configured',side_effect=forbidden):
            self.assertEqual((await run())['status'],'PASS')

class Causality(unittest.TestCase):
    def test_batch_prefix_equals_native_all_timeframes_no_future_leak(self):
        series=bars(4175)
        # Fixtures start on UTC boundary; preserve the exact rolling-start window.
        cache=PrefixCache(series)
        for n in (4160,4161,4167,4175):
            at=series[n-1].time+900
            expected=mc.analyze_window(series[:n],at)
            with cache.installed():actual=mc.analyze_window(series[:n],at)
            self.assertEqual(expected,actual,n)
        changed=deepcopy(series)
        from app.lab.models import Bar
        from decimal import Decimal as D
        for i in range(4161,len(changed)):
            b=changed[i];changed[i]=Bar(b.time,b.open*2,b.high*2,b.low*2,b.close*2,b.volume)
        altered=PrefixCache(changed)
        for step in (900,3600,14400):
            prefix=[b for b in cache.frames[step] if b.time+step<=series[4160].time+900]
            self.assertEqual(cache.states_for(prefix,step),altered.states_for(prefix,step))
    def test_cache_rejects_source_mismatch(self):
        series=bars(300);c=PrefixCache(series)
        with self.assertRaisesRegex(ValueError,'PREFIX_CACHE_MISMATCH'):c.states_for(series[1:])
    def test_replay_has_no_live_controller_db_or_network_path(self):
        tree=ast.parse(Path('scripts/replay_auto42_verification.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith(('app.automated.service','app.automated.storage','httpx','requests','app.bybit_demo','app.testnet')))

class Checkpoints(unittest.TestCase):
    def test_resume_identity_sequence_and_partial_write(self):
        import tempfile,json
        from scripts.replay_auto42_verification import read_checkpoint
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'checkpoint.jsonl';header=json.dumps(dict(fingerprint='test'))+'\n'
            row=dict(closed_at=900,decision=dict(direction=None,reason='WAIT'))
            complete=header+json.dumps([row])+'\n';p.write_text(complete+'[{incomplete')
            self.assertEqual(read_checkpoint(p,'test',0,1800),[row]);self.assertEqual(p.read_text(),complete)
            with self.assertRaises(ValueError):read_checkpoint(p,'wrong',0,1800)
            p.write_text(header+json.dumps([row,row])+'\n')
            with self.assertRaises(ValueError):read_checkpoint(p,'test',0,1800)
    def test_completed_corruption_is_not_skipped(self):
        import tempfile,json
        from scripts.replay_auto42_verification import read_checkpoint
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'checkpoint.jsonl';p.write_text(json.dumps(dict(fingerprint='test'))+'\nnot-json\n')
            with self.assertRaises(ValueError):read_checkpoint(p,'test',0,1800)

class ReplayDelivery(unittest.TestCase):
    def test_complete_checkpoint_can_write_report_without_recalculating_signals(self):
        import tempfile,json,io
        from types import SimpleNamespace
        from scripts import replay_auto42_verification as runner
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'replay.json';out.with_suffix('.checkpoint.jsonl').write_text('placeholder')
            start=1700000000//14400*14400;series=[SimpleNamespace(time=start+i*900) for i in range(14000)];end=series[-1].time+900
            info=dict(sha256='TEST_ONLY',count=len(series),start=start,end_exclusive=end,source_claim='SYNTHETIC_UNIT_FIXTURE')
            def results(bars,rows,begin,end,days):return dict(status='PASS',days=days,evaluated_candles=days*96)
            with patch.object(runner,'load_binance_csv',return_value=(series,info)),patch.object(runner,'read_checkpoint',return_value=[dict(closed_at=end)]),patch.object(runner,'replay',side_effect=results),patch('sys.stdout',io.StringIO()):
                runner.main(['--csv',str(Path(folder)/'TEST_ONLY.csv'),'--output',str(out)])
            value=json.loads(out.read_text());self.assertEqual(value['source']['identity'],mc.SOURCE)
            self.assertEqual(value['status'],'PASS');self.assertEqual([p['days'] for p in value['periods']],[7,30,90])

class AccountingOracle(unittest.TestCase):
    def test_invalid_balance_fees_or_curve_never_pass(self):
        from scripts.build_auto42_verification_report import audit_accounting
        base=dict(trades=[],remaining_position=None,realized_net_pnl='0',fees='0',slippage='0',final_balance='10000',profit_factor=None,
                  equity_curve=[dict(equity='10000')],days=7,max_drawdown_pct='0')
        self.assertEqual(audit_accounting(dict(periods=[base]))['status'],'PASS')
        for change in (dict(final_balance='10001'),dict(fees='1'),dict(equity_curve=[dict(equity='9000')])):
            with self.assertRaises(AssertionError):audit_accounting(dict(periods=[dict(base,**change)]))

class VerificationSafety(unittest.TestCase):
    def test_optimized_python_cannot_disable_assertions_and_generate_pass(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-O','-c','import asyncio;from scripts.verify_auto42_execution import run;asyncio.run(run())'],capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0);self.assertIn('VERIFICATION_REQUIRES_ASSERTIONS',result.stderr)
