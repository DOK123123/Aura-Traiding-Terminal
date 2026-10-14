"""Offline bounded pattern discovery. No runtime integration or account access."""
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal as D
import gzip
import hashlib
import json
from pathlib import Path
import random
from statistics import mean

from app.intelligence.patterns import REGISTRY, detect, features
from app.lab.execution import simulate, metrics
from app.lab.models import Baseline, canonical, digest, money, text
from app.lab.strategies import Decision, decisions
from scripts.lab3_strategies import higher
from scripts.research_inverse import economy
from scripts.run_lab3 import stamp

CONTEXTS = ('NONE', 'TREND', 'VOL_HIGH', 'VOL_LOW', 'VOLUME', 'SR', 'INDICATORS', 'TREND_VOLUME')
PERIODS = {'development': ('2020-01-01', '2023-01-01'), 'validation': ('2023-01-01', '2025-01-01'), 'holdout_reused': ('2025-01-01', '2026-01-01')}
STEPS = {'15m':900, '1h':3600, '4h':14400}

def source_hash():
    paths = ['scripts/pattern_research.py','scripts/run_pattern_research.py',
             'scripts/lab3_history.py','app/intelligence/patterns.py',
             'app/lab/execution.py','app/lab/indicators.py','app/lab/models.py',
             'app/lab/strategies.py','app/lab/series.py','app/lab/local_csv.py','scripts/lab3_strategies.py',
             'scripts/research_inverse.py','scripts/run_lab3.py']
    root = Path(__file__).resolve().parents[1]
    return digest({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths})


def protocol():
    return dict(version='PATTERN_RESEARCH_2.0', source_hash=source_hash(), seed=20261013,
        catalogue=[dict(id=p.id,version=p.version,status=p.status,category=p.category) for p in REGISTRY.values()],
        patterns=[p.id for p in REGISTRY.values() if p.status != 'PLANNED'],
        contexts=list(CONTEXTS), exits=['PCT_2_4','ATR_2_4'], timeframes=list(STEPS),
        search_budget=810, baseline=Baseline().data(), periods=PERIODS,
        warmup=250, rolling_detector_window=250, time_exit='Next open after a closed candle ending at UTC 4-day epoch boundary; maximum 4 days.',
        neutral_policy='Non-directional detector requires causal EMA20/50 direction; no direction means no entry. This is an explicit directional hypothesis, not a neutral-pattern forecast.',
        selection=dict(min_trades=100,min_validation_trades=60, max_drawdown_pct=25,
            positive_net=True, positive_every_calendar_year=True, positive_stress_net=True,
            familywise_alpha=.05,bootstrap_replicates=19999,block_days=14,max_finalists=10),
        multiplicity='Bonferroni over entire 810-hypothesis search, not only profitable survivors. 19999 replicates yield minimum empirical p=1/20000, resolving .05/810. Block stationarity assumptions remain limitations, not a profitability proof.',
        holdout_status='2025 ALREADY OBSERVED in six-year report: repeated locked confirmation, NOT untouched blind holdout. HOLDOUT_PASSED/PAPER_ONLY_ELIGIBLE disabled.',
        gap_policy='Reset 250-bar warmup after every gap. Unresolved positions censored with known entry fee restored ONLY in conditional closed-trade ledger; any censored period fails selection. No execution across a gap.',
        ranking='Net profit descending among fully observed runs; sample size, block uncertainty, drawdown and multiplicity gates applied separately. No ranking implies profitability.')


def hypotheses(frozen):
    return [dict(id=f'{tf}:{pat}:{ctx}:{exit}',timeframe=tf,pattern=pat,context=ctx,exit=exit)
            for tf in frozen['timeframes'] for pat in frozen['patterns'] for ctx in frozen['contexts'] for exit in frozen['exits'] if exit=='PCT_2_4' or ctx=='NONE']


from app.lab.series import split_parts


