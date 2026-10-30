"""Standalone read-only Hunter, never mounted or started by Aura 5.0."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import time

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .market import PublicMarket, STEPS
from .store import Store

ROOT=Path(__file__).resolve().parents[2]
security=HTTPBasic(auto_error=False)


class Hunter:
    def __init__(self, store, market, registry):
        self.store,self.market,self.registry=store,market,registry
        self.quotes={};self.error='STARTING';self.failures=0;self.cycles=0
        self.frame_errors={};self.last_cycle_at=None

    async def cycle(self):
        success=0
        try:
            funding_body=await self.market.get('history-fund-rate',pageSize=100,pageNo=1)
            funding=sorted([[int(x['fundingTime'])//1000,float(x['fundingRate'])] for x in funding_body['data'] if x.get('symbol')=='BTCUSDT'])
        except asyncio.CancelledError:raise
        except Exception:funding=[]
        snapshots=await asyncio.gather(*(self.market.snapshot(frame) for frame in STEPS),return_exceptions=True)
        for frame,snap in zip(STEPS,snapshots):
            try:
                if isinstance(snap,BaseException):raise ValueError('PUBLIC_FRAME_FAILED')
                await asyncio.to_thread(self.store.observe,snap,funding,time.time(),self.registry)
                self.quotes[frame]=snap['quote'];self.frame_errors.pop(frame,None);success+=1
            except asyncio.CancelledError:raise
            except Exception:
                self.quotes.pop(frame,None)
                self.frame_errors[frame]='FRAME_OBSERVATION_FAILED'
        self.cycles+=1
        self.last_cycle_at=time.time()
        self.error=None if success else 'MARKET_DATA_UNAVAILABLE'
        self.failures=0 if success else self.failures+1
        if self.error:await asyncio.to_thread(self.store.invalidate,time.time(),self.error)

    async def run(self):
        while True:
            try:
                await self.cycle()
            except asyncio.CancelledError:raise
            except Exception:
                # Storage failure (including invalidate) must not silently kill
                # the task while HTTP health continues to report success.
                self.quotes.clear();self.error='OBSERVER_CYCLE_FAILED'
                self.failures+=1;self.last_cycle_at=time.time()
            await asyncio.sleep(min(60,5*2**min(self.failures,4)))


def create_app(*, store=None, market=None, password=None, observe=None):
    configured_password=os.environ.get('AURA_HUNTER_PASSWORD','') if password is None else password
    state_path=os.environ.get('AURA_HUNTER_STATE_PATH',str(ROOT/'work/hunter6/observations.sqlite'))
    enabled=os.environ.get('AURA_HUNTER_OBSERVE','false').lower()=='true' if observe is None else observe
    registry=json.loads(Path(__file__).with_name('eligibility.json').read_text())

    def owner(credentials: HTTPBasicCredentials | None=Depends(security)):
        if not configured_password:
            raise HTTPException(503,'HUNTER_OWNER_ACCESS_NOT_CONFIGURED')
        if credentials is None or not (hmac.compare_digest(credentials.username.encode(),b'owner') and hmac.compare_digest(hashlib.sha256(credentials.password.encode()).digest(),hashlib.sha256(configured_password.encode()).digest())):
            raise HTTPException(401,'OWNER_REQUIRED',headers={'WWW-Authenticate':'Basic realm="Aura 6 Hunter"'})

    @asynccontextmanager
    async def lifespan(app):
        observer=Hunter(store or Store(state_path),market or PublicMarket(),registry)
        app.state.hunter=observer
        task=asyncio.create_task(observer.run()) if enabled and configured_password else None
        app.state.observer_task=task
        try:yield
        finally:
            if task:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
            await observer.market.close()

    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

    @app.middleware('http')
    async def read_only(request,call_next):
        if request.method not in ('GET','HEAD'):
            return JSONResponse({'detail':'READ_ONLY_NO_ORDERS'},status_code=405)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        return response

    @app.get('/api/health')
    async def health():
        task=app.state.observer_task
        stopped=task is not None and task.done()
        data={'status':'degraded' if stopped else 'ok','scope':'AURA6_PUBLIC_OBSERVER_ONLY','account_connected':False,'execution_enabled':False,'observer_enabled':bool(enabled and configured_password)}
        return JSONResponse(data,status_code=503 if stopped else 200)

    @app.get('/',dependencies=[Depends(owner)])
    async def index():return HTMLResponse((ROOT/'static/hunter6/index.html').read_text())

    @app.get('/static/hunter6/{asset}',dependencies=[Depends(owner)])
    async def asset(asset:str):
        if asset not in ('hunter.js','hunter.css'):raise HTTPException(404)
        return Response((ROOT/'static/hunter6'/asset).read_text(),media_type='text/javascript' if asset.endswith('.js') else 'text/css')

    @app.get('/api/hunter/snapshot',dependencies=[Depends(owner)])
    async def snapshot():
        h=app.state.hunter
        task=app.state.observer_task
        running=task is not None and not task.done()
        reason=h.error if running else 'OBSERVER_STOPPED' if task else 'OBSERVER_DISABLED'
        status={'running':running,'cycles':h.cycles,'last_cycle_at':h.last_cycle_at,'frame_errors':dict(h.frame_errors)}
        data=await asyncio.to_thread(h.store.snapshot,time.time(),dict(h.quotes),reason)
        data['observer']=status
        return data

    @app.get('/api/hunter/inputs',dependencies=[Depends(owner)])
    async def inputs(frame:str=Query(pattern='^(5m|15m|1h|4h)$'),after:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
        return await asyncio.to_thread(app.state.hunter.store.export_inputs,frame,after,limit)

    return app


app=create_app()
