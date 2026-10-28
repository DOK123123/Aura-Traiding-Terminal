"""Separate opt-in Render preview entrypoint. Does not import app.main/lifespan."""
import asyncio
from contextlib import asynccontextmanager
import os
import secrets
import json
import logging
import time
import websockets
from fastapi import Depends,FastAPI,HTTPException,Request,WebSocket
from fastapi.responses import HTMLResponse,FileResponse,JSONResponse,RedirectResponse
from app.paper.api import owner,basic,HEADERS
from app.manual_paper.api import router as manual_router
from app.manual_paper.service import Service
from app.manual_paper.bitget import fetch_execution_quote
from app.aura_trader5_api import router as analyst_router
from app.aura_trader5_service import AnalystService
from .config import parse
from .store import PreviewStore
from .page import page,ROOT,ASSETS
import httpx


async def preview_owner(request:Request):
    config=request.app.state.preview_config
    credentials=await basic(request)
    if (credentials is None or not secrets.compare_digest(credentials.username.encode(),b'aura')
            or not secrets.compare_digest(credentials.password.encode(),config.owner_password.encode())):
        raise HTTPException(401,'PREVIEW_OWNER_REQUIRED',headers={**HEADERS,'WWW-Authenticate':'Basic realm="Aura isolated preview"'})


@asynccontextmanager
async def lifespan(app):
    config=parse(os.environ)  # Fails BEFORE constructing any HTTP or storage client.
    app.state.preview_config=config
    app.state.preview_ws_token=secrets.token_urlsafe(32)
    store=PreviewStore(config);task=None
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
            app.state.preview_public_client=client
            app.state.preview_market_probe=asyncio.create_task(_preview_probe_history(client))
            app.state.preview_ws_diag={'probe':'PROBE_PENDING','last_stage':'PROBE_PENDING','counts':{}}
            app.state.preview_ws_probe=asyncio.create_task(_preview_probe_ws(app))
            app.state.aura_analyst=AnalystService()
            app.state.preview_store=store
            app.state.manual_paper=Service(store if config.manual_enabled else None,client=client,durable=True,
                                           error=None if config.manual_enabled else 'MANUAL_PAPER_DISABLED')
            if config.manual_enabled:task=asyncio.create_task(app.state.manual_paper.run_protection())
            app.state.preview_protection_task=task
            try:yield
            finally:
                try:
                    if task:
                        task.cancel()
                        try:await task
                        except asyncio.CancelledError:pass
                finally:
                    app.state.preview_market_probe.cancel()
                    app.state.preview_ws_probe.cancel()
                    await asyncio.gather(app.state.preview_market_probe,app.state.preview_ws_probe,return_exceptions=True)
                    await app.state.aura_analyst.close()
    finally:await asyncio.to_thread(store.close)

