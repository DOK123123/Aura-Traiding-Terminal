"""Offline Market Intelligence3.0; deterministic snapshots, checkpoints and research-only reports."""
import argparse
from collections import Counter
from dataclasses import replace
from decimal import Decimal as D
import gzip,hashlib,json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.models import Bar,Baseline,canonical,digest
from app.lab.strategies import Decision,decisions
from scripts.lab3_history import load_years
from scripts.pattern_research import atomic_json,write_artifact
from scripts.run_pattern_research import artifact_read
from research.market_intelligence.structure import prepare,VERSION
from research.market_intelligence.similarity import fit_normalizer,explain
from research.market_intelligence.pipeline import protocol,hypotheses,build_banks,build_streams,portfolio,classify,stamp,CALIBRATION_END,PERIODS


def light(value):
    return {k:v for k,v in value.items() if k not in ('trades','equity_curve')}


def cached(path,key,create):
    metadata=path.with_suffix('.meta.json')
    if metadata.exists():
        record=json.loads(metadata.read_text())
        if record['key']!=key:raise ValueError('CACHE_SIGNATURE_CHANGED')
        return artifact_read(path,record['sha256'])
    value=create();sha=write_artifact(path,value);atomic_json(metadata,dict(key=key,sha256=sha));return value


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=True);frozen=protocol(ROOT)
    pp=out/'protocol.json'
    if pp.exists() and digest(json.loads(pp.read_text()))!=digest(frozen):raise ValueError('PROTOCOL_CHANGED')
    if not pp.exists():atomic_json(pp,frozen)
    result=dict(status='IN_PROGRESS',protocol=frozen,protocol_sha256=digest(frozen),source_commit='4a182d2689fbd82540426cfe525db880bab87466',
        results=[],controls=[],candidates=[],comparison=dict(pattern_research_status='NO_EDGE_FOUND',pattern_grid=810,comparability='Reference only: different detectors,250 versus1000 execution warmup and four-day versus daily expiry. Original report untouched.'),read_only=True,real_money_execution='DISABLED',automatic_execution='DISABLED')
    if not args.archive.exists():
        result.update(status='BLOCKED_DATA_REQUIRED',required_file='AURA_BTCUSDT_15m_2020-2025.zip');atomic_json(args.report,result);return result
    bars,quality=load_years(args.archive,allow_gaps=True)
    actual=(quality['raw_count'],quality['raw_missing_candles'],len(bars),sum(len(m['quarantined']) for m in quality['months']),quality['quality_annotations'])
    if actual!=(210280,152,210272,8,27):raise ValueError('DATA_QUALITY_CHANGED')
    result['data_quality']=quality
    #2025 is deliberately excluded before state/outcome calculations.
    bars=[b for b in bars if b.time<stamp('2025-01-01')]
    key=digest(dict(protocol=frozen,archive=quality['bundle_sha256']))
    cp_path=out/'checkpoint.json';cp=json.loads(cp_path.read_text()) if cp_path.exists() else dict(key=key,jobs={})
    if cp['key']!=key:raise ValueError('CHECKPOINT_CHANGED')
    start_clock=time.monotonic();new_jobs=0
    print('Preparing causal context',len(bars),flush=True)
    data=cached(out/'states.json.gz',key,lambda:[dict(bars=[b.data() for b in part],rows=rows) for part,rows in prepare(bars)])
    prepared=[([Bar.restore(b) for b in p['bars']],p['rows']) for p in data];del data
    normalizer=fit_normalizer([r for p,rows in prepared for r in rows],CALIBRATION_END)
    result['normalizer']=normalizer;atomic_json(out/'normalizer.json',normalizer)
    print('Preparing completed labels',flush=True)
    def label_data():
        bank,stats=build_banks(prepared,frozen)
        return dict(banks=[dict(key=list(k),events=v) for k,v in bank.items()],stats=stats)
    label=cached(out/'labels.json.gz',key,label_data)
    banks={tuple(r['key']):r['events'] for r in label['banks']};result['label_statistics']=label['stats'];del label
    result['state_statistics']=dict(source_candles=len(bars),closed_states=sum(r is not None for p,rows in prepared for r in rows),
        regimes=dict(Counter(r['regime'] for p,rows in prepared for r in rows if r)),
        events=dict(Counter(name for p,rows in prepared for r in rows if r for name in ('breakout','failed_breakout','retest','structure_event','liquidity_sweep') if r[name])))
    states=[r for p,rows in prepared for r in rows if r is not None]
    last_part,last_rows=prepared[-1];result['read_only_example']=explain(last_part[-1],last_rows[-1],banks,normalizer)
    del states
    def job(h,streams,period,stress=False,tag='strategy'):
        nonlocal new_jobs
        ident=h['id']+'|'+period+(' |stress' if stress else ' |base')+'|'+tag
        if ident in cp['jobs']:
            record=cp['jobs'][ident];artifact_read(out/record['artifact'],record['sha256']);return record['summary']
        if args.max_jobs is not None and new_jobs>=args.max_jobs:raise TimeoutError('JOB_BUDGET')
        if time.monotonic()-start_clock>args.seconds:raise TimeoutError('TIME_BUDGET')
        left,right=map(stamp,PERIODS[period]);baseline=Baseline(fee_bps='20',slippage_bps='10') if stress else Baseline()
        value=portfolio(prepared,streams,left,right,baseline,time.monotonic()+args.job_seconds)
        value['hypothesis']=h
        path=out/(digest(ident)+'.json.gz');sha=write_artifact(path,value)
        summary=light(value);summary['artifact']=dict(filename=path.name,sha256=sha)
        cp['jobs'][ident]=dict(artifact=path.name,sha256=sha,summary=summary);atomic_json(cp_path,cp);new_jobs+=1
        print('Completed',len(cp['jobs']),ident,value['metrics']['net_profit'],flush=True);return summary
    grid=hypotheses(frozen)
    if len(grid)!=frozen['search_budget']:raise ValueError('SEARCH_BUDGET')
    result['hypotheses']=grid
    try:
        for h in grid:
            raw_stream=cached(out/(digest(h)+'.streams.gz'),key,lambda:serialize_streams(build_streams(prepared,banks,normalizer,h)))
            streams=restore_streams(raw_stream['streams']);audit=raw_stream['decisions'];examples=raw_stream['examples'];del raw_stream
            for period in PERIODS:
                base=job(h,streams,period);stress=job(h,streams,period,True)
                status,reasons=classify(base,stress,frozen,period=='validation')
                result['results'].append(dict(hypothesis=h,period=period,base=base,stress=stress,classification=status,reasons=reasons,decision_audit=audit,examples=examples))
            del streams
        passing={r['hypothesis']['id'] for r in result['results'] if r['period']=='development' and r['classification']=='RESEARCH_CANDIDATE'}
        result['candidates']=[r['hypothesis'] for r in result['results'] if r['period']=='validation' and r['classification']=='RESEARCH_CANDIDATE' and r['hypothesis']['id'] in passing]
        #Controls never enter candidate selection. No validation-conditioned random frequency.
        reference=dict(id='ALL:RULE:PCT_2_4',family='ALL',mode='RULE',protect='PCT_2_4')
        reference_stream,_,_=build_streams(prepared,banks,normalizer,reference)
        dev_start,dev_end=map(stamp,PERIODS['development'])
        n=sum(dev_start<=b.time<dev_end and ds.direction is not None for (part,rows),(stream,_) in zip(prepared,reference_stream) for b,ds in zip(part,stream))
        denominator=sum(dev_start<=b.time<dev_end and i>=1000 and i%16==0 for part,rows in prepared for i,b in enumerate(part))
        probability=n/max(1,denominator);result['random_frequency_from_development']=probability
        for kind in ('DONCHIAN','EMA_RSI_ADX','RANDOM'):
            for seed in range(20261013,20261018) if kind=='RANDOM' else [20261013]:
                streams=control_streams(prepared,kind,seed,probability)
                h=dict(id=f'CONTROL:{kind}:{seed}',family=kind,mode='BASELINE',protect='PCT_2_4')
                for period in PERIODS:result['controls'].append(dict(kind=kind,seed=seed,period=period,result=job(h,streams,period,tag='control')))
        result['no_trade']=dict(net_profit='0',return_pct='0',max_drawdown_pct='0',trades=0)
        result['status']='RESEARCH_CANDIDATE_FORWARD_REQUIRED' if result['candidates'] else 'NO_EDGE_FOUND'
    except TimeoutError as e:result['status']='INCOMPLETE_'+str(e)
    result['completed_jobs']=len(cp['jobs']);result['results_classes']=dict(Counter(r['classification'] for r in result['results']))
    result['ranking']={p:[r['hypothesis']['id'] for r in sorted((r for r in result['results'] if r['period']==p),key=lambda r:(-D(r['base']['metrics']['net_profit']),r['hypothesis']['id']))] for p in PERIODS}
    atomic_json(args.report,result);return result


