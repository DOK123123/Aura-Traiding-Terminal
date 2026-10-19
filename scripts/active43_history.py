"""Local-only official Binance Spot 5m archives, independently checked HTTPS SHA256."""
import argparse,csv,hashlib,io,json,os,zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
import httpx
from app.lab.models import Bar,validate_series
from app.active43.strategies import PROTOCOL
from app.lab.models import digest
ROOT='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/'

def require_spot_protocol():
    # These frozen public artifacts belong to the original Spot commit. Never
    # relabel its CSV, cost model or selection with the current Bybit core.
    if not PROTOCOL['source'].startswith('BINANCE_SPOT'):
        raise ValueError('ARCHIVED_SPOT_STUDY_REQUIRES_COMMIT_6284A3C')


def load(path):
    path=Path(path)
    if path.stat().st_size>40*1024*1024:raise ValueError('HISTORY_LIMIT')
    bars=[]
    with path.open() as stream:
        for row in csv.reader(stream):
            if len(row)!=6 or len(bars)>=130000:raise ValueError('HISTORY_FORMAT_OR_LIMIT')
            bars.append(Bar(int(row[0]),*map(D,row[1:])))
    validate_series(bars,300,int(datetime.now(timezone.utc).timestamp()))
    return bars

def aggregate(bars,step):
    if step==300:return bars
    result=[];groups={}
    for b in bars:
        bucket=b.time//step*step
        groups.setdefault(bucket,[]).append(b)
    for t,g in groups.items():
        if len(g)==step//300 and g[0].time==t and g[-1].time+300==t+step:
            result.append(Bar(t,g[0].open,max(b.high for b in g),min(b.low for b in g),g[-1].close,sum((b.volume for b in g),D(0))))
    return result

def download(folder):
    require_spot_protocol()
    if os.getenv('RENDER'):raise ValueError('LOCAL_ONLY')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    # Freeze protocol before fetching/inspecting candidate outcomes.
    protocol=folder/'protocol.json'
    if protocol.exists() and json.loads(protocol.read_text())!=PROTOCOL:raise ValueError('PROTOCOL_CHANGED')
    protocol.write_text(json.dumps(PROTOCOL,indent=2))
    months=[f'2025-{m:02d}' for m in range(8,13)]+[f'2026-{m:02d}' for m in range(1,10)]
    def fetch(month):
        name='BTCUSDT-5m-'+month+'.zip';url=ROOT+name
        with httpx.Client(timeout=25,follow_redirects=False) as client:
            checksum=client.get(url+'.CHECKSUM');checksum.raise_for_status();parts=checksum.text.strip().split()
            if len(parts)!=2 or parts[1].lstrip('*')!=name:raise ValueError('CHECKSUM_NAME')
            local=folder/name
            if local.exists():raw=local.read_bytes()
            else:
                raw=bytearray()
                with client.stream('GET',url) as r:
                    r.raise_for_status()
                    for chunk in r.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>8*1024*1024:raise ValueError('ARCHIVE_LIMIT')
                raw=bytes(raw)
            if hashlib.sha256(raw).hexdigest()!=parts[0].lower():raise ValueError('CHECKSUM_MISMATCH')
            local.write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if z.namelist()!=[name[:-4]+'.csv'] or z.infolist()[0].file_size>16*1024*1024:raise ValueError('ZIP_FORMAT')
            data=z.read(z.infolist()[0])
        bars=[]
        for row in csv.reader(io.StringIO(data.decode())):
            stamp=int(row[0]);close=int(row[6]);unit=1000000 if stamp>=10**15 else 1000
            if stamp%unit or close!=stamp+300*unit-1:raise ValueError('TIMESTAMP_OR_CLOSE_TIME')
            bars.append(Bar(stamp//unit,*map(D,row[1:6])))
        return bars,dict(url=url,checksum_url=url+'.CHECKSUM',zip_sha256=parts[0].lower(),csv_sha256=hashlib.sha256(data).hexdigest(),count=len(bars))
    with ThreadPoolExecutor(max_workers=3) as pool:parts=list(pool.map(fetch,months))
    bars=[b for batch,_ in parts for b in batch];validate_series(bars,300,int(datetime.now(timezone.utc).timestamp()))
    path=folder/'btc-5m.csv'
    text='\n'.join(','.join([str(b.time),*[str(getattr(b,k)) for k in ('open','high','low','close','volume')]]) for b in bars)+'\n'
    path.write_text(text)
    report=dict(source='BINANCE_SPOT_BTCUSDT_5m_OFFICIAL_HTTPS',checksums_verified=True,files=[m for _,m in parts],
        csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),count=len(bars),protocol_hash=digest(PROTOCOL),
        evaluation_start=int(datetime(2025,10,1,tzinfo=timezone.utc).timestamp()),evaluation_end=int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()),
        synthetic=False,futures=False,previous_project_holdout_overlap=True,
        limitation='Chronological holdout within this frozen experiment, not a pristine project-wide holdout. Requires new forward validation.')
    (folder/'provenance.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(count=len(bars),csv=str(path))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True);download(p.parse_args().folder)
