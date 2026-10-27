"""Owner-only virtual trading. Execution prices are never accepted from clients."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.paper.api import owner, mutation, HEADERS
from .service import Service
from urllib.parse import urlsplit

def manual_mutation(request:Request, _:None=Depends(mutation)):
    origin=request.headers.get('origin')
    if origin and urlsplit(origin).scheme != request.url.scheme:
        raise HTTPException(403,'ORIGIN_MISMATCH',headers=HEADERS)


router=APIRouter(prefix='/api/manual-paper',tags=['Manual Paper · virtual only'])


class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')


class Open(Command):
    side: Literal['LONG','SHORT']
    quantity: StrictStr = Field(min_length=1,max_length=32,pattern=r'^\d{1,12}(\.\d{1,12})?$')
    stop: StrictStr = Field(min_length=1,max_length=32,pattern=r'^\d{1,12}(\.\d{1,12})?$')
    target: StrictStr = Field(min_length=1,max_length=32,pattern=r'^\d{1,12}(\.\d{1,12})?$')
    # Adverse price bound, never a client-supplied execution price.
    entry_limit: StrictStr | None = Field(default=None,max_length=32,pattern=r'^\d{1,12}(\.\d{1,12})?$')
    analyst_at: float | None = Field(default=None,strict=True,gt=0,allow_inf_nan=False)


ERRORS={
    'MANUAL_PAPER_DISABLED','MANUAL_STORAGE_PATH_INVALID','PERSISTENT_DISK_REQUIRED','PERSISTENT_STORAGE_NOT_READY',
    'STORAGE_UNAVAILABLE','CORRUPT_JOURNAL','STORAGE_SCOPE_MISMATCH','SOURCE_MISMATCH','STALE_QUOTE',
    'INVALID_QUOTE','SERVER_TIME_MISMATCH','MARKET_UNAVAILABLE','INVALID_NUMBER','INVALID_SIDE','INVALID_STOPS',
    'POSITION_ALREADY_OPEN','POSITION_SIZE_LIMIT','RISK_LIMIT','INSUFFICIENT_BALANCE','INVALID_REQUEST_ID',
    'IDEMPOTENCY_CONFLICT','CONCURRENT_UPDATE','POSITION_NOT_FOUND','NO_POSITION','QUOTE_BEFORE_ENTRY',
    'DRAWDOWN_LIMIT','INSUFFICIENT_QUOTE_LIQUIDITY','WRITE_LIMIT','INVALID_STORAGE_CONFIGURATION','STORAGE_RESPONSE_LIMIT',
    'STALE_ANALYST','ANALYST_PLAN_CHANGED','ENTRY_OUTSIDE_ZONE','ENTRY_PRICE_MOVED',
}


def service(request):
    return getattr(request.app.state,'manual_paper',Service(error='MANUAL_PAPER_DISABLED'))


def reply(data,status=200):
    # Decimal fields remain exact strings on the wire.
    from decimal import Decimal
    return JSONResponse(jsonable_encoder(data,custom_encoder={Decimal:str}),status_code=status,headers=HEADERS)


async def respond(operation):
    try:
        return reply(await operation)
    except ValueError as exc:
        code=str(exc) if str(exc) in ERRORS else 'CORRUPT_JOURNAL'
        status=409 if code in {'POSITION_ALREADY_OPEN','POSITION_SIZE_LIMIT','RISK_LIMIT','INVALID_STOPS',
                              'IDEMPOTENCY_CONFLICT','CONCURRENT_UPDATE','POSITION_NOT_FOUND','NO_POSITION',
                              'QUOTE_BEFORE_ENTRY','DRAWDOWN_LIMIT','INVALID_NUMBER','INSUFFICIENT_QUOTE_LIQUIDITY',
                              'STALE_ANALYST','ANALYST_PLAN_CHANGED','ENTRY_OUTSIDE_ZONE','ENTRY_PRICE_MOVED'} else 503
        return reply(dict(code=code,virtual_only=True,real_money_execution='DISABLED'),status)


@router.get('/capabilities')
async def capabilities(request:Request):
    svc=service(request)
    return reply(dict(mode='MANUAL_PAPER',virtual_only=True,real_money_execution='DISABLED',
                      ready=False,manual_orders_enabled=False,balance=None,position=None,
                      configured=svc.store is not None and not svc.error,
                      reason=svc.error or 'OWNER_STATE_READ_REQUIRED'))


@router.get('/state',dependencies=[Depends(owner)])
async def state(request:Request,offset:int=Query(0,ge=0,le=1000000),limit:int=Query(50,ge=1,le=200)):
    return await respond(service(request).state(offset=offset,limit=limit))


@router.get('/quote',dependencies=[Depends(owner)])
async def quote(request:Request):
    return await respond(service(request).quote())


@router.post('/orders',dependencies=[Depends(manual_mutation)])
async def open_position(request:Request,body:Open):
    return await respond(service(request).open(body.model_dump(),scenario_check=scenario_check(request,body)))


def scenario_check(request: Request, body: Open):
    """An optional copied signal is evidence, never authority to submit orders."""
    if body.analyst_at is None:
        return None
    async def check(quote):
        from decimal import Decimal
        analyst = getattr(request.app.state,'aura_analyst',None)
        if analyst is None:
            raise ValueError('STALE_ANALYST')
        result = await analyst.inspect()
        now = service(request).clock()
        if (result.get('state') not in ('LONG','SHORT') or result.get('scenario') is None
                or result.get('generated_at') != body.analyst_at
                or not result.get('generated_at',now+1) <= now < result.get('valid_until',0)
                or result.get('asof_closed_at') != int(now)//300*300):
            raise ValueError('STALE_ANALYST')
        plan = result['scenario']
        if (result['state'] != body.side or Decimal(str(plan['stop_loss'])) != Decimal(body.stop)
                or Decimal(str(plan['take_profit'])) != Decimal(body.target)):
            raise ValueError('ANALYST_PLAN_CHANGED')
        price = quote['ask'] if body.side == 'LONG' else quote['bid']
        if not Decimal(str(plan['entry_zone']['low'])) <= price <= Decimal(str(plan['entry_zone']['high'])):
            raise ValueError('ENTRY_OUTSIDE_ZONE')
        return int(result['valid_until']*1000)
    return check


@router.post('/preview',dependencies=[Depends(manual_mutation)])
async def preview(request:Request,body:Open):
    return await respond(service(request).preview(body.model_dump(),scenario_check=scenario_check(request,body)))


@router.post('/positions/{position_id}/close',dependencies=[Depends(manual_mutation)])
async def close_position(position_id:str,request:Request,body:Command):
    if not re.fullmatch(r'[a-f0-9]{32}',position_id):
        raise HTTPException(422,'INVALID_POSITION_ID',headers=HEADERS)
    return await respond(service(request).close_position(position_id,body.request_id))
