"""Fixed official public futures GET/WS probes; results are diagnostics, not quotes."""
import asyncio
import io
import gzip
import json
import re
import socket
import ssl
import time
from decimal import Decimal, InvalidOperation

import httpx
from websockets.asyncio.client import connect

REST = {'BINGX':'https://open-api.bingx.com', 'BITGET':'https://api.bitget.com'}
WS = {'BINGX':'wss://open-api-swap.bingx.com/swap-market', 'BITGET':'wss://ws.bitget.com/v2/ws/public'}
PATHS = {
 'BINGX':{'contract':'/openApi/swap/v2/quote/contracts','ticker':'/openApi/swap/v2/quote/ticker','mark':'/openApi/swap/v2/quote/premiumIndex','candles':'/openApi/swap/v3/quote/klines'},
 'BITGET':{'contract':'/api/v2/mix/market/contracts','ticker':'/api/v2/mix/market/ticker','candles':'/api/v2/mix/market/candles'},
}
INTERVALS = {'15m':900000,'1h':3600000,'4h':14400000}

class ProbeError(Exception):
    def __init__(self, code, status='INVALID_RESPONSE'):
        super().__init__(code)
        self.code, self.status = code, status

def number(value, positive=True):
    if isinstance(value, bool) or not isinstance(value,(str,int,float)) or len(str(value))>80:
        raise ProbeError('INVALID_NUMBER')
    try: d=Decimal(str(value))
    except InvalidOperation: raise ProbeError('INVALID_NUMBER') from None
    if not d.is_finite() or d<0 or positive and d==0 or d.adjusted()>15 or d!=0 and d.adjusted() < -18:
        raise ProbeError('INVALID_NUMBER')
    return d

def timestamp(value):
    if isinstance(value,bool) or not re.fullmatch(r'\d{13}',str(value)):
        raise ProbeError('INVALID_TIMESTAMP')
    return int(value)

def fresh(value, now, ttl=30000):
    at=timestamp(value)
    if not -3000 <= now*1000-at <= ttl: raise ProbeError('STALE_DATA','PARTIALLY_AVAILABLE')
    return at

def identity(exchange):
    return dict(exchange=exchange,market_type='USDT_PERPETUAL',symbol='BTC-USDT' if exchange=='BINGX' else 'BTCUSDT',settlement='USDT')

def contract(exchange,data):
    if not isinstance(data,list): raise ProbeError('INVALID_CONTRACT')
    rows=[r for r in data if isinstance(r,dict) and r.get('symbol')==identity(exchange)['symbol']]
    if len(rows)!=1: raise ProbeError('CONTRACT_MISMATCH')
    r=rows[0]
    if exchange=='BINGX':
        valid=r.get('currency')=='USDT' and r.get('asset')=='BTC' and r.get('status')==1
    else:
        valid=r.get('baseCoin')=='BTC' and r.get('quoteCoin')=='USDT' and r.get('symbolType')=='perpetual' and r.get('supportMarginCoins')==['USDT'] and r.get('symbolStatus')=='normal'
    if not valid: raise ProbeError('CONTRACT_MISMATCH')
    return identity(exchange)

def ticker(exchange,data,now):
    if exchange=='BITGET':
        if not isinstance(data,list) or len(data)!=1: raise ProbeError('INVALID_TICKER')
        data=data[0]
    if not isinstance(data,dict) or data.get('symbol')!=identity(exchange)['symbol']: raise ProbeError('SYMBOL_MISMATCH')
    at=fresh(data.get('closeTime') if exchange=='BINGX' else data.get('ts'),now)
    last=str(number(data.get('lastPrice') if exchange=='BINGX' else data.get('lastPr')))
    mark=data.get('markPrice')
    return dict(last_price=last,mark_price=str(number(mark)) if mark is not None else None,server_at_ms=at,freshness='FRESH')

