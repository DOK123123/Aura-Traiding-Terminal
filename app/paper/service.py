"""Protective virtual exits plus explicitly armed server-owned Auto Paper; no private client."""
import asyncio
import logging
import os
from pathlib import Path

from .engine import Engine
from .market import Market
from .models import PaperError
from .storage import Store
from .auto import Auto

logger = logging.getLogger(__name__)


class Service:
    def __init__(self, market, engine=None, signals=None):
        self.market = market
        self.signals = signals
        self.auto = None
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
        try:
            self.auto = await asyncio.to_thread(Auto,self.engine)
        except PaperError:
            self.failure = 'CORRUPT_JOURNAL'
            logger.error('Auto Paper state corrupt; no execution enabled.')
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
            try:
                await self.auto_tick()
            except PaperError as error:
                logger.warning('Auto Paper monitor: %s',error.code)
            except Exception:
                if self.auto is not None:
                    await asyncio.to_thread(self.auto.fail,'SIGNAL_ERROR')
                logger.error('Auto Paper failed safely; no exchange client available.')
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

    async def state(self, scope='ALL') -> dict:
        async with self.lock:
            data = await asyncio.to_thread(self.ready().snapshot,scope)
            if self.auto is not None:
                data['auto_paper'] = await asyncio.to_thread(self.auto.state)
                data['auto_statistics'] = (await asyncio.to_thread(self.ready().snapshot,'AUTO'))['statistics']
            return data

    async def configure_auto(self,body):
        if self.auto is None:
            raise PaperError('STORAGE_UNAVAILABLE')
        async with self.lock:
            window = await self.market.window(body['symbol'],body['timeframe']) if body['enabled'] else None
            if window is not None and window.source != body['expected_source']:
                raise PaperError('SOURCE_MISMATCH')
            return await asyncio.to_thread(self.auto.configure,body['enabled'],window,fallback_policy=body['fallback_policy'])

    async def auto_tick(self):
        if self.auto is None:return
        initial = await asyncio.to_thread(self.auto.state)
        if not initial['configured']:return
        window = None
        try:
            if initial['enabled'] and len(os.getenv('AURA_TESTNET_VIEW_PASSWORD',''))<12:
                await asyncio.to_thread(self.auto.fail,'OWNER_NOT_CONFIGURED');return
            window = await self.market.window(initial['symbol'],initial['timeframe'])
            # Protective exits remain independent of auto entry state.
            async with self.lock:
                await asyncio.to_thread(self.ready().advance,window)
            signal = None
            if await asyncio.to_thread(self.auto.needs_signal,window):
                if self.signals is None:raise PaperError('SIGNAL_ERROR')
                signal = await self.signals.read(window)
            async with self.lock:
                await asyncio.to_thread(self.auto.process,window,signal,initial['generation'])
        except PaperError as error:
            await asyncio.to_thread(self.auto.fail,error.code,window,initial['generation'])
            logger.warning('Auto Paper public data/decision: %s',error.code)


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
