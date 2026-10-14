"""Bounded read-only historical descriptors, never an execution recommendation."""
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from math import sqrt, isfinite
import gzip
import hashlib
import json

from app.lab.models import digest, canonical
from research.market_intelligence.structure import VERSION, VECTOR_NAMES
from research.market_intelligence.similarity import normalized

VERSION4 = 'AURA_ANALOGS_4.0'
HORIZONS = (4, 8, 16, 32)
STEPS = {'15m': 900, '1h': 3600, '4h': 14400}
MAX_STATES = 8192
MAX_BYTES = 16 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]
FILES = ('app/intelligence/analogs.py', 'app/intelligence/market_context.py',
         'scripts/lab3_history.py', 'app/lab/local_csv.py', 'research/market_intelligence/structure.py',
         'research/market_intelligence/similarity.py', 'app/intelligence/patterns.py',
         'scripts/build_historical_analogs.py', 'app/lab/indicators.py', 'app/lab/models.py', 'app/lab/series.py', 'app/lab/execution.py')
GROUPS = ((0, 1, 11, 12, 13, 14), (2,), (3,), (4, 5, 6, 17), (7, 15, 16), (8, 9, 10), (18, 19, 20))


def software():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def absent(reason='ARTIFACT_MISSING'):
    return dict(status='ANALOG_DATA_UNAVAILABLE', reason=reason, model_version=VERSION4,
                eligible_analogs=None, non_overlapping_samples=None,
                effective_independent_samples=None, horizons={}, decision='WAIT',
                execution_enabled=False, validation='FORWARD_VALIDATION_REQUIRED')


def signature(row):
    return (row['regime'], row['trend_direction'], row['high_leg'], row['low_leg'],
            row['structure_known_mask'], row['mtf']['known_mask'],
            row['vector'][18], row['vector'][19], row['relative_volume'] is not None)


