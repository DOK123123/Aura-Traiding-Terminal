"""Owner-only intelligence reads and protected virtual replay mutations."""
import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictInt
from app.paper.api import owner,mutation,HEADERS
from app.lab.models import Bar,LabError
from .service import Service,IntelligenceError
from .patterns import catalogue
from .analysis import analyze
from decimal import Decimal as D
import time
import sqlite3

router=APIRouter(prefix='/api/intelligence',tags=['Manual replay intelligence'])

@lru_cache(maxsize=1)
def service():return Service(Path(__file__).resolve().parents[2]/'.data/intelligence.sqlite3')

async def respond(fn,*args):
    try:return JSONResponse(await asyncio.to_thread(fn,*args),headers=HEADERS)
    except (IntelligenceError,LabError,ValueError,OSError,KeyError,sqlite3.Error) as e:
        code=str(e) if isinstance(e,IntelligenceError) else 'HISTORY_OR_STORAGE_UNAVAILABLE'
        return JSONResponse(dict(status='ERROR',code=code,message='Действие не выполнено: '+code,real_money_execution='DISABLED'),status_code=409,headers=HEADERS)

def call(name,*args):return getattr(service(),name)(*args)

class Create(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    timeframe:Literal['15m','1h','4h']='15m'
    candle_time:StrictInt=Field(ge=0)
    manual_research:bool=False

class Proposal(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    manual:bool=False

class Decide(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    proposal_id:str=Field(min_length=36,max_length=36)
    confirm:bool

class Advance(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    steps:StrictInt=Field(default=1,ge=1,le=32)

@router.get('/catalogue',dependencies=[Depends(owner)])
async def catalog():return JSONResponse(catalogue(),headers=HEADERS)

@router.get('/manifest',dependencies=[Depends(owner)])
async def manifest():return await respond(call,'manifest')

@router.post('/sessions',dependencies=[Depends(mutation)])
async def create(body:Create):return await respond(call,'create',body.timeframe,body.candle_time,body.manual_research)

@router.get('/sessions/{sid}',dependencies=[Depends(owner)])
async def state(sid:str):return await respond(call,'state',sid)

@router.post('/sessions/{sid}/proposal',dependencies=[Depends(mutation)])
async def proposal(sid:str,body:Proposal):return await respond(call,'proposal',sid,body.manual)

@router.post('/sessions/{sid}/decision',dependencies=[Depends(mutation)])
async def decide(sid:str,body:Decide):return await respond(call,'decide',sid,body.proposal_id,body.confirm)

@router.post('/sessions/{sid}/advance',dependencies=[Depends(mutation)])
async def advance(sid:str,body:Advance):return await respond(call,'advance',sid,body.steps)

@router.get('/live',dependencies=[Depends(owner)])
async def live(timeframe:Literal['15m','1h']='15m'):
    # Reuse public infrastructure; never create a proposal or private request.
    from app.main import market
    try:
        async with asyncio.timeout(15):data=await market('BTCUSDT',timeframe,500)
        if data['stale']:raise IntelligenceError('STALE_DATA')
        step=900 if timeframe=='15m' else 3600;now=int(time.time())
        bars=[Bar(c['time'],*[D(str(c[k])) for k in ('open','high','low','close','volume')]) for c in data['candles'] if c['time']+step<=now]
        value=await asyncio.to_thread(analyze,bars[-250:],service().pack['index'],timeframe)
        value.update(strategy='WAIT',reason='LIVE_VALIDATION_REQUIRED',source=data['source'],execution_enabled=False)
        return JSONResponse(value,headers=HEADERS)
    except (IntelligenceError,LabError,ValueError,OSError,KeyError,TimeoutError,HTTPException):return JSONResponse(dict(strategy='WAIT',reason='NO_FRESH_DATA',message='Нет свежих данных',execution_enabled=False),headers=HEADERS,status_code=503)


@router.get('/market-context', dependencies=[Depends(owner)])
async def market_context(request: Request, timeframe: Literal['15m','1h','4h']='15m'):
    """GET analysis only; deliberately independent of Service/replay/SQLite."""
    from .market_context import unavailable
    adapter = getattr(request.app.state, 'market_context', None)
    value = await adapter.snapshot(timeframe) if adapter else dict(unavailable(), timeframe=timeframe)
    return JSONResponse(value, headers=HEADERS, status_code=200 if value['status'] in ('OK','INSUFFICIENT_HISTORY') else 503)
