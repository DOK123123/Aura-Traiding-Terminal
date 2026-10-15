"""Explicit one-off rebind for the verified zones-only optimization; no reindex."""
import argparse,gzip,hashlib,json
from pathlib import Path
from app.intelligence.analogs import software,MAX_BYTES,AnalogIndex
from app.lab.models import canonical,digest

FILE='research/market_intelligence/structure.py'
OLD='984295140de91d696e6b693c2a54124ce8f02f169c71325aa9deef2deffacfe6'
NEW='9fd64bab64c49409f8a5c6893ab5d822cf8782783e01e17f07f79917f30ca1d3'
INPUT='e4db02f80f47d8b5071af987957106e0d560a5bf77d32db9af3cfde50ba9e82d'

def rebind(path,output):
    path=Path(path);output=Path(output)
    if path.stat().st_size>2*1024*1024:raise ValueError('ARTIFACT_SIZE')
    compressed=path.read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=INPUT:raise ValueError('UNEXPECTED_INPUT')
    with gzip.open(path,'rb') as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('ARTIFACT_SIZE')
    pack=json.loads(raw)
    if pack['content_sha256']!=digest({k:v for k,v in pack.items() if k!='content_sha256'}):raise ValueError('ARTIFACT_CHECKSUM')
    current=software();expected=dict(current);expected[FILE]=OLD
    if current[FILE]!=NEW or pack['software']!=expected:raise ValueError('UNEXPECTED_SOFTWARE')
    payload=digest({k:v for k,v in pack.items() if k not in ('software','content_sha256')})
    pack['software']=current;pack['content_sha256']=digest({k:v for k,v in pack.items() if k!='content_sha256'})
    if payload!=digest({k:v for k,v in pack.items() if k not in ('software','content_sha256')}):raise ValueError('PAYLOAD_CHANGED')
    AnalogIndex(pack)  # The same strict runtime validator, no compatibility bypass.
    result=gzip.compress(canonical(pack),compresslevel=9,mtime=0)
    if len(result)>2*1024*1024:raise ValueError('ARTIFACT_SIZE')
    output.write_bytes(result)
    return dict(input_sha256=INPUT,output_sha256=hashlib.sha256(result).hexdigest(),unchanged_payload_sha256=payload,states=len(pack['states']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(rebind(a.input,a.output),indent=2))