def prepare(bars,tf):
    """Unchanged production detectors on exactly observed rolling prefixes."""
    step=STEPS[tf];parts=split_parts(bars if tf=='15m' else higher(bars,step),step)
    output=[];counts=Counter()
    for part in parts:
        rows=[None]*len(part)
        for i in range(249,len(part)):
            prefix=part[i-249:i+1];ctx=features(prefix)
            found=detect(prefix,timeframe=tf,cutoff=part[i].time+step)
            low=min(b.low for b in prefix[-51:-1]);high=max(b.high for b in prefix[-51:-1])
            row=dict(patterns={p['pattern_id']:p['direction'] for p in found},
                direction=ctx['direction'],regime=ctx['regime'],adx=ctx['adx'],rsi=ctx['rsi'],
                atr=ctx['atr'],volume=ctx['relative_volume'],vol=ctx['volatility_ratio'],
                near_low=float(part[i].close-low)/ctx['atr'] <= 1,
                near_high=float(high-part[i].close)/ctx['atr'] <= 1)
            rows[i]=row
            for p in found:counts[(str(part[i].time//1),p['pattern_id'])]+=1
        output.append((part,rows))
    return output


def side_for(row,h):
    if row is None or h['pattern'] not in row['patterns']:return None
    side=row['patterns'][h['pattern']] or row['direction']
    if side not in ('LONG','SHORT'):return None
    trend=(row['adx']>=25 and side==row['direction'])
    volume=row['volume'] is not None and row['volume']>=1.5
    ctx=h['context']
    passes={'NONE':True,'TREND':trend,'VOL_HIGH':row['vol']>=1.5,
            'VOL_LOW':row['vol']<=.65,'VOLUME':volume,
            'SR':row['near_low'] if side=='LONG' else row['near_high'],
            'INDICATORS':trend and (50<=row['rsi']<=70 if side=='LONG' else 30<=row['rsi']<=50),
            'TREND_VOLUME':trend and volume}
    return side if passes[ctx] else None


def streams(part,rows,h,step):
    result=[]
    for b,row in zip(part,rows):
        side=side_for(row,h)
        stop=b.close*D('.02') if h['exit']=='PCT_2_4' else D(str(row['atr']))*2 if row else None
        target=None if stop is None else stop*2
        expire=(b.time+step)%(4*86400)==0
        result.append(Decision(side,stop,target,expire,expire,h['id']))
    return result


def blocked_bootstrap(curve,seed=20261013,reps=19999,days=14):
    """Non-iid circular moving-block bootstrap of daily portfolio PnL."""
    daily={p['time']//86400:D(p['equity']) for p in curve}
    keys=sorted(daily)
    missing=sum(b-a-1 for a,b in zip(keys,keys[1:]))
    if missing:
        # Missing marks may represent unknown exposure or omitted cash periods.
        # Neither can be inferred from endpoints alone; never compress time.
        return dict(status='INCOMPLETE_CALENDAR',p_value=None,missing_days=missing,
            block_days=days,notes='Daily observations are not contiguous; portfolio inference is undefined. No interpolation or blocks across missing dates.')
    returns=[float(daily[b]-daily[a]) for a,b in zip(keys,keys[1:])]
    if len(returns)<days*4:return dict(status='INSUFFICIENT_DAYS',p_value=None,lower95_mean_daily=None)
    n=len(returns);rng=random.Random(seed);observed=mean(returns);draws=[]
    blocks=[sum(returns[(i+j)%n] for j in range(days)) for i in range(n)]
    remainder=n%days
    tails=[sum(returns[(i+j)%n] for j in range(remainder)) for i in range(n)]
    for _ in range(reps):
        total=sum(blocks[rng.randrange(n)] for j in range(n//days))
        if remainder:total+=tails[rng.randrange(n)]
        draws.append(total/n)
    null_tail=sum(x-observed>=observed for x in draws)
    return dict(status='DESCRIPTIVE_DEPENDENT_BLOCKS',days=n,block_days=days,replicates=reps,
        p_value=(1+null_tail)/(reps+1),lower95_mean_daily=sorted(draws)[int(.025*reps)],
        observed_mean_daily=observed,notes='Fixed 14-day circular blocks; approximate stationarity, overlapping exposures retained; censored ledgers invalid for inference. No iid trade bootstrap.')


def grouped(trades,key):
    out=defaultdict(list)
    for t in trades:out[key(t)].append(t)
    return {k:economy(v) for k,v in sorted(out.items())}


def period_run(prepared,h,start,end,baseline,step):
    """Independent period balance; unknown gap fills are never manufactured."""
    balance=D(baseline.starting_balance);trades=[];curve=[];unknown=[];rejections=Counter();detected=signals=used=0
    for part,rows in prepared:
        times=[b.time for b in part];left=bisect_left(times,start);right=bisect_left(times,end)
        begin=max(left,249)
        if begin>=right:continue
        if balance<D('.01'):break
        detected+=sum(row is not None and h['pattern'] in row['patterns'] for row in rows[begin:right])
        count=sum(side_for(row,h) is not None for row in rows[begin:right]);signals+=count;used+=right-begin
        if not count:
            # This observed, continuous segment holds only cash. Retain UTC
            # daily closes from actual bars so zero-PnL days enter inference.
            marks=[part[begin].time]
            marks.extend(b.time+step for b in part[begin:right] if (b.time+step)%86400==0)
            if marks[-1]!=part[right-1].time+step:marks.append(part[right-1].time+step)
            curve.extend(dict(time=t,balance=text(balance),equity=text(balance)) for t in marks);continue
        ds=streams(part,rows,h,step)
        # No prior-period pending order; validation starts with its own cash ledger.
        gap_end=right==len(part) and part[-1].time+step<end
        run=simulate(part,ds,begin,right,step,replace(baseline,starting_balance=text(balance)),close_at_end=not gap_end)
        p=run.get('open_position')
        if p is not None:
            unknown.append(dict(position=p,last_observed_close=part[right-1].time+step,reason='UNRESOLVED_GAP'))
            restored=money(D(run['equity_curve'][-1]['balance'])+D(p['entry_fee']))
            for point in run['equity_curve']:
                if point['time']>=p['entry_time']+step:point.update(balance=text(restored),equity=text(restored))
        balance=D(run['equity_curve'][-1]['balance'])
        for t in run['trades']:
            row=rows[bisect_left(times,t['signal_time']-step)]
            t['regime']=row['regime']
            if D(t['risk_usdt'])>D(t['risk_budget_usdt']) or D(t['notional'])>D(baseline.max_notional):raise ValueError('RISK_ACCOUNTING')
            if t['entry_time']<t['signal_time']:raise ValueError('LOOK_AHEAD')
            if abs(D(t['gross_price_pnl'])-D(t['fees'])-D(t['realized_pnl']))>D('.00000002'):raise ValueError('ACCOUNTING')
        trades.extend(run['trades']);curve.extend(run['equity_curve']);rejections.update(run['rejections'])
    if not curve:curve=[dict(time=start,balance=baseline.starting_balance,equity=baseline.starting_balance),dict(time=end,balance=baseline.starting_balance,equity=baseline.starting_balance)]
    value=metrics(trades,curve,baseline)
    result=dict(hypothesis=h,metrics=value,economy=economy(trades),detections=detected,signals=signals,processed_candles=used,
        rejection_counts=dict(rejections),censored_positions=unknown,full_period_execution_valid=not unknown,
        by_year=grouped(trades,lambda t:__import__('datetime').datetime.fromtimestamp(t['exit_time'],__import__('datetime').timezone.utc).strftime('%Y')),
        by_month=grouped(trades,lambda t:__import__('datetime').datetime.fromtimestamp(t['exit_time'],__import__('datetime').timezone.utc).strftime('%Y-%m')),
        by_direction=grouped(trades,lambda t:t['direction']),by_regime=grouped(trades,lambda t:t['regime']),
        bootstrap=blocked_bootstrap(curve) if value['trades']>=20 and D(value['net_profit'])>0 and not unknown else dict(status='NOT_APPLICABLE',p_value=None),
        trades=trades,equity_curve=curve)
    return result


def classify(result,stress,frozen,validation=False):
    m=result['metrics'];reasons=[]
    if D(m['net_profit'])<=0:reasons.append('NET_NONPOSITIVE')
    if not result['full_period_execution_valid']:reasons.append('CENSORED_GAP')
    if reasons:return 'REJECTED',reasons
    sel=frozen['selection'];minimum=sel['min_validation_trades'] if validation else sel['min_trades']
    if m['trades']<minimum:reasons.append('TOO_FEW_TRADES')
    if D(m['max_drawdown_pct'])>D(sel['max_drawdown_pct']):reasons.append('DRAWDOWN')
    required_years=('2023','2024') if validation else ('2020','2021','2022')
    if any(y not in result['by_year'] or D(result['by_year'][y]['net_pnl'])<=0 for y in required_years):reasons.append('YEAR_UNSTABLE')
    if D(stress['metrics']['net_profit'])<=0:reasons.append('STRESS_NEGATIVE')
    if not stress['full_period_execution_valid']:reasons.append('STRESS_CENSORED')
    boot=result['bootstrap'];p=boot.get('p_value')
    if p is None or p>.05/frozen['search_budget']:reasons.append('MULTIPLE_COMPARISON_UNCERTAINTY')
    if boot.get('lower95_mean_daily',-1)<=0:reasons.append('BLOCK_CI_NONPOSITIVE')
    return ('INSUFFICIENT_EVIDENCE',reasons) if reasons else ('RESEARCH_CANDIDATE',[])


def atomic_json(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(canonical(value));tmp.replace(path)


def lock_finalists(path,frozen,finalists):
    lock=dict(protocol_sha256=digest(frozen),finalists=finalists,holdout_status=frozen['holdout_status'])
    if Path(path).exists():
        if json.loads(Path(path).read_text())!=lock:raise ValueError('HOLDOUT_LOCK_MISMATCH')
    else:atomic_json(path,lock)
    return digest(lock)


def write_artifact(path,value):
    raw=canonical(value)
    with Path(path).open('wb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0,filename='') as z:z.write(raw)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
