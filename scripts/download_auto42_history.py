"""Standalone official Binance Spot BTCUSDT 15m history + CHECKSUM provenance.

No private credentials, account API or production storage. Never mounted by web.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

import httpx
from app.lab.local_csv import load_binance_csv

ROOT = 'https://data.binance.vision/data/spot/'


def archives(end_date, days=90):
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if not 90 <= days <= 120 or end.timestamp() > datetime.now(timezone.utc).timestamp():
        raise ValueError('Require 90..120 days ending in the past')
    start = int((end-timedelta(days=days)).timestamp())//14400*14400-4160*900
    first = datetime.fromtimestamp(start, timezone.utc)
    cursor = first.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    result = []
    while cursor < end:
        following = (cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
        if following <= end:
            name = 'BTCUSDT-15m-'+cursor.strftime('%Y-%m')+'.zip'
            result.append(('monthly',name));cursor=following
        else:
            while cursor < end:
                result.append(('daily','BTCUSDT-15m-'+cursor.strftime('%Y-%m-%d')+'.zip'))
                cursor += timedelta(days=1)
    return result, start, int(end.timestamp())


def get(client, url, limit):
    raw=bytearray()
    with client.stream('GET',url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw)>limit:raise ValueError('ARCHIVE_RESPONSE_LIMIT')
    return bytes(raw)


def download(end_date, output, days=90):
    if os.getenv('RENDER'):raise ValueError('Standalone local tool only')
    output=Path(output)
    provenance=output.with_suffix('.provenance.json')
    if output.exists() or provenance.exists():raise ValueError('Use new output paths')
    wanted,start,end=archives(end_date,days)
    def fetch(item):
        kind,name=item;url=ROOT+kind+'/klines/BTCUSDT/15m/'+name
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            check=get(client,url+'.CHECKSUM',512)
            fields=check.decode('ascii').strip().split()
            if len(fields)!=2 or fields[1].lstrip('*')!=name:raise ValueError('CHECKSUM_FILENAME')
            raw=get(client,url,8*1024*1024)
        if hashlib.sha256(raw).hexdigest()!=fields[0].lower():raise ValueError('CHECKSUM_MISMATCH')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.namelist()!=[name[:-4]+'.csv']:raise ValueError('ARCHIVE_MEMBERS')
            info=archive.infolist()[0]
            if info.file_size>16*1024*1024:raise ValueError('ARCHIVE_SIZE')
            csv=archive.read(info)
        with tempfile.TemporaryDirectory(prefix='aura-official-history-') as folder:
            path=Path(folder)/'month.csv';path.write_bytes(csv)
            bars,_=load_binance_csv(path)
        return bars,dict(url=url,checksum_url=url+'.CHECKSUM',zip_sha256=fields[0].lower(),
                         csv_sha256=hashlib.sha256(csv).hexdigest(),rows=len(bars))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(fetch,wanted))
    bars=[b for batch,_ in results for b in batch if start<=b.time<end]
    if not bars or bars[0].time!=start or bars[-1].time+900!=end or any(b.time-a.time!=900 for a,b in zip(bars,bars[1:])):
        raise ValueError('INCOMPLETE_HISTORY_NO_SYNTHETIC_FILL')
    # Standard validated six-column Binance shape, millisecond UTC open time.
    csv='\n'.join(','.join([str(b.time*1000),str(b.open),str(b.high),str(b.low),str(b.close),str(b.volume)]) for b in bars)+'\n'
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:stream.write(csv)
    loaded,identity=load_binance_csv(output)
    report=dict(source='Binance Spot BTCUSDT 15m official archives',checksums_verified=True,
        authenticated_via='Official HTTPS ZIP and matching official CHECKSUM GET; no account API',
        csv_sha256=identity['sha256'],count=len(loaded),start=start,end_exclusive=end,
        evaluation_days=days,evaluation_start=end-days*86400,warmup='Exact UTC 4h boundary minus 4160 15m candles',
        files=[m for _,m in results],synthetic_data=False,production_access=False)
    with provenance.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(csv=str(output),provenance=str(provenance),candles=len(loaded),days=days)))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-date',required=True)
    parser.add_argument('--days',type=int,default=90)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();download(args.end_date,args.output,args.days)
