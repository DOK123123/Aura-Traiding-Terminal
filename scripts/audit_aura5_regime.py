"""Frozen before/after causal archive audit. No network, accounts, or parameter fit.

The baseline is the original PR #84 source. It runs only in this offline tool.
Historical quotes/funding are modeled; archive has been used in prior research.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import types

from app.hunter.costs import risk_reward, exit_fill
from app.hunter.market import SOURCE, STEPS, validate_bars
from app.manual_preview.explainable import evaluate, MODEL_HASH
from app.manual_preview.market_regime import RULES
from scripts.replay_explainable import bars_for

ROOT=Path(__file__).resolve().parents[1]
BASELINE='2317fe129bb6d2f3f803df7ac92b88a58a7177f7'
ARCHIVE=ROOT/'research/strategy_engine/bitget-2026-07-10-15m.json.gz'
NATIVE=ROOT/'research/strategy_engine/bitget-native-5m-2026-11-02.json.gz'


def reference():
    source=subprocess.check_output(['git','show',BASELINE+':app/manual_preview/explainable.py'],cwd=ROOT,text=True)
    module=types.ModuleType('app.manual_preview.audit_baseline')
    module.__file__=str(ROOT/'app/manual_preview/explainable.py')
    module.__package__='app.manual_preview'
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    # The pure baseline source reads MODEL_HASH at import; use its source digest
    # for audit-only identities rather than claiming the new file's hash is old.
    module.MODEL_HASH=hashlib.sha256(source.encode()).hexdigest()
    return module.evaluate,module.MODEL_HASH


def outcome(plan,bars,step,multiplier):
    i=plan['index'];hold=plan['hold'];side=plan['direction'];sign=1 if side=='LONG' else -1
    if i+hold>=len(bars):return {'state':'RIGHT_CENSORED'}
    entry=bars[i+1][1]*(1+sign*.0001)
    costs=risk_reward(entry,plan['sl'],plan['tp'],side,step,hold,entry*.0002,multiplier=multiplier)
    if (costs is None or costs['net_rr']<1.5 or not plan['zone'][0]<=costs['entry_fill']<=plan['zone'][1]
            or not plan['zone'][0]<=entry<=plan['zone'][1]):return {'state':'NO_FILL'}
    kind='TIMEOUT';exit_price=bars[i+hold][4]*(1-sign*.0001)
    for b in bars[i+1:i+hold+1]:
        o,h,l,_=(x*(1-sign*.0001) for x in b[1:5])
        if sign*(o-plan['sl'])<=0:exit_price=o;kind='SL';break
        if (l<=plan['sl'] if sign==1 else h>=plan['sl']):exit_price=plan['sl'];kind='SL';break
        if (h>=plan['tp'] if sign==1 else l<=plan['tp']):exit_price=plan['tp'];kind='TP';break
    filled=exit_fill(exit_price,side,multiplier=multiplier);e=costs['entry_fill']
    pnl=sign*(filled-e)-.001*multiplier*(e+filled)-costs['funding_reserve']
    return {'state':kind,'net_r':pnl/costs['net_loss']}


def performance(plans,bars,step):
    output={}
    for multiplier in (1,1.5,2):
        rows=[outcome(p,bars,step,multiplier) for p in plans]
        closed=[x['net_r'] for x in rows if 'net_r' in x]
        gains=sum(max(0,x) for x in closed);losses=-sum(min(0,x) for x in closed)
        output[str(multiplier)]=dict(setups=len(plans),outcomes=dict(Counter(x['state'] for x in rows)),
            filled=len(closed),mean_net_r=sum(closed)/len(closed) if closed else None,
            profit_factor=gains/losses if losses else None)
    return output


def run(output: Path):
    old,old_hash=reference();base=json.load(gzip.open(ARCHIVE));native=json.load(gzip.open(NATIVE))
    assert native['source']==SOURCE and native['frame']=='5m' and native['product']=='USDT-FUTURES'
    report=dict(scope='OFFLINE_CAUSAL_RESEARCH_NO_ORDERS',verdict='INSUFFICIENT_EVIDENCE',baseline_commit=BASELINE,
        baseline_source_sha256=old_hash,model_sha256=MODEL_HASH,rules=RULES,
        archives={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ARCHIVE,NATIVE)},
        costs=dict(fee_bps_per_side=10,slippage_bps_per_side=5,full_spread_bps=2,funding_reserve_bps_per_8h=1),
        protocol=dict(decisions='EVERY_CLOSED_PREFIX_260_BARS',entry='NEXT_ACTUAL_OPEN_AFTER_DECISION',ties='SL_FIRST',
                      gap='ADVERSE_STOP_OPEN',stress=[1,1.5,2],parameter_search=False),
        limitations=['Reused historical archive, not independent OOS','5m archive has a different coverage interval',
                     '1h/4h aggregated from complete 15m groups, not fabricated 5m',
                     'Historical bid/ask and funding unavailable: fixed model, not observed execution costs',
                     'Overlapping hypotheses, not independent trades, not portfolio returns',
                     'Class boundaries are descriptive conventions, not a qualified predictive filter'],frames={})
    for frame,step in STEPS.items():
        bars=native['bars'] if frame=='5m' else bars_for(base,step);validate_bars(bars,step)
        scores=Counter();regimes=Counter();states=Counter();before=defaultdict(list);after=defaultdict(list);removed=[]
        differences=[]
        for i in range(259,len(bars)):
            prefix=bars[i-259:i+1];now=bars[i][0]+step;mid=bars[i][4]
            q=dict(source=SOURCE,bid=mid*.9999,ask=mid*1.0001,last=mid,time=now,received_at=now)
            previous=old(prefix,frame,q,now);current=evaluate(prefix,frame,q,now)
            regimes[current[0]['market_regime']['state']]+=1
            for prior,row in zip(previous,current):
                key=row['strategy']+'|'+row['direction'];scores[key+'|'+str(row['score'])]+=1
                states[key+'|'+row['state']]+=1
                if row['score']!=prior['score']:differences.append({'at':now,'key':key,'kind':'SCORE_CHANGED'})
                plan=dict(index=i,direction=row['direction'],sl=prior['sl'],tp=prior['tp'],hold=prior['horizon']['hold_bars'],
                          zone=[mid-.25*prior['indicators']['atr'],mid+.25*prior['indicators']['atr']])
                if prior['state']=='WATCH':before[key].append(plan)
                if row['state']=='WATCH':
                    assert prior['state']=='WATCH', 'NEW_WATCH_NOT_ALLOWED_BY_THIS_RESTRICTION'
                    assert all(row[k]==prior[k] for k in ('entry','sl','tp','net_rr'))
                    after[key].append(plan)
                elif prior['state']=='WATCH':removed.append(dict(at=now,key=key,regime=row['market_regime']['state'],rejection=row['rejection']))
        groups={}
        for strategy in ('TREND_PULLBACK','BREAKOUT_RETEST','MOMENTUM_DIVERGENCE'):
            for side in ('LONG','SHORT'):
                key=strategy+'|'+side;groups[key]=dict(before=performance(before[key],bars,step),after=performance(after[key],bars,step))
        report['frames'][frame]=dict(bars=len(bars),closed_decisions=max(0,len(bars)-259),
            first_utc=datetime.fromtimestamp(bars[0][0],timezone.utc).isoformat(),
            last_close_utc=datetime.fromtimestamp(bars[-1][0]+step,timezone.utc).isoformat(),
            regimes=dict(regimes),score_histogram=dict(scores),states=dict(states),score_differences=differences,
            removed_watch=removed,groups=groups,
            before=performance([p for values in before.values() for p in values],bars,step),
            after=performance([p for values in after.values() for p in values],bars,step))
        assert not differences
        print(frame,json.dumps({'decisions':len(bars)-259,'regimes':dict(regimes),'removed_watch':len(removed)}),flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
