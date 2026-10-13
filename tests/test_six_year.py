"""Gap/censoring regression fixtures, not historical-return estimates."""
from dataclasses import replace
from decimal import Decimal as D
import unittest
import hashlib,io,zipfile

from app.lab.models import Bar,Baseline
from app.lab.strategies import Decision
from app.lab.execution import simulate
from scripts.run_six_year import segments,censor_gap,period_job
from scripts.lab3_strategies import generate,higher
from scripts.research_inverse import verify_accounting
from scripts.run_lab3 import audit_trailing
from scripts.lab3_history import monthly_bytes


def rows(n,start=1577836800):
    return [Bar(start+i*900,D(100),D(101),D(99),D(100),D(20)) for i in range(n)]


class SixYearTests(unittest.TestCase):
    def test_import_quarantines_bad_close_without_changing_price_or_filling(self):
        name='BTCUSDT-15m-2020-01.zip';base=1577836800;lines=[]
        for i in (0,1,3):
            t=base+i*900;close=(t+900)*1000-1 if i!=1 else t*1000-1
            lines.append(','.join(map(str,[t*1000,100,101,99,100,10,close,1000,3,4,400,0])))
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr(name[:-4]+'.csv','\n'.join(lines))
        raw=stream.getvalue();check=hashlib.sha256(raw).hexdigest().encode()
        with self.assertRaises(ValueError):monthly_bytes(raw,check,name)
        actual,meta=monthly_bytes(raw,check,name,allow_gaps=True)
        self.assertEqual([b.time for b in actual],[base,base+2700])
        self.assertEqual(meta['raw_candles'],3);self.assertEqual(meta['candles'],2)
        self.assertEqual(len(meta['quarantined']),1);self.assertEqual(meta['raw_gaps'][0]['missing'],1)
        self.assertTrue(all(b.close==D(100) for b in actual))
    def test_segments_preserve_only_observed_bars(self):
        first=rows(1005);second=rows(1005,first[-1].time+2700)
        parts=segments(first+second)
        self.assertEqual([len(x) for x in parts],[1005,1005])
        self.assertEqual([b for p in parts for b in p],first+second)

    def test_state_and_indicator_warmup_restart(self):
        first=rows(1100);second=rows(1100,first[-1].time+2700)
        second=[replace(b,open=D(200),high=D(201),low=D(199),close=D(200)) for b in second]
        for name in 'ABCDE':
            signals,_=generate(second,name)
            self.assertTrue(all(d.direction is None for d in signals[:200]))
            self.assertEqual(generate(segments(first+second)[1],name),generate(second,name))

    def test_no_htf_bucket_crosses_gap(self):
        bs=rows(16,0)
        for part in segments(bs[:5]+bs[6:]):
            self.assertEqual(higher(part,14400),[])

    def test_gap_end_does_not_invent_exit(self):
        bs=rows(3);ds=[Decision('LONG',D(10),D(20)),Decision(),Decision()]
        value=simulate(bs,ds,0,3,900,Baseline(),close_at_end=False)
        self.assertEqual(value['trades'],[]);self.assertIsNotNone(value['open_position'])
        self.assertNotIn('exit_price',value['open_position'])
        unknown=censor_gap(value)
        self.assertIsNone(unknown['exit_price']);self.assertIsNone(unknown['realized_pnl'])
        self.assertEqual(D(value['equity_curve'][-1]['balance']),10000)
        self.assertGreater(D(unknown['known_entry_fee']),0)

    def test_gap_censoring_not_full_period_return(self):
        first=rows(1005);second=rows(1005,first[-1].time+2700)
        ds=[Decision() for _ in first];ds[1000]=Decision('LONG',D(10),D(20))
        value=period_job([first,second],[(ds,None),([Decision() for _ in second],None)],[['RANGE_LOW']*1005]*2,
            first[0].time,second[-1].time+900,Baseline(),None)
        self.assertFalse(value['full_period_execution_valid'])
        self.assertEqual(value['statistics_scope'],'CONDITIONAL_CLOSED_TRADES')
        self.assertEqual(value['metrics']['trades'],0)
        self.assertEqual(len(value['unresolved_positions']),1)
        self.assertEqual(value['warmup_skipped'],2000)
        self.assertEqual(value['processed_candles'],10)

    def test_pending_signal_not_executed_across_gap(self):
        first=rows(1001);second=rows(1001,first[-1].time+2700)
        ds=[Decision() for _ in first];ds[-1]=Decision('LONG',D(10),D(20))
        result=period_job([first,second],[(ds,None),([Decision() for _ in second],None)],[['RANGE_LOW']*1001]*2,
            first[0].time,second[-1].time+900,Baseline(),None)
        self.assertEqual(result['metrics']['trades'],0);self.assertEqual(result['unresolved_positions'],[])

    def test_period_end_known_close_preserves_previous_model(self):
        bs=rows(3);ds=[Decision('LONG',D(10),D(20)),Decision(),Decision()]
        old=simulate(bs,ds,0,3,900,Baseline())
        explicit=simulate(bs,ds,0,3,900,Baseline(),close_at_end=True)
        self.assertEqual(old,explicit);self.assertEqual(old['trades'][0]['exit_reason'],'SEGMENT_END_CLOSE')

    def test_known_stop_before_gap_is_not_censored(self):
        bs=rows(3);bs[-1]=replace(bs[-1],low=D(80),close=D(90))
        value=simulate(bs,[Decision('LONG',D(10),D(20)),Decision(),Decision()],0,3,900,Baseline(),close_at_end=False)
        self.assertIsNone(censor_gap(value));self.assertEqual(value['trades'][0]['exit_reason'],'STOP_LOSS')
        verify_accounting(value,bs,Baseline())

    def test_stress_trailing_independent_fee_oracle(self):
        bs=rows(3);bs[1]=replace(bs[1],high=D(110),close=D(109));bs[2]=replace(bs[2],open=D(108),high=D(109),low=D(106),close=D(108))
        base=replace(Baseline(),starting_balance='9000',fee_bps='20',slippage_bps='10')
        value=simulate(bs,[Decision('LONG',D(2),D(20)),Decision(),Decision()],0,3,900,base,trailing_atr=[D(3)]*3)
        self.assertEqual(audit_trailing(value,bs,[D(3)]*3,base),1)

    def test_closed_long_short_ambiguous_remain_stop_first(self):
        bs=rows(2);bs[-1]=replace(bs[-1],high=D(110),low=D(90))
        for side in ('LONG','SHORT'):
            out=simulate(bs,[Decision(side,D(2),D(4)),Decision()],0,2,900,Baseline(),close_at_end=False)
            self.assertEqual(out['trades'][0]['exit_reason'],'STOP_LOSS_AMBIGUOUS')
            self.assertIsNone(out['open_position'])


if __name__=='__main__':unittest.main()
