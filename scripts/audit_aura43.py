"""Independent offline Decimal accounting/coverage audit of the frozen study."""
import argparse
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN,ROUND_CEILING
import gzip
import json
import math
from pathlib import Path
import statistics
from app.lab.local_csv import load_binance_csv
from app.lab.models import digest


def audit(path: Path,csv: Path) -> dict:
    with gzip.open(path,'rb') as f:raw=f.read(24*1024*1024+1)
    if len(raw)>24*1024*1024:raise ValueError('REPORT_LIMIT')
    report=json.loads(raw);checksum=report.pop('checksum')
    if checksum!=digest(report):raise ValueError('CHECKSUM')
    bars,source=load_binance_csv(csv)
    if source['sha256']!=report['source']['sha256']:raise ValueError('DATASET_HASH')
    assert report['closed_candles_processed']==8640 and report['end_exclusive']-report['start']==90*86400
    assert report['split_at']-report['start']==60*86400
    assert report['end_exclusive']-report['split_at']==30*86400
    assert report['policy']['risk_pct']=='0.5' and report['policy']['daily_loss_pct']=='2'
    assert report['policy']['drawdown_pct']=='10' and report['policy']['max_positions']==1
    count=0
    def rounded(n,up=False):return n.quantize(D('.00000001'),rounding=ROUND_CEILING if up else ROUND_HALF_EVEN)
    with localcontext() as ctx:
        ctx.prec=64
        for run in report['runs']:
            pnl=D(0);fees=D(0);profit=D(0);loss=D(0)
            prior_exit=run['start']
            for t in run['trades']:
                assert run['start']<=t['signal_at']==t['entry_time']<run['end_exclusive']
                assert t['entry_time']>=prior_exit and t['entry_time']<=t['exit_time']<=run['end_exclusive']
                prior_exit=t['exit_time'];sign=1 if t['direction']=='LONG' else -1;q=D(t['size'])
                entry=D(t['entry_raw_price'])*(1+sign*D('.0005'))
                exit=D(t['exit_raw_price'])*(1-sign*D('.0005'))
                ef=rounded(entry*q*D('.001'),True);xf=rounded(exit*q*D('.001'),True)
                net=rounded(rounded(sign*(exit-entry)*q)-ef-xf)
                assert D(t['entry_price'])==entry and D(t['exit_price'])==exit
                assert D(t['entry_fee'])==ef and D(t['exit_fee'])==xf and D(t['realized_pnl'])==net
                assert D(t['fees'])==ef+xf and D(t['risk_usdt'])<=D(t['risk_budget_usdt'])
                assert D(t['notional'])<=2000
                pnl+=net;fees+=ef+xf;profit+=max(net,D(0));loss+=max(-net,D(0));count+=1
            opened=run['open_position'];entry_fee=D(opened['entry_fee']) if opened else D(0)
            balance=10000+pnl-entry_fee;metrics=run['metrics']
            assert D(metrics['final_balance'])==balance
            assert D(metrics['realized_net_pnl'])==pnl and D(metrics['fees'])==fees+entry_fee
            assert metrics['trades']==len(run['trades'])
            wins=[D(t['realized_pnl']) for t in run['trades'] if D(t['realized_pnl'])>0]
            losses=[-D(t['realized_pnl']) for t in run['trades'] if D(t['realized_pnl'])<0]
            if run['trades']:assert D(metrics['win_rate'])==rounded(D(len(wins))/len(run['trades'])*100)
            if wins:assert D(metrics['average_win'])==rounded(sum(wins)/len(wins))
            if losses:assert D(metrics['average_loss'])==rounded(sum(losses)/len(losses))
            if opened:
                last=next(b for b in reversed(bars) if b.time+900==run['end_exclusive'])
                sign=1 if opened['direction']=='LONG' else -1;q=D(opened['size'])
                px=last.close*(1-sign*D('.0005'))
                equity=rounded(balance+rounded(sign*(px-D(opened['entry_price']))*q)-rounded(px*q*D('.001'),True))
            else:equity=balance
            assert D(metrics['final_equity'])==equity and D(metrics['net_profit'])==equity-10000
            assert D(metrics['return_pct'])==rounded((equity-10000)/100)
            assert (metrics['profit_factor'] is None and loss==0) or D(metrics['profit_factor'])==rounded(profit/loss)
            if run['trades']:assert D(metrics['expectancy'])==rounded(pnl/len(run['trades']))
            peak=D(10000);lower_bound=D(0)
            for point in run['equity_curve']:
                eq=D(point['equity']);peak=max(peak,eq);lower_bound=max(lower_bound,(peak-eq)/peak*100)
            assert D(metrics['max_drawdown_pct'])+D('.00000001')>=lower_bound
            daily=run['daily_equity'];returns=[float(D(b['equity'])/D(a['equity'])-1) for a,b in zip(daily,daily[1:]) if b['time']-a['time']==86400 and D(a['equity'])>0]
            if len(run['trades'])<20 or len(returns)<30 or statistics.stdev(returns)==0:assert metrics['sharpe'] is None
            else:assert abs(metrics['sharpe']-statistics.mean(returns)/statistics.stdev(returns)*math.sqrt(365))<1e-12
    return dict(status='PASS',runs=len(report['runs']),trade_records_checked=count,dataset_sha256=source['sha256'],
        calendar_and_trade_boundaries_valid=True,fee_slippage_balance_pnl_oracle='INDEPENDENT_DECIMAL_64',
        production_access=False,proves_live_execution=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--csv',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not __debug__:raise RuntimeError('AUDIT_REQUIRES_ASSERTIONS')
    result=audit(a.report,a.csv);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
