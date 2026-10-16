"""Owner-protected research-only API; no Paper/exchange imports or activation route."""
import os
import secrets
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,Request,HTTPException,Query
from fastapi.responses import JSONResponse,Response,RedirectResponse
from fastapi.security import HTTPBasic,HTTPBasicCredentials
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field,model_validator
from .models import LabError,canonical

router=APIRouter(prefix='/api/lab',tags=['Strategy Lab research only'])
basic=HTTPBasic(auto_error=False)
HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}


def owner(credentials:HTTPBasicCredentials|None=Depends(basic)):
    password=os.getenv('AURA_TESTNET_VIEW_PASSWORD','')
    if len(password)<12:raise HTTPException(403,'Configure owner-view password to access Strategy Lab.',headers=HEADERS)
    if credentials is None or not secrets.compare_digest(credentials.username.encode(),b'aura') or not secrets.compare_digest(credentials.password.encode(),password.encode()):
        raise HTTPException(401,'Owner login required.',headers=dict(HEADERS,**{'WWW-Authenticate':'Basic realm="Aura Strategy Lab", charset="UTF-8"'}))


def mutation(request:Request,_=Depends(owner)):
    if request.headers.get('X-Aura-Lab')!='research-only' or request.headers.get('Sec-Fetch-Site')=='cross-site':raise HTTPException(403,'Research request blocked.',headers=HEADERS)
    origin=request.headers.get('origin')
    if origin:
        try:
            url=urlsplit(origin)
            if url.scheme not in ('https','http') or url.netloc.lower()!=request.headers.get('host','').lower() or url.username or url.password or url.path or url.query or url.fragment:raise ValueError()
        except ValueError:raise HTTPException(403,'Research request blocked.',headers=HEADERS) from None


class RunRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    days:StrictInt=Field(default=60,ge=1,le=80)
    start:StrictInt|None=Field(default=None,ge=0)
    end:StrictInt|None=Field(default=None,gt=0)
    development_pct:StrictStr=Field(default='70',max_length=24)
    fee_bps:StrictStr=Field(default='10',max_length=24)
    slippage_bps:StrictStr=Field(default='5',max_length=24)
    @model_validator(mode='after')
    def dates(self):
        if (self.start is None)!=(self.end is None):raise ValueError('Provide both start/end or neither.')
        return self


MESSAGES={
 'BUSY':'Another research run is active. Try later.', 'DATA_LIMIT':'Requested history exceeds 12000 base 15m candles including 250 warm-up 4h bars. Request a shorter interval.',
 'INVALID_RANGE':'Use a closed BTCUSDT range with start/end at UTC 4h boundaries.', 'INVALID_TIMESTAMPS':'Invalid/alignment-conflicting historical timestamps.',
 'INVALID_OHLCV':'Invalid historical OHLCV.', 'DUPLICATE_OR_UNORDERED':'Duplicate or unordered historical candles.',
 'MISSING_CANDLES':'Missing historical interval: no forward-fill is permitted.', 'INCOMPLETE_HISTORY':'Source did not supply the entire requested history; no truncated experiment was run.',
 'FETCH_TIMEOUT':'Historical fetch exceeded 60 seconds.', 'PUBLIC_DATA_UNAVAILABLE':'Public historical data is unavailable; no synthetic dataset was used.',
 'COMPUTE_TIMEOUT':'Research compute exceeded its 30-second budget.', 'INVALID_DATA':'Invalid research data.',
 'INVALID_CONFIG':'Invalid shared baseline configuration.', 'INSUFFICIENT_DATA':'Insufficient closed historical data.',
 'INVALID_SPLIT':'Insufficient common-calendar range for the requested split.', 'ACCOUNTING_ERROR':'Research accounting invariant failed.',
 'STORAGE_UNAVAILABLE':'Research snapshot storage unavailable.', 'PATH_CONFLICT':'Lab storage must be separate from Paper and historical archive databases.',
 'CORRUPT_EXPERIMENT':'Stored research experiment failed integrity validation.', 'EXPERIMENT_NOT_FOUND':'Experiment not found or evicted by retention.',
 'SOFTWARE_MISMATCH':'Stored snapshot belongs to a different engine build; retrieve/export it, do not silently recompute.',
 'REPRODUCIBILITY_ERROR':'Replay did not reproduce stored results.', 'RESULT_LIMIT':'Research result exceeds the bounded storage limit.'}


