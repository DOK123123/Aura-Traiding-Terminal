"""Frozen descriptive-score replay on archived Bitget candles (no real quotes)."""
from collections import defaultdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from app.hunter.confidence import score_at, VERSION
from app.hunter.costs import risk_reward
from app.hunter.engine import Prepared, RULES
from app.hunter.outcomes import simulate
from research.hunter6.data import load, aggregate

START=1782864000                 # 2026-07-01 UTC
TRAIN_END=1785542400             # 2026-08-01 UTC
VALID_END=1788220800             # 2026-09-01 UTC
END=1793318400                   # 2026-10-30 UTC (already studied)
PERIODS={'TRAIN':(START,TRAIN_END),'VALIDATION':(TRAIN_END,VALID_END),
         'REUSED_TEST_NOT_UNTOUCHED':(VALID_END,END)}
FRAMES={'5m':300,'15m':900,'1h':3600,'4h':14400}


def utc(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def bin_name(score):return '50-64' if score<65 else '65-79' if score<80 else '80-100'


def plan_at(prepared,index,evidence):
    """Levels use only closing-candle evidence; next-open fill comes later."""
    sign=1 if evidence['direction']=='LONG' else -1
    entry=evidence['reference_close'];atr=evidence['atr']
    anchor=evidence['support'] if sign==1 else evidence['resistance']
    distance=max(1.5*atr,sign*(entry-anchor)+.25*atr)
    stop=entry-sign*distance;target=entry+sign*2.5*distance
    costs=risk_reward(entry,stop,target,evidence['direction'],prepared.step,24)
    if not costs or costs['net_rr']<RULES['planning']['min_net_rr'] or min(entry,stop,target)<=0:
        return None
    decision=evidence['closed_at']
    return {'direction':evidence['direction'],'frame':prepared.frame,
            'signal_time':decision,'valid_until':decision+prepared.step,
            'entry':entry,'sl':stop,'tp':target,'zone':[entry-.5*atr,entry+.5*atr],
            'step':prepared.step,'hold_bars':24,'mode':'HISTORICAL_OHLC_PROXY',
            'technical_score':evidence['score'],'score_version':VERSION}


def group_metrics(entries):
    closed=[x for x in entries if x['entered'] and x['outcome'] in ('TP','SL','TIMEOUT') and x['pnl_usdt'] is not None]
    pnl=[float(x['pnl_usdt']) for x in closed]
    wins=sum(x for x in pnl if x>0);losses=-sum(x for x in pnl if x<0)
    equity=peak=drawdown=0.
    for value in pnl:
        equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    return {'attempts':len(entries),'entered':sum(bool(x['entered']) for x in entries),
            'closed':len(closed),'unknown':sum(x['outcome']=='UNKNOWN' for x in entries),
            'no_fill':sum(x['outcome']=='NO_FILL' for x in entries),
            'net_pnl_usdt_per_independent_1btc_hypothesis':round(sum(pnl),4),
            'profit_factor':round(wins/losses,5) if losses else None,
            'expectancy_usdt_per_closed_hypothesis':round(sum(pnl)/len(pnl),5) if pnl else None,
            'max_sequential_hypothesis_drawdown_usdt_not_portfolio':round(drawdown,4)}


def run():
    archive,funding,manifest=load()
    source=[b for b in archive if START-45*86400<=b[0]<END+86400]
    report={'protocol':'AURA5_CONFIDENCE_RESEARCH_V1_NO_FITTING',
            'score_version':VERSION,'source':manifest['source'],
            'history_start_utc':utc(START),'history_end_exclusive_utc':utc(END),
            'archive_hashes':'data/hunter6/acquisition.json',
            'periods':{k:[utc(a),utc(b)] for k,(a,b) in PERIODS.items()},
            'untouched_holdout':False,'independent_edge_validated':False,
            'calibrated_win_probability':None,
            'notes':['All periods previously explored by Aura; reused test is NOT untouched holdout',
                     'One candidate max per side/frame until earlier hypothetical exit; no cross-frame portfolio claim',
                     'OHLC next-open with modeled 2bps spread, 5bps slippage and 10bps fee per side',
                     'Funding missingness modeled; historical Bid/Ask and fills unavailable',
                     'Fixed 50/65/80 bins; no optimization or threshold selection'],
            'score_counts':{},'results':{},'examples':[]}
    for frame,step in FRAMES.items():
        rows=source if frame=='5m' else aggregate(source,step)
        prepared=Prepared(rows,frame)
        score_counts=defaultdict(int);runs=defaultdict(list);unblocked={}
        for i in range(259,len(rows)-25):
            if not prepared.valid[i]:continue
            decision=rows[i][0]+step
            period=next((name for name,(a,b) in PERIODS.items() if a<=decision<b),None)
            if period is None:continue
            for evidence in score_at(prepared,i):
                score=evidence['score']
                if score<50:continue
                name=bin_name(score);key=(period,evidence['direction'],name)
                score_counts[key]+=1
                plan=plan_at(prepared,i,evidence)
                if plan is None:continue
                side_key=(period,evidence['direction'])
                if decision<unblocked.get(side_key,0):continue
                boundary=PERIODS[period][1]
                future=[b for b in rows[i+1:i+25] if b[0]<boundary]
                outcome=simulate(plan,future,funding)
                runs[key].append(outcome)
                unblocked[side_key]=outcome['exit_time']+step if outcome['entered'] and outcome['exit_time'] is not None else decision+step
                if len([x for x in report['examples'] if x['direction']==plan['direction']])<8:
                    report['examples'].append({'period':period,'direction':plan['direction'],'frame':frame,
                        'detected_at_utc':utc(decision),'score':score,'entry_reference':round(plan['entry'],2),
                        'sl':round(plan['sl'],2),'tp':round(plan['tp'],2),
                        'outcome':outcome['outcome'],'pnl_usdt':outcome['pnl_usdt'],
                        'warning':'HISTORICAL_HYPOTHESIS_NOT_LIVE_QUOTE'})
        for key,count in sorted(score_counts.items()):report['score_counts']['|'.join((frame,*key))]=count
        for key,outcomes in sorted(runs.items()):report['results']['|'.join((frame,*key))]=group_metrics(outcomes)
    return report


if __name__=='__main__':
    cli=argparse.ArgumentParser(description='Reproduce descriptive Aura 5 score replay')
    cli.add_argument('--output',type=Path,default=None)
    args=cli.parse_args()
    payload=json.dumps(run(),ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(payload)
        print('WROTE',args.output)
    else:print(payload)
