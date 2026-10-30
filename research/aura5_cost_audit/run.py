"""Frozen, paired before/after correctness audit. Offline, no strategy selection."""
from bisect import bisect_left,bisect_right
from collections import Counter
from contextlib import contextmanager
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from app.hunter import engine,outcomes
from app.hunter.market import SOURCE,STEPS
from app.hunter.store import MODEL_HASH
from app.hunter.diagnostics import utc
from research.hunter6.data import load,aggregate
from .baseline import engine as old,outcomes as old_outcomes,MODEL_HASH as OLD_HASH

ROOT=Path(__file__).parent
P=json.loads((ROOT/'protocol.json').read_text())
T=lambda s:int(dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def captured_costs(module,rows):
    """Observe original planning calls without changing their return or eligibility."""
    original=module.net_rr
    def capture(entry,stop,target,direction,step,hold,spread=None):
        rr=original(entry,stop,target,direction,step,hold,spread)
        rows.append({'entry':float(entry),'sl':float(stop),'tp':float(target),'direction':direction,
                     'hold_bars':hold,'net_rr':float(rr) if rr is not None else None})
        return rr
    module.net_rr=capture
    try:yield
    finally:module.net_rr=original


def metrics(records):
    done=[r for r in records if r.get('entered') and r['outcome'] in ('TP','SL','TIMEOUT') and r.get('pnl_usdt') is not None]
    pnls=[float(r['pnl_usdt']) for r in done];wins=sum(x for x in pnls if x>0);loss=-sum(x for x in pnls if x<0)
    common=[float(r['pnl_usdt'])/abs(r['entry']-r['sl']) for r in done]
    peak=total=dd=0
    for r in sorted(done,key=lambda r:(r['exit_time'],r['id'])):
        total+=float(r['pnl_usdt']);peak=max(peak,total);dd=max(dd,peak-total)
    return {'signals':len(records),'entered':sum(bool(r.get('entered')) for r in records),'closed':len(done),
            'unknown':sum(r['outcome']=='UNKNOWN' for r in records),'no_fill':sum(r['outcome']=='NO_FILL' for r in records),
            'overlap_excluded':sum(r['outcome']=='OVERLAP' for r in records),
            'net_pnl_usdt_per_independent_1btc':sum(pnls) if done else None,
            'fees_usdt':sum(float(r['fees_usdt']) for r in done),'funding_usdt':sum(float(r['funding_usdt']) for r in done),
            'modeled_funding_settlements':sum(r['missing_funding_settlements'] for r in done),
            'win_rate':sum(x>0 for x in pnls)/len(done) if done else None,'profit_factor':wins/loss if loss else None,
            'expectancy_common_gross_R':sum(common)/len(done) if done else None,
            'native_r_definition':'SEE_VERSION_R_DEFINITION_NOT_DIRECTLY_COMPARABLE',
            'max_drawdown_sum_independent_1btc':dd if done else None,
            'outcomes':dict(sorted(Counter(r['outcome'] for r in records).items())),'portfolio_return':None}


def evaluate(plans,rows,funding,simulate,multiplier,end):
    times=[r[0] for r in rows];rate_times=[r[0] for r in funding];busy={};results=[]
    for p in sorted(plans,key=lambda p:(p['signal_time'],p['id'])):
        key=(p['strategy'],p['frame'],p['direction'])
        if p['signal_time']<busy.get(key,0):
            results.append({**p,'outcome':'OVERLAP','entered':False});continue
        a=bisect_left(times,p['signal_time']);b=min(bisect_left(times,end),a+p['hold_bars'])
        rates=funding[bisect_left(rate_times,p['signal_time']):bisect_right(rate_times,p['signal_time']+(p['hold_bars']+1)*p['step'])]
        r=simulate(p,rows[a:b],rates,multiplier=multiplier)
        if r['entered']:busy[key]=r['last_time']+p['step']
        results.append(r)
    return results


def run(destination,*,start=None,end=None,write=True):
    start=T(start or P['comparison_window'][0]);end=T(end or P['comparison_window'][1])
    issue_start,issue_end=map(T,P['issue66_window']);base,funding,manifest=load()
    base=[r for r in base if start-261*max(STEPS.values())<=r[0]<end]
    issue=[];plan_counts={};all_results=[];group_rows=[];prep_count=0
    for frame,step in STEPS.items():
        rows=aggregate(base,step);versions={'before':[],'after':[]};counter=Counter()
        for i,b in enumerate(rows):
            cutoff=b[0]+step
            if i<259 or not start<=cutoff<end:continue
            prepared=engine.Prepared(rows[i-259:i+1],frame)
            # Indicator code/parameters are unchanged. Share immutable arrays to
            # avoid computing the same 260-bar preparation twice at each cutoff.
            legacy=object.__new__(old.Prepared);legacy.__dict__=prepared.__dict__.copy()
            counter['closed_windows']+=1;prep_count+=1
            for family in engine.FAMILIES:
                captures=[];current=[]
                with captured_costs(old,captures):before=legacy.plans(259,family,cutoff=cutoff,watch=True)
                after=prepared.plans(259,family,cutoff=cutoff,watch=True,audit=current)
                before_geometry=[(r['direction'],r['entry'],r['sl'],r['tp'],r['hold_bars']) for r in captures]
                after_geometry=[(r['direction'],r['entry'],r['sl'],r['tp'],r['hold_bars']) for r in current]
                if before_geometry!=after_geometry:raise ValueError('UNAUTHORIZED_SETUP_OR_LEVEL_CHANGE')
                counter['candidates']+=len(captures);counter['before_plans']+=len(before);counter['after_plans']+=len(after)
                counter['before_triggered']+=sum(p['technical_trigger'] for p in before)
                counter['after_triggered']+=sum(p['technical_trigger'] for p in after)
                for version,plans in [('before',before),('after',after)]:
                    versions[version].extend({**p,'step':step} for p in plans if p['technical_trigger'])
                if issue_start<=cutoff<issue_end:
                    for a,z in zip(captures,current):
                        gross=(a['tp']-a['entry'])/(a['entry']-a['sl'])
                        issue.append({'frame':frame,'strategy':family,'direction':a['direction'],'closed_candle_close_utc':utc(cutoff),
                            'before':a,'after':z,'gross_rr':gross,'source':SOURCE,'quote_observed':False,
                            'input_sha256':hashlib.sha256(json.dumps(prepared.rows,separators=(',',':')).encode()).hexdigest()})
        plan_counts[frame]=dict(counter)
        # Check preparation parity independently on a representative complete window.
        if len(rows)>=260:
            a=engine.Prepared(rows[-260:],frame);b=old.Prepared(rows[-260:],frame)
            for key in ('ema20','ema50','ema200','atr','rsi','er20','mean20','std20','volume20','high20','low20','high40','low40','valid'):
                if not np.array_equal(getattr(a,key),getattr(b,key),equal_nan=True):raise ValueError('INDICATOR_CHANGED')
        for mult in P['cost_multipliers']:
            for version,plans,sim in [('before',versions['before'],old_outcomes.simulate),
                                      ('same_signals_corrected_execution',versions['before'],outcomes.simulate),
                                      ('after',versions['after'],outcomes.simulate)]:
                rs=evaluate(plans,rows,funding,sim,mult,end)
                all_results.extend({**r,'audit_version':version,'cost_multiplier':mult} for r in rs)
                for family in engine.FAMILIES:
                    for side in ('LONG','SHORT'):
                        ts=[r for r in rs if (r['strategy'],r['direction'])==(family,side)]
                        group_rows.append({'version':version,'cost_multiplier':mult,'frame':frame,'strategy':family,'direction':side,**metrics(ts)})
        print(json.dumps({'frame':frame,**dict(counter)}),flush=True)
    # Baseline 229 decisions must match the frozen Issue #66 archive identities.
    archived=json.loads(gzip.decompress(Path('docs/aura_trader5/issue66/replay/decisions.json.gz').read_bytes()))
    expected={(r['frame'],r['strategy'],r['direction'],r['closed_candle_close_utc']) for r in archived if r['candidate'] is True}
    actual={(r['frame'],r['strategy'],r['direction'],r['closed_candle_close_utc']) for r in issue}
    if start<=issue_start and end>=issue_end and (actual!=expected or len(issue)!=229):raise ValueError('ISSUE66_CANDIDATE_MISMATCH')
    summary={'scope':P['scope'],'source':SOURCE,'start_utc':utc(start),'end_exclusive_utc':utc(end),
             'baseline_commit':P['baseline_commit'],'baseline_model_sha256':OLD_HASH,'model_sha256':MODEL_HASH,
             'protocol_sha256':digest(ROOT/'protocol.json'),'archive_manifest_sha256':digest('data/hunter6/acquisition.json'),
             'archive_rows_verified':sum(m['rows'] for m in manifest['months']),'archive_window_rows':len(base),
             'funding_rows':len(funding),'funding_start_utc':utc(funding[0][0]),'funding_end_utc':utc(funding[-1][0]),
             'plan_counts':plan_counts,'closed_windows':prep_count,'issue66_candidates_audited':len(issue),
             'issue66_before_admitted':sum(r['before']['net_rr'] is not None and r['before']['net_rr']>=1.5 for r in issue),
             'issue66_after_admitted':sum(r['after']['rejection'] is None for r in issue),'groups':group_rows,
             'totals':[{'version':v,'cost_multiplier':m,**metrics([r for r in all_results if r['audit_version']==v and r['cost_multiplier']==m])}
                       for m in P['cost_multipliers'] for v in ('before','same_signals_corrected_execution','after')],
             'no_strategy_parameter_changes':True,'no_selection':True,'independent_unseen_oos':False,'orders':0,
             'actual_historical_quotes':False,'native_higher_tf_parity_claimed':False,'approved_for_confirmed':[],
             'funding_mark_prices_observed':False,'spread_slippage_model_not_actual_fills':True,
             'sum_independent_hypotheses_not_portfolio_return':True}
    if write:
        out=Path(destination);out.mkdir(parents=True,exist_ok=True)
        (out/'summary.json').write_text(json.dumps(summary,sort_keys=True,indent=2,allow_nan=False)+'\n')
        for name,value in [('candidates229.json.gz',issue),('outcomes.json.gz',all_results)]:
            (out/name).write_bytes(gzip.compress(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),mtime=0))
        cols=['frame','strategy','direction','closed_candle_close_utc','gross_rr','before_rr','after_rr','technical_trigger','entry','sl','tp','net_loss','net_reward','stop_fees','target_fees','funding_reserve','rejection']
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=cols,lineterminator='\n');writer.writeheader()
        for r in issue:
            a=r['after'];cost=a['costs'] or {}
            writer.writerow({**{k:r[k] for k in cols[:5]},'before_rr':r['before']['net_rr'],'after_rr':a['net_rr'],
                             **{k:a[k] for k in ('technical_trigger','entry','sl','tp','rejection')},
                             **{k:cost.get(k) for k in ('net_loss','net_reward','stop_fees','target_fees','funding_reserve')}})
        (out/'candidates229.csv').write_text(stream.getvalue())
    return summary


if __name__=='__main__':
    s=run(sys.argv[1] if len(sys.argv)>1 else 'docs/aura_trader5/cost_audit/results')
    print(json.dumps({'issue66_before':s['issue66_before_admitted'],'issue66_after':s['issue66_after_admitted'],'totals':s['totals']}))
