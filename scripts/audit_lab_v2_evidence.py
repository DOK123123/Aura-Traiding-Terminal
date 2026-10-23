"""Independent Decimal indicator oracle plus real-data native/prefix evidence."""
from bisect import bisect_left
from dataclasses import replace
from decimal import Decimal as D,localcontext
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from app.lab.models import digest
from app.lab.series import higher
from app.lab.v2_strategies import prepare,decide,FAMILIES
from scripts.aura43_history import load_history
from scripts.lab_v2_baselines import read_checkpoint,code_hashes as native_hashes
from scripts.research_lab_v2 import code_hashes,eligible,VARIANTS
from scripts.replay_auto42_verification import PrefixCache,snapshot
from scripts.aura43_profile_context import snapshot as projected


def reference(frame):
    n=len(frame);out={k:[None]*n for k in ('ema20','ema50','ema200','atr','rsi','adx','di_plus','di_minus')}
    close=[b.close for b in frame]
    for period in (20,50,200):
        if n<period:continue
        value=sum(close[:period])/period;out['ema'+str(period)][period-1]=value
        alpha=D(2)/(period+1)
        for i in range(period,n):
            value=value*(1-alpha)+close[i]*alpha;out['ema'+str(period)][i]=value
    tr=[b.high-b.low if i==0 else max(b.high-b.low,abs(b.high-frame[i-1].close),abs(b.low-frame[i-1].close)) for i,b in enumerate(frame)]
    if n>=14:
        value=sum(tr[:14])/14;out['atr'][13]=value
        for i in range(14,n):value=(13*value+tr[i])/14;out['atr'][i]=value
    if n>14:
        changes=[b-a for a,b in zip(close,close[1:])];gain=sum(max(x,D(0)) for x in changes[:14])/14;loss=sum(max(-x,D(0)) for x in changes[:14])/14
        for i in range(14,n):
            if i>14:gain=(13*gain+max(changes[i-1],D(0)))/14;loss=(13*loss+max(-changes[i-1],D(0)))/14
            out['rsi'][i]=D(50) if gain==loss==0 else D(100) if loss==0 else 100-100/(1+gain/loss)
    if n>=28:
        plus=[];minus=[]
        for a,b in zip(frame,frame[1:]):
            up=b.high-a.high;down=a.low-b.low;plus.append(up if up>down and up>0 else D(0));minus.append(down if down>up and down>0 else D(0))
        total=sum(tr[1:15]);p=sum(plus[:14]);m=sum(minus[:14]);dx=[];ax=None
        for i in range(14,n):
            if i>14:total=total*D(13)/14+tr[i];p=p*D(13)/14+plus[i-1];m=m*D(13)/14+minus[i-1]
            pd=100*p/total if total else D(0);md=100*m/total if total else D(0)
            out['di_plus'][i]=pd;out['di_minus'][i]=md;dx.append(100*abs(pd-md)/(pd+md) if pd+md else D(0))
            if i==27:ax=sum(dx[:14])/14
            elif i>27:ax=(13*ax+dx[-1])/14
            out['adx'][i]=ax
    return out


