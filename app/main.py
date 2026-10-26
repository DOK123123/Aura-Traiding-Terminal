import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Literal
import logging
import lzma

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .indicators import analyze
from .models import Candle, INTERVALS, validate_candles, data_fresh
from .providers import DataUnavailable
from .bitget_chart import BitgetProvider
from .gold import GoldProvider
from .live import serve_market
from .patterns.api import router as patterns_router
from .testnet.api import router as testnet_router
from .testnet.client import TestnetReader
from .bybit_demo.api import router as bybit_demo_router
from .bybit_demo.client import BybitDemoReader
from .paper.api import router as paper_router
from .paper.market import Market as PaperMarket
from .paper.service import Service as PaperService
from .paper.signals import SignalReader as PaperSignalReader
from .patterns.history import history_service
from .lab.api import router as lab_router
from .lab.service import Service as LabService
from .lab.data import public_page as lab_public_page
from .intelligence.api import router as intelligence_router
from .intelligence.market_context import MarketContext
from .forward.api import router as forward_router
from .forward.service import configured as configured_forward
from .active43.api import router as active43_router
from .active43.service import configured as configured_active43
from .automated.api import router as auto42_router
from .automated.service import configured as configured_auto42
from .bybit_linear.api import router as bybit_linear_router,configured as configured_linear
from .exchange_diagnostics.api import router as diagnostics_router, configured as configured_diagnostics
from .practice.api import router as practice_router
from .practice.service import configured as configured_practice
from .execution_verification import router as verification_router
from .manual_paper.api import router as manual_paper_router
from .manual_paper.service import configured as configured_manual_paper

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = {"BTCUSDT": BitgetProvider()}
cache = {}
locks = {}
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    # Public Bitget, unchanged Active43, and separately configured Manual Paper.
    # Retired ledgers are not constructed, seeded, migrated or repriced.
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        app.state.client = client
        app.state.active43 = configured_active43()
        app.state.manual_paper = configured_manual_paper(client)
        manual_protection = (asyncio.create_task(app.state.manual_paper.run_protection())
                             if app.state.manual_paper.store is not None else None)
        try:
            yield
        finally:
            try:
                if manual_protection is not None:
                    manual_protection.cancel()
                    try:
                        await manual_protection
                    except asyncio.CancelledError:
                        pass
            finally:
                try:
                    await app.state.manual_paper.close()
                finally:
                    await app.state.active43.close()


app = FastAPI(title="Trading Terminal", version="0.1.0", lifespan=lifespan)
app.include_router(patterns_router)
app.include_router(testnet_router)
app.include_router(bybit_demo_router)
app.include_router(paper_router)
app.include_router(lab_router)
app.include_router(intelligence_router)
app.include_router(forward_router)
app.include_router(auto42_router)
app.include_router(active43_router)
app.include_router(bybit_linear_router)
app.include_router(diagnostics_router)
app.include_router(verification_router)
app.include_router(practice_router)
app.include_router(manual_paper_router)
FRAME_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
}


class ProtectedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # StaticFiles normalizes alternate paths (e.g. //index.html). Protect
        # the actual document response, not only one spelling of its route.
        if response.headers.get("content-type", "").split(";", 1)[0] == "text/html":
            response.headers.update(FRAME_HEADERS)
        return response


@app.middleware('http')
async def bitget_only_boundary(request, call_next):
    path = request.url.path
    retired = ('/api/bybit-demo', '/api/bybit-linear', '/api/testnet',
               '/api/auto42', '/api/auto42-verification', '/api/practice', '/api/intelligence',
               '/api/lab', '/api/exchange-diagnostics', '/api/execution-verification',
               '/api/alignment', '/api/live-paper-monitor')
    legacy_paper = path.startswith('/api/paper/') and path != '/api/paper/login'
    if legacy_paper or any(path == prefix or path.startswith(prefix + '/') for prefix in retired):
        from fastapi.responses import JSONResponse
        return JSONResponse({'code':'LEGACY_PROVIDER_RETIRED',
            'message':'Only Bitget Futures is active. Legacy data is preserved; no exchange request or trading action was run.'},
            status_code=410, headers={'Cache-Control':'no-store'})
    return await call_next(request)


app.mount("/static", ProtectedStaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html", headers=FRAME_HEADERS)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.websocket('/ws/market')
async def live_market(socket: WebSocket):
    await serve_market(socket, app.state.client, PROVIDERS)


@app.get("/api/market")
async def market(symbol: Literal["BTCUSDT", "XAUUSD"] = "BTCUSDT",
                 timeframe: Literal["1m", "5m", "15m", "1h"] = "15m",
                 limit: int = Query(500)):
    if limit not in (500, 2000):
        raise HTTPException(422, "Число свечей должно быть 500 или 2000.")
    if symbol not in PROVIDERS:
        raise HTTPException(422, "Доступен только BTCUSDT Bitget USDT-M Futures.")
    key = (symbol, timeframe, limit)
    async with locks.setdefault(key, asyncio.Lock()):
        if key in cache and time.monotonic() - cache[key][0] < 30:
            result = dict(cache[key][1])
            result['stale'] = not data_fresh(Candle(**result['candles'][-1]), timeframe, time.time())
            return result
        provider = PROVIDERS[symbol]
        try:
            async with asyncio.timeout(100):
                candles = await provider.fetch(app.state.client, timeframe, limit)
            if len(candles) < limit:
                raise DataUnavailable(f"Источник вернул {len(candles)} из {limit} свечей.")
            validate_candles(candles, timeframe, now=time.time(),
                             contiguous=symbol == 'BTCUSDT', count=limit)
            analysis = analyze(candles)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, DataUnavailable, TimeoutError, lzma.LZMAError, OSError) as exc:
            logger.warning("Provider %s failed: %s", symbol, exc)
            message = f"{provider.name}: источник временно недоступен или вернул некорректные данные. Повторите запрос позже."
            if isinstance(exc, DataUnavailable):
                message = f"{provider.name}: {exc} Выберите меньшую глубину или повторите запрос позже."
            elif isinstance(exc, httpx.HTTPStatusError):
                message = f"{provider.name}: источник ответил HTTP {exc.response.status_code}. Повторите запрос позже или выберите другой инструмент."
            elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                message = f"{provider.name}: превышено время ожидания источника. Повторите запрос позже."
            raise HTTPException(503, message) from exc
        now = time.time()
        closed_at = candles[-1].time + INTERVALS[timeframe]
        result = {
            "symbol": symbol, "timeframe": timeframe,
            "source": getattr(candles, "source", provider.name), "note": getattr(candles, "note", provider.note),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "last_closed_at": closed_at,
            "stale": not data_fresh(candles[-1], timeframe, now),
            "candles": [asdict(c) for c in candles], "analysis": analysis,
        }
        if symbol == "XAUUSD":
            result.update(fallback=getattr(candles, "fallback", False),
                          fallback_reason=getattr(candles, "reason", None))
        cache[key] = (time.monotonic(), result)
        return result
