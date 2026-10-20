"""Owner controls; independent scheduler authority. No manual/artificial signal API."""
import os,secrets,re
from decimal import Decimal as D
from app.lab.models import money,text
from app.automated.engine import liquidation_equity
from .market import quote_checked
from typing import Literal
from fastapi import APIRouter,Depends,Request,HTTPException,Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictStr,StrictInt
from app.paper.api import owner,mutation,HEADERS
from app.automated.engine import DemoError
from .service import scheduler_configured

router=APIRouter(prefix='/api/active43',tags=['Aura 4.3 Active Paper virtual only'])
class Control(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:Literal['START','STOP','EMERGENCY']
    request_id:StrictStr=Field(pattern='^[a-f0-9]{32}$')
    expected_revision:StrictInt|None=Field(None,ge=1)
    confirmation:StrictStr=Field('',max_length=80)


def svc(request):
    value=getattr(request.app.state,'active43',None)
    if value is None:raise DemoError('ACTIVE43_NOT_CONFIGURED')
    return value


def scheduler_rejected(request:Request,code:str,status:int):
    # Whitelisted flags only. No token value/length/fingerprint or raw headers.
    commit=os.getenv('RENDER_GIT_COMMIT','')
    detail=dict(code=code,component='AURA43_SCHEDULER_AUTH',
        header_received=bool(request.headers.get('X-Aura-Active43-Bitget-Token','')),
        origin_rejected=bool(request.headers.get('origin')) or request.headers.get('Sec-Fetch-Site')=='cross-site',
        secret_variable='AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',
        config_source='CURRENT_PROCESS_ENV_NO_FALLBACK',
        render_commit=commit if re.fullmatch('[a-f0-9]{40}',commit) else None)
    raise HTTPException(status,detail,headers=HEADERS)


def scheduler(request:Request):
    if not scheduler_configured():scheduler_rejected(request,'SCHEDULER_NOT_CONFIGURED',503)
    if request.headers.get('origin') or request.headers.get('Sec-Fetch-Site')=='cross-site':
        scheduler_rejected(request,'SCHEDULER_ORIGIN_REJECTED',401)
    tokens=request.headers.getlist('X-Aura-Active43-Bitget-Token')
    if not tokens or not tokens[0]:scheduler_rejected(request,'SCHEDULER_TOKEN_MISSING',401)
    if len(tokens)!=1:scheduler_rejected(request,'SCHEDULER_TOKEN_DUPLICATED',401)
    if not secrets.compare_digest(tokens[0].encode(),os.getenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','').encode()):
        scheduler_rejected(request,'SCHEDULER_TOKEN_MISMATCH',401)


async def respond(operation):
    try:return JSONResponse(await operation,headers=HEADERS)
    except (DemoError,TimeoutError) as exc:
        code=exc.code if isinstance(exc,DemoError) else 'REQUEST_TIMEOUT_OUTCOME_UNKNOWN'
        return JSONResponse(dict(code=code,message='Aura 4.3: '+code,paper_only=True,exchange_execution=False,
            production_paper_verified=False),status_code=409 if code in ('CONCURRENT_UPDATE','IDEMPOTENCY_CONFLICT','ALREADY_ON','DAILY_LOSS_LIMIT','DRAWDOWN_LIMIT','EMERGENCY_STOP') else 503,headers=HEADERS)


@router.get('/status',dependencies=[Depends(owner)])
async def status(request:Request):
    async def read():return await svc(request).dashboard()
    return await respond(read())


@router.get('/quote',dependencies=[Depends(owner)])
async def quote(request:Request):
    async def read():
        service=svc(request);service.ready()
        if service.quotes is None:raise DemoError('QUOTE_UNAVAILABLE')
        quote=await service.quotes.get();env=await service.load();state=env['state'];p=state['position']
        quote_checked(quote,service.clock())
        net=text(money(liquidation_equity(state,D(quote['price']))-D(state['balance'])-D(p['entry_fee']))) if p else None
        return dict(quote=quote,position_id=p['id'] if p else None,position_net_pnl_at_quote=net,revision=env['revision'],read_only=True,paper_only=True,exchange_execution=False)
    return await respond(read())


@router.get('/journal',dependencies=[Depends(owner)])
async def journal(request:Request,after:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    async def read():
        service=svc(request);service.ready();env=await service.load()
        rows=await service.store.history(epoch=env['state']['epoch'],after=after,limit=limit)
        return dict(rows=rows,next_cursor=rows[-1]['seq'] if rows else after,page_may_have_more=len(rows)==limit,paper_only=True,exchange_execution=False)
    return await respond(read())


@router.get('/trades',dependencies=[Depends(owner)])
async def trades(request:Request,before:int|None=Query(None,ge=1),limit:int=Query(50,ge=1,le=200)):
    async def read():
        service=svc(request);service.ready();env=await service.load()
        rows=await service.store.history(epoch=env['state']['epoch'],before=before,kind='CLOSE',limit=limit)
        return dict(trades=[e['payload'] for e in rows],epoch=env['state']['epoch'],next_cursor=rows[-1]['seq'] if rows else None,page_may_have_more=len(rows)==limit,paper_only=True,exchange_execution=False)
    return await respond(read())


@router.post('/control',dependencies=[Depends(mutation)])
async def control(request:Request,body:Control):
    if body.action=='START' and (body.confirmation!='START EXPERIMENTAL PAPER' or body.expected_revision is None):raise HTTPException(409,'EXPLICIT_EXPERIMENTAL_CONFIRMATION_REQUIRED',headers=HEADERS)
    async def perform():return await svc(request).control(body.action,body.request_id,body.expected_revision)
    return await respond(perform())


@router.post('/tick',dependencies=[Depends(scheduler)])
async def tick(request:Request):
    async def perform():return await svc(request).tick()
    return await respond(perform())


@router.post('/diagnostics',dependencies=[Depends(mutation)])
async def diagnostics(request:Request):
    return await respond(svc(request).diagnostics.run())


@router.post('/diagnostics/scheduler',dependencies=[Depends(scheduler)])
async def scheduler_diagnostics(request:Request):
    return await respond(svc(request).diagnostics.run(scheduler_delivery=True))
