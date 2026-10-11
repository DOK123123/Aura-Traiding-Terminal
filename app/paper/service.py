"""Bounded public-data monitor for protective virtual exits only, never auto-entry."""
import asyncio
import logging
import os
from pathlib import Path

from .engine import Engine
from .market import Market
from .models import PaperError
from .storage import Store

logger = logging.getLogger(__name__)


class Service:
    def __init__(self, market, engine=None):
        self.market = market
        self.engine = engine
        self.failure = None
        self.task = None
        self.lock = asyncio.Lock()

    async def start(self, root: Path) -> None:
        if self.engine is None:
            try:
                path = Path(os.getenv('PAPER_DB_PATH',str(root/'.data'/'paper.sqlite3')))
                self.engine = await asyncio.to_thread(lambda:Engine(Store(path)))
            except (PaperError,OSError,ValueError):
                self.failure = 'STORAGE_UNAVAILABLE'
                logger.error('Paper journal unavailable; virtual ledger was not reset.')
                return
        self.task = asyncio.create_task(self.monitor(),name='paper-protective-exits')

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def ready(self) -> Engine:
        if self.engine is None or self.failure:
            raise PaperError(self.failure or 'STORAGE_UNAVAILABLE')
        return self.engine

    async def monitor(self) -> None:
        while True:
            try:
                await self.refresh()
            except PaperError as error:
                logger.warning('Paper monitor: %s',error.code)
            except Exception:
                logger.error('Paper monitor failed safely; no exchange execution is available.')
            await asyncio.sleep(15)

    async def refresh(self) -> dict:
        async with self.lock:
            engine = self.ready()
            scopes = await asyncio.to_thread(engine.scopes)
            for symbol,timeframe in scopes:
                try:
                    window = await self.market.window(symbol,timeframe)
                    await asyncio.to_thread(engine.advance,window)
                except PaperError as error:
                    await asyncio.to_thread(engine.unavailable,symbol,timeframe,error.code)
                    logger.warning('Paper public market %s/%s: %s',symbol,timeframe,error.code)
        return await self.state()

    async def state(self) -> dict:
        return await asyncio.to_thread(self.ready().snapshot)

    async def quote(self, symbol: str, timeframe: str) -> dict:
        self.ready()
        return (await self.market.window(symbol,timeframe)).quote()

    async def open(self, payload: dict) -> dict:
        async with self.lock:
            engine = self.ready()
            replay = await asyncio.to_thread(engine.replay,payload['request_id'],'open',payload)
            if replay is not None:
                return replay
            window = await self.market.window(payload['symbol'],payload['timeframe'])
            return await asyncio.to_thread(engine.open,payload,window)

    async def close_position(self, trade_id: str, payload: dict) -> dict:
        async with self.lock:
            engine = self.ready()
            replay = await asyncio.to_thread(engine.replay,payload['request_id'],'close',dict(payload,trade_id=trade_id))
            if replay is not None:
                return replay
            trade = await asyncio.to_thread(engine.trade,trade_id)
            window = await self.market.window(trade['symbol'],trade['timeframe'])
            return await asyncio.to_thread(engine.close,trade_id,payload,window)

    async def configure(self, values: dict) -> dict:
        async with self.lock:
            return await asyncio.to_thread(self.ready().configure,values)
