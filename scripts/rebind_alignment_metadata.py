"""One-off strict metadata-only rebind after additive alignment instrumentation.

Does not regenerate analog events, change runtime validation or loosen hashes.
Run only together with baseline/prefix equivalence evidence in the alignment report.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from app.intelligence.analogs import software,MAX_BYTES,AnalogIndex
from app.lab.models import canonical,digest

INPUT='05a669e562f78db1453dc57d88206287a03e00d0ebdf9916a667e840e6f96fa6'
CHANGES={
    'app/intelligence/market_context.py':(
        '6776c9bcff8ddd2c90a3d6635025ed98686ced25a05e9e2bb221267115bd9ce0',
        '04070137ed41a3595c73d87234722fc20a9e00f514c8231f1ba1b70c82680c05'),
    'research/market_intelligence/structure.py':(
        '9fd64bab64c49409f8a5c6893ab5d822cf8782783e01e17f07f79917f30ca1d3',
        'ad347adcfb88483f907700c8e05e231667eeba1bf4f85b8103bd8b4e70b42c17')}


def rebind(path: Path, output: Path) -> dict:
    compressed=path.read_bytes()
    if len(compressed)>2*1024*1024 or hashlib.sha256(compressed).hexdigest()!=INPUT:
        raise ValueError('UNEXPECTED_INPUT')
    with gzip.open(path,'rb') as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('ARTIFACT_SIZE')
    pack=json.loads(raw)
    if pack['content_sha256']!=digest({k:v for k,v in pack.items() if k!='content_sha256'}):
        raise ValueError('ARTIFACT_CHECKSUM')
    current=software();expected=dict(current)
    for name,(old,new) in CHANGES.items():
        if current[name]!=new:raise ValueError('UNEXPECTED_SOFTWARE')
        expected[name]=old
    if pack['software']!=expected:raise ValueError('UNEXPECTED_SOFTWARE')
    payload=digest({k:v for k,v in pack.items() if k not in ('software','content_sha256')})
    pack['software']=current;pack['content_sha256']=digest({k:v for k,v in pack.items() if k!='content_sha256'})
    if payload!=digest({k:v for k,v in pack.items() if k not in ('software','content_sha256')}):
        raise ValueError('PAYLOAD_CHANGED')
    AnalogIndex(pack)
    result=gzip.compress(canonical(pack),compresslevel=9,mtime=0)
    if len(result)>2*1024*1024:raise ValueError('ARTIFACT_SIZE')
    output.write_bytes(result)
    return dict(input_sha256=INPUT,output_sha256=hashlib.sha256(result).hexdigest(),
        unchanged_payload_sha256=payload,states=len(pack['states']),changed_software=list(CHANGES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();print(json.dumps(rebind(args.input,args.output),indent=2))
