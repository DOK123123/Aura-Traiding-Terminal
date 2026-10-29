"""Explicit standalone public-only probe. Never a production or order client."""
import json,time
from pathlib import Path
import httpx
from websockets.sync.client import connect
def main():
    report={'scope':'DEVELOPMENT_PUBLIC_NETWORK_ONLY','production_changed':False,'rest':{},'websocket':{}}
    import argparse
    parser=argparse.ArgumentParser(description='Public Bitget read-only probe; never run in regression CI')
    parser.add_argument('--output-dir',type=Path,required=True)
    root=parser.parse_args().output_dir
    root.mkdir(parents=True,exist_ok=False)
    with httpx.Client(timeout=10,follow_redirects=False) as client:
     for frame in ('1m','5m','15m','1H','4H'):
      try:
       started=time.time();r=client.get('https://api.bitget.com/api/v2/mix/market/candles',params={'symbol':'BTCUSDT','productType':'USDT-FUTURES','granularity':frame,'limit':201});r.raise_for_status();b=r.json();report['rest'][frame]={'http_status':r.status_code,'code':b.get('code'),'rows':len(b.get('data',[])),'duration_ms':round((time.time()-started)*1000)};(root/(frame+'.json')).write_text(json.dumps(b))
      except (httpx.HTTPError,ValueError) as e:report['rest'][frame]={'error_type':type(e).__name__}
    try:
     with connect('wss://ws.bitget.com/v2/ws/public',open_timeout=10,close_timeout=2) as ws:
      channels=['ticker','candle1m','candle5m','candle15m','candle1H','candle4H'];ws.send(json.dumps({'op':'subscribe','args':[{'instType':'USDT-FUTURES','instId':'BTCUSDT','channel':c} for c in channels]}));end=time.monotonic()+18;seen={};messages=[]
      while time.monotonic()<end:
       try:raw=ws.recv(timeout=2)
       except TimeoutError:continue
       if raw=='pong':continue
       b=json.loads(raw)
       if b.get('data'):
        messages.append(b);ch=b.get('arg',{}).get('channel');seen[ch]=seen.get(ch,0)+1
       if len(messages)>=40:break
      (root/'ws.json').write_text(json.dumps(messages));report['websocket']={'received':seen,'messages':len(messages)}
    except Exception as e:report['websocket']={'error_type':type(e).__name__}
    (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
