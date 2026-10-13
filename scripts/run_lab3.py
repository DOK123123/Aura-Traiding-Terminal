"""Manual offline research runner; no automatic activation or account integrations."""
import argparse
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal as D,ROUND_CEILING
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.execution import simulate
from app.lab.models import Baseline,canonical,money,precise,text
from app.lab.local_csv import load_binance_csv
from scripts.lab3_history import load_years
from scripts.lab3_strategies import generate,labels
from scripts.offline_fixed_strategies import monthly,buy_hold
from scripts.research_inverse import invert,economy,verify_accounting
from scripts.research_candidates import registry
from scripts.run_research_cycle import load_protocol

PROTOCOL=ROOT/'docs/AURA_LAB3_PROTOCOL.json'
PROTOCOL_SHA='0c3ca8474de2ceb6ec9228bc32c8d34dace2b353e449942f4cc19fee48f39221'


def stamp(s):return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


@precise
def audit_trailing(run,bars,distances,baseline):
    """Independent trail chronology, costs, initial risk, equity and drawdown."""
    ix={b.time:i for i,b in enumerate(bars)};total=D(0);rate=D('.001');tick=D('.00000001')
    curve=run['equity_curve'];ci={p['time']:i for i,p in enumerate(curve)}
    events=[D(0)]*len(curve);marks=[None]*len(curve)
    for t in run['trades']:
        sign=1 if t['direction']=='LONG' else -1
        ep,xp,er,xr,q=[D(t[k]) for k in ('entry_price','exit_price','entry_raw_price','exit_raw_price','size')]
        assert F(ep)==F(er)*(1+sign*F(1,2000)) and F(xp)==F(xr)*(1-sign*F(1,2000))
        ef=(ep*q*rate).quantize(tick,rounding=ROUND_CEILING);xf=(xp*q*rate).quantize(tick,rounding=ROUND_CEILING)
        pnl=money(money(sign*(xp-ep)*q)-ef-xf)
        assert pnl==D(t['realized_pnl']) and ef==D(t['entry_fee']) and xf==D(t['exit_fee'])
        initial=D(t['initial_stop_loss']);planned=initial*(1-D(sign)*D('.0005'))
        risk=(abs(ep-planned)*q).quantize(tick,rounding=ROUND_CEILING)+ef+(planned*q*rate).quantize(tick,rounding=ROUND_CEILING)
        assert risk==D(t['risk_usdt']) and risk<=D(t['risk_budget_usdt']) and D(t['notional'])<=2000
        active=initial;extreme=ep;history=[]
        opening=t['exit_reason'] in ('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE','STRATEGY_EXIT_NEXT_OPEN')
        last=ix[t['exit_time'] if opening else t['exit_time']-900]
        for i in range(ix[t['entry_time']],last):
            b=bars[i];extreme=max(extreme,b.high) if sign==1 else min(extreme,b.low)
            candidate=min(extreme-distances[i],b.close) if sign==1 else max(extreme+distances[i],b.close)
            new=max(active,candidate) if sign==1 else min(active,candidate)
            if new!=active:history.append(dict(effective_from=b.time+900,stop_loss=text(new)));active=new
        assert history==t['stop_history'] and active==D(t['stop_loss'])
        b=bars[last];target=D(t['take_profit']);reason=t['exit_reason']
        if reason.startswith('STOP'):
            assert (b.low<=active if sign==1 else b.high>=active)
            assert xr==(b.open if opening else active)
        elif reason.startswith('TAKE_PROFIT'):
            assert xr==target and (b.high>=target if sign==1 else b.low<=target)
        else:assert xr==(b.open if opening else b.close)
        a=ci[t['entry_time']+900];z=ci[t['exit_time']+(900 if opening else 0)]
        events[a]-=ef;events[z]+=money(sign*(xp-ep)*q)-xf
        for index in range(a,z):assert marks[index] is None;marks[index]=(sign,ep,q)
        total+=pnl
    cash=D(10000);peak=cash;dd=D(0)
    for i,p in enumerate(curve):
        cash=money(cash+events[i]);eq=cash
        if marks[i] is not None:
            sign,ep,q=marks[i];price=bars[ix[p['time']-900]].close*(1-D(sign)*D('.0005'))
            eq=money(cash+money(sign*(price-ep)*q)-(price*q*rate).quantize(tick,rounding=ROUND_CEILING))
        assert cash==D(p['balance']) and eq==D(p['equity'])
        peak=max(peak,eq);dd=max(dd,(peak-eq)/peak*100)
    assert total==D(run['metrics']['net_profit']) and cash==10000+total and money(dd)==D(run['metrics']['max_drawdown_pct'])
    return len(run['trades'])


