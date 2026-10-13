"""Past-fit normalization, completed-only analogs, purge and conservative evidence."""
from bisect import bisect_left
from collections import defaultdict
from math import sqrt,isfinite
from statistics import mean,pstdev,stdev
from app.lab.models import digest
from .structure import VECTOR_NAMES,VERSION


def fit_normalizer(rows,cutoff):
    eligible=[r for r in rows if r is not None and r['timestamp']<=cutoff]
    if len(eligible)<1000:raise ValueError('INSUFFICIENT_CALIBRATION')
    if any(len(r['vector'])!=len(VECTOR_NAMES) or not all(isfinite(v) for v in r['vector']) for r in eligible):raise ValueError('INVALID_VECTOR')
    centers=[mean(r['vector'][j] for r in eligible) for j in range(len(VECTOR_NAMES))]
    scales=[max(pstdev(r['vector'][j] for r in eligible),.1) for j in range(len(VECTOR_NAMES))]
    return dict(version=VERSION,features=list(VECTOR_NAMES),fit_closed_through=cutoff,count=len(eligible),means=centers,scales=scales,source_rows_sha256=digest([dict(timestamp=r['timestamp'],vector=r['vector']) for r in eligible]))


def normalized(vector,normalizer,query_time):
    if type(query_time) is not int or type(normalizer.get('fit_closed_through')) is not int:raise ValueError('INVALID_CUTOFF')
    if len(normalizer['means'])!=len(VECTOR_NAMES) or len(normalizer['scales'])!=len(VECTOR_NAMES) or any(type(x) not in (int,float) or not isfinite(x) for x in normalizer['means']+normalizer['scales']) or any(s<=0 for s in normalizer['scales']):raise ValueError('INVALID_NORMALIZER')
    if query_time<=normalizer['fit_closed_through']:raise ValueError('NORMALIZATION_NOT_YET_AVAILABLE')
    if len(vector)!=len(VECTOR_NAMES) or not all(isfinite(x) for x in vector):raise ValueError('INVALID_VECTOR')
    return [max(-5,min(5,(x-m)/s)) for x,m,s in zip(vector,normalizer['means'],normalizer['scales'])]


def nearest(query,events,normalizer,max_pool=2048,max_neighbors=64,purge_seconds=345600):
    at=query['timestamp'];q=normalized(query['vector'],normalizer,at)
    # Bank is sorted by outcome resolution, not entry; strict cutoff avoids unresolved labels.
    times=[r['resolved_at'] for r in events]
    if any(b<a for a,b in zip(times,times[1:])):raise ValueError('UNORDERED_BANK')
    right=bisect_left(times,at)
    pool=events[max(0,right-max_pool):right];ranked=[]
    for event in pool:
        if type(event['timestamp']) is not int or type(event['resolved_at']) is not int or event['resolved_at']<event['timestamp']+900:raise ValueError('INVALID_LABEL_TIME')
        if event['timestamp']+purge_seconds>at or event['resolved_at']>=at:continue
        if event.get('structure_mask',0)!=query.get('structure_mask',0):continue
        if event['regime']!=query['regime'] or event['mtf_mask']!=query['mtf_mask']:continue
        if event.get('volume_known',True)!=query.get('volume_known',True):continue
        if event['family']!=query['family'] or event['direction']!=query['direction']:continue
        v=normalized(event['vector'],normalizer,at)
        groups=((0,1,11,12,13,14),(2,),(3,),(4,5,6,17),(7,15,16),(8,9,10),(18,19,20))
        distance=sqrt(sum(sum((q[j]-v[j])**2 for j in group)/len(group) for group in groups)/len(groups))
        if distance<=1.5:ranked.append((distance,event))
    ranked.sort(key=lambda x:(x[0],x[1]['timestamp'],x[1]['resolved_at']));picked=[]
    for distance,event in ranked:
        if all(abs(event['timestamp']-p['timestamp'])>=purge_seconds for p in picked):picked.append(dict(event,distance=distance))
        if len(picked)>=max_neighbors:break
    return picked


