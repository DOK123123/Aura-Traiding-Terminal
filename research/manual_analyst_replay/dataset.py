"""Strict local UTC OHLCV reader. No download, exchange clients or storage APIs."""
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import re
from urllib.parse import urlparse
import zipfile
from .config import decimal, digest

SOURCE = 'BITGET_USDT_FUTURES_BTCUSDT'
STEPS = {'5m':300,'15m':900,'1h':3600,'4h':14400}
MAX_FILE_BYTES = 128*1024*1024


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


@dataclass(frozen=True)
class Bar:
    time: int
    open: D
    high: D
    low: D
    close: D
    volume: D
    available_at: int

    def validate(self, step: int) -> None:
        if type(self.time) is not int or self.time<0 or self.time%step or type(self.available_at) is not int or not self.time+step<=self.available_at<=self.time+step+3600:
            raise ValueError('INVALID_AVAILABILITY_OR_TIMESTAMP')
        if any(not isinstance(v,D) or not v.is_finite() for v in (self.open,self.high,self.low,self.close,self.volume)):
            raise ValueError('INVALID_OHLCV')
        if self.low<=0 or self.volume<0 or self.high<max(self.open,self.close,self.low) or self.low>min(self.open,self.close):
            raise ValueError('INVALID_OHLCV')


def validate(bars: tuple[Bar,...] | list[Bar], step: int) -> None:
    if not bars:raise ValueError('NO_DATA')
    for i,b in enumerate(bars):
        b.validate(step)
        if i and b.time!=bars[i-1].time+step:
            raise ValueError('DUPLICATE_OR_GAP_OR_UNORDERED')
        if i and b.available_at<bars[i-1].available_at:
            raise ValueError('AVAILABILITY_NOT_MONOTONIC')


