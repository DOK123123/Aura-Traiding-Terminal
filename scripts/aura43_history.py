"""Offline bounded 6-12 month public history; original Lab importer stays unchanged."""
import argparse
import asyncio
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import httpx
from app.lab.data import public_page
from app.lab.local_csv import load_binance_csv
from app.lab.models import LabError

MAX_BYTES=12*1024*1024
MAX_ROWS=40000

def load_history(path):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise LabError('LOCAL_FILE_TOO_LARGE')
    raw=path.read_bytes()
    if len(raw)>MAX_BYTES:raise LabError('LOCAL_FILE_TOO_LARGE')
    lines=raw.splitlines(keepends=True)
    if not 1<=len(lines)<=MAX_ROWS:raise LabError('INVALID_ROW_COUNT')
    bars=[]
    with tempfile.TemporaryDirectory(prefix='aura43-import-') as folder:
        for i in range(0,len(lines),10000):
            chunk=Path(folder)/'chunk.csv';chunk.write_bytes(b''.join(lines[i:i+10000]))
            part,_=load_binance_csv(chunk)
            if bars and part[0].time-bars[-1].time!=900:raise LabError('MISSING_OR_DUPLICATE_BOUNDARY')
            bars.extend(part)
    return bars,dict(sha256=hashlib.sha256(raw).hexdigest(),count=len(bars),start=bars[0].time,
        end_exclusive=bars[-1].time+900,source_claim='Binance public REST; see bundled acquisition provenance')

async def fetch(path,start,end):
    if start%14400 or end%14400 or not 180*86400<=end-start<=366*86400:raise ValueError('COVERAGE')
    cursor=start-4160*900;rows=[];pages=[]
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        async with asyncio.timeout(600):
            for _ in range(40):
                if cursor>=end:break
                query=dict(symbol='BTCUSDT',interval='15m',startTime=cursor*1000,endTime=end*1000-1,limit=min(1000,(end-cursor)//900))
                data=await public_page(client,query)
                if not isinstance(data,list) or not data or any(type(r) is not list or len(r)!=12 for r in data):raise ValueError('INCOMPLETE_HISTORY')
                pages.append(dict(query=query,sha256=hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()))
                rows.extend(data);cursor=data[-1][0]//1000+900
    if cursor!=end or len(rows)!=(end-start)//900+4160:raise ValueError('INCOMPLETE_HISTORY')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:csv.writer(f,lineterminator='\n').writerows(rows)
    bars,info=load_history(path)
    if bars[0].time!=start-4160*900 or bars[-1].time+900!=end:raise ValueError('COVERAGE')
    provenance=dict(**info,endpoint='https://data-api.binance.vision/api/v3/klines',symbol='BTCUSDT',interval='15m',
        acquired_at_utc=datetime.now(timezone.utc).isoformat(),pages=pages,source='REAL_BINANCE_PUBLIC_REST_NO_SYNTHETIC_DATA')
    path.with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    return {k:v for k,v in provenance.items() if k!='pages'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    protocol=json.loads(Path('docs/AURA43_PROFILES_PROTOCOL.json').read_text())
    stamp=lambda k:int(datetime.fromisoformat(protocol[k].replace('Z','+00:00')).timestamp())
    print(json.dumps(asyncio.run(fetch(a.output,stamp('start_utc'),stamp('end_exclusive_utc')))))
