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
from app.lab.local_csv import load_binance_csv,_timestamp
from app.lab.models import validate_series,Bar,number

BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/'
MONTHS=tuple(f'BTCUSDT-15m-{y}-{m:02d}.zip' for y in range(2020,2026) for m in range(1,13))
MAX_ZIP=8*1024*1024


def checksum(raw,name):
    fields=raw.decode('ascii').strip().split()
    if len(fields) not in (1,2) or not re.fullmatch('[0-9a-fA-F]{64}',fields[0]):
        raise ValueError('Invalid CHECKSUM')
    if len(fields)==2 and fields[1].lstrip('*')!=name:raise ValueError('CHECKSUM filename mismatch')
    return fields[0].lower()


def monthly_bytes(raw,check,name,*,allow_gaps=False):
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
    lines=content.decode('utf-8-sig').splitlines()
    header=lines[:1] if first[0].lower()=='open_time' else []
    data=lines[len(header):];chunks=[];chunk=[];previous=None;quarantined=[];raw_times=[]
    for line in data:
        row=next(csv.reader([line]))
        if len(row)!=12:raise ValueError('Invalid columns')
        stamp=_timestamp(row[0],step=900)
        Bar(stamp,*[number(row[i].strip(),positive=i<5) for i in range(1,6)]).validate(900,int(time.time()))
        for i in (7,9,10,11):number(row[i].strip())
        if not row[8].isascii() or not row[8].isdigit() or len(row[8])>24:raise ValueError('Invalid trade count')
        if raw_times and stamp<=raw_times[-1]:raise ValueError('Duplicate/unordered raw candles')
        raw_times.append(stamp)
        unit=1000000 if int(row[0])>=10**15 else 1000
        if not row[6].isascii() or not row[6].isdigit() or int(row[6])!=(stamp+900)*unit-1:
            if not allow_gaps:raise ValueError('Invalid close_time')
            quarantined.append(dict(time=stamp,reason='INVALID_CLOSE_TIME',provided=row[6],expected=str((stamp+900)*unit-1)))
            continue
        if previous is not None:
            if stamp<=previous:raise ValueError('Duplicate/unordered candles')
            if stamp-previous!=900:
                if not allow_gaps:raise ValueError('Missing candles')
                chunks.append(chunk);chunk=[]
        chunk.append(line);previous=stamp
    if chunk:chunks.append(chunk)
    bars=[]
    with tempfile.TemporaryDirectory() as folder:
        for chunk in chunks:
            p=Path(folder)/'month.csv';p.write_text('\n'.join(header+chunk)+'\n')
            part,_=load_binance_csv(p);bars.extend(part)
    year,month=map(int,name[:-4].split('-')[-2:])
    start=int(datetime(year,month,1,tzinfo=timezone.utc).timestamp())
    expected=calendar.monthrange(year,month)[1]*96
    if not bars or bars[0].time<start or bars[-1].time+900>start+expected*900:raise ValueError('Wrong month')
    if not allow_gaps and (len(bars)!=expected or bars[0].time!=start or bars[-1].time+900!=start+expected*900):
        raise ValueError('Incomplete or wrong month')
    raw_gaps=[dict(previous=a,current=b,missing=(b-a)//900-1) for a,b in zip(raw_times,raw_times[1:]) if b-a!=900]
    return bars,dict(name=name,zip_sha256=digest,csv_sha256=hashlib.sha256(content).hexdigest(),candles=len(bars),raw_candles=len(data),raw_gap_count=len(raw_gaps),raw_gaps=raw_gaps,quarantined=quarantined,expected=expected,start=start)


def load_years(path,*,allow_gaps=False):
    """Directory of 72 ZIP/CHECKSUM pairs, or downloader's exact nested bundle."""
    path=Path(path);bars=[];metadata=[]
    if path.is_dir():
        def read(name,limit):
            p=path/name
            if p.stat().st_size>limit:raise ValueError('Archive file too large')
            return p.read_bytes()
        archive=None;manifest_hashes=None;manifest=None;quality=None
    else:
        if path.stat().st_size>600*1024*1024:raise ValueError('Bundle too large')
        archive=zipfile.ZipFile(path)
        names=archive.namelist()
        flat=MONTHS[0] in names
        wanted={'manifest.json'}|({n for n in MONTHS}|{n+'.CHECKSUM' for n in MONTHS} if flat else {'monthly/'+n for n in MONTHS}|{'checksums/'+n+'.CHECKSUM' for n in MONTHS})
        if 'AURA_DATA_QUALITY_REPORT.json' in names:wanted.add('AURA_DATA_QUALITY_REPORT.json')
        if len(names)!=len(wanted) or set(names)!=wanted:
            archive.close();raise ValueError('Incomplete/duplicate/unexpected bundle members')
        try:
            if archive.getinfo('manifest.json').file_size>65536:raise ValueError('Manifest size')
            manifest=json.loads(archive.read('manifest.json'))
            if (manifest.get('symbol'),manifest.get('timeframe',manifest.get('interval')),manifest.get('years'))!=('BTCUSDT','15m',list(range(2020,2026))) or manifest.get('source') not in (BASE,'Binance public spot monthly klines'):
                raise ValueError('Manifest identity mismatch')
            manifest_hashes={x['name']:x['sha256'] for x in manifest['files']}
            if len(manifest['files'])!=72 or set(manifest_hashes)!=set(MONTHS):raise ValueError('Manifest files mismatch')
            quality=None
            if 'AURA_DATA_QUALITY_REPORT.json' in names:
                if archive.getinfo('AURA_DATA_QUALITY_REPORT.json').file_size>65536:raise ValueError('Quality report size')
                quality=json.loads(archive.read('AURA_DATA_QUALITY_REPORT.json'))
        except Exception:
            archive.close();raise
        def read(name,limit):
            key=name if flat else 'checksums/'+name if name.endswith('.CHECKSUM') else 'monthly/'+name
            info=archive.getinfo(key)
            if info.file_size>limit:raise ValueError('Archive member too large')
            return archive.read(key)
    try:
        for name in MONTHS:
            month,meta=monthly_bytes(read(name,MAX_ZIP),read(name+'.CHECKSUM',512),name,allow_gaps=allow_gaps)
            if manifest_hashes is not None and manifest_hashes[name]!=meta['zip_sha256']:raise ValueError('Manifest SHA mismatch')
            bars.extend(month);metadata.append(meta)
        if len(bars)>211000:raise ValueError('Multi-year row limit')
        if allow_gaps:
            for b in bars:b.validate(900,int(time.time()))
            if any(b.time<=a.time for a,b in zip(bars,bars[1:])):raise ValueError('Duplicate/unordered global history')
        else:validate_series(bars,900,int(time.time()))
    finally:
        if archive is not None:archive.close()
    expected_start=int(datetime(2020,1,1,tzinfo=timezone.utc).timestamp());expected_end=int(datetime(2026,1,1,tzinfo=timezone.utc).timestamp())
    points=[expected_start-900]+[b.time for b in bars]+[expected_end]
    gaps=[dict(start_exclusive_previous=a,start=a+900,end_exclusive=b,missing=(b-a)//900-1) for a,b in zip(points,points[1:]) if b-a>900]
    missing=sum(g['missing'] for g in gaps);incomplete=sum(m['raw_candles']!=m['expected'] for m in metadata)
    if len(bars)+missing!=210432:raise ValueError('Six-year count reconciliation')
    if manifest is not None:
        for row,actual in zip(manifest['files'],metadata):
            if row['name']!=actual['name'] or ('rows' in row and row['rows']!=actual['raw_candles']):raise ValueError('Manifest row mismatch')
        if 'total_rows' in manifest and manifest['total_rows']!=sum(m['raw_candles'] for m in metadata):raise ValueError('Manifest total mismatch')
    annotations=sum(m['raw_gap_count'] for m in metadata)+incomplete
    if quality is not None and quality.get('data_gaps_detected')!=annotations:raise ValueError('Quality count mismatch')
    return bars,dict(source=BASE,checksums_verified=True,count=len(bars),raw_count=sum(m['raw_candles'] for m in metadata),raw_missing_candles=210432-sum(m['raw_candles'] for m in metadata),months=metadata,gaps=gaps,missing_candles=missing,incomplete_months=incomplete,quality_annotations=annotations,
                     bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
                     supplied_quality_report=quality,
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