def mark(data,now):
    if not isinstance(data,dict) or data.get('symbol')!='BTC-USDT': raise ProbeError('SYMBOL_MISMATCH')
    # REST updateTime may refer to funding schedule, not mark-price freshness.
    # Never substitute receipt time for a trustworthy quote timestamp.
    value=str(number(data.get('markPrice')))
    at=data.get('updateTime')
    try: fresh(at,now)
    except ProbeError: return dict(mark_price=value,mark_freshness='UNVERIFIED',mark_at_ms=at if isinstance(at,int) else None)
    return dict(mark_price=value,mark_freshness='FRESH',mark_at_ms=at)

def candles(exchange,data,tf,now):
    if not isinstance(data,list) or not 1<=len(data)<=10: raise ProbeError('INVALID_CANDLES')
    step=INTERVALS[tf]; rows=[]
    for r in data:
        if exchange=='BINGX':
            if not isinstance(r,dict):raise ProbeError('INVALID_CANDLE')
            at=timestamp(r.get('time')); values=[r.get(k) for k in ('open','high','low','close','volume')]
        else:
            if not isinstance(r,list) or len(r)!=7:raise ProbeError('INVALID_CANDLE')
            at=timestamp(r[0]);values=r[1:6]
        o,h,l,c=[number(v) for v in values[:4]];number(values[4],False)
        if at%step or h<max(o,c) or l>min(o,c) or h<l or at>now*1000+3000:raise ProbeError('INVALID_CANDLE')
        rows.append(at)
    if len(set(rows))!=len(rows):raise ProbeError('DUPLICATE_CANDLE')
    if rows!=sorted(rows) and rows!=sorted(rows,reverse=True):raise ProbeError('CANDLE_ORDER')
    rows=sorted(rows)
    if any(b-a!=step for a,b in zip(rows,rows[1:])):raise ProbeError('MISSING_CANDLE')
    closed=[at for at in rows if at+step<=now*1000]
    if not closed:raise ProbeError('NO_CLOSED_CANDLES')
    expected=int(now*1000)//step*step-step
    if closed[-1]!=expected:raise ProbeError('STALE_CANDLES','PARTIALLY_AVAILABLE')
    return dict(count=len(closed),forming_excluded=len(rows)-len(closed),last_closed_open_ms=closed[-1],last_closed_end_ms=closed[-1]+step,freshness='FRESH')

def network_error(exc):
    chain=[]; item=exc
    for _ in range(6):
        if item is None:break
        chain.append(item);item=item.__cause__ or item.__context__
    if any(isinstance(e,(TimeoutError,httpx.TimeoutException)) for e in chain):return ProbeError('TIMEOUT','TIMEOUT')
    if any(isinstance(e,socket.gaierror) for e in chain):return ProbeError('DNS_ERROR','UNAVAILABLE')
    if any(isinstance(e,ssl.SSLError) for e in chain):return ProbeError('TLS_ERROR','UNAVAILABLE')
    response=getattr(exc,'response',None); status=getattr(response,'status_code',None)
    if status in (403,451):return ProbeError('HTTP_'+str(status),'BLOCKED_'+str(status))
    if status==429:return ProbeError('HTTP_429','RATE_LIMITED')
    return ProbeError('NETWORK_ERROR','UNAVAILABLE')

