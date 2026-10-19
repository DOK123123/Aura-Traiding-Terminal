"""Owner controls and separate external scheduler authority, internal records only."""
import os,secrets
from typing import Literal
from fastapi import APIRouter,Depends,Request,HTTPException,Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictStr,StrictInt
from app.paper.api import owner,mutation,HEADERS
from .engine import DemoError
from .service import scheduler_configured,Service

router=APIRouter(prefix='/api/auto42',tags=['Experimental automated virtual portfolio'])


class Control(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:Literal['START','STOP','EMERGENCY','RESET']
    request_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    confirmation:StrictStr=Field(default='',max_length=80)
    expected_revision:StrictInt|None=Field(default=None,ge=1)


def scheduler(request:Request):
    if not scheduler_configured():raise HTTPException(503,'SCHEDULER_NOT_CONFIGURED',headers=HEADERS)
    expected=os.getenv('AURA_AUTO42_SCHEDULER_SECRET','');received=request.headers.get('X-Aura-Auto42-Token','')
    if request.headers.get('origin') or request.headers.get('Sec-Fetch-Site')=='cross-site' or not secrets.compare_digest(received.encode(),expected.encode()):raise HTTPException(401,'SCHEDULER_AUTH_REQUIRED',headers=HEADERS)


def service(request):
    value=getattr(request.app.state,'auto42',None)
    if value is None:return Service(None,reason='STORAGE_NOT_CONFIGURED')
    return value


async def respond(operation,diagnostic=None,snapshot=None):
    import asyncio,logging
    try:return JSONResponse(await operation,headers=HEADERS)
    except (DemoError,TimeoutError) as exc:
        code=exc.code if isinstance(exc,DemoError) else 'REQUEST_TIMEOUT'
        logging.getLogger(__name__).warning('Auto42 action rejected: code=%s',code)
        return JSONResponse(dict(**(snapshot() if snapshot else {}),status='NOT_OPERATIONAL',code=code,message='Деморежим: '+code,paper_only=True,exchange_execution=False,diagnostics=diagnostic(error=code) if diagnostic else None),status_code=409 if code in ('RESET_BLOCKED_OPEN_POSITION','STOP_BEFORE_RESET','IDEMPOTENCY_CONFLICT','ALREADY_ON','DAILY_LOSS_LIMIT','DRAWDOWN_LIMIT','EMERGENCY_RESET_REQUIRED','OPEN_POSITION_RESUME_REQUIRES_TICK') else 503,headers=HEADERS)


@router.get('/status',dependencies=[Depends(owner)])
async def status(request:Request):
    svc=service(request)
    return await respond(svc.dashboard(),svc.diagnostics)


@router.get('/alignment',dependencies=[Depends(owner)])
async def alignment(request:Request):
    return await respond(service(request).alignment_dashboard())


@router.get('/quote',dependencies=[Depends(owner)])
async def quote(request:Request):
    async def read():
        svc=service(request);svc.ready()
        if svc.quotes is None:raise DemoError('QUOTE_UNAVAILABLE')
        return dict(quote=await svc.quotes.get(),read_only=True,paper_only=True,exchange_execution=False)
    return await respond(read())


@router.get('/live-monitor',dependencies=[Depends(owner)])
async def live_monitor(request:Request):
    try:
        return JSONResponse(await service(request).live_monitor(),headers=HEADERS)
    except (DemoError,TimeoutError) as exc:
        return JSONResponse(dict(status='FAILED',reason=exc.code if isinstance(exc,DemoError) else 'REQUEST_TIMEOUT',
            read_only=True,paper_only=True,exchange_execution=False,live_cycle_verified=False),status_code=503,headers=HEADERS)


@router.get('/live-monitor/events',dependencies=[Depends(owner)])
async def live_monitor_events(request:Request,after:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    async def read():
        svc=service(request);svc.ready();rows=await svc.store.history(after=after,limit=limit)
        return dict(events=[dict(e['payload'],event_id=e['id'],sequence=e['seq'],epoch=e['epoch'])
            for e in rows if e['kind']=='LIVE_MONITOR'],next_cursor=rows[-1]['seq'] if rows else after,
            read_only=True,paper_only=True,exchange_execution=False,page_may_have_more=len(rows)==limit)
    return await respond(read())


@router.post('/control',dependencies=[Depends(mutation)])
async def control(request:Request,body:Control):
    required={'START':'START PAPER','RESET':'RESET DEMO'}.get(body.action)
    if body.action=='START' and body.expected_revision is None:raise HTTPException(409,'REFRESH_BEFORE_START',headers=HEADERS)
    if required and body.confirmation!=required:raise HTTPException(409,'EXPLICIT_CONFIRMATION_REQUIRED',headers=HEADERS)
    svc=service(request)
    return await respond(svc.control(body.action,body.request_id,body.expected_revision),svc.diagnostics,svc.operation_snapshot)


@router.post('/tick',dependencies=[Depends(scheduler)])
async def tick(request:Request):
    svc=service(request)
    return await respond(svc.tick(),svc.diagnostics)


@router.get('/journal',dependencies=[Depends(owner)])
async def journal(request:Request,after:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    async def read():
        svc=service(request);svc.ready();rows=await svc.store.history(after=after,limit=limit)
        return dict(rows=rows,next_cursor=rows[-1]['seq'] if rows else after,paper_only=True,exchange_execution=False)
    return await respond(read())


@router.get('/trades',dependencies=[Depends(owner)])
async def trades(request:Request,before:int|None=Query(None,ge=1),limit:int=Query(50,ge=1,le=200)):
    async def read():
        svc=service(request);svc.ready();env=await svc.store.load()
        rows=await svc.store.closed_trades(env['state']['epoch'],before,limit)
        return dict(trades=[e['payload'] for e in rows],epoch=env['state']['epoch'],
            next_cursor=rows[-1]['seq'] if rows else None,page_may_have_more=len(rows)==limit,
            read_only=True,paper_only=True,exchange_execution=False)
    return await respond(read())
