"""Loopback-only synthetic browser server. Not imported/mounted by production."""
import argparse
import base64
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import os
import time
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from app.manual_paper.api import router as manual_router
from app.manual_paper.service import Service
from app.manual_paper.store import ManualStore
from app.aura_trader5_api import router as analyst_router
from app.aura_trader5_scenarios import wait
from app.indicators import analyze
from tests.test_aura_trader5_scenarios import windows

ROOT=Path(__file__).resolve().parents[1]
PASSWORD='dummy-browser-manual-password'


def create(db):
    os.environ['AURA_TESTNET_VIEW_PASSWORD']=PASSWORD
    fixture=json.loads((ROOT/'tests/fixtures/aura_analyst_synthetic.json').read_text())
    state=dict(case='LONG',bid=None,stale=False,loss=False,unauthorized=False,offset=0)
    now=lambda:fixture['now']+state['offset']
    store=ManualStore(db)
    svc=Service(store,clock=now)
    async def quote():
        p=fixture[state['case'] if state['case'] in ('LONG','SHORT') else 'LONG']['scenario']
        reference=Decimal(str(p['reference_entry']))
        bid=Decimal(state['bid']) if state['bid'] is not None else reference-Decimal('0.1') if state['case']!='SHORT' else reference
        return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',
                    bid=bid,ask=bid+Decimal('0.1'),bid_size=Decimal('1'),ask_size=Decimal('1'),
                    price=bid,time=int(now()*1000)-(6000 if state['stale'] else 0))
    svc.quote=quote
    original_open=svc.open
    async def open_with_loss(*a,**kw):
        receipt=await original_open(*a,**kw)
        if state['loss']:
            state['loss']=False
            raise ValueError('STORAGE_UNAVAILABLE')
        return receipt
    svc.open=open_with_loss
    class Analyst:
        async def inspect(self):
            if state['case'] in ('RATE_LIMIT','HISTORY_CANDLE_CHANGED'):
                return wait(state['case'],now())
            return deepcopy(fixture[state['case']])
    app=FastAPI();app.state.manual_paper=svc;app.state.aura_analyst=Analyst()
    @app.middleware('http')
    async def guard(request,call_next):
        if request.url.path.startswith('/api/manual-paper/') and state['unauthorized']:
            return JSONResponse({'detail':'OWNER_REQUIRED'},status_code=401)
        return await call_next(request)
    app.include_router(manual_router);app.include_router(analyst_router)
    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
    @app.get('/')
    async def page():return FileResponse(ROOT/'static/index.html')
    @app.get('/api/market')
    async def market(timeframe:str='15m',limit:int=500,symbol:str='BTCUSDT'):
        bars=windows()[timeframe]
        return dict(symbol='BTCUSDT',timeframe=timeframe,candles=[asdict(b) for b in bars],
                    analysis=analyze(bars),source=fixture['LONG']['source'],stale=False,
                    last_closed_at=bars[-1].time+{'1m':60,'5m':300,'15m':900,'1h':3600}[timeframe],
                    fetched_at='2027-01-15T08:02:30Z',note='SYNTHETIC FIXTURE')
    @app.post('/__test/control')
    async def control(request:Request):
        change=await request.json();protect=change.pop('protect',False)
        assert set(change)<=set(state)
        state.update(change)
        if protect:await svc.protect()
        return dict(ok=True)
    @app.get('/__test/audit')
    async def audit():
        ledger,version=store.load()
        return dict(version=version,ledger=json.loads(store.encode(ledger)) if ledger else None)
    return app


if __name__=='__main__':
    if os.getenv('RENDER'):raise ValueError('LOCAL_TEST_ONLY')
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args()
    uvicorn.run(create(a.db),host='127.0.0.1',port=a.port,log_level='error')
