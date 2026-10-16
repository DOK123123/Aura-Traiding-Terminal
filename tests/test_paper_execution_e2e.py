"""Isolated executable harness, not Render/Supabase live verification."""
import json
from copy import deepcopy
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

from scripts.paper_e2e_oracle import quantize,audit_close
from scripts.verify_paper_e2e import isolated
from app.automated.storage import SupabaseStore

class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='aura-e2e-regression-')
        cls.path=Path(cls.folder.name)/'PAPER_EXECUTION_TECHNICAL_VERIFICATION.json'
        run=subprocess.run([sys.executable,'-m','scripts.verify_paper_e2e','--output',str(cls.path),'--sandbox-poll'],capture_output=True,text=True,timeout=60)
        if run.returncode:raise AssertionError('Harness CLI failed: '+run.stdout+run.stderr)
        cls.report=json.loads(cls.path.read_bytes())
    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()
    def scenario(self,n):return next(c for c in self.report['scenarios'] if c['id']==n)

    def test_all_twelve_scenarios_pass_without_live_verified(self):
        r=self.report;self.assertEqual(r['technical_execution'],'PASS');self.assertEqual(r['scenarios_passed'],12)
        self.assertEqual(r['live_autonomous_execution'],'WAITING_FOR_REAL_SIGNAL');self.assertFalse(r['proves_live_autonomy'])
        self.assertEqual(r['actual_open_count'],15);self.assertEqual(r['actual_close_count'],15)
        for c in r['scenarios']:
            for s in c['subcases']:
                self.assertFalse(s['live_cycle_verified']);self.assertEqual(s['starting_balance'],'10000')
                for key in ('direction','entry_price','size','stop_loss','take_profit','exit_price','fees','slippage','net_pnl','final_balance','actual_open_count','actual_close_count'):self.assertIn(key,s)

    def test_independent_exact_accounting_and_position_updates_all_cycles(self):
        for case in self.report['scenarios']:
            for s in case['subcases']:
                if s['actual_open_count']==0:continue
                self.assertEqual(F(s['final_balance']),F(10000)+F(s['net_pnl']))
                self.assertEqual(F(s['fees']),F(s['entry_fee'])+F(s['exit_fee']))
                self.assertLessEqual(F(s['risk_usdt']),F(50));self.assertGreater(F(s['slippage']),0)
                self.assertIn('POSITION_UPDATE',s['event_types']);self.assertIn('SIGNAL',s['event_types'])
                self.assertEqual(s['actual_open_count'],s['actual_close_count']);self.assertTrue(s['position_update'])

    def test_new_process_restart_not_just_a_new_object(self):
        c=self.scenario(6)['subcases'][0]['checks'];self.assertTrue(c['pid_distinct']);self.assertTrue(c['duplicate']);self.assertEqual(c['monitor_status'],'WAITING_FOR_REAL_SIGNAL')

    def test_atomic_failure_really_occurred_after_writes_and_recovery_same_candle(self):
        a=self.scenario(9)['subcases'][0];b=self.scenario(10)['subcases'][0]
        self.assertEqual(a['actual_open_count'],0);self.assertEqual(a['final_balance'],'10000')
        self.assertTrue(a['checks']['failed_after_account_update']);self.assertEqual(a['checks']['attempted_open_rows'],1)
        self.assertTrue(a['checks']['atomic_state_events_watermark_rollback']);self.assertTrue(b['checks']['same_candle_retry'])
        self.assertEqual(b['checks']['monitor_after_recovery'],'WAITING_FOR_REAL_SIGNAL');self.assertEqual(b['actual_open_count'],1)

    def test_scheduler_real_client_and_forced_concurrency_not_a_mock_engine(self):
        c=self.scenario(8)['subcases'][0]['checks'];self.assertTrue(c['real_scheduler_client']);self.assertTrue(c['in_process_ASGI_only']);self.assertEqual(c['runs'],3);self.assertEqual(c['repeated_opens'],0)
        c=self.scenario(11)['subcases'][0]['checks'];self.assertTrue(c['same_revision_barrier']);self.assertEqual(c['winning_opens'],1);self.assertEqual(c['duplicate_loser'],1)
        self.assertTrue(self.scenario(7)['subcases'][0]['checks']['new_slot_same_candle'])

    def test_ambiguous_and_gap_execution_preserve_conservatism(self):
        for c in self.scenario(5)['subcases']:self.assertEqual(c['exit_reason'],'STOP_LOSS_AMBIGUOUS');self.assertLess(F(c['net_pnl']),0)
        for c in self.scenario(12)['subcases']:
            if 'STOP' in c['label']:self.assertLess(F(c['net_pnl']),-50);self.assertEqual(c['exit_reason'],'STOP_GAP')
            else:self.assertEqual(c['exit_reason'],'TAKE_PROFIT_GAP_CONSERVATIVE');self.assertEqual(c['exit_raw_price'],c['take_profit'])

    def test_cli_cannot_select_database_or_overwrite_unrelated_report(self):
        p=Path(self.folder.name)/'unrelated.json';p.write_text('DO NOT CHANGE')
        run=subprocess.run([sys.executable,'-m','scripts.verify_paper_e2e','--output',str(p)],capture_output=True,timeout=10)
        self.assertNotEqual(run.returncode,0);self.assertEqual(p.read_text(),'DO NOT CHANGE')
        run=subprocess.run([sys.executable,'-m','scripts.verify_paper_e2e','--db','auto-paper-42.sqlite3'],capture_output=True,timeout=10)
        self.assertNotEqual(run.returncode,0)

class OracleAndGuard(unittest.TestCase):
    def test_fraction_rounding_reference_positive_negative_and_half_even(self):
        self.assertEqual(quantize(F(1,3)),F(33333333,10**8));self.assertEqual(quantize(F(1,3),True),F(33333334,10**8))
        self.assertEqual(quantize(F(5,10**9)),0);self.assertEqual(quantize(F(-15,10**9)),F(-2,10**8))

    def test_network_and_supabase_construction_forbidden_even_with_host_environment(self):
        from unittest.mock import patch
        with patch.dict('os.environ',RENDER='true',RENDER_GIT_COMMIT='a'*40):
            with isolated():
                for method in ('connect','connect_ex'):
                    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
                        with self.assertRaisesRegex(AssertionError,'HARNESS_NETWORK_FORBIDDEN'):getattr(s,method)(('127.0.0.1',9))
                with self.assertRaisesRegex(AssertionError,'HARNESS_SUPABASE_FORBIDDEN'):SupabaseStore('https://example.invalid','DUMMY_NEVER_USED')
                import os
                self.assertEqual(os.getenv('RENDER'),'')

    def test_oracle_rejects_tampered_engine_trade_math(self):
        from app.automated.engine import initial,open_virtual,protective,mark
        from scripts.verify_auto42_execution import bar,SOURCE
        s=initial(900,epoch='TEST_ORACLE_ONLY');s['mode']='ON'
        plan=dict(direction='LONG',signal_at=900,stop_loss='98',take_profit='104',reason='TEST_ONLY',source=SOURCE)
        open_virtual(s,plan,bar(900),1800);p=deepcopy(s['position']);b=bar(1800,h='105');t=protective(s,b,2700)['payload'];mark(s,b,2700)
        self.assertTrue(audit_close(p,t,s,b))
        for key in ('realized_pnl','exit_price','exit_fee','size'):
            bad=deepcopy(t);bad[key]=str(D(bad[key])+1)
            with self.assertRaises(AssertionError):audit_close(p,bad,s,b)
