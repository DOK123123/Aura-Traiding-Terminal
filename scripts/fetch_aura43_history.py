"""Read-only fixed Binance public history acquisition; no account credentials."""
import argparse
import asyncio
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import httpx
from app.lab.data import public_page
from app.lab.local_csv import load_binance_csv


async def fetch(output: Path, end: int) -> dict:
    if end%14400:raise ValueError('UTC_4H_BOUNDARY_REQUIRED')
    start=end-90*86400-4160*900;cursor=start;rows=[];pages=[]
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        async with asyncio.timeout(180):
            for _ in range(14):
                if cursor>=end:break
                query=dict(symbol='BTCUSDT',interval='15m',startTime=cursor*1000,endTime=end*1000-1,limit=min(1000,(end-cursor)//900))
                data=await public_page(client,query)
                if not isinstance(data,list) or not data:raise ValueError('INCOMPLETE_HISTORY')
                if any(type(r) is not list or len(r)!=12 for r in data):raise ValueError('INVALID_DATA')
                pages.append(dict(query=query,sha256=hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()))
                rows.extend(data);cursor=data[-1][0]//1000+900
    if cursor!=end or len(rows)!=(end-start)//900:raise ValueError('INCOMPLETE_HISTORY')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='') as f:
        csv.writer(f,lineterminator='\n').writerows(rows)
    bars,info=load_binance_csv(output)
    if bars[0].time!=start or bars[-1].time+900!=end:raise ValueError('COVERAGE_MISMATCH')
    provenance=dict(endpoint='https://data-api.binance.vision/api/v3/klines',symbol='BTCUSDT',interval='15m',
        acquired_at_utc=datetime.now(timezone.utc).isoformat(),count=len(bars),start=start,end_exclusive=end,
        sha256=info['sha256'],pages=pages,source='BINANCE_PUBLIC_REST_NOT_SYNTHETIC',
        limitations=['REST response hashes and strict OHLCV validation; no archive checksum attestation.'])
    output.with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    return {k:v for k,v in provenance.items() if k!='pages'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--end',default='2026-10-16T00:00:00+00:00');a=p.parse_args()
    print(json.dumps(asyncio.run(fetch(a.output,int(datetime.fromisoformat(a.end).timestamp())))))
