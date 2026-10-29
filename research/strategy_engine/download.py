"""Public Bitget BTCUSDT history, fixed host, no credentials or dependencies."""
import json,time,urllib.request,urllib.parse,hashlib,os
from pathlib import Path
out=Path(os.environ.get('AURA_RESEARCH_OUTPUT','/tmp/aura-strategy-data'));out.mkdir(exist_ok=True)
start=int(os.environ.get('AURA_RESEARCH_START_MS','1759276800000')) # 2025-10-01 UTC; development data, NOT untouched OOS
end=1793232000000 # 2026-10-29 UTC
rows={}
previous_oldest=None
while end>start:
    q=urllib.parse.urlencode(dict(symbol='BTCUSDT',productType='USDT-FUTURES',granularity='15m',limit=200,endTime=end))
    with urllib.request.urlopen('https://api.bitget.com/api/v2/mix/market/history-candles?'+q,timeout=20) as r: body=json.load(r)
    if body.get('code')!='00000' or not body.get('data'):break
    data=body['data'];old=min(int(x[0]) for x in data)
    if previous_oldest is not None and old>=previous_oldest:raise ValueError('PAGINATION_FAILED')
    previous_oldest=old
    for x in data:
        if int(x[0])>=start:rows[int(x[0])]=x
    end=old+1800000;print(json.dumps(dict(downloaded=len(rows),oldest_ms=old)),flush=True);time.sleep(.08)
    if len(rows)>40000:break
values=[dict(time=k//1000,open=float(v[1]),high=float(v[2]),low=float(v[3]),close=float(v[4]),volume=float(v[5])) for k,v in sorted(rows.items())]
assert all(b['time']-a['time']==900 for a,b in zip(values,values[1:])), 'GAP'
p=out/'15m.json';p.write_text(json.dumps(values));print(json.dumps(dict(rows=len(values),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),first=values[0]['time'] if values else None,last=values[-1]['time'] if values else None)))
