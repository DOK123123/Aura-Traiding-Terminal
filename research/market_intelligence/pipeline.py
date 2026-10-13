"""Frozen offline experiment construction; reuse existing segmented Decimal ledger."""
from collections import Counter,defaultdict
from dataclasses import replace
from pathlib import Path
import hashlib
import time
from app.lab.models import Baseline,digest
from app.lab.execution import simulate
from app.lab.strategies import Decision,decisions
from scripts.run_six_year import period_job
from scripts.pattern_research import blocked_bootstrap
from scripts.run_lab3 import stamp
from .strategies import FAMILIES,RULES,candidates,decision
from .similarity import route

CALIBRATION_END=stamp('2020-04-01')
PERIODS={'development':('2020-04-01','2023-01-01'),'validation':('2023-01-01','2025-01-01')}


def protocol(root):
    paths=[*sorted((root/'research/market_intelligence').glob('*.py')),root/'scripts/run_market_intelligence.py',
        root/'scripts/lab3_history.py',root/'scripts/pattern_research.py',root/'scripts/run_pattern_research.py',root/'scripts/run_six_year.py',root/'scripts/research_inverse.py',
        root/'scripts/offline_fixed_strategies.py',root/'scripts/lab3_strategies.py',root/'scripts/run_lab3.py',
        root/'app/intelligence/patterns.py',root/'app/lab/models.py',root/'app/lab/indicators.py',root/'app/lab/strategies.py',root/'app/lab/execution.py']
    return dict(version='AURA_MARKET_INTELLIGENCE_3.0',software={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        families=list(FAMILIES),rules=RULES,modes=['RULE','NEAREST','EDGE'],protect=['PCT_2_4','ATR_2_4'],
        search_budget=42,calibration=['2020-01-01','2020-04-01'],periods=PERIODS,
        normalizer='Only2020Q1 closed states; frozen means/std>=0.1; standardized vector clipped+-5. Calibration not included in trading metrics.',
        warmup=dict(context=250,execution=1000,higher=250),anchor_stride=16,anchor_phase='segment index divisible by16, after1000-bar execution warmup',horizon_max_bars=98,max_labels=100000,
        similarity=dict(metric='Equal7-family RMS standardized Euclidean; exact family,side,regime,structure-mask,MTF-mask,volume availability',max_distance=1.5,max_pool=2048,neighbors64=64,purge_seconds=345600,min_samples=30),
        router='RULE priority frozen family order; NEAREST smallest mean distance without edge gate (baseline); EDGE lower95 block-mean positive,PF>=1.1,positive14day-block fraction>=2/3 and>=8blocks; never production-approved.',
        exits='Independent family hypotheses use formal invalidation. ALL meta-router uses protective stops/targets and UTC daily timed exit only; analog banks use exactly that UNIVERSAL exit model. No exit reinterpretation as entry family changes.',
        baseline=Baseline().data(),stress=dict(fee_bps='20',slippage_bps='10',signal_policy='Same frozen baseline-cost signals, no stress retuning'),
        selection=dict(min_trades=100,min_validation_trades=60,max_dd=25,positive_each_year=True,positive_stress=True,bootstrap_reps=19999,block_days=14,alpha=.05,known_comparison_family_minimum=869),
        multiple_search_note='869=810 prior Pattern hypotheses+42 current+17 prior Lab versions; earlier exploratory searches not exhaustively counted, hence research only and no confirmed/blind edge claim.',
        validation_note='Temporal validation only:2023-24 already seen in prior studies.2025 is already observed and NOT run or optimised here. New forward period required.',
        safety='OFFLINE_ONLY; no web routing, private-account imports, portfolio DB access or execution activation.')


def hypotheses(frozen):
    return [dict(id=f'{family}:{mode}:{protect}',family=family,mode=mode,protect=protect)
        for family in [*frozen['families'],'ALL'] for mode in frozen['modes'] for protect in frozen['protect']]


def build_banks(prepared,frozen):
    banks=defaultdict(list);stats=Counter()
    for part,rows in prepared:
        for i in range((1000+frozen['anchor_stride']-1)//frozen['anchor_stride']*frozen['anchor_stride'],len(part)-1,frozen['anchor_stride']):
            row=rows[i]
            if row is None:continue
            options=candidates(part[i],row);stats['sampled_states']+=1
            for family,side in options.items():
                stats['setups']+=1
                for protect in frozen['protect']:
                    for scope in ('FAMILY','UNIVERSAL'):
                        end=min(len(part),i+frozen['horizon_max_bars'])
                        if end-i<2:continue
                        ds=[decision(part[j],rows[j],family if scope=='FAMILY' else 'ALL',side if j==i else None,protect) for j in range(i,end)]
                        value=simulate(part[i:end],ds,0,len(ds),900,Baseline(),close_at_end=False)
                        if not value['trades']:
                            if value['rejections']:
                                stats.update({'label_rejected:'+k:v for k,v in value['rejections'].items()})
                            elif value.get('open_position') is not None:stats['unresolved_gap_labels']+=1
                            else:stats['no_label_trade']+=1
                            continue
                        trade=value['trades'][0]
                        if trade['entry_time']!=row['timestamp'] or trade['exit_time']<=trade['signal_time']:raise ValueError('LABEL_CAUSALITY')
                        event=dict(timestamp=row['timestamp'],resolved_at=trade['exit_time'],vector=row['vector'],
                            family=family,direction=side,regime=row['regime'],mtf_mask=row['mtf']['known_mask'],structure_mask=row.get('structure_known_mask',0),volume_known=row['relative_volume'] is not None,
                            target_first=trade['exit_reason'].startswith('TAKE_PROFIT'),net_pnl=trade['realized_pnl'],exit_scope=scope,protect=protect)
                        banks[(protect,family,side,scope)].append(event);stats['completed_labels']+=1
                        if stats['completed_labels']>frozen['max_labels']:raise ValueError('LABEL_BUDGET_EXCEEDED')
    for v in banks.values():v.sort(key=lambda e:(e['resolved_at'],e['timestamp']))
    return dict(banks),dict(stats)


def build_streams(prepared,banks,normalizer,h):
    streams=[];audit=Counter();examples=[]
    for part,rows in prepared:
        ds=[]
        for i,(bar,row) in enumerate(zip(part,rows)):
            side=None;chosen=h['family'];result=None
            if i>=1000 and i%16==0 and row is not None:
                result=route(bar,row,banks,normalizer,h['protect'],h['mode'],h['family'])
                audit[result['reason']]+=1
                if result['strategy']!='WAIT':side=result['direction']
                if len(examples)<8 and row['timestamp']>=CALIBRATION_END:
                    examples.append(dict(timestamp=row['timestamp'],regime=row['regime'],decision=result))
            ds.append(decision(bar,row,chosen,side,h['protect']))
        streams.append((ds,None))
    return streams,dict(audit),examples


def portfolio(prepared,streams,start,end,baseline,deadline):
    parts=[p for p,r in prepared];regimes=[[r['regime'] if r else 'UNKNOWN' for r in rows] for p,rows in prepared]
    result=period_job(parts,streams,regimes,start,end,baseline,deadline)
    if result['metrics']['trades']>=20 and float(result['metrics']['net_profit'])>0 and result['full_period_execution_valid']:
        result['bootstrap']=blocked_bootstrap(result['equity_curve'],reps=19999)
    else:result['bootstrap']=dict(status='NOT_APPLICABLE',p_value=None)
    return result


def classify(base,stress,frozen,validation=False):
    m=base['metrics'];reasons=[]
    if not base['full_period_execution_valid']:return 'REJECTED',['UNRESOLVED_GAP_OR_BALANCE_HALT']
    if m['trades']==0:return 'INSUFFICIENT_EVIDENCE',['NO_TRADES']
    if float(m['net_profit'])<=0:return 'REJECTED',['NET_NONPOSITIVE']
    minimum=60 if validation else 100
    if m['trades']<minimum:reasons.append('TOO_FEW_TRADES')
    if float(m['max_drawdown_pct'])>25:reasons.append('DRAWDOWN')
    if float(stress['metrics']['net_profit'])<=0 or not stress['full_period_execution_valid']:reasons.append('STRESS_FAIL')
    years={'2023','2024'} if validation else {'2020','2021','2022'}
    totals={x['year']:float(x['net_pnl']) for x in base['yearly']}
    if any(totals.get(y,0)<=0 for y in years):reasons.append('YEAR_UNSTABLE')
    p=base['bootstrap'].get('p_value');sel=frozen['selection']
    if p is None or p>sel['alpha']/sel['known_comparison_family_minimum']:reasons.append('MULTIPLE_SEARCH_UNCERTAINTY')
    if base['bootstrap'].get('lower95_mean_daily',-1)<=0:reasons.append('BLOCK_CI_NONPOSITIVE')
    return ('INSUFFICIENT_EVIDENCE',reasons) if reasons else ('RESEARCH_CANDIDATE',[])
