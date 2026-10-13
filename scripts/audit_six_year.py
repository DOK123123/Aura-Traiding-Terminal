"""Independent archive annotations, journal accounting and checkpoint verification."""
import argparse
from collections import Counter
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN,ROUND_CEILING
import gzip,hashlib,json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.lab3_history import load_years


def quality_audit(bars,quality):
    expected=[]
    for m in quality['months']:
        anomalies=[dict(type='gap_or_duplicate',previous=g['previous']*1000,current=g['current']*1000,delta_ms=(g['current']-g['previous'])*1000) for g in m['raw_gaps']]
        if m['raw_candles']!=m['expected']:
            last=max([b.time for b in bars if m['start']<=b.time<m['start']+m['expected']*900]+[q['time'] for q in m['quarantined']])
            anomalies.append(dict(type='incomplete_month',actual_rows=m['raw_candles'],expected_rows=m['expected'],last=last*1000))
        if anomalies:expected.append(dict(name=m['name'],sha256=m['zip_sha256'],rows=m['raw_candles'],anomalies=anomalies))
    if quality['supplied_quality_report']['files_with_anomalies']!=expected:raise ValueError('Independent annotation geometry mismatch')
    return dict(raw_count=quality['raw_count'],raw_missing=quality['raw_missing_candles'],raw_gap_intervals=sum(len(m['raw_gaps']) for m in quality['months']),
        incomplete_months=len(expected),declared_annotations=quality['quality_annotations'],valid_count=len(bars),quarantined=sum(len(m['quarantined']) for m in quality['months']),effective_gaps=len(quality['gaps']))


def audit(archive,report_path,work):
    report=json.loads(report_path.read_bytes());bars,quality=load_years(archive,allow_gaps=True)
    qa=quality_audit(bars,quality)
    if report['dataset_quality']!=quality:raise ValueError('Archive quality report mismatch')
    count=0;tick=D('.00000001');observed={b.time:b for b in bars}
    with localcontext() as ctx:
        ctx.prec=64
        for row in report['results']:
            raw=(work/row['ledger_filename']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['ledger_gzip_sha256']:raise ValueError('Journal hash mismatch')
            data=gzip.decompress(raw)
            if hashlib.sha256(data).hexdigest()!=row['ledger_uncompressed_sha256']:raise ValueError('Journal content mismatch')
            trades=json.loads(data);net=D(0);fees=D(0);slip=D(row['baseline']['slippage_bps'])/10000;rate=D(row['baseline']['fee_bps'])/10000
            seen=set();previous_exit=None
            for t in trades:
                key=(t['signal_time'],t['direction'])
                if key in seen:raise ValueError('Duplicate execution')
                seen.add(key)
                if t['entry_time']!=t['signal_time'] or t['entry_time']-900 not in observed:raise ValueError('Causal entry mismatch')
                if previous_exit is not None and t['entry_time']<previous_exit:raise ValueError('Concurrent positions')
                previous_exit=t['exit_time']
                sign=1 if t['direction']=='LONG' else -1
                ep,xp,er,xr,q=[D(t[k]) for k in ('entry_price','exit_price','entry_raw_price','exit_raw_price','size')]
                if ep!=er*(1+sign*slip) or xp!=xr*(1-sign*slip):raise ValueError('Fill mismatch')
                ef=(ep*q*rate).quantize(tick,rounding=ROUND_CEILING);xf=(xp*q*rate).quantize(tick,rounding=ROUND_CEILING)
                pnl=(sign*(xp-ep)*q).quantize(tick,rounding=ROUND_HALF_EVEN)-ef-xf
                if pnl!=D(t['realized_pnl']) or ef!=D(t['entry_fee']) or xf!=D(t['exit_fee']):raise ValueError('Independent fee/PnL mismatch')
                if D(t['risk_usdt'])>D(t['risk_budget_usdt']) or D(t['notional'])>2000:raise ValueError('Risk limit')
                if any(t['entry_time']<g['end_exclusive'] and t['exit_time']>g['start'] for g in quality['gaps']):raise ValueError('Trade crosses missing data')
                net+=pnl;fees+=ef+xf;count+=1
            if len(trades)!=row['metrics']['trades'] or net!=D(row['metrics']['net_profit']) or fees!=D(row['metrics']['total_fees']):raise ValueError('Metric ledger sum')
            if D(row['metrics']['final_balance'])!=10000+net:raise ValueError('Conditional balance')
            if sum((D(m['cashflow_pnl']) for m in row['monthly']),D(0))!=net:raise ValueError('Monthly cashflow sum')
    return dict(status='PASS',journals=len(report['results']),closed_trades=count,quality=qa)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('report',type=Path);p.add_argument('work',type=Path);a=p.parse_args()
    print(audit(a.archive,a.report,a.work))
