"""Owner-triggered, off-by-default, memory-only connectivity report."""
import asyncio
import os
import logging
import time
from copy import deepcopy

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.paper.api import owner, mutation, HEADERS
from .probes import exchange_probe

log=logging.getLogger(__name__)

router=APIRouter(prefix='/api/exchange-diagnostics',tags=['Public exchange connectivity diagnostics'])

class Diagnostics:
    def __init__(self):
        self.lock=asyncio.Lock()
        self.last_started=None
        self.report=None

    async def run(self):
        if self.lock.locked():return 409,dict(code='TEST_IN_PROGRESS',status='NOT_TESTED')
        if self.last_started is not None and time.monotonic()-self.last_started<120:
            return 429,dict(code='COOLDOWN_120_SECONDS',status='RATE_LIMITED')
        async with self.lock:
            self.last_started=time.monotonic()
            async with httpx.AsyncClient(timeout=5,follow_redirects=False,limits=httpx.Limits(max_connections=2,max_keepalive_connections=2)) as client:
                async def one(name):
                    try:
                        async with asyncio.timeout(58):return await exchange_probe(name,client)
                    except TimeoutError:return dict(status='TIMEOUT',code='TOTAL_BUDGET_EXCEEDED',tested_at_ms=int(time.time()*1000))
                values=await asyncio.gather(one('BINGX'),one('BITGET'))
            self.report=dict(zip(('BINGX','BITGET'),values))
            for name,value in self.report.items():
                log.info('Exchange connectivity: exchange=%s rest=%s ws=%s',name,value.get('rest',value).get('status'),value.get('websocket',{}).get('status'))
            return 200,deepcopy(self.report)

def configured():
    return Diagnostics() if os.getenv('AURA_EXCHANGE_DIAGNOSTICS','').lower()=='true' else None

def comparison(request):
    feed=getattr(request.app.state,'bybit_linear_preview',None)
    if feed is None:return dict(status='NOT_TESTED',code='EXISTING_PREVIEW_DISABLED')
    # No new Bybit requests, no change to preview implementation.
    value=feed.ticker.read()
    return dict(tested_at_ms=int(time.time()*1000),rest=dict(status='NOT_TESTED',code='NO_NEW_BYBIT_REST_PROBE'),
                websocket=dict(status='AVAILABLE' if value.get('status')=='LIVE' else 'UNAVAILABLE',
                    code='EXISTING_WS_PREVIEW_ONLY',last_price=value.get('last_price'),mark_price=value.get('mark_price'),
                    server_at_ms=value.get('server_at_ms'),preview_error=feed.error))

def envelope(request,report):
    return dict(read_only=True,trading_enabled=False,environment='SERVER_RUNTIME',
                historical_diagnostic=True,not_execution_authority=True,exchanges=dict(report or {},BYBIT=comparison(request)))

@router.get('',dependencies=[Depends(owner)])
async def status(request:Request):
    service=getattr(request.app.state,'exchange_diagnostics',None)
    if service is None:return JSONResponse(dict(code='FEATURE_DISABLED',status='NOT_TESTED',**envelope(request,None)),status_code=503,headers=HEADERS)
    return JSONResponse(envelope(request,deepcopy(service.report)),headers=HEADERS)

@router.post('/run',dependencies=[Depends(mutation)])
async def run(request:Request):
    service=getattr(request.app.state,'exchange_diagnostics',None)
    if service is None:return JSONResponse(dict(code='FEATURE_DISABLED',status='NOT_TESTED',**envelope(request,None)),status_code=503,headers=HEADERS)
    code,value=await service.run()
    payload=envelope(request,value) if code==200 else dict(**value,**envelope(request,service.report))
    return JSONResponse(payload,status_code=code,headers=HEADERS)
