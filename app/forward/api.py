"""Owner reads and isolated scheduler authentication; no trading route."""
import csv
import io
import os
import secrets
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from fastapi.responses import JSONResponse,Response
from app.paper.api import owner,HEADERS
from .models import ForwardError,verify,scheduler_secret_valid

router=APIRouter(prefix='/api/intelligence/forward',tags=['Read-only scientific validation'])


def scheduler(request:Request):
    expected=os.getenv('AURA_FORWARD_SCHEDULER_SECRET','')
    forbidden=(os.getenv('AURA_TESTNET_VIEW_PASSWORD',''),os.getenv('AURA_FORWARD_SUPABASE_SERVICE_KEY',''))
    if not scheduler_secret_valid(expected,*forbidden):
        raise HTTPException(503,'SCHEDULER_NOT_CONFIGURED',headers=HEADERS)
    received=request.headers.get('X-Aura-Forward-Token','')
    if request.headers.get('origin') or request.headers.get('Sec-Fetch-Site')=='cross-site' or not secrets.compare_digest(received.encode(),expected.encode()):
        raise HTTPException(401,'SCHEDULER_AUTH_REQUIRED',headers=HEADERS)


def service(request):
    value=getattr(request.app.state,'forward_validation',None)
    if value is None:raise ForwardError('STORAGE_NOT_CONFIGURED')
    return value


def failure(code):return JSONResponse(dict(status=code,message='Проверка прогнозов недоступна: '+code,execution_enabled=False),status_code=503,headers=HEADERS)


@router.post('/tick',dependencies=[Depends(scheduler)])
async def tick(request:Request):
    try:
        result=await service(request).tick()
        return JSONResponse(result,status_code=200 if result['status']=='COMPLETED' else 503,headers=HEADERS)
    except ForwardError as exc:return failure(exc.code)


@router.get('/status',dependencies=[Depends(owner)])
async def status(request:Request,cohort:str|None=Query(None,pattern=r'^[a-f0-9]{64}$')):
    try:return JSONResponse(await service(request).dashboard(cohort),headers=HEADERS)
    except ForwardError as exc:return failure(exc.code)


@router.get('/export',dependencies=[Depends(owner)])
async def export(request:Request,after:int=Query(0,ge=0),through:int|None=Query(None,ge=0),limit:int=Query(100,ge=1,le=200),format:Literal['json','csv']='json'):
    try:
        svc=service(request)
        if svc.store is None:raise ForwardError('STORAGE_NOT_CONFIGURED')
        monitor=await svc.store.status()
        end=monitor['max_seq'] if through is None else min(through,monitor['max_seq'])
        rows=await svc.store.read(mode='export',after=after,limit=limit,through=end)
        next_cursor=rows[-1]['seq'] if rows else after
        if format=='json':return JSONResponse(dict(rows=rows,next_cursor=next_cursor,through=end,
            snapshot_total_rows=monitor['total_rows'] if through is None or through==monitor['max_seq'] else None,
            complete=not rows or next_cursor>=end),headers=HEADERS)
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['seq','id','kind','created_ms','cohort','timeframe','closed_at','payload','sha256'])
        def safe(value):
            text=str(value)
            return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
        for row in rows:writer.writerow([safe(row[k]) for k in ('seq','id','kind','created_ms','cohort','tf','closed_at','payload','sha256')])
        return Response(stream.getvalue(),media_type='text/csv; charset=utf-8',headers=dict(HEADERS,**{'Content-Disposition':'attachment; filename="aura-forward-page.csv"','X-Next-Cursor':str(next_cursor),'X-Snapshot-Through':str(end)}))
    except ForwardError as exc:return failure(exc.code)
