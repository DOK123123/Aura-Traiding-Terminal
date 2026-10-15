"""Owner-only market preview. Never accepted by Auto42 or account endpoints."""
import os
from fastapi import APIRouter,Depends,Request
from fastapi.responses import JSONResponse
from app.paper.api import owner,HEADERS
from .client import IDENTITY,MarketError,Client
from .feed import Feed

router=APIRouter(prefix='/api/bybit-linear',tags=['Bybit linear read-only preview'])

def configured():
    return Feed(Client()) if os.getenv('AURA_BYBIT_LINEAR_PREVIEW','').lower()=='true' else None

@router.get('/ticker',dependencies=[Depends(owner)])
async def ticker(request:Request):
    feed=getattr(request.app.state,'bybit_linear_preview',None)
    base=dict(identity=IDENTITY.data(),read_only=True,execution_enabled=False,production_source_unchanged=True)
    if feed is None:return JSONResponse(dict(base,status='FEATURE_DISABLED',code='FEATURE_DISABLED'),status_code=503,headers=HEADERS)
    try:
        value=await feed.quote()
        return JSONResponse(dict(value,**base),status_code=200 if value['status']=='LIVE' else 503,headers=HEADERS)
    except (MarketError,TimeoutError) as exc:
        return JSONResponse(dict(base,status='DATA_UNAVAILABLE',code=exc.code if isinstance(exc,MarketError) else 'UPSTREAM_TIMEOUT'),status_code=503,headers=HEADERS)
