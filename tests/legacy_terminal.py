"""Isolated archived-router regression harness, never mounted by production.

The Bitget-only application rejects these routes. Keeping an offline harness
lets existing auth/CSRF/ledger/provider tests continue checking preserved code,
without re-enabling a retired provider in the actual app.
"""
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app import main
from app.testnet.client import TestnetReader
from app.bybit_demo.client import BybitDemoReader
from app.paper.market import Market
from app.paper.service import Service
from app.paper.signals import SignalReader
from app.intelligence.market_context import MarketContext
from app.lab.service import Service as LabService
from app.lab.data import public_page


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        app.state.client=client
        app.state.market_context=MarketContext.from_client(client)
        app.state.forward_validation=main.configured_forward(app.state.market_context)
        app.state.auto42=main.configured_auto42(app.state.market_context)
        app.state.active43=main.configured_active43()
        app.state.exchange_diagnostics=main.configured_diagnostics()
        app.state.bybit_linear_preview=None
        app.state.practice=main.configured_practice()
        app.state.testnet=TestnetReader()
        app.state.bybit_demo=BybitDemoReader()
        async def fetch(symbol,timeframe):return await main.market(symbol,timeframe,500)
        async def history(symbol,timeframe,**kw):return await main.history_service.get(client,symbol,timeframe,**kw)
        app.state.paper=Service(Market(fetch),signals=SignalReader(history,synchronize=True))
        async def page(query):return await public_page(client,query)
        app.state.lab=LabService(main.ROOT,page)
        await app.state.paper.start(main.ROOT)
        try:yield
        finally:
            await app.state.paper.close()
            await app.state.practice.close()
            await app.state.active43.close()
            await app.state.auto42.close()
            await app.state.forward_validation.close()
            await app.state.market_context.close()
            await app.state.bybit_demo.close()
            await app.state.testnet.close()


app=FastAPI(lifespan=lifespan)
for router in (main.testnet_router,main.bybit_demo_router,main.paper_router,
               main.lab_router,main.intelligence_router,main.forward_router,
               main.auto42_router,main.active43_router,main.bybit_linear_router,
               main.diagnostics_router,main.verification_router,main.practice_router):
    app.include_router(router)
app.mount('/static',main.ProtectedStaticFiles(directory=main.ROOT/'static'))
app.add_api_route('/api/health',main.health)
app.add_api_route('/api/market',main.market)
@app.get('/')
def index():return FileResponse(main.ROOT/'tests/fixtures/legacy_terminal.html',headers=main.FRAME_HEADERS)