async def get(client,exchange,kind,tf=None):
    """Only this closed GET allowlist can reach the network. Never follow redirects."""
    started=time.monotonic();meta={}
    params={'symbol':identity(exchange)['symbol']}
    if exchange=='BITGET':params['productType']='USDT-FUTURES'
    if kind=='candles':params.update(limit='5',**({'interval':tf} if exchange=='BINGX' else {'granularity':{'15m':'15m','1h':'1H','4h':'4H'}[tf]}))
    try:
        async with asyncio.timeout(6):
            async with client.stream('GET',REST[exchange]+PATHS[exchange][kind],params=params,follow_redirects=False) as response:
                meta['http_status']=response.status_code
                meta['received_at_ms']=int(time.time()*1000)
                if response.status_code in (403,451):raise ProbeError('HTTP_'+str(response.status_code),'BLOCKED_'+str(response.status_code))
                if response.status_code==429:raise ProbeError('HTTP_429','RATE_LIMITED')
                if response.status_code!=200:raise ProbeError('HTTP_ERROR','UNAVAILABLE')
                body=bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body)>1024*1024:raise ProbeError('RESPONSE_TOO_LARGE')
                try: payload=json.loads(body)
                except (ValueError,UnicodeError):raise ProbeError('MALFORMED_JSON') from None
                if not isinstance(payload,dict):raise ProbeError('INVALID_RESPONSE')
                code=payload.get('code');ok=type(code) is int and code==0 if exchange=='BINGX' else code=='00000'
                meta['api_code']=str(code) if re.fullmatch(r'-?\d{1,12}',str(code)) else None
                if not ok:raise ProbeError('API_ERROR','RATE_LIMITED' if str(code) in ('100410','100429','429','40015') else 'UNAVAILABLE')
                data=payload.get('data');now=time.time()
                value=contract(exchange,data) if kind=='contract' else ticker(exchange,data,now) if kind=='ticker' else mark(data,now) if kind=='mark' else candles(exchange,data,tf,now)
                return dict(status='AVAILABLE',**meta,**value,latency_ms=round((time.monotonic()-started)*1000))
    except (ProbeError,httpx.HTTPError,TimeoutError) as exc:
        error=exc if isinstance(exc,ProbeError) else network_error(exc)
        return dict(status=error.status,code=error.code,**meta,latency_ms=round((time.monotonic()-started)*1000))

def ws_message(exchange,raw,now):
    if isinstance(raw,bytes):
        if len(raw)>65536:raise ProbeError('WS_MESSAGE_TOO_LARGE')
        if raw[:2]==b'\x1f\x8b':
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:raw=stream.read(65537)
            if len(raw)>65536:raise ProbeError('WS_MESSAGE_TOO_LARGE')
        raw=raw.decode('utf-8')
    if raw in ('Ping','Pong','ping','pong'):return {'heartbeat':raw}
    d=json.loads(raw)
    if not isinstance(d,dict):raise ProbeError('INVALID_WS_MESSAGE')
    if exchange=='BINGX':
        if d.get('code',0)!=0:raise ProbeError('SUBSCRIPTION_REJECTED')
        topic=d.get('dataType');v=d.get('data')
        if topic not in ('BTC-USDT@lastPrice','BTC-USDT@markPrice') or not v:return None
        if not isinstance(v,dict) or v.get('s')!='BTC-USDT':raise ProbeError('SYMBOL_MISMATCH')
        at=fresh(v.get('E'),now)
        return dict(server_at_ms=at,**{'last_price' if topic.endswith('@lastPrice') else 'mark_price':str(number(v.get('c') if topic.endswith('@lastPrice') else v.get('p')))})
    if d.get('event')=='error':raise ProbeError('SUBSCRIPTION_REJECTED')
    if not d.get('data'):return None
    if d.get('arg')!={'instType':'USDT-FUTURES','channel':'ticker','instId':'BTCUSDT'}:raise ProbeError('SYMBOL_MISMATCH')
    return ticker('BITGET',d['data'],now)