def distribution(rows, horizon):
    values = [r['outcomes'][str(horizon)] for r in rows]
    if not values:
        return dict(count=0, mean_return_pct=None, median_return_pct=None)
    returns = [float(v['return_pct']) for v in values]
    def summary(key):
        xs = sorted(float(v[key]) for v in values)
        return dict(min=xs[0], p10=xs[int((len(xs)-1)*.1)], median=median(xs),
                    mean=mean(xs), p90=xs[int((len(xs)-1)*.9)], max=xs[-1])
    blocks = len({r['timestamp'] // (14*86400) for r in rows})
    return dict(count=len(values), mean_return_pct=mean(returns), median_return_pct=median(returns),
                positive_frequency=sum(x>0 for x in returns)/len(returns),
                negative_frequency=sum(x<0 for x in returns)/len(returns),
                zero_frequency=sum(x==0 for x in returns)/len(returns),
                forward_return=summary('return_pct'), favorable_excursion=summary('mfe_pct'),
                adverse_excursion=summary('mae_pct'), drawdown_upper_bound=summary('drawdown_pct'),
                hypothetical_long_net_pct=mean(float(v['long_net_pct']) for v in values),
                hypothetical_short_net_pct=mean(float(v['short_net_pct']) for v in values),
                observed_14day_blocks=blocks, confidence_interval=None, uncertainty='UNKNOWN',
                uncertainty_reason='IRREGULAR_DEPENDENT_ANALOG_SAMPLE',
                interpretation='Descriptive outcomes, not a trading probability or a portfolio backtest.')


class AnalogIndex:
    """Immutable in-process compact bank. No downloads, storage writes or clients."""
    def __init__(self, pack):
        if not isinstance(pack,dict):raise ValueError('INVALID_ARTIFACT')
        if (pack.get('version') != VERSION4 or pack.get('feature_version') != VERSION or
                pack.get('features') != list(VECTOR_NAMES) or pack.get('software') != software() or
                pack.get('identity') != ['Binance', 'SPOT', 'BTCUSDT']):
            raise ValueError('INCOMPATIBLE_ARTIFACT')
        if pack.get('content_sha256') != digest({k:v for k,v in pack.items() if k!='content_sha256'}):
            raise ValueError('ARTIFACT_CHECKSUM')
        states = pack['states']
        if not isinstance(states, list) or len(states)>MAX_STATES:
            raise ValueError('ARTIFACT_SIZE')
        self.pack = pack
        self.frames = defaultdict(list)
        previous = {}
        for r in states:
            tf = r['timeframe']; step = STEPS[tf]; at = r['timestamp']
            if (type(at) is not int or at%step or at<=previous.get(tf,-1) or
                    r['available_at'] != at or r['quality']!='VALID_CONTINUOUS' or
                    r['resolved_at']!=at+32*step or len(r['vector'])!=len(VECTOR_NAMES) or
                    not all(type(v) in (int,float) and isfinite(v) for v in r['vector']) or
                    any(p['confirmation_time']>at or p['pivot_time']>=p['confirmation_time'] for p in r['context']['confirmed_pivots']) or
                    any(x and (x['closed_at']>at or x['closed_at']%STEPS[{'h1':'1h','h4':'4h'}[k]]) for k,x in r['mtf'].items() if k in ('h1','h4'))):
                raise ValueError('INVALID_STATE')
            # Check all fields consumed by matching and outcome aggregation now,
            # not in an HTTP request. Invalid artifacts fail closed at startup.
            signature(r)
            for h in HORIZONS:
                out = r['outcomes'][str(h)]
                for key in ('return_pct','mfe_pct','mae_pct','drawdown_pct','long_net_pct','short_net_pct'):
                    if not isfinite(float(out[key])):raise ValueError('INVALID_OUTCOME')
            previous[tf] = at; self.frames[tf].append(r)
        for tf in STEPS:
            n = pack['normalizers'][tf]
            if n['features']!=list(VECTOR_NAMES) or n['version']!=VERSION or n['count']<1000:
                raise ValueError('INVALID_CALIBRATION')
            normalized([0.0]*len(VECTOR_NAMES),n,n['fit_closed_through']+1)

    @classmethod
    def load(cls, path):
        try:
            path = Path(path)
            if not path.exists():return None, 'ARTIFACT_MISSING'
            if path.stat().st_size>2*1024*1024:raise ValueError('ARTIFACT_SIZE')
            with gzip.open(path,'rb') as f:
                raw=f.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('ARTIFACT_SIZE')
            return cls(json.loads(raw)), None
        except (ValueError, KeyError, TypeError, IndexError, OSError, OverflowError, EOFError, RecursionError):
            return None, 'ARTIFACT_INVALID_OR_INCOMPATIBLE'

    def query(self, row, timeframe, *, bank_before=None):
        if timeframe not in STEPS or not row or row.get('version')!=VERSION or row.get('timeframe')!=timeframe or row.get('symbol')!='BTCUSDT' or row.get('exchange')!='Binance' or row.get('market_type')!='SPOT':
            return absent('INCOMPATIBLE_QUERY')
        at=row['timestamp'];step=STEPS[timeframe];normalizer=self.pack['normalizers'][timeframe]
        if at<=normalizer['fit_closed_through']:return absent('CALIBRATION_NOT_AVAILABLE')
        q=normalized(row['vector'],normalizer,at)
        # Outcome resolution and 250-candle embargo precede the query. Validation
        # additionally freezes memory at the training boundary.
        pool=[r for r in self.frames[timeframe] if r['resolved_at']<at and
              r['timestamp']+250*step<at and (bank_before is None or r['resolved_at']<bank_before)]
        target=(row['regime'],row['trend_direction'],row['high_leg'],row['low_leg'],
                row['structure_known_mask'],row['mtf']['known_mask'],
                row['vector'][18],row['vector'][19],row['relative_volume'] is not None)
        comparable=[r for r in pool if signature(r)==target]
        ranked=[]
        for r in comparable:
            v=normalized(r['vector'],normalizer,at)
            distance=sqrt(sum(sum((q[j]-v[j])**2 for j in g)/len(g) for g in GROUPS)/len(GROUPS))
            if distance<=1.5:ranked.append((distance,r))
        ranked.sort(key=lambda pair:(pair[0],pair[1]['timestamp']))
        picked=[];distances=[]
        for distance,r in ranked:
            if all(abs(r['timestamp']-p['timestamp'])>32*step for p in picked):
                picked.append(r);distances.append(distance)
                if len(picked)==64:break
        def baseline(rows, detailed=False):
            if detailed:return {str(h):distribution(rows,h) for h in HORIZONS}
            return {str(h):dict(count=len(rows), mean_return_pct=mean(float(r['outcomes'][str(h)]['return_pct']) for r in rows) if rows else None) for h in HORIZONS}
        # Baselines have the same causal temporal eligibility. They describe the
        # indexed grid, not every candle in the exchange's history.
        regime=[r for r in pool if r['regime']==row['regime']]
        trend=[r for r in pool if r['trend_direction']==row['trend_direction']]
        result=dict(status='DESCRIPTIVE_ONLY' if len(picked)>=20 else 'INSUFFICIENT_ANALOG_DATA',
            model_version=VERSION4, feature_version=VERSION, current_regime=row['regime'],
            source='Binance Spot BTCUSDT', timeframe=timeframe, query_closed_at=at,
            eligible_analogs=len(ranked), comparable_states=len(comparable),
            non_overlapping_samples=len(picked), effective_independent_samples=None,
            effective_sample_note='Non-overlapping outcome windows do not imply statistical independence.',
            historical_range=[min(r['timestamp'] for r in picked),max(r['timestamp'] for r in picked)] if picked else None,
            mean_distance=mean(distances) if distances else None,
            similarity='Equal seven-family RMS standardized Euclidean; distance <=1.5; frozen past-only per-TF calibration: 2020, or 2020–2021 for 4h.',
            horizons=baseline(picked, True), baselines=dict(unconditional=baseline(pool),same_regime=baseline(regime),simple_trend=baseline(trend)),
            analogs=[dict(timestamp=r['timestamp'],resolved_at=r['resolved_at'],distance=d) for r,d in zip(picked,distances)],
            artifact_sha256=self.pack['content_sha256'], artifact_updated_at=self.pack['updated_at'],
            validation='FORWARD_VALIDATION_REQUIRED', edge_status='NO_EDGE_FOUND',
            decision='WAIT', execution_enabled=False,
            costs=dict(fee_per_side_pct='0.10',slippage_per_fill_pct='0.05'),
            warning='Historical frequencies are not guaranteed future probabilities. Uncertainty UNKNOWN; effective independent sample size not established.')
        return result
