"""Bounded public archive downloader and offline verified monthly importer."""
import argparse
import calendar
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
import zipfile
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.lab.local_csv import load_binance_csv
from app.lab.models import validate_series

BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/'
MONTHS=tuple(f'BTCUSDT-15m-{y}-{m:02d}.zip' for y in range(2020,2026) for m in range(1,13))
MAX_ZIP=8*1024*1024


def checksum(raw,name):
    fields=raw.decode('ascii').strip().split()
    if len(fields) not in (1,2) or not re.fullmatch('[0-9a-fA-F]{64}',fields[0]):
        raise ValueError('Invalid CHECKSUM')
    if len(fields)==2 and fields[1].lstrip('*')!=name:raise ValueError('CHECKSUM filename mismatch')
    return fields[0].lower()


def monthly_bytes(raw,check,name):
    if name not in MONTHS or len(raw)>MAX_ZIP or len(check)>512:raise ValueError('Archive limits')
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=checksum(check,name):raise ValueError('SHA256 mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        if len(infos)!=1 or infos[0].filename!=name[:-4]+'.csv' or infos[0].file_size>16*1024*1024:
            raise ValueError('Unexpected ZIP member/size')
        info=infos[0]
        if info.flag_bits&1 or (info.external_attr>>16)&0o170000==0o120000:
            raise ValueError('Encrypted/symlink member')
        content=z.read(info) # Bounded member read checks ZIP CRC; never extract paths.
    first=next(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
    if len(first)!=12:raise ValueError('Official klines require 12 columns')
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/'month.csv';p.write_bytes(content)
        bars,meta=load_binance_csv(p)
    year,month=map(int,name[:-4].split('-')[-2:])
    start=int(datetime(year,month,1,tzinfo=timezone.utc).timestamp())
    expected=calendar.monthrange(year,month)[1]*96
    if len(bars)!=expected or bars[0].time!=start or bars[-1].time+900!=start+expected*900:
        raise ValueError('Incomplete or wrong month')
    return bars,dict(name=name,zip_sha256=digest,csv_sha256=meta['sha256'],candles=len(bars),start=start)


def load_years(path):
    """Directory of 72 ZIP/CHECKSUM pairs, or downloader's exact nested bundle."""
    path=Path(path);bars=[];metadata=[]
    if path.is_dir():
        def read(name,limit):
            p=path/name
            if p.stat().st_size>limit:raise ValueError('Archive file too large')
            return p.read_bytes()
        archive=None;manifest_hashes=None
    else:
        if path.stat().st_size>600*1024*1024:raise ValueError('Bundle too large')
        archive=zipfile.ZipFile(path)
        wanted={'manifest.json'}|{'monthly/'+n for n in MONTHS}|{'checksums/'+n+'.CHECKSUM' for n in MONTHS}
        names=archive.namelist()
        if len(names)!=145 or set(names)!=wanted:
            archive.close();raise ValueError('Incomplete/duplicate/unexpected bundle members')
        try:
            if archive.getinfo('manifest.json').file_size>65536:raise ValueError('Manifest size')
            manifest=json.loads(archive.read('manifest.json'))
            if (manifest.get('symbol'),manifest.get('timeframe'),manifest.get('source'),manifest.get('years'))!=('BTCUSDT','15m',BASE,list(range(2020,2026))):
                raise ValueError('Manifest identity mismatch')
            manifest_hashes={x['name']:x['sha256'] for x in manifest['files']}
            if len(manifest['files'])!=72 or set(manifest_hashes)!=set(MONTHS):raise ValueError('Manifest files mismatch')
        except Exception:
            archive.close();raise
        def read(name,limit):
            key='checksums/'+name if name.endswith('.CHECKSUM') else 'monthly/'+name
            info=archive.getinfo(key)
            if info.file_size>limit:raise ValueError('Archive member too large')
            return archive.read(key)
    try:
        for name in MONTHS:
            month,meta=monthly_bytes(read(name,MAX_ZIP),read(name+'.CHECKSUM',512),name)
            if manifest_hashes is not None and manifest_hashes[name]!=meta['zip_sha256']:raise ValueError('Manifest SHA mismatch')
            bars.extend(month);metadata.append(meta)
        if len(bars)>211000:raise ValueError('Multi-year row limit')
        validate_series(bars,900,int(time.time()))
    finally:
        if archive is not None:archive.close()
    return bars,dict(source=BASE,checksums_verified=True,count=len(bars),months=metadata,
                     authentication='Provided official-format checksum pairs; independent official retrieval required for authenticity')


def download(folder,seconds=900):
    """No redirects/retries; fixed official GET paths; abort on first failure."""
    import httpx
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+seconds
    with httpx.Client(timeout=8,follow_redirects=False) as client:
        for name in MONTHS:
            payloads=[]
            for suffix,limit in (('.CHECKSUM',512),('',MAX_ZIP)):
                data=bytearray()
                with client.stream('GET',BASE+name+suffix) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        if time.monotonic()>deadline or len(data)+len(chunk)>limit:raise ValueError('Download size/time budget')
                        data.extend(chunk)
                payloads.append(bytes(data))
            check,raw=payloads
            monthly_bytes(raw,check,name)
            for suffix,content in (('.CHECKSUM',check),('',raw)):
                destination=folder/(name+suffix)
                if destination.exists() and destination.read_bytes()!=content:raise ValueError('Refuse to replace different archive')
                if not destination.exists():destination.write_bytes(content)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path);p.add_argument('--download',action='store_true');a=p.parse_args()
    if a.download:download(a.path)
    bars,meta=load_years(a.path);print({'verified_candles':len(bars),'months':len(meta['months'])})
