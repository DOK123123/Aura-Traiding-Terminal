"""Reproducible common-calendar split. No native Aura semantics are substituted."""
from decimal import Decimal as D
from pathlib import Path
import hashlib
import time
import platform

from .models import Baseline,STEPS,VERSION,WARMUP_4H,LabError,digest,precise
from .data import restore,aggregate
from .strategies import decisions,PARAMETERS,AURA_INCOMPATIBILITY
from .execution import simulate


def software_hash():
    root=Path(__file__).parent
    return hashlib.sha256(platform.python_version().encode()+b''.join((root/name).read_bytes() for name in ('models.py','data.py','indicators.py','strategies.py','execution.py','experiment.py'))).hexdigest()


@precise
def execute(snapshot,config:Baseline,deadline=None):
    config.validate();base=restore(snapshot)
    start,end=snapshot['start'],snapshot['end']
    split_at=start+int(D(end-start)*D(config.development_pct)/100)//14400*14400
    if not start<split_at<end:raise LabError('INVALID_SPLIT')
    runs=[];coverage={}
    for timeframe,step in STEPS.items():
        if deadline is not None and time.monotonic()>deadline:raise LabError('COMPUTE_TIMEOUT')
        bars=aggregate(base,step,end)
        begin=(start-bars[0].time)//step;split=(split_at-bars[0].time)//step
        coverage[timeframe]=dict(start=start,end_exclusive=end,candles=len(bars)-begin,warmup_bars=begin,
                                 development_candles=split-begin,validation_candles=len(bars)-split)
        for name in PARAMETERS:
            signal=decisions(bars,name)
            for label,a,b in (('development',begin,split),('validation',split,len(bars))):
                run=simulate(bars,signal,a,b,step,config,deadline)
                run.update(strategy=name,timeframe=timeframe,split=label,parameters=dict(PARAMETERS[name]),starting_balance=config.starting_balance)
                runs.append(run)
        for label in ('development','validation'):
            runs.append(dict(strategy='AURA_EXISTING',timeframe=timeframe,split=label,status='INCOMPATIBLE',
                             reason=AURA_INCOMPATIBILITY,metrics=None,trades=[],equity_curve=[],parameters='Original Aura unchanged; see existing Historical Pattern backtest.'))
    # No development result selects a parameter set; rank validation only after frozen runs.
    rankings={}
    for timeframe in STEPS:
        compatible=[r for r in runs if r['timeframe']==timeframe and r['split']=='validation' and r['status']=='OK']
        ordered=sorted(compatible,key=lambda r:(-D(r['metrics']['return_pct']),D(r['metrics']['max_drawdown_pct']),r['strategy']))
        eligible=[r for r in ordered if r['metrics']['trades']>=config.min_trades]
        rankings[timeframe]=dict(numerical_order=[r['strategy'] for r in ordered],
                                 best_numerical=ordered[0]['strategy'] if ordered else None,
                                 qualified_order=[r['strategy'] for r in eligible],
                                 criterion='Validation return descending, max drawdown ascending tie-break, strategy name deterministic final tie-break. Only >=20 trades eligible; no profit/safety/production claim.')
    return dict(version=VERSION,runtime_python=platform.python_version(),software_hash=software_hash(),dataset_id=digest(snapshot),config=config.data(),
                parameter_sets=PARAMETERS,requested_development_pct=config.development_pct,
                actual_development_pct=str(D(split_at-start)/D(end-start)*100),split_at=split_at,
                coverage=coverage,runs=runs,rankings=rankings,symbol='BTCUSDT',source=snapshot['source'],
                dataset_start=start,dataset_end_exclusive=end,base_count=len(base),history_truncated=False,
                aura_comparison='INCOMPATIBLE',aura_reason=AURA_INCOMPATIBILITY,
                safety={'research_only':True,'activation_available':False,'real_money_execution':'DISABLED'},
                limitations=['Aura is not ranked: incompatible execution semantics.',
                            'SHORT is a virtual directional exposure with 1x collateral, not Spot borrowing.',
                            'Fee/slippage are model assumptions, not exchange fee facts.',
                            'Drawdown is sampled liquidation equity; no tick/intrabar price path is known.',
                            'A single chronological holdout and descriptive ranking do not establish robustness.'])


def summary(report):
    result={k:v for k,v in report.items() if k!='runs'}
    result['runs']=[{k:v for k,v in row.items() if k not in ('trades','equity_curve')} for row in report['runs']]
    return result
