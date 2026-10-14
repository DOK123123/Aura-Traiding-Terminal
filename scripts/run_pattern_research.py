"""Explicit offline entry point; finite grid, hash-locked checkpoints, no downloads."""
import argparse
from collections import Counter
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.models import Bar, Baseline, canonical, digest
from scripts.lab3_history import load_years
from scripts.pattern_research import (protocol,hypotheses,prepare,PERIODS,STEPS,period_run,
    stamp,classify,atomic_json,lock_finalists,write_artifact,source_hash)



LEGACY_SOURCE='4480c20dcad43b62202ed5f36242ae308a9666f14099c9e0845bd40f37409361'
LEGACY_KERNEL='992233ccfe762f98ec3cc77324bdff2c5f6cc8938f0184292974bec77c248e9f'

def compatible_protocol(saved,current):
    """Canonical JSON comparison; one pinned pre-fix runner, unchanged math kernel."""
    if digest(saved)==digest(current):return True
    paths=['scripts/pattern_research.py','scripts/lab3_history.py','app/intelligence/patterns.py',
        'app/lab/execution.py','app/lab/indicators.py','app/lab/models.py','app/lab/strategies.py',
        'app/lab/series.py','app/lab/local_csv.py',
        'scripts/lab3_strategies.py','scripts/research_inverse.py','scripts/run_lab3.py']
    kernel=digest({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    a={k:v for k,v in saved.items() if k!='source_hash'}
    b={k:v for k,v in current.items() if k!='source_hash'}
    return saved.get('source_hash')==LEGACY_SOURCE and kernel==LEGACY_KERNEL and digest(a)==digest(b)



def selection_result(base,stress,frozen,validation=False):
    if base['metrics']['trades']==0 and base['full_period_execution_valid']:
        return 'INSUFFICIENT_EVIDENCE',['NO_TRADES']
    return classify(base,stress,frozen,validation)


def validation_targets(ranked,candidates):
    exploratory=[r for r in ranked if r['full_period_execution_valid']][:10]
    ids={r['hypothesis']['id'] for r in exploratory+candidates}
    return [r for r in ranked if r['hypothesis']['id'] in ids]


def summary(run):
    return {k:v for k,v in run.items() if k not in ('trades','equity_curve')}


def artifact_read(path,sha):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('CHECKPOINT_ARTIFACT_MISMATCH')
    with gzip.open(path,'rt') as f:return json.load(f)


def cached_prepare(bars,tf,out,key):
    meta_path=out/(tf+'.cache.json');data_path=out/(tf+'.cache.gz')
    if meta_path.exists():
        meta=json.loads(meta_path.read_text())
        if meta['key']!=key:raise ValueError('STALE_DETECTOR_CACHE')
        data=artifact_read(data_path,meta['sha256'])
        return [(list(map(Bar.restore,p['bars'])),p['rows']) for p in data]
    value=prepare(bars,tf)
    raw=[dict(bars=[b.data() for b in part],rows=rows) for part,rows in value]
    sha=write_artifact(data_path,raw);atomic_json(meta_path,dict(key=key,sha256=sha))
    return value


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    frozen=protocol();grid=hypotheses(frozen)
    if len(grid)!=frozen['search_budget']:raise ValueError('SEARCH_BUDGET_MISMATCH')
    freeze_path=out/'protocol.json'
    if freeze_path.exists():
        saved=json.loads(freeze_path.read_text())
        if not compatible_protocol(saved,frozen):raise ValueError('FROZEN_PROTOCOL_CHANGED')
        frozen=saved # Original pre-result manifest remains frozen and auditable.
    if not freeze_path.exists():atomic_json(freeze_path,frozen)
    if not args.archive.exists():
        result=dict(status='BLOCKED_DATA_REQUIRED',required_file='AURA_BTCUSDT_15m_2020-2025.zip',protocol=frozen)
        atomic_json(args.report,result);return result
    bars,quality=load_years(args.archive,allow_gaps=True)
    actual=(quality['raw_count'],quality['raw_missing_candles'],len(bars),quality['quality_annotations'],sum(len(m['quarantined']) for m in quality['months']))
    if actual!=(210280,152,210272,27,8):raise ValueError('DATA_QUALITY_DIFFERENT: review instead of fitting expected numbers')
    key=digest(dict(archive=quality['bundle_sha256'],protocol=frozen))
    checkpoint=out/'checkpoint.json'
    state=json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(key=key,jobs={})
    if state['key']!=key:raise ValueError('CHECKPOINT_SOURCE_CHANGED')
    prepared={};new_jobs=0;start_clock=time.monotonic()
    def job(h,period,stress=False):
        nonlocal new_jobs
        ident=h['id']+'|'+period+(' |stress' if stress else ' |base')
        if ident in state['jobs']:
            record=state['jobs'][ident]
            artifact_read(out/record['artifact'],record['sha256'])
            return record['summary']
        if args.max_jobs is not None and new_jobs>=args.max_jobs:raise TimeoutError('JOB_BUDGET')
        if time.monotonic()-start_clock>args.seconds:raise TimeoutError('TIME_BUDGET')
        tf=h['timeframe']
        if tf not in prepared:
            print('Preparing closed detector history',tf,flush=True)
            prepared.clear() # At most one timeframe in RAM plus base archive.
            prepared[tf]=cached_prepare(bars,tf,out,key)
        left,right=PERIODS[period];base=Baseline(fee_bps='20',slippage_bps='10') if stress else Baseline()
        full=period_run(prepared[tf],h,stamp(left),stamp(right),base,STEPS[tf])
        path=out/(digest(ident)+'.json.gz');sha=write_artifact(path,full)
        record=dict(artifact=path.name,sha256=sha,summary=summary(full));state['jobs'][ident]=record
        atomic_json(checkpoint,state);new_jobs+=1
        print('Completed',len(state['jobs']),ident,full['metrics']['net_profit'],flush=True)
        return record['summary']
    result=dict(status='IN_PROGRESS',protocol=frozen,protocol_sha256=digest(frozen),implementation_source_hash=source_hash(),data_quality=quality,
        hypotheses=grid,development=[],validation=[],holdout=[],finalists=[],holdout_lock_sha256=None,
        baseline_note='No-trade=0. Buy-and-hold and old frozen strategies are supplied as historical reference in AURA_SIX_YEAR_BACKTEST; not reranked as equivalent risk. New matched-frequency random controls are NOT RUN in this version.')
    # One fixed candidate grid. No subsequent grid expansion after seeing results.
    try:
        for h in grid:
            base=job(h,'development');stress=job(h,'development',True)
            label,reasons=selection_result(base,stress,frozen)
            result['development'].append(dict(**base,classification=label,reasons=reasons,stress=stress))
        ranked=sorted(result['development'],key=lambda x:(-float(x['metrics']['net_profit']),x['hypothesis']['id']))
        candidates=[r for r in ranked if r['classification']=='RESEARCH_CANDIDATE'][:10]
        # Top ten numerical cases are audited even if inference gate fails; never finalists.
        exploratory=[r for r in ranked if r['full_period_execution_valid']][:10]
        val_ids={r['hypothesis']['id'] for r in candidates}
        for r in validation_targets(ranked,candidates):
            base=job(r['hypothesis'],'validation');stress=job(r['hypothesis'],'validation',True)
            label,reasons=selection_result(base,stress,frozen,True)
            eligible=r['hypothesis']['id'] in val_ids and label=='RESEARCH_CANDIDATE'
            result['validation'].append(dict(**base,classification=label,reasons=reasons,stress=stress,
                scope='SELECTION' if r['hypothesis']['id'] in val_ids else 'EXPLORATORY_NOT_ELIGIBLE',eligible=eligible))
        result['finalists']=[r['hypothesis'] for r in result['validation'] if r['eligible']]
        result['holdout_lock_sha256']=lock_finalists(out/'finalists.lock.json',frozen,result['finalists'])
        for h in result['finalists']:
            base=job(h,'holdout_reused');stress=job(h,'holdout_reused',True)
            result['holdout'].append(dict(**base,stress=stress,classification='REPEATED_CONFIRMATION_ONLY'))
        result['status']='NO_EDGE_FOUND' if not result['finalists'] else 'RESEARCH_ONLY_REPEATED_CONFIRMATION'
        result['top10_development']=[dict(id=r['hypothesis']['id'],net=r['metrics']['net_profit'],trades=r['metrics']['trades'],classification=r['classification'],reasons=r['reasons']) for r in ranked[:10]]
    except TimeoutError as error:result['status']='INCOMPLETE_'+str(error)
    result['completed_jobs']=len(state['jobs']);result['artifact_directory']=str(out)
    result['counts']=dict(development=len(result['development']),validation=len(result['validation']),finalists=len(result['finalists']),holdout=len(result['holdout']))
    result['rejection_reasons']=dict(Counter(reason for r in result['development'] for reason in r['reasons']))
    # Detector occurrences include neutral events regardless of directional hypothesis.
    occurrences=[]
    for tf in STEPS:
        if (out/(tf+'.cache.json')).exists():
            meta=json.loads((out/(tf+'.cache.json')).read_text())
            cache=artifact_read(out/(tf+'.cache.gz'),meta['sha256']);counts=Counter()
            from datetime import datetime,timezone
            for p in cache:
                for bar,row in zip(p['bars'],p['rows']):
                    if row:
                        year=datetime.fromtimestamp(bar['time'],timezone.utc).year
                        counts.update((year,k) for k in row['patterns'])
            occurrences.extend(dict(timeframe=tf,year=y,pattern=k,count=n) for (y,k),n in sorted(counts.items()))
    result['detector_occurrences']=occurrences
    atomic_json(args.report,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=14400);p.add_argument('--max-jobs',type=int)
    a=p.parse_args()
    if a.seconds<=0 or (a.max_jobs is not None and a.max_jobs<0):p.error('Positive resource budget required')
    result=run(a);print(result['status'],result.get('counts'),flush=True)