async def websocket(exchange,connector=connect):
    started=time.monotonic();errors=[]
    for attempt in range(2):
        result={};heartbeat=False;pong=False
        try:
            async with asyncio.timeout(9):
                async with connector(WS[exchange],open_timeout=3,close_timeout=1,ping_interval=None,max_size=65536,max_queue=8) as ws:
                    if exchange=='BINGX':
                        for topic in ('lastPrice','markPrice'):await ws.send(json.dumps(dict(id='aura-diagnostic-'+topic,reqType='sub',dataType='BTC-USDT@'+topic)))
                    else:
                        await ws.send(json.dumps(dict(op='subscribe',args=[dict(instType='USDT-FUTURES',channel='ticker',instId='BTCUSDT')])));await ws.send('ping')
                    # Also verify transport ping/pong; application heartbeat reported separately.
                    waiter=await ws.ping();await asyncio.wait_for(waiter,2);pong=True
                    for _ in range(100):
                        raw=await asyncio.wait_for(ws.recv(),4)
                        value=ws_message(exchange,raw,time.time())
                        if not value:continue
                        if 'heartbeat' in value:
                            heartbeat=True
                            if value['heartbeat']=='Ping':await ws.send('Pong')
                            continue
                        if not result:result['first_message_ms']=round((time.monotonic()-started)*1000)
                        result.update(value)
                        if result.get('last_price') and result.get('mark_price'):
                            return dict(status='AVAILABLE',**result,attempts=attempt+1,reconnect_test='NOT_TESTED' if attempt==0 else 'RECOVERED',transport_pong=pong,application_heartbeat=heartbeat)
        except asyncio.CancelledError:raise
        except Exception as exc:
            error=exc if isinstance(exc,ProbeError) else network_error(exc) if not isinstance(exc,(ValueError,TypeError,UnicodeError)) else ProbeError('INVALID_WS_MESSAGE')
            errors.append(dict(status=error.status,code=error.code))
        if result:return dict(status='PARTIALLY_AVAILABLE',**result,code='MISSING_MARK_OR_LAST',attempts=attempt+1,transport_pong=pong,application_heartbeat=heartbeat)
        if errors and errors[-1]['status'] in ('BLOCKED_403','BLOCKED_451','RATE_LIMITED'):break
        if attempt==0:await asyncio.sleep(.5)
    return dict(errors[-1] if errors else dict(status='UNAVAILABLE',code='WS_DISCONNECTED'),attempts=len(errors),reconnect_test='FAILED' if len(errors)>1 else 'NOT_TESTED')

async def exchange_probe(exchange,client):
    # Sequential REST calls bound upstream pressure; WS is independent and bounded.
    output=dict(identity=identity(exchange),tested_at_ms=int(time.time()*1000),candles={})
    output['contract']=await get(client,exchange,'contract')
    if output['contract']['status']!='AVAILABLE':
        output.update(rest=dict(output['contract']),websocket=dict(status='NOT_TESTED',code='CONTRACT_NOT_VERIFIED'))
        return output
    output['rest']=await get(client,exchange,'ticker')
    if exchange=='BINGX' and output['rest']['status'] not in ('BLOCKED_403','BLOCKED_451','RATE_LIMITED'):output['mark']=await get(client,exchange,'mark')
    elif output['rest']['status']=='AVAILABLE' and not output['rest'].get('mark_price'):output['rest'].update(status='PARTIALLY_AVAILABLE',code='MISSING_MARK_PRICE')
    if output['rest']['status'] in ('BLOCKED_403','BLOCKED_451','RATE_LIMITED'):
        output['websocket']=dict(status='NOT_TESTED',code='REST_ACCESS_RESTRICTED')
        return output
    for tf in INTERVALS:
        output['candles'][tf]=await get(client,exchange,'candles',tf)
        if output['candles'][tf]['status'] in ('BLOCKED_403','BLOCKED_451','RATE_LIMITED'):
            output['websocket']=dict(status='NOT_TESTED',code='REST_ACCESS_RESTRICTED')
            return output
    if exchange=='BINGX' and output.get('mark',{}).get('mark_price'):
        output['rest'].update({k:v for k,v in output['mark'].items() if k in ('mark_price','mark_at_ms','mark_freshness')})
        if output['rest'].get('last_price') and output['mark'].get('mark_freshness')!='FRESH':output['rest'].update(status='PARTIALLY_AVAILABLE',code='MARK_FRESHNESS_UNVERIFIED')
    if exchange=='BINGX' and output['rest'].get('last_price') and not output.get('mark',{}).get('mark_price'):
        output['rest'].update(status='PARTIALLY_AVAILABLE',code='MISSING_MARK_PRICE')
    output['websocket']=await websocket(exchange)
    return output