def evidence(selected):
    pnls=[float(r['net_pnl']) for r in sorted(selected,key=lambda r:r['timestamp'])];n=len(pnls)
    if not n:return dict(count=0,status='INSUFFICIENT_DATA',expectancy=None,lower95=None,positive_period_fraction=None,tp_first=None,profit_factor=None,mean_distance=None,block_count=0)
    blocks=defaultdict(list)
    for r in selected:blocks[r['timestamp']//(14*86400)].append(float(r['net_pnl']))
    means=[mean(v) for v in blocks.values()];lower=mean(means)-1.96*stdev(means)/sqrt(len(means)) if len(means)>=8 else None
    wins=sum(p>0 for p in pnls);losses=sum(p<0 for p in pnls);loss=-sum(p for p in pnls if p<0)
    period_fraction=sum(x>0 for x in means)/len(means)
    positive=mean(pnls)>0 and lower is not None and lower>0 and period_fraction>=2/3 and loss>0 and sum(p for p in pnls if p>0)/loss>=1.1
    peak=running=dd=0.
    for p in pnls:running+=p;peak=max(peak,running);dd=max(dd,peak-running)
    return dict(count=n,wins=wins,losses=losses,tp_first=sum(r['target_first'] for r in selected)/n,
        expectancy=mean(pnls),lower95=lower,positive_period_fraction=period_fraction,
        profit_factor=sum(p for p in pnls if p>0)/loss if loss else None,
        mean_distance=mean(r['distance'] for r in selected),block_count=len(means),descriptive_drawdown_usdt=dd,
        status='HISTORICAL_EDGE_ONLY' if n>=30 and positive else 'INSUFFICIENT_DATA' if n<30 or len(means)<8 else 'NO_EDGE',
        uncertainty='Approximate95% normal interval of14-day block mean outcomes; not calibrated forecast, stationarity assumed. Portfolio significance tested separately with block bootstrap.')


def route(bar,row,banks,normalizer,protect,mode='EDGE',family='ALL'):
    from .strategies import candidates,FAMILIES
    if mode not in ('RULE','NEAREST','EDGE') or family not in (*FAMILIES,'ALL') or protect not in ('PCT_2_4','ATR_2_4'):raise ValueError('INVALID_ROUTER_CONFIGURATION')
    options=candidates(bar,row)
    if not options:return dict(strategy='WAIT',reason='NO_CONTEXT_SETUP',options=[])
    if row['timestamp']<=normalizer['fit_closed_through']:return dict(strategy='WAIT',reason='CALIBRATION',options=[])
    if family!='ALL':options={k:v for k,v in options.items() if k==family}
    scored=[];rejected=[]
    scope='UNIVERSAL' if family=='ALL' else 'FAMILY'
    for name in FAMILIES:
        if name not in options:continue
        side=options[name]
        if mode=='RULE':ev=None;score=-FAMILIES.index(name)
        else:
            q=dict(timestamp=row['timestamp'],vector=row['vector'],regime=row['regime'],mtf_mask=row['mtf']['known_mask'],structure_mask=row.get('structure_known_mask',0),volume_known=row['relative_volume'] is not None,family=name,direction=side)
            matches=nearest(q,banks.get((protect,name,side,scope),[]),normalizer);ev=evidence(matches)
            if ev['count']<30:
                rejected.append(dict(strategy=name,reason='INSUFFICIENT_ANALOGS',evidence=ev));continue
            if mode=='EDGE' and ev['status']!='HISTORICAL_EDGE_ONLY':
                rejected.append(dict(strategy=name,reason=ev['status'],evidence=ev));continue
            score=-ev['mean_distance'] if mode=='NEAREST' else ev['lower95']
        scored.append(dict(strategy=name,direction=side,evidence=ev,score=score))
    if not scored:return dict(strategy='WAIT',reason='INSUFFICIENT_DATA_OR_NO_EDGE',options=rejected)
    chosen=max(scored,key=lambda r:(r['score'],-FAMILIES.index(r['strategy'])))
    return dict(chosen,reason='RESEARCH_'+mode,execution='DISABLED',validation='NOT_PRODUCTION_APPROVED')


def explain(bar,row,banks,normalizer,protect='PCT_2_4'):
    proposal=route(bar,row,banks,normalizer,protect)
    return dict(state=row,historical_research=proposal,strategy='WAIT',reason='FORWARD_VALIDATION_AND_OWNER_CONFIRMATION_REQUIRED',
        read_only=True,execution='DISABLED',manual_confirmation_required=True)
