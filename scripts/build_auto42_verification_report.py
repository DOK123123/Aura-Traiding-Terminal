"""Build small owner-visible evidence from isolated tests and completed real replay."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from decimal import Decimal as D,localcontext,ROUND_CEILING,ROUND_HALF_EVEN
from scripts.verify_auto42_execution import run
from scripts.replay_auto42_verification import code_hashes
from app.lab.models import canonical,digest

def audit_accounting(report):
    """Independent report oracle; no production fee/fill/accounting calls."""
    if not __debug__:raise RuntimeError('VERIFICATION_REQUIRES_ASSERTIONS')
    checked=0;drawdowns={}
    with localcontext() as ctx:
        ctx.prec=64
        def money(x,ceil=False):return x.quantize(D('.00000001'),rounding=ROUND_CEILING if ceil else ROUND_HALF_EVEN)
        for period in report['periods']:
            total=D(0);fees=D(0);slip=D(0);wins=0;profit=D(0);loss=D(0)
            for t in period['trades']:
                q=D(t['size']);long=t['direction']=='LONG';sign=1 if long else -1
                en=D(t['entry_raw_price'])*(D('1.0005') if long else D('.9995'))
                ex=D(t['exit_raw_price'])*(D('.9995') if long else D('1.0005'))
                ef=money(en*q*D('.001'),True);xf=money(ex*q*D('.001'),True)
                net=money(money(sign*(ex-en)*q)-ef-xf)
                assert D(t['entry_price'])==en and D(t['exit_price'])==ex
                assert D(t['entry_fee'])==ef and D(t['exit_fee'])==xf
                assert D(t['realized_pnl'])==net and t['entry_time']==t['signal_at']
                assert D(t['notional'])<=2000 and D(t['risk_usdt'])<=D(t['risk_budget_usdt'])
                total+=net;fees+=ef+xf;wins+=net>0;profit+=max(net,D(0));loss+=max(-net,D(0))
                slip=money(slip+abs(en-D(t['entry_raw_price']))*q)
                slip=money(slip+abs(ex-D(t['exit_raw_price']))*q);checked+=1
            remaining=period['remaining_position']
            if remaining:
                fees+=D(remaining['entry_fee']);slip=money(slip+abs(D(remaining['entry_price'])-D(remaining['entry_raw_price']))*D(remaining['size']))
            assert D(period['realized_net_pnl'])==total and D(period['fees'])==fees and D(period['slippage'])==slip
            assert D(period['final_balance'])==D(10000)+total-(D(remaining['entry_fee']) if remaining else 0)
            expected_pf=money(profit/loss) if loss else None
            assert (D(period['profit_factor']) if period['profit_factor'] is not None else None)==expected_pf
            peak=D(10000);dd=D(0)
            for point in period['equity_curve']:
                eq=D(point['equity']);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak*100)
            assert money(dd)<=D(period['max_drawdown_pct'])
            drawdowns[str(period['days'])]=dict(close_equity_curve_max_dd_pct=str(money(dd)),engine_max_dd_pct=period['max_drawdown_pct'],
                note='Engine additionally checks candle-open liquidation equity before settlement.')
    return dict(status='PASS',real_closed_trades_checked=checked,drawdown_cross_check=drawdowns)

async def build(replay_path):
    isolated=await run();historical=dict(status='NOT_TESTED',reason='REAL_REPLAY_NOT_RUN')
    if replay_path:
        if replay_path.stat().st_size>32*1024*1024:raise ValueError('Replay report exceeds offline bound')
        raw=replay_path.read_bytes();replay=json.loads(raw)
        if replay.get('code_hashes')!=code_hashes():raise ValueError('Replay used a different production version')
        periods=replay.get('periods',[])
        accounting=audit_accounting(replay)
        complete=replay.get('status')=='PASS' and sorted(p.get('days') for p in periods)==[7,30,90] and all(p.get('status')=='PASS' for p in periods)
        historical=dict(status='PASS' if complete else 'INCONCLUSIVE',evidence_type='REAL_HISTORICAL_REPLAY_NOT_LIVE',
            interpretation='PASS means replay completed, NOT profitable or independently verified Binance provenance.',
            independent_accounting=accounting,source=replay['source'],policy=replay['policy'],strategy_parameters=replay['strategy_parameters'],
            raw_report_sha256=hashlib.sha256(raw).hexdigest(),
            periods=[{k:v for k,v in p.items() if k not in ('equity_curve','open_events')} for p in periods],
            equity_curves='Full curves and OPEN events remain in reproducible offline replay.json; not copied to Git.',
            limitations=replay['limitations'])
    value=dict(base_commit='5dfcf37f58789b1ef4373309ae3e69169fff1767',code_hashes=code_hashes(),
        isolated=isolated,historical=historical,
        live=dict(status='NOT_TESTED',reason='NO_OBSERVED_DEPLOYED_STRATEGY_OPEN_CLOSE_CYCLE'),
        read_only=True,test_only=True,live_execution_enabled=False)
    return dict(value,checksum=digest(value))

async def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--replay',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();value=await build(args.replay);args.output.write_bytes(canonical(value));print('Isolated:',value['isolated']['status'],'Historical:',value['historical']['status'],'Live: NOT_TESTED')

if __name__=='__main__':asyncio.run(main())
