"""Synthetic fixtures prove algorithms only, never historical performance."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import gzip
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from app.intelligence.analogs import (AnalogIndex, VERSION4, HORIZONS, STEPS,
    software, distribution, absent)
from app.lab.models import digest, canonical
from research.market_intelligence.structure import VERSION, VECTOR_NAMES
from scripts.build_historical_analogs import outcome, frame_states, PROTOCOL
from tests.test_market_intelligence import bars


def sample(at):
    return dict(timestamp=at,available_at=at,resolved_at=at+32*900,timeframe='15m',
        vector=[0.0]*21,regime='TREND_UP',trend_direction=1,high_leg='HH',low_leg='HL',
        structure_known_mask=3,relative_volume=1,mtf=dict(h1=None,h4=None,known_mask=0),
        quality='VALID_CONTINUOUS',context=dict(confirmed_pivots=[]),
        outcomes={str(h):dict(return_pct='1',mfe_pct='2',mae_pct='-1',drawdown_pct='3',long_net_pct='.7',short_net_pct='-1.3') for h in HORIZONS})


def pack(n=40):
    states=[sample(900000+i*64*900) for i in range(n)]
    p=dict(version=VERSION4,feature_version=VERSION,features=list(VECTOR_NAMES),identity=['Binance','SPOT','BTCUSDT'],
        software=software(),states=states,updated_at=4000000,
        normalizers={tf:dict(features=list(VECTOR_NAMES),version=VERSION,count=1000,fit_closed_through=100,
            means=[0.0]*21,scales=[1.0]*21) for tf in STEPS})
    p['content_sha256']=digest(p);return p


def query(at=5000400):
    return dict(sample(at),symbol='BTCUSDT',version=VERSION,exchange='Binance',market_type='SPOT')


class AnalogTests(unittest.TestCase):
    def test_selection_causal_purged_and_deterministic(self):
        index=AnalogIndex(pack());q=query()
        a=index.query(q,'15m');b=index.query(q,'15m')
        self.assertEqual(a,b);self.assertEqual(a['non_overlapping_samples'],40)
        self.assertEqual(a['status'],'DESCRIPTIVE_ONLY');self.assertEqual(a['decision'],'WAIT')
        self.assertFalse(a['execution_enabled']);self.assertIsNone(a['effective_independent_samples'])
        for r in a['analogs']:self.assertLess(r['resolved_at'],q['timestamp'])
        for x in a['horizons'].values():self.assertEqual(x['uncertainty'],'UNKNOWN');self.assertIsNone(x['confidence_interval'])

    def test_no_future_outcome_selection_leak(self):
        p=pack();a=AnalogIndex(p).query(query(),'15m')
        p=deepcopy(p)
        for r in p['states']:
            for out in r['outcomes'].values():out['return_pct']='-100'
        p['content_sha256']=digest({k:v for k,v in p.items() if k!='content_sha256'})
        b=AnalogIndex(p).query(query(),'15m')
        self.assertEqual(a['analogs'],b['analogs'])
        self.assertNotEqual(a['horizons'],b['horizons'])

    def test_embargo_and_resolved_labels_strictly_before_query(self):
        p=pack();q=query(p['states'][10]['resolved_at'])
        result=AnalogIndex(p).query(q,'15m')
        self.assertTrue(all(r['resolved_at']<q['timestamp'] for r in result['analogs']))
        self.assertTrue(all(r['timestamp']+250*900<q['timestamp'] for r in result['analogs']))
        frozen=p['states'][4]['resolved_at']
        result=AnalogIndex(p).query(query(),'15m',bank_before=frozen)
        self.assertTrue(all(r['resolved_at']<frozen for r in result['analogs']))

    def test_overlapping_outcomes_purged(self):
        p=pack()
        for i,r in enumerate(p['states']):r.update(timestamp=900000+i*900,available_at=900000+i*900,resolved_at=900000+(i+32)*900)
        p['content_sha256']=digest({k:v for k,v in p.items() if k!='content_sha256'})
        result=AnalogIndex(p).query(query(),'15m')
        times=sorted(r['timestamp'] for r in result['analogs'])
        self.assertTrue(all(b-a>32*900 for a,b in zip(times,times[1:])))
        self.assertEqual(result['status'],'INSUFFICIENT_ANALOG_DATA')

    def test_structure_filters_and_wrong_source_or_version(self):
        index=AnalogIndex(pack());q=query();q['high_leg']='LH'
        self.assertEqual(index.query(q,'15m')['eligible_analogs'],0)
        q=query();q['symbol']='ETHUSDT'
        self.assertEqual(index.query(q,'15m')['status'],'ANALOG_DATA_UNAVAILABLE')
        p=pack();p['identity']=['Bybit','FUTURES','BTCUSDT']
        with self.assertRaises(ValueError):AnalogIndex(p)

    def test_outcome_next_open_costs_and_drawdown_independent_arithmetic(self):
        bs=bars(5);bs[1]=replace(bs[1],open=D(100),high=D(112),low=D(98),close=D(110))
        x=outcome(bs,0,1,900)
        self.assertEqual(D(x['return_pct']),D(10))
        entry=D('100.05');exit=D('109.945')
        expected=(exit-entry-D('.10005')-D('.109945'))/entry*100
        self.assertAlmostEqual(float(x['long_net_pct']),float(expected),places=10)
        self.assertEqual(D(x['mfe_pct']),D(12));self.assertEqual(D(x['mae_pct']),D(-2))
        self.assertAlmostEqual(float(x['drawdown_pct']),14/112*100)
        self.assertLess(D(x['short_net_pct']),D(-10))

    def test_outcome_horizon_and_gap_censoring(self):
        xs=bars(40);a=outcome(xs,0,4,900)
        xs[20]=replace(xs[20],close=D('101'))
        self.assertEqual(a,outcome(xs,0,4,900))
        self.assertIsNone(outcome(xs,20,32,900))
        with self.assertRaises(ValueError):outcome(xs[:3]+xs[4:],0,8,900)

    def test_feature_causality_mtf_and_pivot_confirmation(self):
        prefix=bars(320);_,a=frame_states(prefix);_,b=frame_states(prefix+bars(350)[320:])
        for at,r in a['15m'].items():
            self.assertEqual(r,b['15m'][at])
            for p in r['confirmed_pivots']:self.assertLessEqual(p['confirmation_time'],at)
        self.assertFalse(a['4h']);self.assertFalse(a['1h'])

    def test_distribution_zero_and_undefined_uncertainty(self):
        self.assertIsNone(distribution([],4)['mean_return_pct'])
        rows=[sample(900000)];x=distribution(rows,4)
        self.assertEqual(x['positive_frequency'],1)
        self.assertIsNone(x['confidence_interval'])

    def test_loader_missing_corrupt_version_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'artifact.gz'
            self.assertEqual(AnalogIndex.load(path)[1],'ARTIFACT_MISSING')
            path.write_bytes(b'not gzip');self.assertIsNone(AnalogIndex.load(path)[0])
            path.write_bytes(gzip.compress(canonical(pack()),mtime=0))
            a,e=AnalogIndex.load(path);b,e2=AnalogIndex.load(path)
            self.assertIsNone(e);self.assertIsNone(e2)
            self.assertEqual(a.query(query(),'15m'),b.query(query(),'15m'))
            p=pack();p['version']='OLD'
            path.write_bytes(gzip.compress(canonical(p),mtime=0));self.assertIsNone(AnalogIndex.load(path)[0])

    def test_read_only_boundary_and_no_archives_in_live_module(self):
        source=Path('app/intelligence/analogs.py').read_text()
        for token in ('app.paper','app.bybit','app.testnet','requests','httpx','sqlite','create_order','cancel_order','amend_order','withdraw','os.environ'):
            self.assertNotIn(token,source)
        self.assertIsNone(PROTOCOL['untouched_holdout'])

    def test_live_lookup_bounded_work(self):
        index=AnalogIndex(pack(1000));start=time.monotonic()
        result=index.query(query(900000+2000*64*900),'15m')
        self.assertLess(time.monotonic()-start,2)
        self.assertLessEqual(result['non_overlapping_samples'],64)


    def test_full_utc_mtf_matches_online_market_algorithms(self):
        from app.intelligence.market_context import analyze_window
        xs=bars(4160);_,maps=frame_states(xs)
        values=analyze_window(xs,xs[-1].time+950)
        for tf,value in values.items():
            self.assertEqual(maps[tf][value['last_closed_at']],value['state'])

    def test_truncated_gzip_is_safe_unavailability(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'artifact.gz';p.write_bytes(gzip.compress(canonical(pack()))[:-8])
            self.assertIsNone(AnalogIndex.load(p)[0])

    def test_context_resets_after_gap(self):
        xs=bars(4400);_,maps=frame_states(xs[:4000]+xs[4001:])
        self.assertNotIn(xs[4100].time+900,maps['15m'])
        self.assertIn(xs[-1].time+900,maps['15m'])
        self.assertIsNone(maps['15m'][xs[-1].time+900]['mtf']['h4'])


    def test_query_requires_explicit_same_exchange_and_market(self):
        index=AnalogIndex(pack())
        for change in ({'exchange':'Bybit'},{'market_type':'FUTURES'},{'exchange':None}):
            q=query();q.update(change)
            result=index.query(q,'15m')
            self.assertEqual(result['reason'],'INCOMPATIBLE_QUERY')
            self.assertFalse(result['execution_enabled'])


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_index_enrichment_and_market_state_unchanged(self):
        from app.intelligence.market_context import MarketContext
        from tests.test_market_context import fixture
        bs=fixture();now=bs[-1].time+950
        index=AnalogIndex(pack())
        svc=MarketContext(None,clock=lambda:now,analog_index=index)
        with patch('app.intelligence.market_context.fetch_window',return_value=(bs,{})):
            result=await svc.snapshot('15m')
        self.assertEqual(result['status'],'OK')
        self.assertEqual(result['analog_availability']['model_version'],VERSION4)
        self.assertEqual(result['decision']['action'],'WAIT')
        await svc.close()

    async def test_missing_artifact_preserves_current_analysis(self):
        from app.intelligence.market_context import MarketContext
        from tests.test_market_context import fixture
        bs=fixture();now=bs[-1].time+950
        svc=MarketContext(None,clock=lambda:now)
        with patch('app.intelligence.market_context.fetch_window',return_value=(bs,{})):
            result=await svc.snapshot('15m')
        self.assertEqual(result['status'],'OK');self.assertIsNotNone(result['state'])
        self.assertEqual(result['analog_availability']['reason'],'ARTIFACT_MISSING')
        await svc.close()

    async def test_shipped_real_artifact_compatible_without_history_archive(self):
        index,reason=AnalogIndex.load('app/intelligence/data/analogs-v4.json.gz')
        self.assertIsNone(reason);self.assertIsNotNone(index)
        self.assertEqual(index.pack['source']['raw_count'],210280)
        self.assertEqual(index.pack['source']['valid_count'],210272)
        self.assertGreaterEqual(index.pack['normalizers']['4h']['count'],1000)
        self.assertEqual(sum(len(rows) for rows in index.frames.values()),4136)
