"""Offline archive/causality/math fixtures, never historical-return evidence."""
import hashlib
import io
import json
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from datetime import datetime,timezone
import calendar

from app.lab.execution import simulate
from app.lab.models import Bar,Baseline,LabError
from app.lab.strategies import Decision
from scripts import lab3_history as history,lab3_strategies as strategies
from scripts.run_lab3 import audit_trailing


def month(name,unit=1000):
    y,m=map(int,name[:-4].split('-')[-2:]);start=int(datetime(y,m,1,tzinfo=timezone.utc).timestamp());rows=[]
    for i in range(calendar.monthrange(y,m)[1]*96):
        t=start+i*900
        rows.append(','.join(map(str,[t*unit,100,101,99,100,10,(t+900)*unit-1,1000,3,4,400,0])))
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr(name[:-4]+'.csv','\n'.join(rows)+'\n')
    raw=stream.getvalue();return raw,(hashlib.sha256(raw).hexdigest()+'  '+name).encode()


def bars(n):
    return [Bar(i*900,D(100+i%13),D(102+i%13),D(99+i%13),D(101+i%13),D(20)) for i in range(n)]


class Lab3Tests(unittest.TestCase):
    def test_ms_and_microsecond_months(self):
        for unit in (1000,1000000):
            raw,check=month(history.MONTHS[0],unit);bs,meta=history.monthly_bytes(raw,check,history.MONTHS[0])
            self.assertEqual(len(bs),2976);self.assertEqual(meta['zip_sha256'],hashlib.sha256(raw).hexdigest())

    def test_checksum_content_and_filename(self):
        raw,check=month(history.MONTHS[0])
        for c in (b'0'*64,b'bad',check.replace(b'2020-01',b'2020-02')):
            with self.assertRaises(ValueError):history.monthly_bytes(raw,c,history.MONTHS[0])

    def test_malicious_zip_path_is_not_extracted(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('../outside.csv','malicious')
        raw=stream.getvalue()
        with self.assertRaises(ValueError):history.monthly_bytes(raw,hashlib.sha256(raw).hexdigest().encode(),history.MONTHS[0])

    def test_duplicate_gap_invalid_ohlcv_rejected(self):
        raw,_=month(history.MONTHS[0])
        with zipfile.ZipFile(io.BytesIO(raw)) as z:original=z.read(z.namelist()[0]).decode().splitlines()
        for lines in ([original[0],*original],original[1:],[original[0].replace(',101,',',98,'),*original[1:]]):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as z:z.writestr(history.MONTHS[0][:-4]+'.csv','\n'.join(lines))
            raw=stream.getvalue()
            with self.assertRaises((ValueError,LabError)):history.monthly_bytes(raw,hashlib.sha256(raw).hexdigest().encode(),history.MONTHS[0])

    def test_complete_six_year_directory_no_20000_total_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in history.MONTHS:
                raw,check=month(name);(Path(folder)/name).write_bytes(raw);(Path(folder)/(name+'.CHECKSUM')).write_bytes(check)
            bs,meta=history.load_years(folder)
        self.assertEqual(len(bs),210432);self.assertEqual(len(meta['months']),72)
        self.assertEqual(bs[-1].time+900,int(datetime(2026,1,1,tzinfo=timezone.utc).timestamp()))

    def test_incomplete_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'partial.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('manifest.json','{}')
            with self.assertRaises(ValueError):history.load_years(p)

    def test_bundle_manifest_identity_checked_before_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'wrong.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('manifest.json',json.dumps({'symbol':'ETHUSDT'}))
                for name in history.MONTHS:z.writestr('monthly/'+name,b'');z.writestr('checksums/'+name+'.CHECKSUM',b'')
            with self.assertRaises(ValueError):history.load_years(p)

    def test_deadline_aborts_research(self):
        with self.assertRaises(ValueError):strategies.generate(bars(1000),'A',deadline=0)
        with self.assertRaises(ValueError):strategies.labels(bars(1000),deadline=0)

    def test_htf_only_completed_buckets(self):
        xs=bars(16)
        self.assertEqual(strategies.higher(xs[:15],14400),[])
        self.assertEqual(len(strategies.higher(xs,14400)),1)
        self.assertEqual(len(strategies.higher(xs[:3],3600)),0)
        self.assertEqual(len(strategies.higher(xs[:4],3600)),1)
        self.assertIsNone(strategies.higher_alignment(bars(799),14400)[-1])
        self.assertIsNotNone(strategies.higher_alignment(bars(800),14400)[-1])

    def test_five_candidates_prefix_causality(self):
        prefix=bars(1100);future=[Bar(i*900,D(9999),D(20000),D(1),D(15000),D(99999)) for i in range(1100,1200)]
        for name in 'ABCDE':
            with self.subTest(name=name):
                old,trail=strategies.generate(prefix,name);new,nt=strategies.generate(prefix+future,name)
                self.assertEqual(old,new[:1100])
                if trail is not None:self.assertEqual(trail,nt[:1100])
        self.assertEqual(strategies.labels(prefix),strategies.labels(prefix+future)[:1100])

    def test_b_e_signal_cooldown(self):
        for name in 'BE':
            signals,_=strategies.generate(bars(1500),name);active=[i for i,d in enumerate(signals) if d.direction]
            self.assertTrue(all(b-a>=64 for a,b in zip(active,active[1:])))

    def test_closed_trailing_ratchets_long_and_short_without_retrofill(self):
        for side in ('LONG','SHORT'):
            if side=='LONG':xs=[Bar(0,D(100),D(101),D(99),D(100),D(1)),Bar(900,D(100),D(110),D(99),D(109),D(1)),Bar(1800,D(108),D(109),D(106),D(108),D(1))]
            else:xs=[Bar(0,D(100),D(101),D(99),D(100),D(1)),Bar(900,D(100),D(101),D(90),D(91),D(1)),Bar(1800,D(92),D(94),D(91),D(92),D(1))]
            ds=[Decision(side,D(2),D(20)),Decision(),Decision()];trail=[D(3)]*3
            result=simulate(xs,ds,0,3,900,Baseline(),trailing_atr=trail);t=result['trades'][0]
            self.assertEqual(t['exit_time'],2700);self.assertEqual(t['exit_reason'],'STOP_LOSS')
            self.assertEqual(t['stop_history'][0]['effective_from'],1800)
            audit_trailing(result,xs,trail,Baseline())

    def test_invalid_trailing_inputs_fail_closed(self):
        for trail in ([D(-1)]*3,[D('NaN')]*3,[D(2)]):
            with self.assertRaises(LabError):simulate(bars(3),[Decision()]*3,0,3,900,Baseline(),trailing_atr=trail)

    def test_trailing_none_preserves_existing_output(self):
        xs=bars(5);ds=[Decision('LONG',D(10),D(20))]+[Decision()]*4
        self.assertEqual(simulate(xs,ds,0,5,900,Baseline()),simulate(xs,ds,0,5,900,Baseline(),trailing_atr=None))
        self.assertNotIn('stop_history',simulate(xs,ds,0,5,900,Baseline())['trades'][0])

    def test_no_account_or_exchange_execution_imports(self):
        for path in ('scripts/lab3_strategies.py','scripts/run_lab3.py','scripts/lab3_history.py'):
            text=Path(path).read_text()
            for forbidden in ('app.paper','app.bybit','app.testnet','create_order','cancel_order','getenv','sqlite','api-demo.bybit'):
                self.assertNotIn(forbidden,text)


if __name__=='__main__':unittest.main()