def serialize_streams(value):
    from dataclasses import asdict
    streams,audit,examples=value
    return dict(streams=[[dict(asdict(d),stop_distance=str(d.stop_distance) if d.stop_distance is not None else None,target_distance=str(d.target_distance) if d.target_distance is not None else None) for d in ds] for ds,_ in streams],decisions=audit,examples=examples)


def restore_streams(data):
    return [([Decision(**dict(r,stop_distance=D(r['stop_distance']) if r['stop_distance'] is not None else None,target_distance=D(r['target_distance']) if r['target_distance'] is not None else None)) for r in rows],None) for rows in data]


def control_streams(prepared,kind,seed,probability):
    from research.market_intelligence.strategies import decision
    rng=random.Random(seed);out=[]
    for part,rows in prepared:
        base=decisions(part,kind) if kind!='RANDOM' else None;ds=[]
        for i,(bar,row) in enumerate(zip(part,rows)):
            side=None
            if i>=1000 and i%16==0 and row:
                side=rng.choice(('LONG','SHORT')) if kind=='RANDOM' and rng.random()<probability else None if kind=='RANDOM' else base[i].direction
            ds.append(decision(bar,row,'ALL',side,'PCT_2_4'))
        out.append((ds,None))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--seconds',type=int,default=14400);p.add_argument('--job-seconds',type=int,default=900);p.add_argument('--max-jobs',type=int)
    a=p.parse_args()
    if a.seconds<=0 or not 1<=a.job_seconds<=900 or (a.max_jobs is not None and a.max_jobs<0):p.error('Valid bounded resource budgets required')
    r=run(a);print(r['status'],r.get('completed_jobs'),flush=True)
