"""Research-only causal analogue diagnostics. No Paper state or exchange access."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics as st
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import numpy as np
from app.lab.local_csv import load_binance_csv
from app.models import Candle
from app.patterns.config import PatternConfig
from app.patterns.features import build_features,multi_timeframe
from app.patterns.matching import find_matches
from app.patterns.outcomes import statistics
from app.patterns.signals import decide,wilson_lower

SIMILARITIES=(60,65,70,75,80,85)
SAMPLES=(5,10,15,20,25)
START=1788220800
END=1790812800


def utc(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()


def distribution(values):
    return dict(minimum=min(values),median=st.median(values),mean=st.mean(values),maximum=max(values),
                histogram={str(k):v for k,v in sorted(Counter(values).items())})


def trace(features,target,config):
    """Reproduce metric independently, exposing pre-purge and uncapped counts."""
    low=features.valid_from;high=target-config.lookback-max(config.horizons)
    candidate=features.vectors[low:high+1];query=features.vectors[target]
    if high<low:return np.array([]),{s:[] for s in SIMILARITIES},0
    mask=np.isfinite(candidate)&np.isfinite(query)
    square=np.where(mask,candidate-query,0)**2
    groups=[np.sum(square[:,a:b],axis=1)/np.maximum(1,np.sum(mask[:,a:b],axis=1))
            for a,b in ((0,21),(21,candidate.shape[1]))]
    scores=100*np.exp(-3*np.sqrt((groups[0]+groups[1])/2))
    order=np.argsort(-scores,kind='stable')
    chosen=[];separation=config.lookback+max(config.horizons)
    for i in order:
        if scores[i]<min(SIMILARITIES):break
        index=low+int(i)
        if all(abs(index-m['index'])>=separation for m in chosen):
            chosen.append(dict(index=index,similarity=float(scores[i])))
    # Greedy processing is descending and independent of future low-score
    # candidates. Filtering a low-threshold selection yields the same prefix
    # as starting at a higher threshold; retain the production max_matches cap.
    return scores,{s:[m for m in chosen if m['similarity']>=s] for s in SIMILARITIES},high-low+1


def gates(result,stats,n,config):
    main=stats[str(config.decision_horizon)]
    side='LONG' if (main['up_pct'] or 0)>=(main['down_pct'] or 0) else 'SHORT'
    sign=1 if side=='LONG' else -1;c=result['confidence_components']
    raw=100*c['sample']*c['similarity']*c['directional_rate']*(.5+.5*c['consistency'])*c['volatility']*(.75+.25*c['mtf'])
    failed=[name for name,ok in (
        ('MINIMUM_SAMPLE',n>=config.minimum_sample),
        ('DIRECTIONAL_RATE',result['directional_rate_pct']>=config.signal_threshold),
        ('WILSON',wilson_lower(main['up'] if side=='LONG' else main['down'],n)>.5),
        ('CONFIDENCE',raw>=config.minimum_confidence),
        ('EXPECTED_MOVE_COST',sign*(main['average_move_pct'] or 0)>config.round_trip_cost_bps/100),
        ('MEDIAN_DIRECTION',sign*(main['median_move_pct'] or 0)>0),
        ('HORIZON_CONSISTENCY',c['consistency']>=.5)) if not ok]
    if result['signal']!=(side if not failed else 'WAIT'):raise ValueError('Gate diagnostic disagrees with production')
    return failed,raw,side if n else None,main['up'] if side=='LONG' else main['down']


def summarize(rows):
    failures=Counter(f for r in rows for f in r['failed_filters'])
    pairs={a+' & '+b:sum(a in r['failed_filters'] and b in r['failed_filters'] for r in rows)
           for a in sorted(failures) for b in sorted(failures) if a<b}
    combinations=Counter('|'.join(r['failed_filters']) or 'PASS' for r in rows)
    only={f:sum(r['failed_filters']==[f] for r in rows) for f in failures}
    return dict(candles=len(rows),signals=dict(Counter(r['signal'] for r in rows)),
        selected_analogues=distribution([r['selected'] for r in rows]),
        pre_purge=distribution([r['similarity_pass'] for r in rows]),
        post_purge_uncapped=distribution([r['post_purge_uncapped'] for r in rows]),
        available_windows=distribution([r['available_windows'] for r in rows]),
        filter_failures=dict(failures),sole_blocker=only,pair_intersections=pairs,
        failure_combinations=dict(combinations),
        without_sample_gate_signals=sum(not(set(r['failed_filters'])-{'MINIMUM_SAMPLE'}) for r in rows),
        max_confidence_raw=max(r['confidence_raw'] for r in rows),
        max_nearest_similarity=max(r['nearest_similarity'] for r in rows))


def audit(csv_path,baseline_path,budget=600):
    bars,metadata=load_binance_csv(csv_path)
    baseline=json.loads(baseline_path.read_text())
    if metadata['sha256']!=baseline['local_csv']['sha256']:raise ValueError('Baseline CSV hash mismatch')
    full=[Candle(b.time,*[float(getattr(b,k)) for k in ('open','high','low','close','volume')]) for b in bars]
    reference=baseline['results'][0]
    if reference['status']!='COMPLETE' or len(reference['decisions'])!=2880:raise ValueError('Incomplete baseline')
    config=PatternConfig();depths={};grid={};base_rows=[];began=time.monotonic()
    for depth in (10000,5000,2000):
        rows=[c for c in full if START-depth*900<=c.time<END]
        if len(rows)!=depth+2880:raise ValueError('Incomplete exact warm-up/test coverage')
        features=build_features(rows,20,500);features.vectors.setflags(write=False)
        detail=[];research={ (s,n):[] for s in SIMILARITIES for n in SAMPLES } if depth==10000 else {}
        for offset,target in enumerate(range(depth,len(rows))):
            if time.monotonic()-began>budget:raise TimeoutError('Audit budget exceeded; no complete result')
            scores,selections,available=trace(features,target,config)
            mtf=multi_timeframe(rows,target,900)
            thresholds=SIMILARITIES if depth==10000 else (75,)
            for similarity in thresholds:
                matches=selections[similarity][:config.max_matches]
                if offset in (0,500,1500,2879):
                    expected=find_matches(features,target,PatternConfig(minimum_similarity=similarity))
                    if matches!=expected:raise ValueError('Diagnostic selection disagrees with production')
                stats=statistics(rows,matches,config.horizons)
                sample_values=SAMPLES if depth==10000 else (20,)
                for minimum in sample_values:
                    cfg=PatternConfig(minimum_similarity=similarity,minimum_sample=minimum)
                    result=decide(stats,matches,features.facts[target],mtf,cfg)
                    failed,raw,side,directional=gates(result,stats,len(matches),cfg)
                    item=dict(candle_open_utc=utc(rows[target].time),signal_close_utc=utc(rows[target].time+900),
                        available_windows=available,similarity_pass=int(np.count_nonzero(scores>=similarity)),
                        post_purge_uncapped=len(selections[similarity]),selected=len(matches),
                        candidate_direction=side,directional_analogues=directional,
                        up=stats['20']['up'],down=stats['20']['down'],flat=stats['20']['flat'],
                        average_similarity=result['average_similarity'],nearest_similarity=float(max(scores)),
                        signal=result['signal'],confidence_raw=raw,confidence_display=result['confidence'],
                        wilson_lower_pct=result['wilson_lower_pct'],directional_rate_pct=result['directional_rate_pct'],
                        decision_average_move_pct=stats['20']['average_move_pct'],
                        decision_median_move_pct=stats['20']['median_move_pct'],
                        horizon_consistency=result['confidence_components']['consistency'],failed_filters=failed)
                    if depth==10000:research[(similarity,minimum)].append(item)
                    if similarity==75 and minimum==20:
                        detail.append(item)
                        if depth==10000:
                            recorded=reference['decisions'][offset]
                            if (result['signal']!=recorded['signal_result'] or
                                    result['confidence']!=float(recorded['confidence'])):
                                raise ValueError('Per-candle baseline signal/confidence mismatch')
            if (offset+1)%500==0:print(f'depth={depth}: {offset+1}/2880',flush=True)
        depths[str(depth)]=dict(initial_warmup=depth,
            depth_mode='initial warm-up then accumulated test history; not a fixed rolling archive',
            history_size_first=depth+1,history_size_last=depth+2880,summary=summarize(detail))
        if depth==10000:
            base_rows=detail
            grid={f'{s}/{n}':summarize(r) for (s,n),r in research.items()}
    if depths['10000']['summary']['filter_failures']!=reference['strategy_gate_failures']:
        raise ValueError('Baseline gate accounting mismatch')
    software={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (ROOT/'app/patterns').glob('*.py')}
    return dict(status='COMPLETE',research_only=True,local_csv=metadata,start=utc(START),end_exclusive=utc(END),
        baseline_report_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        software_sha256=software,diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_config=config.model_dump(),per_candle=base_rows,baseline=depths['10000']['summary'],
        top_ten=sorted(base_rows,key=lambda r:(-r['selected'],-r['nearest_similarity'],r['candle_open_utc']))[:10],
        sensitivity=grid,depth_comparison=depths,
        baseline_per_candle_matches=2880,
        limitations=['Signal sensitivity only: no Paper executions or PnL simulated.',
            'September is the studied sample, not out-of-sample evidence or a parameter-selection recommendation.',
            'Depth means initial warm-up; history grows during September exactly as in the previous replay.',
            'Features remain causally seeded per depth; later descriptors do not enter earlier matches.',
            'Greedy purging is similarity-first and may not maximize the number of non-overlapping intervals.',
            'Disjoint pattern+outcome windows are not statistically independent financial observations.'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path)
    parser.add_argument('--baseline',type=Path,default=ROOT/'docs/AURA_SEPTEMBER_2026_BACKTEST.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-seconds',type=int,default=600)
    args=parser.parse_args(argv)
    if args.output.exists() or not 1<=args.max_seconds<=3600:parser.error('New output and bounded budget required')
    result=audit(args.csv,args.baseline,args.max_seconds)
    with args.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    print('COMPLETE')
    return 0


if __name__=='__main__':raise SystemExit(main())
