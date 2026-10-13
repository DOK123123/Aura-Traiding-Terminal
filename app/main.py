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
from .providers import BinanceProvider, DataUnavailable
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

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = {"BTCUSDT": BinanceProvider(), "XAUUSD": GoldProvider()}
cache = {}
locks = {}
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        app.state.client = client
        app.state.market_context = MarketContext.from_client(client)
        app.state.testnet = TestnetReader()
        app.state.bybit_demo = BybitDemoReader()
        async def paper_fetch(symbol, timeframe):
            return await market(symbol, timeframe, 500)
        async def paper_history(symbol,timeframe,**requirements):
            return await history_service.get(client,symbol,timeframe,**requirements)
        app.state.paper = PaperService(PaperMarket(paper_fetch),signals=PaperSignalReader(paper_history,synchronize=True))
        async def lab_page(query):
            return await lab_public_page(client,query)
        app.state.lab = LabService(ROOT,lab_page)
        await app.state.paper.start(ROOT)
        try:
            yield
        finally:
            await app.state.market_context.close()
            await app.state.paper.close()
            await app.state.bybit_demo.close()
            await app.state.testnet.close()


app = FastAPI(title="Trading Terminal", version="0.1.0", lifespan=lifespan)
app.include_router(patterns_router)
app.include_router(testnet_router)
app.include_router(bybit_demo_router)
app.include_router(paper_router)
app.include_router(lab_router)
app.include_router(intelligence_router)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


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
