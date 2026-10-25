"""Explicit local public Bitget REST/WS probe; no accounts, keys or order APIs."""
import argparse
import json
import os
from pathlib import Path
import time
import httpx
from websockets.sync.client import connect
from websockets.exceptions import WebSocketException


def main():
    if os.getenv('RENDER'):
        raise ValueError('LOCAL_PUBLIC_PROBE_ONLY')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('NEW_OUTPUT_REQUIRED')
    result=dict(scope='LOCAL_PUBLIC_ONLY_NOT_RENDER',production_changed=False,orders=0,frames={})
    for frame,channel,step in [('1m','candle1m',60),('5m','candle5m',300),('15m','candle15m',900),('1H','candle1H',3600)]:
        item={}
        try:
            r=httpx.get('https://api.bitget.com/api/v2/mix/market/candles',params=dict(symbol='BTCUSDT',productType='USDT-FUTURES',granularity=frame,limit=200),headers={'Origin':'http://127.0.0.1:8000'},timeout=12,follow_redirects=False)
            r.raise_for_status();body=r.json()
            item.update(rest_http=r.status_code,rest_code=body.get('code'),cors=r.headers.get('access-control-allow-origin'),rest=body,events=[])
            with connect('wss://ws.bitget.com/v2/ws/public',proxy=os.getenv('HTTPS_PROXY'),open_timeout=12,close_timeout=2,max_size=1048576) as ws:
                ws.send(json.dumps(dict(op='subscribe',args=[dict(instType='USDT-FUTURES',channel=channel,instId='BTCUSDT')])))
                deadline=time.monotonic()+25
                while len(item['events'])<4 and time.monotonic()<deadline:
                    raw=ws.recv(timeout=max(.1,min(10,deadline-time.monotonic())))
                    if raw=='pong':continue
                    msg=json.loads(raw)
                    if 'data' in msg:
                        item['events'].append(dict(received_at=time.time(),message=msg))
            current=[e for e in item['events'] if int(e['message']['data'][-1][0])//1000==int(e['received_at']//step)*step]
            changed=any(a['message']['data'][-1]!=b['message']['data'][-1] and a['message']['data'][-1][0]==b['message']['data'][-1][0] for a,b in zip(current,current[1:]))
            fresh=all(-3000<=e['received_at']*1000-int(e['message']['ts'])<=10000 for e in current)
            item.update(status='PASS' if changed and fresh and body.get('code')=='00000' else 'UNVERIFIED',current_candle_changed=changed,event_timestamps_fresh=fresh)
        except (httpx.HTTPError,WebSocketException,OSError,TimeoutError,ValueError,KeyError,TypeError) as exc:
            item.update(status='BLOCKED',error=type(exc).__name__)
        result['frames'][frame]=item
    result['status']='PASS' if all(i.get('status')=='PASS' for i in result['frames'].values()) else 'BLOCKED'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(status=result['status'],frames={k:{n:v for n,v in i.items() if n not in ('events','rest')} for k,i in result['frames'].items()})))

if __name__=='__main__':main()
