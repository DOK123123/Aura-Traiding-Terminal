"""Independent Fraction/Decimal audit of completed research artifacts, no replay writes."""
import argparse
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import json
import hashlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.run_pattern_research import artifact_read
from scripts.pattern_research import atomic_json


def check(run,fee_bps,slippage_bps,prices,step):
    tick=D('.00000001');rate=D(fee_bps)/10000;slip=Fraction(slippage_bps)/10000
    def rounded(x):return x.quantize(tick,rounding=ROUND_HALF_EVEN)
    def fee(p,q):return (p*q*rate).quantize(tick,rounding=ROUND_CEILING)
    total=D(0);previous=None;events={};intervals=[]
    with localcontext() as ctx:
        ctx.prec=64
        for t in run['trades']:
            s=1 if t['direction']=='LONG' else -1
            e,x,er,xr,q=[D(t[k]) for k in ('entry_price','exit_price','entry_raw_price','exit_raw_price','size')]
            if Fraction(e)!=Fraction(er)*(1+s*slip) or Fraction(x)!=Fraction(xr)*(1-s*slip):raise ValueError('ADVERSE_FILL')
            ef,xf=fee(e,q),fee(x,q)
            gross=rounded(s*(x-e)*q);net=rounded(gross-ef-xf)
            if net!=D(t['realized_pnl']) or ef!=D(t['entry_fee']) or xf!=D(t['exit_fee']):raise ValueError('FEES_PNL')
            if t['entry_time']!=t['signal_time'] or D(prices[t['entry_time']]['open'])!=er:raise ValueError('NEXT_OPEN')
            if previous is not None and t['entry_time']<previous:raise ValueError('OVERLAP')
            previous=t['exit_time']
            stop,target=D(t['stop_loss']),D(t['take_profit'])
            if not (stop<e<target if s==1 else target<e<stop):raise ValueError('STOP_SIDE')
            sf=stop*(1-D(s)*D(slippage_bps)/10000)
            risk=(abs(e-sf)*q).quantize(tick,rounding=ROUND_CEILING)+ef+fee(sf,q)
            if risk!=D(t['risk_usdt']) or risk>D(t['risk_budget_usdt']) or D(t['notional'])>2000:raise ValueError('PLANNED_RISK')
            reason=t['exit_reason'];opening=reason in ('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE','STRATEGY_EXIT_NEXT_OPEN')
            candle=prices[t['exit_time'] if opening else t['exit_time']-step]
            if reason.startswith('STOP'):
                if not (D(candle['low'])<=stop if s==1 else D(candle['high'])>=stop):raise ValueError('STOP_TOUCH')
                raw=D(candle['open']) if opening else stop
                if 'AMBIGUOUS' in reason and not (D(candle['high'])>=target if s==1 else D(candle['low'])<=target):raise ValueError('AMBIGUITY')
            elif reason.startswith('TAKE_PROFIT'):
                if not (D(candle['high'])>=target if s==1 else D(candle['low'])<=target):raise ValueError('TP_TOUCH')
                raw=target
            elif reason=='STRATEGY_EXIT_NEXT_OPEN':raw=D(candle['open'])
            elif reason=='SEGMENT_END_CLOSE':raw=D(candle['close'])
            else:raise ValueError('UNKNOWN_EXIT')
            if raw!=xr:raise ValueError('RAW_EXECUTION_PRICE')
            total+=net
            entry_point=t['entry_time']+step;exit_point=t['exit_time']+(step if opening else 0)
            events[entry_point]=events.get(entry_point,D(0))-ef
            events[exit_point]=events.get(exit_point,D(0))+gross-xf
            if entry_point<exit_point:intervals.append((entry_point,exit_point,t))
        if D(run['metrics']['net_profit'])!=total or D(run['metrics']['final_balance'])!=10000+total:raise ValueError('FINAL_LEDGER')
        peak=D(10000);dd=D(0);cash=D(10000);j=k=0;times=sorted(events)
        for p in run['equity_curve']:
            stamp=p['time']
            while j<len(times) and times[j]<=stamp:cash+=events[times[j]];j+=1
            while k<len(intervals) and intervals[k][1]<=stamp:k+=1
            expected=cash
            if k<len(intervals) and intervals[k][0]<=stamp<intervals[k][1]:
                t=intervals[k][2];sign=1 if t['direction']=='LONG' else -1
                price=D(prices[stamp-step]['close'])*(1-D(sign)*D(slippage_bps)/10000)
                q=D(t['size']);expected=rounded(cash+rounded(sign*(price-D(t['entry_price']))*q)-fee(price,q))
            if cash!=D(p['balance']) or expected!=D(p['equity']):raise ValueError('EQUITY_ACCOUNTING')
            equity=expected;peak=max(peak,equity);dd=max(dd,(peak-equity)/peak*100)
        if rounded(dd)!=D(run['metrics']['max_drawdown_pct']):raise ValueError('DRAWDOWN')
    return len(run['trades'])


def audit(output):
    state=json.loads((output/'checkpoint.json').read_text());prices={};checked=trades=0
    cp_path=output/'audit.checkpoint.json'
    key=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+':'+state['key']
    cp=json.loads(cp_path.read_text()) if cp_path.exists() else dict(key=key,jobs={})
    if cp['key']!=key:raise ValueError('AUDIT_CHECKPOINT_CHANGED')
    for key,record in state['jobs'].items():
        if key in cp['jobs']:
            old=cp['jobs'][key]
            if old['sha256']!=record['sha256']:raise ValueError('AUDITED_ARTIFACT_CHANGED')
            if hashlib.sha256((output/record['artifact']).read_bytes()).hexdigest()!=old['sha256']:raise ValueError('AUDIT_ARTIFACT_CORRUPT')
            checked+=1;trades+=old['trades'];continue
        tf=record['summary']['hypothesis']['timeframe']
        if tf not in prices:
            cm=json.loads((output/(tf+'.cache.json')).read_text());cache=artifact_read(output/(tf+'.cache.gz'),cm['sha256'])
            prices.clear();prices[tf]={b['time']:b for p in cache for b in p['bars']}
        full=artifact_read(output/record['artifact'],record['sha256']);stress=key.endswith('|stress')
        count=check(full,'20' if stress else '10','10' if stress else '5',prices[tf],{'15m':900,'1h':3600,'4h':14400}[tf]);checked+=1;trades+=count
        cp['jobs'][key]=dict(sha256=record['sha256'],trades=count)
        if checked%50==0:atomic_json(cp_path,cp);print('Audited',checked,flush=True)
    atomic_json(cp_path,cp)
    value=dict(jobs_checked=checked,closed_trades_checked=trades,errors=0,method='Independent exact Fraction adverse fills, Decimal ceil fees, next-open/touch/side/risk/overlap checks and independently reconstructed cash/liquidation equity/drawdown. Conditional gap ledgers checked as conditional, not asserted investable.')
    atomic_json(output/'independent.audit.json',value);return value

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(audit(a.output))