def run(source,archives=False,budget=240):
    raw=PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA:raise ValueError('Frozen Lab3 protocol mismatch')
    protocol=json.loads(raw)
    bars,meta=load_years(source) if archives else load_binance_csv(source)
    if archives:
        sections=[('development',1000,(stamp('2023-01-01')-bars[0].time)//900),
            ('validation',(stamp('2023-01-01')-bars[0].time)//900,(stamp('2025-01-01')-bars[0].time)//900),
            ('final_2025',(stamp('2025-01-01')-bars[0].time)//900,len(bars))]
    else:
        if meta['sha256']!='cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07':raise ValueError('Unexpected fallback CSV')
        sections=[('development',1000,(stamp('2026-08-01')-bars[0].time)//900),('retrospective_test',(stamp('2026-08-01')-bars[0].time)//900,len(bars))]
    deadline=time.monotonic()+budget;regimes=labels(bars,deadline);base=Baseline();results=[];audited=0
    for name in 'ABCDE':
        signals,trail=generate(bars,name,deadline)
        for section,a,b in sections:
            outcome=simulate(bars,signals,a,b,900,base,deadline,trailing_atr=trail)
            audited+=audit_trailing(outcome,bars,trail,base) if trail is not None else verify_accounting(outcome,bars,base)
            outcome.update(strategy=name,section=section,candles=b-a,
                signals=dict(Counter(d.direction or 'WAIT' for d in signals[a:b])),
                economics=economy(outcome['trades']),monthly=monthly(outcome,bars,a,b,base),
                regime_attribution={label:economy([t for t in outcome['trades'] if regimes[(t['signal_time']-900-bars[0].time)//900]==label]) for label in sorted(set(regimes[a:b]))},
                yearly=[dict(year=year,net_closed_pnl=text(sum((D(t['realized_pnl']) for t in outcome['trades'] if datetime.fromtimestamp(t['exit_time']-int(t['exit_reason'] not in ('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE','STRATEGY_EXIT_NEXT_OPEN')),timezone.utc).year==year),D(0)))) for year in sorted({datetime.fromtimestamp(x.time,timezone.utc).year for x in bars[a:b]})])
            curve=outcome['equity_curve'];outcome['equity_full_sha256']=hashlib.sha256(canonical(curve)).hexdigest()
            outcome['equity_curve']=[p for i,p in enumerate(curve) if i in (0,len(curve)-1) or p['time']%86400==0]
            results.append(outcome)
    controls=[]
    for section,a,b in sections:
        for cap in ('2000','10000'):
            value=buy_hold(bars,a,b,base,cap)
            controls.append(dict(section=section,strategy='BUY_HOLD_'+cap,metrics=value['metrics'],risk_equivalent=False,reason='No protective SL; passive exposure differs'))
    comparison=[]
    if not archives:
        previous=json.loads((ROOT/'docs/AURA_INVERSE_STRATEGY_RESEARCH.json').read_bytes());a,b=sections[-1][1:]
        for name,candidate in registry(load_protocol()).items():
            signals=candidate.generate(bars)
            for variant in ('ORIGINAL','I','II'):
                value=simulate(bars,invert(signals,variant),a,b,900,base,deadline)
                old=next(x for x in previous['results'] if x['strategy']==name and x['variant']==variant and x['section']=='test')
                if value['metrics']!=old['metrics'] or value['trades']!=old['trades']:raise ValueError('Existing execution regression')
                comparison.append(dict(strategy=name,variant=variant,section='retrospective_test',metrics=value['metrics'],exact_prior_match=True))
    paths=[Path(__file__),ROOT/'scripts/lab3_history.py',ROOT/'scripts/lab3_strategies.py',PROTOCOL,
        ROOT/'scripts/offline_fixed_strategies.py',ROOT/'scripts/research_inverse.py',ROOT/'scripts/research_candidates.py',ROOT/'scripts/run_research_cycle.py',ROOT/'app/indicators.py']+sorted((ROOT/'app/lab').glob('*.py'))
    return dict(status='COMPLETE',actual_backtest=True,multi_year_performed=archives,protocol=protocol,protocol_sha256=PROTOCOL_SHA,
        dataset=meta,results=results,buy_hold=controls,previous_comparison=comparison,independent_trades_audited=audited,
        previous_report_sha256=hashlib.sha256((ROOT/'docs/AURA_INVERSE_STRATEGY_RESEARCH.json').read_bytes()).hexdigest(),
        software_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        history_acquisition=dict(status='BLOCKED_NETWORK',error='ConnectError',archives_received=0),
        safety=dict(real_money='DISABLED',production_changes=False,auto_activation=False),
        limitations=['User CSV not independently authenticated','2026 periods repeatedly viewed, not blind OOS','Full15m equity audited; report daily/endpoints only','Multi-year path implemented and offline-tested, NOT run on real2020-2025 archives','Cost/slippage assumptions exclude funding/borrow/spread/liquidity','A trailing armed after close, clamps to close, cannot retroactively fill; fresh split ledgers and terminal liquidation','Development first1000 bars vs prior500: prior comparison only same August/September','Buy hold not risk-equivalent; no profitability proof'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--archives',action='store_true');p.add_argument('--output',required=True,type=Path);p.add_argument('--max-seconds',type=int,default=240);a=p.parse_args()
    if a.output.exists() or not 1<=a.max_seconds<=900:p.error('New output; bounded CPU budget required')
    report=run(a.source,a.archives,a.max_seconds)
    with a.output.open('xb') as f:f.write(canonical(report))
    for x in report['results']:print(x['section'],x['strategy'],x['metrics']['trades'],x['metrics']['net_profit'])
