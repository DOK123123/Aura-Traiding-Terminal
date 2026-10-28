"""Separate opt-in Render preview entrypoint. Does not import app.main/lifespan."""
import asyncio
from contextlib import asynccontextmanager
import os
import secrets
from fastapi import Depends,FastAPI,HTTPException,Request
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
    store=PreviewStore(config);task=None
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
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
                finally:await app.state.aura_analyst.close()
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

@app.get('/api/health')
async def health():
    return {'status':'ok','scope':'ISOLATED_MANUAL_PREVIEW','exchange_execution':False,'active43_controller_enabled':False,'automatic_entry_scheduler_enabled':False}

@app.get('/')
async def index():return HTMLResponse(page())

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
