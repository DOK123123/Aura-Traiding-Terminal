"""Practice-only owner/CSRF boundary; no client-controlled source/storage/sizing."""
from typing import Literal
import uuid
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.paper.api import owner,mutation,HEADERS
from app.automated.engine import DemoError

router=APIRouter(prefix='/api/practice',tags=['PAPER PRACTICE — VIRTUAL ONLY'])
class Command(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    request_id:str
    @field_validator('request_id')
    @classmethod
    def identifier(cls,v):
        if str(uuid.UUID(v))!=v:raise ValueError('canonical UUID required')
        return v
class Open(Command):
    direction:Literal['LONG','SHORT']
    stop_loss:str=Field(min_length=1,max_length=26)
    take_profit:str=Field(min_length=1,max_length=26)
    expected_price:str=Field(min_length=1,max_length=26)
class Close(Command):position_id:str=Field(min_length=1,max_length=150)

def service(request:Request):return request.app.state.practice
async def respond(call):
    try:return JSONResponse(await call,headers=HEADERS)
    except DemoError as e:
        status=409 if e.code in ('CONCURRENT_UPDATE','IDEMPOTENCY_CONFLICT','POSITION_CHANGED','POSITION_LIMIT') else 503 if e.code in ('CORRUPT_PORTFOLIO','ACCOUNTING_ERROR','PRACTICE_SCOPE_MISMATCH') or any(k in e.code for k in ('STORAGE','QUOTE','NOT_CONFIGURED','OUTCOME_UNKNOWN')) else 400
        return JSONResponse(dict(confirmed=False,code=e.code,scope='PAPER_PRACTICE_ONLY',message='Операция не подтверждена. При неопределённом исходе повторите тот же request_id.'),status_code=status,headers=HEADERS)
    except Exception:return JSONResponse(dict(confirmed=False,code='PRACTICE_UNAVAILABLE_OUTCOME_UNKNOWN'),status_code=503,headers=HEADERS)

@router.get('/login',dependencies=[Depends(owner)])
def login():return RedirectResponse('/static/practice.html',303,headers=HEADERS)
@router.get('/state',dependencies=[Depends(owner)])
async def state(s=Depends(service)):return await respond(s.view())
@router.get('/quote',dependencies=[Depends(owner)])
async def quote(s=Depends(service)):return await respond(s.quote())
@router.post('/open',dependencies=[Depends(mutation)])
async def open_position(body:Open,s=Depends(service)):return await respond(s.command('OPEN',body.model_dump()))
@router.post('/close',dependencies=[Depends(mutation)])
async def close_position(body:Close,s=Depends(service)):return await respond(s.command('CLOSE',body.model_dump()))