def aggregate(bars: tuple[Bar,...], source_step: int, step: int) -> tuple[Bar,...]:
    if step<source_step or step%source_step:raise ValueError('INVALID_AGGREGATION')
    groups={}
    for b in bars:groups.setdefault(b.time//step*step,[]).append(b)
    result=[]
    first=bars[0].time;end=bars[-1].time+source_step
    for t,group in groups.items():
        if t<first or t+step>end:continue  # Only incomplete boundary bins may be dropped.
        if len(group)!=step//source_step or group[0].time!=t or group[-1].time+source_step!=t+step:
            raise ValueError('INCOMPLETE_AGGREGATE')
        result.append(Bar(t,group[0].open,max(b.high for b in group),min(b.low for b in group),
                          group[-1].close,sum((b.volume for b in group),D(0)),max(b.available_at for b in group)))
    result=tuple(result);validate(result,step);return result


@dataclass(frozen=True)
class Dataset:
    execution: tuple[Bar,...]
    execution_step: int
    frames: dict[str,tuple[Bar,...]]
    manifest: dict
    data_hash: str


def load(path: Path, max_rows: int = 500000) -> Dataset:
    """Manifest + checksummed local CSV/CSV.GZ or official Bitget minute ZIP.

    `available_at` must be explicit for observed data. Historical archives use an
    explicitly labelled close+delay assumption, never invented observed receipts.
    """
    if path.stat().st_size>2*1024*1024:raise ValueError('MANIFEST_TOO_LARGE')
    m=json.loads(path.read_text())
    if not isinstance(m,dict):raise ValueError('MANIFEST_SCHEMA')
    if m.get('data_kind') not in ('REAL_PUBLIC_ARCHIVE','SYNTHETIC_TEST'):raise ValueError('DATA_KIND_REQUIRED')
    if m.get('version')!=1 or m.get('source')!=SOURCE or m.get('symbol')!='BTCUSDT' or m.get('product_type')!='USDT-FUTURES':
        raise ValueError('SOURCE_MISMATCH')
    step=m.get('execution_step')
    if type(step) is not int or step not in (60,300):raise ValueError('EXECUTION_STEP')
    mode=m.get('availability_mode')
    if mode not in ('OBSERVED','ASSUMED_CLOSE_PLUS_DELAY'):raise ValueError('AVAILABILITY_MODE')
    delay=m.get('publication_delay_seconds')
    if mode=='ASSUMED_CLOSE_PLUS_DELAY' and (type(delay) is not int or not 1<=delay<=60):raise ValueError('PUBLICATION_DELAY_REQUIRED')
    captured=m.get('asof')
    if type(captured) is not int or captured<=0:raise ValueError('ASOF_REQUIRED')
    files=m.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=36:raise ValueError('FILE_LIMIT')
    root=path.resolve().parent;out=[];seen_files=set();read_bytes=0
    for meta in files:
        file=(root/meta['path']).resolve()
        if not file.is_relative_to(root) or file in seen_files or file.stat().st_size>MAX_FILE_BYTES:raise ValueError('UNSAFE_FILE')
        seen_files.add(file)
        if sha256(file)!=meta['sha256']:raise ValueError('CHECKSUM_MISMATCH')
        fmt=meta.get('format')
        if fmt=='BITGET_OFFICIAL_MINUTE_ZIP':
            if step!=60:raise ValueError('ZIP_STEP')
            if not re.fullmatch(r'BTCUSDT_UMCBL_1min_[0-9]{6}\.zip',file.name):raise ValueError('FUTURES_FILENAME')
            if m['data_kind']=='REAL_PUBLIC_ARCHIVE':
                url=urlparse(meta.get('source_url',''))
                if url.scheme!='https' or url.hostname!='img.bitgetimg.com' or url.query or url.fragment or url.path.rsplit('/',1)[-1]!=file.name:raise ValueError('OFFICIAL_ARCHIVE_PROVENANCE_REQUIRED')
            with zipfile.ZipFile(file) as archive:
                names=archive.infolist()
                if len(names)!=1 or names[0].file_size>MAX_FILE_BYTES or names[0].filename!=file.stem+'.csv':raise ValueError('UNSAFE_ARCHIVE')
                with archive.open(names[0]) as stream:
                    rows=_rows(io.TextIOWrapper(stream,encoding='utf-8-sig'),step,mode,delay,True,max_rows-len(out));out.extend(rows)
        elif fmt in ('CSV','CSV_GZ'):
            opener=gzip.open if fmt=='CSV_GZ' else open
            with opener(file,'rt',encoding='utf-8-sig',newline='') as stream:
                out.extend(_rows(stream,step,mode,delay,False,max_rows-len(out)))
        else:raise ValueError('FILE_FORMAT')
        if sha256(file)!=meta['sha256']:raise ValueError('SOURCE_CHANGED_DURING_READ')
        read_bytes+=file.stat().st_size
        if read_bytes>512*1024*1024:raise ValueError('TOTAL_INPUT_LIMIT')
    bars=tuple(out);validate(bars,step)
    if bars[-1].available_at>captured:raise ValueError('FUTURE_OR_UNAVAILABLE_DATA')
    frames={tf:aggregate(bars,step,s) for tf,s in STEPS.items()}
    identity=dict(manifest=m,files=[f['sha256'] for f in files])
    return Dataset(bars,step,frames,m,digest(identity))


def _rows(stream,step,mode,delay,official,remaining):
    reader=csv.DictReader(stream)
    required={'timestamp','open','high','low','close','basevolume'} if official else {'time','open','high','low','close','volume'}
    if len(reader.fieldnames or [])!=len(set(reader.fieldnames or [])) or not required.issubset(reader.fieldnames or []) or mode=='OBSERVED' and 'available_at' not in reader.fieldnames:
        raise ValueError('CSV_SCHEMA')
    out=[]
    for row in reader:
        if len(out)>=remaining:raise ValueError('ROW_LIMIT')
        if None in row or any(not isinstance(v,str) or len(v)>512 for k,v in row.items()):raise ValueError('INVALID_CSV_ROW')
        raw=row['timestamp' if official else 'time']
        if not raw.isascii() or not raw.isdigit() or len(raw)>10:raise ValueError('TIMESTAMP_UNITS')
        t=int(raw)
        if mode=='OBSERVED':
            raw_available=row['available_at']
            if not raw_available.isascii() or not raw_available.isdigit() or len(raw_available)>10:raise ValueError('INVALID_AVAILABILITY')
            available=int(raw_available)
        else:available=t+step+delay
        if mode=='OBSERVED' and 'received_at' in row:
            receipt=row['received_at']
            if not receipt.isascii() or not receipt.isdigit() or len(receipt)>10 or int(receipt)<t+step:raise ValueError('INVALID_RECEIPT')
            available=max(available,int(receipt))
        b=Bar(t,*[decimal(row[k],zero=k=='volume') for k in ('open','high','low','close')],
              decimal(row['basevolume' if official else 'volume'],zero=True),available)
        out.append(b)
    return out
