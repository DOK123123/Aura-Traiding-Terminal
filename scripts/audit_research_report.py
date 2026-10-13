"""Independent rational/Decimal real-history report checks; no exchange access."""
import argparse
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN,ROUND_CEILING
from fractions import Fraction as F
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.run_research_cycle import run
from scripts.offline_fixed_strategies import dataset


def audit(csv_path,report_path):
    report=json.loads(report_path.read_bytes())
    if report['status']!='COMPLETE':raise ValueError('No completed actual result to audit')
    repeated=run(csv_path)
    if repeated!=report:raise ValueError('Deterministic complete report mismatch')
    bars,meta=dataset(csv_path);prices={b.time:b for b in bars}
    tick=D('.00000001')
    def money(v):return v.quantize(tick,rounding=ROUND_HALF_EVEN)
    def ceil_fee(price,qty):return (price*qty*D('.001')).quantize(tick,rounding=ROUND_CEILING)
    count=0
    with localcontext() as ctx:
        ctx.prec=64
        for row in report['results']:
            pnl=D(0);fees=D(0)
            for trade in row['trades']:
                sign=1 if trade['direction']=='LONG' else -1
                entry,exit_,qty=map(D,(trade['entry_price'],trade['exit_price'],trade['size']))
                eraw,xraw=D(trade['entry_raw_price']),D(trade['exit_raw_price'])
                if F(entry)!=F(eraw)*(1+sign*F(1,2000)) or F(exit_)!=F(xraw)*(1-sign*F(1,2000)):
                    raise ValueError('Adverse fill mismatch')
                ef,xf=ceil_fee(entry,qty),ceil_fee(exit_,qty)
                expected=money(money(sign*(exit_-entry)*qty)-ef-xf)
                if expected!=D(trade['realized_pnl']) or ef!=D(trade['entry_fee']) or xf!=D(trade['exit_fee']):
                    raise ValueError('Independent fee/PnL mismatch')
                if eraw!=prices[trade['entry_time']].open:raise ValueError('Entry raw candle mismatch')
                if 'signal_time' in trade:
                    if trade['entry_time']!=trade['signal_time']:raise ValueError('Not next-open entry')
                    if D(trade['notional'])>2000 or D(trade['risk_usdt'])>D(trade['risk_budget_usdt']):
                        raise ValueError('Risk/notional violated')
                reason=trade['exit_reason']
                opening=reason in ('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE','STRATEGY_EXIT_NEXT_OPEN')
                bar=prices[trade['exit_time'] if opening else trade['exit_time']-900]
                if reason.startswith('STOP'):
                    stop=D(trade['stop_loss'])
                    if not (bar.low<=stop if sign==1 else bar.high>=stop):
                        raise ValueError('Stop not touched by closed OHLC')
                    expected_exit=(min(stop,bar.open) if sign==1 else max(stop,bar.open)) if opening else stop
                elif reason.startswith('TAKE_PROFIT'):
                    expected_exit=D(trade['take_profit'])
                    if not (bar.high>=expected_exit if sign==1 else bar.low<=expected_exit):
                        raise ValueError('Target not touched by closed OHLC')
                elif reason=='STRATEGY_EXIT_NEXT_OPEN':expected_exit=bar.open
                else:expected_exit=bar.close
                if xraw!=expected_exit:raise ValueError('Conservative exit mismatch')
                count+=1;pnl+=expected;fees+=ef+xf
            if pnl!=D(row['metrics']['net_profit']) or fees!=D(row['metrics']['total_fees']):
                raise ValueError('Metric sum mismatch')
            if D(row['metrics']['final_balance'])!=10000+pnl:raise ValueError('Balance mismatch')
            peak=D(10000);dd=D(0)
            for point in row['equity_curve']:
                value=D(point['equity']);peak=max(peak,value);dd=max(dd,(peak-value)/peak*100)
            if money(dd)!=D(row['metrics']['max_drawdown_pct']):raise ValueError('Drawdown mismatch')
            if sum((D(x['cashflow_pnl']) for x in row['monthly']),D(0))!=pnl:
                raise ValueError('Monthly attribution sum mismatch')
            for month in row['monthly']:
                if D(month['closing_balance'])-D(month['opening_balance'])!=D(month['cashflow_pnl']):
                    raise ValueError('Monthly cashflow/balance mismatch')
    return dict(status='PASS',real_trades_audited=count,deterministic_report=True,
                checks=['source dataset','fills','ceil fees','Decimal PnL','risk','balance','drawdown','monthly'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path);parser.add_argument('report',type=Path)
    args=parser.parse_args();print(audit(args.csv,args.report))


if __name__=='__main__':main()
