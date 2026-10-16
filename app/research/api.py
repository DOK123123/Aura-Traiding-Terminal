"""Owner-only research endpoints reuse Lab authentication and CSRF boundary."""
from functools import lru_cache
from pathlib import Path
import sqlite3
from fastapi import APIRouter,Depends,HTTPException,Path as ApiPath
from fastapi.responses import JSONResponse,RedirectResponse
from pydantic import BaseModel,ConfigDict
from typing import Literal,Annotated
from app.lab.api import owner,mutation,HEADERS
from app.lab.models import LabError
from .service import Service

router=APIRouter(prefix='/api/research',tags=['AI Research Lab — isolated manual research'])
Id=Annotated[str,ApiPath(pattern='^[0-9a-f]{32}$')]

@lru_cache(maxsize=1)
def service() -> Service:return Service(Path(__file__).resolve().parents[2])

class Enqueue(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    hypothesis:Literal['MEAN_REVERSION','LIQUIDITY_SWEEP','VOLATILITY_BREAKOUT','REGIME_SWITCHING']

async def respond(call):
    try:return JSONResponse(await call,headers=HEADERS)
    except LabError as e:
        known={'BUSY','RESEARCH_NOT_FOUND','RESEARCH_ALREADY_PROCESSED','RESEARCH_QUEUE_FULL','RESEARCH_RUN_FAILED','AI_NOT_CONFIGURED','LLM_INVALID_CONFIG','LLM_BUDGET_EXCEEDED','LLM_TOKEN_LIMIT','LLM_CALL_FAILED','RESEARCH_STORAGE_CONFLICT','RESEARCH_INTEGRITY'}
        code=e.code if e.code in known else 'RESEARCH_UNAVAILABLE'
        status=404 if code=='RESEARCH_NOT_FOUND' else 409 if code in ('BUSY','RESEARCH_ALREADY_PROCESSED') else 503
        return JSONResponse(dict(status='ERROR',code=code,message=code,research_only=True),status_code=status,headers=HEADERS)
    except (OSError,ValueError,RuntimeError,sqlite3.Error):
        return JSONResponse(dict(status='ERROR',code='RESEARCH_UNAVAILABLE',research_only=True),status_code=503,headers=HEADERS)

# Dependency construction happens AFTER authentication to avoid anonymous DB writes.
def instance(_=Depends(owner)) -> Service:
    try:return service()
    except Exception:raise HTTPException(503,'Research storage unavailable.',headers=HEADERS) from None

@router.get('/login',dependencies=[Depends(owner)])
def login():return RedirectResponse('/static/research.html',status_code=303,headers=HEADERS)

@router.get('',dependencies=[Depends(owner)])
async def overview(s:Service=Depends(instance)):return await respond(s.overview())

@router.post('/queue',dependencies=[Depends(mutation)])
async def queue(body:Enqueue,s:Service=Depends(instance)):return await respond(s.enqueue(body.hypothesis))

@router.post('/queue/{ident}/run',dependencies=[Depends(mutation)])
async def run(ident:Id,s:Service=Depends(instance)):return await respond(s.run(ident))

@router.post('/queue/{ident}/retry',dependencies=[Depends(mutation)])
async def retry(ident:Id,s:Service=Depends(instance)):
    async def call():
        import asyncio
        await asyncio.to_thread(s.store.retry,ident)
        return dict(id=ident,state='QUEUED',automatic_run=False)
    return await respond(call())

@router.get('/experiments/{ident}',dependencies=[Depends(owner)])
async def experiment(ident:Id,s:Service=Depends(instance)):return await respond(s.get(ident))

@router.get('/experiments/{ident}/export',dependencies=[Depends(owner)])
async def export(ident:Id,s:Service=Depends(instance)):return await respond(s.get(ident,export=True))

@router.post('/ideas',dependencies=[Depends(mutation)])
async def idea(s:Service=Depends(instance)):return await respond(s.advisor.propose())

@router.post('/recover-interrupted',dependencies=[Depends(mutation)])
async def recover(s:Service=Depends(instance)):
    async def call():
        import asyncio
        return dict(interrupted=await asyncio.to_thread(s.store.interrupt_stale),automatic_retry=False)
    return await respond(call())
