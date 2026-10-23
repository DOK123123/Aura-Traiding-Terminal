"""Local read-only Bitget Futures signal count; NOT an execution/PnL backtest."""
import argparse,asyncio,json,os,time
from pathlib import Path
from datetime import datetime,timezone
from app.active43.bitget import Client,MarketError
from app.active43.strategies import signals
from app.lab.models import Bar,digest


async def scan(end):
    client=Client();start=end-60*3600;cutoff=end-10*3600
    result=dict(scope='READ_ONLY_PUBLIC_BITGET_FUTURES_SIGNAL_SCAN_NOT_BACKTEST_OR_PRODUCTION',
        source='Bitget USDT-M Futures BTCUSDT',end_utc=datetime.fromtimestamp(end,timezone.utc).isoformat(),
        comparison_hours=10,lookback_hours=60,fees_or_pnl_tested=False,production_writes=False)
    try:
        await client.check_time();await client.instrument();rows=[]
        for tf,name,step in [('5m','SR_BOUNCE',300),('15m','DONCHIAN',900)]:
            data=await client.candles(tf,start,end);bars=[Bar.restore(b) for b in data['bars']]
            candidates=[d for b,d in zip(bars,signals(bars,name)) if cutoff<b.time+step<=end]
            rows.append(dict(strategy=name,timeframe=tf,bars=len(bars),comparison_bars=len(candidates),
                long=sum(d.direction=='LONG' for d in candidates),short=sum(d.direction=='SHORT' for d in candidates),data_sha256=digest(data['bars'])))
        result.update(status='PASS',signals=rows,limitation='Only 10 common hours after causal warmup; no profitability/frequency-generalization claim')
    except MarketError as exc:result.update(status='BLOCKED',code=exc.code,limitation='No fabricated or synthetic replacement')
    finally:await client.close()
    return result


def run(output,end=None):
    if os.getenv('RENDER') or not __debug__:raise ValueError('LOCAL_OFFLINE_ONLY')
    output=Path(output)
    if output.exists():raise ValueError('New output required')
    now=int(time.time());end=now//900*900 if end is None else end
    if type(end) is not int or end%900 or end<60*3600 or end>now//900*900:raise ValueError('Closed UTC 15m boundary required')
    result=asyncio.run(scan(end));output.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--end',type=int)
    args=parser.parse_args();print(json.dumps(run(args.output,args.end)))