app=FastAPI(title='Isolated Aura Manual Preview',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.dependency_overrides[owner]=preview_owner
app.include_router(manual_router)
app.include_router(analyst_router)

@app.middleware('http')
async def isolate(request,call_next):
    if request.url.path!='/api/health':
        try:await preview_owner(request)
        except HTTPException as exc:return JSONResponse({'code':'PREVIEW_OWNER_REQUIRED'},status_code=401,headers=exc.headers)
        if request.method not in ('GET','HEAD'):
            if (request.method!='POST' or not request.url.path.startswith('/api/manual-paper/')
                    or request.headers.get('X-Aura-Preview-Confirm')!='manual-virtual'):
                return JSONResponse({'code':'PREVIEW_EXPLICIT_CONFIRMATION_REQUIRED'},status_code=403,headers=HEADERS)
    if request.method=='POST' and request.url.path=='/api/manual-paper/orders' and request.app.state.preview_config.manual_enabled:
        task=getattr(request.app.state,'preview_protection_task',None)
        if task is None or task.done():return JSONResponse({'code':'PREVIEW_PROTECTION_UNAVAILABLE'},503,headers=HEADERS)
    response=await call_next(request)
    for k,v in {**HEADERS,'X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"frame-ancestors 'none'"}.items():response.headers[k]=v
    return response



_preview_log=logging.getLogger('aura.preview.market')
_preview_quality_seen=set()

def _preview_history_quality(body,granularity,now=None):
    """Read-only clone of browser REST integrity checks, returns a safe reason code."""
    now=time.time() if now is None else now
    steps={'1m':60,'5m':300,'15m':900,'1H':3600,'4H':14400}
    step=steps.get(granularity)
    try:
        rows=body['data']
        if (body.get('code')!='00000' or not isinstance(rows,list) or not 101<=len(rows)<=201):
            return 'BAD_SIZE_OR_CODE'
        request_at=float(body['requestTime'])/1000
        if not 0<=now-request_at<=10:return 'STALE_REQUEST_TIME'
        times=[]
        for r in rows:
            if not isinstance(r,list) or len(r)<7:return 'INVALID_ROW'
            t=float(r[0])/1000
            vals=list(map(float,r[1:6]))
            o,h,l,c,v=vals
            if (not t.is_integer() or t%step or t>now or min(o,h,l,c)<=0
                    or v<0 or l>min(o,c) or h<max(o,c)):
                return 'INVALID_ROW_VALUES_OR_TIME'
            times.append(int(t))
        times.sort()
        if len(times)!=len(set(times)):return 'DUPLICATE_CANDLES'
        if any(b-a!=step for a,b in zip(times,times[1:])):return 'HISTORY_GAP'
        closed=[t for t in times if t+step<=now]
        if not closed or closed[-1]+step!=int(now//step)*step:
            return 'STALE_CLOSED_HISTORY'
        return 'PASS'
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,ZeroDivisionError):
        return 'INVALID_HISTORY_RESPONSE'

async def _preview_probe_history(client):
    """One safe public-only startup probe; never reads accounts or creates orders."""
    for granularity in ('1m','5m','15m','1H','4H'):
        try:
            response=await client.get(
                _PREVIEW_MARKET,params={'symbol':'BTCUSDT','productType':'USDT-FUTURES',
                                        'granularity':granularity,'limit':201},timeout=8,
                follow_redirects=False)
            response.raise_for_status()
            if len(response.content)>160000:raise ValueError('response limit')
            body=response.json()
            quality=_preview_history_quality(body,granularity)
            _preview_log.warning('PREVIEW_HISTORY_PROBE frame=%s quality=%s rows=%d',
                                 granularity,quality,len(body.get('data',[])))
        except (httpx.HTTPError,ValueError,TypeError,TimeoutError) as exc:
            _preview_log.warning('PREVIEW_HISTORY_PROBE frame=%s error=%s',
                                 granularity,type(exc).__name__)


# Diagnostic telemetry contains only fixed stage codes and counts, never owner secrets,
# WS query tokens, exchange data, client addresses, or third-party exception text.
def _preview_ws_mark(app,code):
    allowed={
        'PROBE_PENDING','PROBE_CONNECTED','PROBE_SUBSCRIBED','PROBE_ACK','PROBE_TICKER',
        'PROBE_TIMEOUT','PROBE_CONNECT_FAILED','PROBE_NO_TICKER','PROBE_BAD_REPLY',
        'BROWSER_ATTEMPT','BROWSER_REJECT_TOKEN','BROWSER_REJECT_ORIGIN',
        'BROWSER_ACCEPTED','UPSTREAM_CONNECTED','UPSTREAM_SUBSCRIBED',
        'UPSTREAM_EVENT','UPSTREAM_FAILED','BROWSER_CLOSED'
    }
    if code not in allowed:code='UPSTREAM_FAILED'
    state=getattr(app.state,'preview_ws_diag',None)
    if state is None:
        state={'probe':'PROBE_PENDING','last_stage':'PROBE_PENDING','counts':{}}
        app.state.preview_ws_diag=state
    state['last_stage']=code
    state['counts'][code]=state['counts'].get(code,0)+1
    if code.startswith('PROBE_'):state['probe']=code
    # One event log per stage occurrence. Avoid logging any WS URL including token.
    if state['counts'][code]<=3:
        _preview_log.warning('PREVIEW_WS_DIAG stage=%s count=%d',code,state['counts'][code])

async def _preview_probe_ws(app):
    """Non-trading startup probe of Bitget's fixed public ticker endpoint only."""
    _preview_ws_mark(app,'PROBE_PENDING')
    try:
        async with asyncio.timeout(13):
            async with websockets.connect(_PREVIEW_WS,open_timeout=8,close_timeout=2,max_size=1048576,ping_interval=20) as sock:
                _preview_ws_mark(app,'PROBE_CONNECTED')
                await sock.send(json.dumps({'op':'subscribe','args':[{'instType':'USDT-FUTURES','instId':'BTCUSDT','channel':'ticker'}]},separators=(',',':')))
                _preview_ws_mark(app,'PROBE_SUBSCRIBED')
                for _ in range(8):
                    msg=await asyncio.wait_for(sock.recv(),timeout=7)
                    if not isinstance(msg,str) or len(msg)>1048576:
                        _preview_ws_mark(app,'PROBE_BAD_REPLY');return
                    if msg=='pong':continue
                    try:data=json.loads(msg)
                    except (TypeError,ValueError):
                        _preview_ws_mark(app,'PROBE_BAD_REPLY');return
                    if data.get('event')=='error':
                        _preview_ws_mark(app,'PROBE_BAD_REPLY');return
                    if data.get('event')=='subscribe':
                        _preview_ws_mark(app,'PROBE_ACK');continue
                    if (data.get('arg',{}).get('channel')=='ticker'
                            and data.get('arg',{}).get('instId')=='BTCUSDT'
                            and data.get('arg',{}).get('instType')=='USDT-FUTURES'
                            and data.get('action') in {'snapshot','update'}
                            and isinstance(data.get('data'),list)):
                        _preview_ws_mark(app,'PROBE_TICKER');return
                _preview_ws_mark(app,'PROBE_NO_TICKER')
    except (TimeoutError,asyncio.TimeoutError):
        _preview_ws_mark(app,'PROBE_TIMEOUT')
    except asyncio.CancelledError:raise
    except Exception:
        _preview_ws_mark(app,'PROBE_CONNECT_FAILED')

# Fixed, public-market-only proxy for browsers where Bitget cross-origin REST/WS is blocked.
# No private exchange endpoints, credentials, trading orders, or user-supplied upstream URLs.
_PREVIEW_MARKET='https://api.bitget.com/api/v2/mix/market/candles'
_PREVIEW_WS='wss://ws.bitget.com/v2/ws/public'
_PREVIEW_CHANNELS=('candle1m','candle5m','candle15m','candle1H','candle4H','ticker')
_PREVIEW_SUBSCRIBE={'op':'subscribe','args':[{'instType':'USDT-FUTURES','instId':'BTCUSDT','channel':ch} for ch in _PREVIEW_CHANNELS]}

@app.get('/api/preview/bitget/candles')
async def preview_public_candles(request:Request):
    qp=request.query_params
    if (set(qp.keys())!={'symbol','productType','granularity','limit'}
            or qp.get('symbol')!='BTCUSDT' or qp.get('productType')!='USDT-FUTURES'
            or qp.get('granularity') not in {'1m','5m','15m','1H','4H'}
            or qp.get('limit')!='201'):
        raise HTTPException(400,'PUBLIC_MARKET_QUERY_FORBIDDEN')
    try:
        async with request.app.state.preview_public_client.stream(
            'GET',_PREVIEW_MARKET,
            params=dict(symbol='BTCUSDT',productType='USDT-FUTURES',
                        granularity=qp['granularity'],limit='201'),
            timeout=8,follow_redirects=False) as response:
            if response.status_code!=200:raise ValueError('UPSTREAM_HTTP')
            data=bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data)>160000:raise ValueError('UPSTREAM_LIMIT')
        value=json.loads(data)
        if (not isinstance(value,dict) or value.get('code')!='00000'
                or not isinstance(value.get('data'),list) or not 101<=len(value['data'])<=201):
            raise ValueError('UPSTREAM_FORMAT')
        frame=qp['granularity']
        quality=_preview_history_quality(value,frame)
        if quality!='PASS' or frame not in _preview_quality_seen:
            _preview_quality_seen.add(frame)
            _preview_log.warning('PREVIEW_HISTORY_REQUEST frame=%s quality=%s rows=%d',frame,quality,len(value['data']))
        if quality!='PASS':raise ValueError('UNVERIFIED_UPSTREAM_HISTORY')
        return JSONResponse(value,headers={'Cache-Control':'no-store'})
    except (httpx.HTTPError,ValueError,TypeError,TimeoutError):
        return JSONResponse({'code':'PUBLIC_MARKET_UNAVAILABLE'},status_code=503,
                            headers={'Cache-Control':'no-store'})

@app.websocket('/ws/preview/bitget')
async def preview_public_stream(ws:WebSocket):
    _preview_ws_mark(ws.app,'BROWSER_ATTEMPT')
    token=ws.query_params.get('token','')
    correct=ws.app.state.preview_ws_token
    expected_origin='https://'+ws.headers.get('host','')
    if not token or not secrets.compare_digest(token,correct):
        _preview_ws_mark(ws.app,'BROWSER_REJECT_TOKEN')
        await ws.close(code=1008)
        return
    if ws.headers.get('origin')!=expected_origin:
        _preview_ws_mark(ws.app,'BROWSER_REJECT_ORIGIN')
        await ws.close(code=1008)
        return
    await ws.accept()
    _preview_ws_mark(ws.app,'BROWSER_ACCEPTED')
    try:
        async with websockets.connect(_PREVIEW_WS,open_timeout=8,close_timeout=3,
                                      max_size=1048576,ping_interval=20) as upstream:
            _preview_ws_mark(ws.app,'UPSTREAM_CONNECTED')
            await upstream.send(json.dumps(_PREVIEW_SUBSCRIBE,separators=(',',':')))
            _preview_ws_mark(ws.app,'UPSTREAM_SUBSCRIBED')
            async def bitget_to_browser():
                async for msg in upstream:
                    if not isinstance(msg,str) or len(msg)>1048576:break
                    _preview_ws_mark(ws.app,'UPSTREAM_EVENT')
                    await ws.send_text(msg)
            async def browser_to_bitget():
                while True:
                    msg=await ws.receive_text()
                    if msg=='ping':
                        await ws.send_text('pong')
                        continue
                    # Browser Hub sends its fixed subscribe request. Server already subscribed.
                    try:
                        if json.loads(msg)==_PREVIEW_SUBSCRIBE:continue
                    except (TypeError,ValueError):pass
                    break
            async def keepalive():
                while True:
                    await asyncio.sleep(20)
                    await upstream.send('ping')
            tasks=[asyncio.create_task(f()) for f in (bitget_to_browser,browser_to_bitget,keepalive)]
            try:
                await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except Exception:
        # Safe failure: client Hub invalidates ALL quotes and retries. Never synthesize prices.
        _preview_ws_mark(ws.app,'UPSTREAM_FAILED')
    _preview_ws_mark(ws.app,'BROWSER_CLOSED')
    try:await ws.close(code=1001)
    except (RuntimeError,OSError):pass


@app.get('/api/preview/ws-diagnostics')
async def preview_ws_diagnostics(request:Request):
    state=getattr(request.app.state,'preview_ws_diag',{})
    return JSONResponse({
        'scope':'ISOLATED_MANUAL_PREVIEW',
        'read_only':True,
        'upstream_messages_seen':state.get('counts',{}).get('UPSTREAM_EVENT',0),
        'probe':state.get('probe','PROBE_PENDING'),
        'last_stage':state.get('last_stage','PROBE_PENDING'),
        'counts':dict(state.get('counts',{})),
    },headers={'Cache-Control':'no-store'})

@app.get('/api/health')
async def health():
    return {'status':'ok','scope':'ISOLATED_MANUAL_PREVIEW','exchange_execution':False,'active43_controller_enabled':False,'automatic_entry_scheduler_enabled':False}

@app.get('/')
async def index(request:Request):return HTMLResponse(page(request.app.state.preview_ws_token),headers={'Cache-Control':'no-store'})

@app.get('/api/paper/login')
async def login():return RedirectResponse('/',303)

@app.get('/static/{name:path}')
async def asset(name:str):
    if name not in ASSETS:raise HTTPException(404)
    return FileResponse(ROOT/'static'/name)

@app.get('/api/preview/readiness')
async def readiness(request:Request):
    # Read-only: neither load/account seed nor protect/tick is called here.
    config=request.app.state.preview_config;result=dict(scope='ISOLATED_MANUAL_PREVIEW',manual_enabled=config.manual_enabled,
        state_changed=False,supabase='ERROR',bitget='ERROR',ready=False,exchange_execution=False)
    try:
        async with asyncio.timeout(12):await asyncio.to_thread(request.app.state.preview_store.verify_scope)
        result['supabase']='ISOLATED_SCOPE_CONFIRMED'
    except (ValueError,TimeoutError):result['storage_code']='PREVIEW_SCOPE_NOT_CONFIRMED'
    try:
        async with asyncio.timeout(10):await fetch_execution_quote(request.app.state.manual_paper.client)
        result['bitget']='CONNECTED'
    except (ValueError,TimeoutError):result['market_code']='PUBLIC_MARKET_NOT_CONFIRMED'
    task=getattr(request.app.state,'preview_protection_task',None)
    result['protection_worker']='ACTIVE' if task is not None and not task.done() else 'OFF'
    result['manual_operations_ready']=config.manual_enabled and result['protection_worker']=='ACTIVE' and result['supabase']=='ISOLATED_SCOPE_CONFIRMED' and result['bitget']=='CONNECTED'
    result['ready']=result['supabase']=='ISOLATED_SCOPE_CONFIRMED' and result['bitget']=='CONNECTED'
    return result
