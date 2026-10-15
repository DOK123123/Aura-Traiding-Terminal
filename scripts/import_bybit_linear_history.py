"""Explicit offline snapshot download, not a backtest or execution command."""
import argparse,asyncio,json,time
from pathlib import Path
from app.bybit_linear.client import Client,MarketError,STEPS
from app.lab.models import digest

async def download(args):
    if args.output.exists():raise MarketError('OUTPUT_EXISTS')
    if args.output.suffix!='.json' or '.data' in args.output.resolve().parts or args.output.resolve().is_relative_to(Path('app').resolve()):raise MarketError('OUTPUT_SCOPE')
    step=STEPS[args.timeframe];end=int(time.time())//step*step
    warmup=4160 if args.timeframe=='15m' else 250
    start=end-args.days*86400-warmup*step
    client=Client()
    try:
        await client.verify_instrument()
        data=await client.candles(args.timeframe,start,end)
        data.update(format='BYBIT_LINEAR_CLOSED_SNAPSHOT_V1',test_start=start+warmup*step,warmup_candles=warmup,
            purpose='HISTORY_ONLY_NOT_A_REPLAY_OR_TRADING_SIGNAL')
        data['sha256']=digest(data)
        # Never write into production app data directories or overwrite history.
        if args.output.resolve().is_relative_to(Path('app').resolve()):raise MarketError('OUTPUT_SCOPE')
        with args.output.open('x') as f:json.dump(data,f,ensure_ascii=False,sort_keys=True)
        print(json.dumps(dict(status='DOWNLOADED',count=data['count'],sha256=data['sha256'])))
    finally:await client.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--days',type=int,choices=(7,30,90),required=True);p.add_argument('--timeframe',choices=STEPS,default='15m');p.add_argument('--output',type=Path,required=True)
    try:asyncio.run(download(p.parse_args()))
    except (MarketError,TimeoutError) as e:print(json.dumps({'status':'BLOCKED','code':e.code if isinstance(e,MarketError) else 'UPSTREAM_TIMEOUT'}));raise SystemExit(1)
