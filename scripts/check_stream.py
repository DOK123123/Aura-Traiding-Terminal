"""Observe the running app's real live channel; no mocked data."""
import asyncio
import json
from pathlib import Path
import time

from websockets.asyncio.client import connect


async def observe(symbol, timeframe, count, updates):
    rows=[]
    async with asyncio.timeout(150):
        async with connect(f'ws://127.0.0.1:8000/ws/market?symbol={symbol}&timeframe={timeframe}&limit={count}',max_size=4_000_000) as socket:
            async for raw in socket:
                data=json.loads(raw)
                if data['type']=='status':
                    print(data,flush=True)
                    continue
                if symbol=='BTCUSDT' and data['mode']!='streaming': continue
                candle=data.get('candle') or data['candles'][-1]
                a=data['analysis']
                assert a['count']==count
                rows.append({'received_at':data['received_at'],'mode':data['mode'],'source':data['source'],
                             'current_closed':data['current_closed'],'candle':candle,
                             'analysis':{key:a[key] for key in ('price','ema20','ema50','rsi','atr','momentum_pct','signal_up')}})
                print(symbol,timeframe,count,len(rows),candle['time'],candle['close'],candle['volume'],flush=True)
                if len(rows)>=updates: break
    if symbol=='BTCUSDT':
        assert len({(r['candle']['close'],r['candle']['volume']) for r in rows})>1, 'BTC did not change'
        assert any(not r['current_closed'] for r in rows), 'No current candle'
    return {'symbol':symbol,'timeframe':timeframe,'limit':count,'observations':rows}


async def main():
    report={'checked_at':time.time(),'checks':[]}
    for symbol,timeframe,count,updates in [('BTCUSDT','1m',500,4),('BTCUSDT','5m',2000,3),('XAUUSD','1m',500,2)]:
        report['checks'].append(await observe(symbol,timeframe,count,updates))
    Path('live-stream-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': asyncio.run(main())