async def respond(call):
    try:return JSONResponse(await call,headers=HEADERS)
    except LabError as error:
        code=error.code if error.code in MESSAGES else 'INVALID_DATA'
        status=404 if code=='EXPERIMENT_NOT_FOUND' else 409 if code in ('BUSY','SOFTWARE_MISMATCH') else 503 if code in ('FETCH_TIMEOUT','PUBLIC_DATA_UNAVAILABLE','STORAGE_UNAVAILABLE','COMPUTE_TIMEOUT') else 422
        return JSONResponse({'status':'ERROR','code':code,'message':MESSAGES[code],'research_only':True},status_code=status,headers=HEADERS)


@router.get('/login',dependencies=[Depends(owner)])
def login():return RedirectResponse('/',status_code=303,headers=HEADERS)


@router.get('/v2',dependencies=[Depends(owner)])
async def lab_v2_summary():
    import asyncio
    from .v2_report import summary
    return await respond(asyncio.to_thread(summary))


@router.get('/v2/detail',dependencies=[Depends(owner)])
async def lab_v2_detail(variant:str=Query('DONCHIAN_1h',pattern=r'^(AURA42|AURA43|(DONCHIAN|TREND_ATR|EMA_RSI_ADX)_(15m|1h|4h))$'),
    split:Literal['development','validation','full_12m','validation_delayed']='validation',side:Literal['ALL','LONG','SHORT']='ALL',offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    import asyncio
    from .v2_report import detail
    return await respond(asyncio.to_thread(detail,variant,split,offset,limit,side))


@router.get('/profiles43',dependencies=[Depends(owner)])
async def profiles43_summary():
    import asyncio
    from .adaptive43_profiles_report import summary
    return await respond(asyncio.to_thread(summary))


@router.get('/profiles43/detail',dependencies=[Depends(owner)])
async def profiles43_detail(variant:str=Query('Balanced',pattern=r'^(AURA42|AURA43_ORIGINAL|(Conservative|Balanced|Active)(_(TREND_PULLBACK|BREAKOUT|REVERSAL))?)$'),
    split:Literal['full_6m','development','validation']='validation',offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    import asyncio
    from .adaptive43_profiles_report import detail
    return await respond(asyncio.to_thread(detail,variant,split,offset,limit))


@router.get('/adaptive43',dependencies=[Depends(owner)])
async def adaptive43_summary():
    import asyncio
    from .adaptive43_report import summary
    return await respond(asyncio.to_thread(summary))


@router.get('/adaptive43/detail',dependencies=[Depends(owner)])
async def adaptive43_detail(variant:Literal['AURA42','AURA43_ADAPTIVE','AURA43_TREND_PULLBACK','AURA43_BREAKOUT','AURA43_REVERSAL']='AURA43_ADAPTIVE',
    split:Literal['full_90d','development','validation']='validation',offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    import asyncio
    from .adaptive43_report import detail
    return await respond(asyncio.to_thread(detail,variant,split,offset,limit))


@router.get('/experiments',dependencies=[Depends(owner)])
async def experiments(request:Request):
    import asyncio
    return await respond(asyncio.to_thread(request.app.state.lab.store.list))


@router.post('/run',dependencies=[Depends(mutation)])
async def run(request:Request,body:RunRequest):return await respond(request.app.state.lab.run(body.model_dump()))


@router.get('/experiments/{ident}',dependencies=[Depends(owner)])
async def experiment(ident:str,request:Request):return await respond(request.app.state.lab.get(ident))


@router.post('/experiments/{ident}/replay',dependencies=[Depends(mutation)])
async def replay(ident:str,request:Request):return await respond(request.app.state.lab.replay(ident))


@router.get('/experiments/{ident}/detail',dependencies=[Depends(owner)])
async def detail(ident:str,request:Request,timeframe:Literal['15m','1h','4h']='15m',split:Literal['development','validation']='validation',
                 strategy:Literal['AURA_EXISTING','DONCHIAN','TREND_ATR','EMA_RSI_ADX']='DONCHIAN',offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100)):
    return await respond(request.app.state.lab.detail(ident,timeframe,split,strategy,offset,limit))


@router.get('/experiments/{ident}/export',dependencies=[Depends(owner)])
async def export(ident:str,request:Request):
    try:
        import asyncio
        data=await request.app.state.lab.export(ident)
        return Response(await asyncio.to_thread(canonical,data),media_type='application/json',headers=dict(HEADERS,**{'Content-Disposition':'attachment; filename="aura-strategy-lab.json"'}))
    except LabError as error:
        code=error.code if error.code in MESSAGES else 'INVALID_DATA'
        return JSONResponse({'code':code,'message':MESSAGES[code]},status_code=422,headers=HEADERS)