def audit(directory,csv,native_path):
    r=json.loads(gzip.decompress((directory/'report.json.gz').read_bytes()));checksum=r.pop('checksum')
    assert digest(r)==checksum and r['code_hashes']==code_hashes();bars,source=load_history(csv)
    assert source['sha256']==r['source']['sha256'];fp=digest(dict(data=source['sha256'],code=native_hashes(),start=r['start'],end=r['end_exclusive']))
    rows=read_checkpoint(native_path,fp,r['start'],r['end_exclusive']);assert len(rows)==35040
    comparisons=0;ratchets=0;refs={};frames={}
    with localcontext() as ctx:
        ctx.prec=64
        for tf,step in (('15m',900),('1h',3600),('4h',14400)):
            data=prepare(bars,step);frame=data['bars'];ref=reference(frame);refs[tf]=ref;frames[tf]=data
            for key,series in ref.items():
                for a,b in zip(series,data[key]):
                    assert (a is None)==(b is None),(tf,key)
                    if a is not None:assert abs(a-D(str(b)))<=max(D('0.00000001'),abs(a)*D('0.000000000001')),(tf,key)
                    comparisons+=1
        for run in r['runs']:
            path=directory/run['decision_artifact'];compressed=path.read_bytes();assert hashlib.sha256(compressed).hexdigest()==run['decision_sha256']
            logs=gzip.decompress(compressed).splitlines();assert len(logs)==run['decision_total']
            original_by_dispatch={}
            for raw in logs:
                d=json.loads(raw)
                if d.get('direction'):original_by_dispatch[d['closed_at']]=d['original_signal_at']
            for t in run['trades']+([run['open_position']] if run['open_position'] else []):
                assert original_by_dispatch[t['signal_at']]==t['original_signal_at']
                tf=t['strategy_timeframe'];data=frames[tf];frame=data['bars'];step=data['step'];previous=D(t.get('initial_stop_loss',t['stop_loss']))
                for h in t.get('stop_history',[]):
                    cutoff=h['effective_from'];i=bisect_left([b.time for b in frame],cutoff)-1
                    assert frame[i].time+step==cutoff
                    assert abs(D(h['atr'])-refs[tf]['atr'][i])<=D('0.00000001')
                    observed=[b for b in frame[:i+1] if b.time>=t['entry_time']]
                    extreme=max([D(t['entry_raw_price'])]+[b.high for b in observed]) if t['direction']=='LONG' else min([D(t['entry_raw_price'])]+[b.low for b in observed])
                    assert extreme==D(h['extreme']) and frame[i].close==D(h['bar_close'])
                    candidate=min(extreme-3*D(h['atr']),frame[i].close) if t['direction']=='LONG' else max(extreme+3*D(h['atr']),frame[i].close)
                    expected=max(previous,candidate) if t['direction']=='LONG' else min(previous,candidate)
                    assert expected==D(h['stop_loss']);previous=expected;ratchets+=1
    dev=[run for run in r['runs'] if run['split']=='development' and eligible(run,30)]
    winner=max(dev,key=lambda x:D(x['metrics']['expectancy']))['variant'] if dev else None
    assert winner==r['development_selection']['winner'] and digest(r['development_selection'])==r['selection_hash']
    # Real native snapshot inputs at all 15m UTC phases, one dev and one val block.
    times=[b.time for b in bars];cutoffs=0
    for at in (r['start']+20*86400,r['split_at']//14400*14400+20*86400):
        left=bisect_left(times,at-4160*900);full=bars[left:left+4175];cache=PrefixCache(full)
        with cache.installed():
            for n in range(4160,4176):
                w=full[:n];t=w[-1].time+900;a=snapshot(w,t);b=projected(cache,w,t)
                for key in b:assert b[key]==(a[key] if key!='history' else dict(source_sha256=a['history']['source_sha256']))
                cutoffs+=1
        prefix=full[:4161];changed=prefix+[replace(b,open=b.open*2,high=b.high*2,low=b.low*2,close=b.close*2) for b in full[4161:]]
        assert projected(cache,prefix,prefix[-1].time+900)==projected(PrefixCache(changed),prefix,prefix[-1].time+900)
    # All baseline portfolios must match unchanged native engine execution,
    # including the predeclared delayed sensitivity. Ignore only extra metadata.
    from app.automated.engine import initial,advance,mark
    from scripts.research_lab_v2 import decisions
    from app.lab.models import digest as state_digest
    baseline_runs=0
    for run in r['runs']:
        if run['variant'] not in ('AURA42','AURA43'):continue
        start,end=run['start'],run['end_exclusive'];i=bisect_left(times,start)
        state=initial(start,epoch='LAB_ONLY_'+run['variant']+'_'+run['split'])
        state.update(mode='ON',watermark=start,last_bar_hash=state_digest(bars[i-1].data()));mark(state,bars[i-1],start);closed=[]
        for item in decisions(bars,run['variant'],rows,{},start,end,1 if run['split']=='validation_delayed' else 0):
            at=item['closed_at'];k=bisect_left(times,at);state,events=advance(state,bars[k-2:k],item['decision'],at+30)
            closed.extend(e['payload'] for e in events if e['kind']=='CLOSE')
        clean=lambda p:{k:v for k,v in p.items() if k not in ('original_signal_at','strategy_timeframe')}
        assert [clean(t) for t in run['trades']]==closed
        for key in ('balance','equity','fees','slippage','max_drawdown_pct'):
            mk={'balance':'final_balance','equity':'final_equity'}.get(key,key)
            assert state[key]==run['metrics'][mk]
        baseline_runs+=1
    # Full-history new features are causal under price changes strictly after a cutoff.
    cutoff=r['split_at'];changed=[b if b.time<cutoff else replace(b,open=b.open*2,high=b.high*2,low=b.low*2,close=b.close*2) for b in bars]
    for tf,step in (('15m',900),('1h',3600),('4h',14400)):
        a=frames[tf];b=prepare(changed,step);i=max(i for i,x in enumerate(a['bars']) if x.time+step<=cutoff);at=a['bars'][i].time+step
        for family in FAMILIES:assert decide(a,i,family,closed_at=at)==decide(b,i,family,closed_at=at)
    return dict(status='PASS',source_sha256=source['sha256'],native_closed_decisions=35040,native_execution_portfolios_equal=baseline_runs,independent_decimal_indicator_values_checked=comparisons,
        causal_trailing_updates_checked=ratchets,native_real_snapshot_cutoffs_checked=cutoffs,all_decision_artifact_hashes_verified=True,
        future_perturbation_invariant=True,selection_development_only=True,production_access=False,proves_live_execution=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True,type=Path);p.add_argument('--csv',required=True,type=Path);p.add_argument('--native',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if not __debug__:raise RuntimeError('ASSERTIONS_REQUIRED')
    result=audit(a.directory,a.csv,a.native);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
