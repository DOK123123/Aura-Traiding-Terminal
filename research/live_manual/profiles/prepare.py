"""Validate/hash local official archives before native JS minute-prefix replay."""
import argparse,json,hashlib
from pathlib import Path
from research.live_manual.replay import load

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    bars,sources=load(a.input)
    value=dict(source='BITGET_USDT_FUTURES_BTCUSDT',manifest=dict(sources=sources,rows=len(bars),first=bars[0].time,end_exclusive=bars[-1].time+60,gaps=0,duplicates=0,input_manifest_sha256=hashlib.sha256((a.input/'manifest.json').read_bytes()).hexdigest()),rows=[[b.time,b.open,b.high,b.low,b.close,b.volume] for b in bars])
    a.output.write_text(json.dumps(value,separators=(',',':')))
if __name__=='__main__':main()
