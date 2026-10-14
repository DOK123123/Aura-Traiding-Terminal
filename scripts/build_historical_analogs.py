"""Explicit offline builder/validation; never imported by the web adapter."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal as D
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.models import canonical, digest, precise
from app.lab.execution import fill, fee
from app.lab.series import higher, split_parts
from research.market_intelligence.structure import segment_states, VERSION, VECTOR_NAMES
from research.market_intelligence.similarity import fit_normalizer, normalized
from app.intelligence.analogs import AnalogIndex, VERSION4, HORIZONS, STEPS, software, MAX_BYTES
from scripts.lab3_history import load_years

CALIBRATION_END=1609459200 # 2021-01-01 UTC, fixed before research results
VALIDATION_START=1672531200 # 2023-01-01 UTC
VALIDATION_END=1735689600 # 2025-01-01 UTC
PROTOCOL=dict(version=VERSION4, calibration='2020',development='2021–2022 prequential',
    calibration_4h='2020–2021; full 4h warmup leaves <1000 eligible states in 2020 alone',
    validation='2023–2024 frozen 2020–2022 bank; already seen, NOT blind OOS',
    untouched_holdout=None,independent_validation='New preregistered forward collection required',
    archive_years=[2020,2025], horizons=list(HORIZONS), index_stride=64, evaluation_stride=4,
    seed=20261014, min_samples=20, max_neighbors=64, max_distance=1.5,
    embargo_query_feature_bars=250, pairwise_purge_bars=32,
    uncertainty='UNKNOWN: sparse, dependent analog events; no invented effective independent count or CI',
    features='Unchanged CONTEXT_VECTOR_1.1; past per-TF mean/std>=0.1 (2020; 4h 2020–2021), clipped +-5',
    costs=dict(fee_bps='10',slippage_bps='5'),
    comparison_family=48,previous_known_comparison_floor=869,comparison_note='3 TF x 4 horizons x 4 baselines; previous known minimum 869, full historical search count unknown; no significance or edge claim.',
    safety='READ_ONLY / WAIT / FORWARD_VALIDATION_REQUIRED')
CONTEXT=('high_leg','low_leg','confirmed_pivots','structure_event','liquidity_sweep',
    'support','resistance','support_source','resistance_source','breakout','failed_breakout','retest',
    'rsi','trend_strength','atr','volatility_ratio','volatility','relative_volume',
    'range_position','pullback_depth_atr','equal_highs','equal_lows','fvg','order_block')


def atomic(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(data);tmp.replace(path)


@precise
def outcome(part, i, h, step):
    if i+h>=len(part):return None
    future=part[i+1:i+h+1]
    if any(b.time!=part[i].time+(j+1)*step for j,b in enumerate(future)):
        raise ValueError('OUTCOME_GAP')
    price=part[i].close;close=future[-1].close
    peak=price;dd=D(0)
    for b in future:
        peak=max(peak,b.high)
        dd=max(dd,(peak-b.low)/peak*100)
    def net(side):
        entry=fill(future[0].open,side,True,D('.0005'))
        exit=fill(close,side,False,D('.0005'))
        sign=1 if side=='LONG' else -1
        pnl=sign*(exit-entry)-fee(entry,D(1),D('.001'))-fee(exit,D(1),D('.001'))
        return str((pnl/entry*100).quantize(D('0.000000000001')))
    def pct(value):return str(value.quantize(D('0.000000000001')))
    return dict(return_pct=pct((close/price-1)*100),
        mfe_pct=pct(max(D(0),max(b.high for b in future)/price-1)*100),
        mae_pct=pct(min(D(0),min(b.low for b in future)/price-1)*100),
        drawdown_pct=pct(dd),long_net_pct=net('LONG'),short_net_pct=net('SHORT'))


def frame_states(bars):
    """Reuse detectors/indicators unchanged; full UTC blocks, reset at every gap."""
    maps={};parts={}
    for tf,step in STEPS.items():
        frame=bars if step==900 else higher(bars,step)
        parts[tf]=split_parts(frame,step);mapping={}
        for part in parts[tf]:
            for row in segment_states(part,step):
                if row:mapping[row['timestamp']]=row
        maps[tf]=mapping
    for tf, mapping in maps.items():
        for row in mapping.values():
            directions=[];mask=0
            for j,other in enumerate(('1h','4h')):
                step=STEPS[other];other_map=maps[other]
                # The required completed bucket is exact, never a forming bar.
                at=row['timestamp']//step*step
                state=other_map.get(at)
                if state and state['segment_start']>=(row['segment_start']+step-1)//step*step:
                    side=state['trend_direction'];mask|=1<<j
                    row['mtf']['h1' if j==0 else 'h4']=dict(direction=side,closed_at=at)
                else:side=0
                directions.append(side)
            row['mtf']['known_mask']=mask
            row['mtf']['alignment']=mask==3 and directions[0]==directions[1]==row['trend_direction']!=0
            row['vector'][-3:]=directions+[mask]
    return parts,maps


def build(bars,quality):
    started=time.monotonic();parts,maps=frame_states(bars)
    print('Calibration counts:',{tf:sum(r['timestamp']<=CALIBRATION_END for r in mapping.values()) for tf,mapping in maps.items()},flush=True)
    normalizers={tf:fit_normalizer(list(mapping.values()),1640995200 if tf=='4h' else CALIBRATION_END) for tf,mapping in maps.items()}
    samples=[];counts={};clipping={}
    for tf,segments in parts.items():
        step=STEPS[tf];mapping=maps[tf];count=0;clipped=0;features=0;per_feature=Counter()
        for part in segments:
            for i in range(249,len(part)-32,PROTOCOL['index_stride']):
                row=mapping.get(part[i].time+step)
                if not row:continue
                at=row['timestamp'];outs={str(h):outcome(part,i,h,step) for h in HORIZONS}
                samples.append(dict(timestamp=at,available_at=at,resolved_at=at+32*step,
                    timeframe=tf,vector=row['vector'],regime=row['regime'],trend_direction=row['trend_direction'],
                    high_leg=row['high_leg'],low_leg=row['low_leg'],structure_known_mask=row['structure_known_mask'],
                    relative_volume=row['relative_volume'],mtf=row['mtf'],quality='VALID_CONTINUOUS',
                    context={k:row[k] for k in CONTEXT},outcomes=outs))
                count+=1
                if at>normalizers[tf]['fit_closed_through']:
                    n=normalizers[tf]
                    flags=[abs((v-m)/s)>5 for v,m,s in zip(row['vector'],n['means'],n['scales'])]
                    clipped+=sum(flags)
                    per_feature.update({name:int(flag) for name,flag in zip(VECTOR_NAMES,flags)})
                    features+=len(VECTOR_NAMES)
        counts[tf]=dict(closed_states=len(mapping),indexed_states=count,calibration_states=normalizers[tf]['count'])
        clipping[tf]=dict(clipped_features=clipped,evaluated_features=features,rate=clipped/features if features else None,per_feature=dict(per_feature))
    pack=dict(version=VERSION4, feature_version=VERSION,features=list(VECTOR_NAMES),
        identity=['Binance','SPOT','BTCUSDT'],software=software(),protocol=PROTOCOL,
        updated_at=bars[-1].time+900,source=dict(archive_sha256=quality['bundle_sha256'],
            raw_count=quality['raw_count'],valid_count=quality['count'],
            missing_candles=quality['missing_candles'],quarantined=sum(len(m['quarantined']) for m in quality['months']),
            authentication=quality['authentication']),normalizers=normalizers,states=samples)
    pack['content_sha256']=digest(pack)
    return pack,dict(state_counts=counts,clipping=clipping,elapsed_seconds=round(time.monotonic()-started,3))


def evaluate(index):
    """Frozen grid, descriptive forecast errors, not a strategy PnL backtest."""
    results=[]
    for tf in STEPS:
        queries=[r for r in index.frames[tf] if index.pack['normalizers'][tf]['fit_closed_through']<r['timestamp']<VALIDATION_END][::4]
        for phase,left,right,freeze in [('development',CALIBRATION_END,VALIDATION_START,None),
                                       ('validation',VALIDATION_START,VALIDATION_END,VALIDATION_START)]:
            errors=defaultdict(list);reasons=Counter();examples=[]
            for r in queries:
                if not left<=r['timestamp']<right or r['resolved_at']>=right:continue
                query=dict(r,version=VERSION,symbol='BTCUSDT',exchange='Binance',market_type='SPOT')
                result=index.query(query,tf,bank_before=freeze)
                reasons[result['status']]+=1
                if len(examples)<2:examples.append({k:result.get(k) for k in ('query_closed_at','status','eligible_analogs','non_overlapping_samples','historical_range')})
                if result['status']!='DESCRIPTIVE_ONLY':continue
                # Randomized matched-frequency baseline uses eligible prior bank
                # only, independent of any future query outcome.
                step=STEPS[tf]
                bank=[x for x in index.frames[tf] if x['resolved_at']<r['timestamp'] and x['timestamp']+250*step<r['timestamp'] and (freeze is None or x['resolved_at']<freeze)]
                random_rows=random.Random(PROTOCOL['seed']+r['timestamp']).sample(bank,min(len(bank),result['non_overlapping_samples']))
                for h in HORIZONS:
                    actual=float(r['outcomes'][str(h)]['return_pct'])
                    predicted=result['horizons'][str(h)]['mean_return_pct']
                    base={k:v[str(h)]['mean_return_pct'] for k,v in result['baselines'].items()}
                    base['randomized']=sum(float(x['outcomes'][str(h)]['return_pct']) for x in random_rows)/len(random_rows)
                    errors[h].append(dict(timestamp=r['timestamp'],actual=actual,predicted=predicted,
                        absolute_error=abs(actual-predicted),baselines={k:abs(actual-v) if v is not None else None for k,v in base.items()}))
            summaries={}
            for h,rows in errors.items():
                summaries[str(h)]=dict(forecasts=len(rows),mean_absolute_error=sum(x['absolute_error'] for x in rows)/len(rows),
                    baselines={k:sum(x['baselines'][k] for x in rows if x['baselines'][k] is not None)/sum(x['baselines'][k] is not None for x in rows) for k in ('unconditional','same_regime','simple_trend','randomized')},
                    by_year={str(y):dict(count=sum(datetime.fromtimestamp(x['timestamp'],timezone.utc).year==y for x in rows),
                        mean_absolute_error=(sum(x['absolute_error'] for x in rows if datetime.fromtimestamp(x['timestamp'],timezone.utc).year==y)/sum(datetime.fromtimestamp(x['timestamp'],timezone.utc).year==y for x in rows)) if any(datetime.fromtimestamp(x['timestamp'],timezone.utc).year==y for x in rows) else None) for y in range(2021,2025)},
                    significance='NOT_ESTABLISHED', multiple_comparison_control='48 TF/horizon/baseline comparisons plus previous known minimum 869; significance NOT TESTED, no hypothesis accepted')
            results.append(dict(timeframe=tf,phase=phase,reasons=dict(reasons),horizons=summaries,examples=examples))
    return dict(status='NO_EDGE_FOUND',interpretation='No independently validated predictive advantage. MAE comparisons descriptive only; not PnL or proof that true edge is zero.',
        results=results,holdout='NONE_UNTOUCHED; 2025 previously examined, excluded from validation',
        walk_forward='Development prequential expanding memory, year counts saved; validation frozen at 2023-01-01.',
        uncertainty='UNKNOWN: no valid independence/effective-N estimate for selected irregular analogs; no fabricated CI.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    if not args.archive.exists():
        atomic(args.report,canonical(dict(status='BLOCKED_DATA_REQUIRED',required_file='AURA_BTCUSDT_15m_2020-2025.zip')));return
    bars,quality=load_years(args.archive,allow_gaps=True)
    print('Verified archive:',quality['raw_count'],len(bars),'missing',quality['missing_candles'],flush=True)
    checkpoint=args.report.with_suffix('.checkpoint.gz')
    key=digest(dict(software=software(),protocol=PROTOCOL,archive=quality['bundle_sha256']))
    saved=None
    if checkpoint.exists() and checkpoint.stat().st_size<8*1024*1024:
        with gzip.open(checkpoint,'rb') as f:
            payload=f.read(32*1024*1024+1)
        if len(payload)>32*1024*1024:raise ValueError('CHECKPOINT_SIZE')
        candidate=json.loads(payload)
        if candidate['key']==key:saved=candidate
    if saved:
        pack,stats=saved['pack'],saved['stats'];print('Verified checkpoint resumed',flush=True)
    else:
        pack,stats=build(bars,quality)
        atomic(checkpoint,gzip.compress(canonical(dict(key=key,pack=pack,stats=stats)),mtime=0))
    index=AnalogIndex(pack)
    raw=canonical(pack)
    if len(raw)>MAX_BYTES:raise ValueError('ARTIFACT_SIZE')
    compressed=gzip.compress(raw,mtime=0)
    if len(compressed)>2*1024*1024:raise ValueError('COMPRESSED_ARTIFACT_SIZE')
    atomic(args.output,compressed)
    print('Index saved:',len(pack['states']),'states;',len(compressed),'bytes',flush=True)
    report=dict(version=VERSION4,status='COMPLETED_DESCRIPTIVE_RESEARCH',protocol=PROTOCOL,
        source=pack['source'],data_quality=quality,statistics=stats,
        artifact=dict(path=args.output.name,sha256=hashlib.sha256(compressed).hexdigest(),content_sha256=pack['content_sha256'],bytes=len(compressed),uncompressed_bytes=len(raw)),
        validation=evaluate(index),software=pack['software'],read_only=True,execution_enabled=False)
    atomic(args.report,canonical(report));print('Validation saved',flush=True)

if __name__=='__main__':main()
