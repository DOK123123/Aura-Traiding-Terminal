"""Source-separated SQLite archive. Never generate bars or mix broker feeds."""
import asyncio
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
import logging

from ..gold import TradingViewGoldProvider, FAILURES, failure_reason, GoldProvider
from ..models import Candle, INTERVALS, validate_candles
from ..providers import DataUnavailable

DB_PATH = Path(__file__).resolve().parents[2] / '.cache' / 'patterns.sqlite3'
logger = logging.getLogger(__name__)


class Archive:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('''CREATE TABLE IF NOT EXISTS candles (
            symbol TEXT, timeframe TEXT, source TEXT, time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY(symbol,timeframe,source,time))''')
        return db

    def save(self, symbol, timeframe, source, candles):
        with closing(self.connect()) as db, db:
            db.executemany('INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?)',
                           [(symbol,timeframe,source,c.time,c.open,c.high,c.low,c.close,c.volume) for c in candles])

    def read(self, symbol, timeframe, source, limit=100000):
        with closing(self.connect()) as db, db:
            rows = db.execute('''SELECT time,open,high,low,close,volume FROM candles
                WHERE symbol=? AND timeframe=? AND source=? ORDER BY time DESC LIMIT ?''',
                              (symbol,timeframe,source,limit)).fetchall()
        return [Candle(*r) for r in reversed(rows)]


@dataclass
class Dataset:
    candles: list[Candle]
    source: str
    fetched_at: float
    requested: int
    note: str


class HistoryService:
    def __init__(self, archive=None):
        self.archive = archive or Archive()
        self.cache, self.locks = {}, {}

    async def binance(self, client, timeframe, count=10000):
        now, rows = int(time.time()*1000), {}
        end = now
        for _ in range((count+999)//1000+1):
            response = await client.get('https://data-api.binance.vision/api/v3/klines', params={
                'symbol':'BTCUSDT','interval':timeframe,'limit':1000,'endTime':end})
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch,list) or not batch:
                break
            for row in batch:
                if int(row[6]) < now:
                    c = Candle(int(row[0])//1000,*map(float,row[1:6]))
                    if c.time in rows and rows[c.time] != c:
                        raise DataUnavailable('Conflicting duplicate Binance archive candle')
                    rows[c.time] = c
            next_end = int(batch[0][0])-1
            if next_end >= end:
                raise DataUnavailable('Non-progressing Binance pagination')
            end = next_end
            if len(rows) >= count:
                break
        return sorted(rows.values(), key=lambda c:c.time)[-count:]

    async def get(self, client, symbol, timeframe):
        key = symbol,timeframe
        async with self.locks.setdefault(key,asyncio.Lock()):
            cached = self.cache.get(key)
            if cached and time.time()-cached.fetched_at < 60:
                return cached
            requested = 10000 if symbol == 'BTCUSDT' else 5000
            note = ''
            async with asyncio.timeout(100):
                if symbol == 'BTCUSDT':
                    rows = await self.binance(client,timeframe,requested)
                    source = 'Binance · Spot'
                else:
                    try:
                        rows = await TradingViewGoldProvider().fetch(client,timeframe,requested)
                        source = TradingViewGoldProvider.name
                    except FAILURES as exc:
                        logger.warning('Gold archive %s fallback: %s', timeframe, exc)
                        note = 'OANDA archive: '+failure_reason(exc)+'. '
                        rows = await GoldProvider().fetch(client,timeframe,2000)
                        source = rows.source
            if len(rows) < 500:
                raise DataUnavailable('Insufficient real archive: fewer than 500 candles')
            step, now = INTERVALS[timeframe], time.time()
            validate_candles(rows, timeframe, now=now, contiguous=symbol=='BTCUSDT')
            if (any(c.time % step or c.time+step > now for c in rows)
                    or any(a.time >= b.time for a,b in zip(rows,rows[1:]))):
                raise DataUnavailable('Invalid archive timestamps')
            # Never use a failed refresh as permission to signal on a stale disk cache.
            if now-rows[-1].time-step > 4*86400:
                raise DataUnavailable('Archive older than four days')
            await asyncio.to_thread(self.archive.save,symbol,timeframe,source,rows)
            merged = await asyncio.to_thread(self.archive.read,symbol,timeframe,source)
            # If a provider rolls back, do not resurrect newer cached bars silently.
            merged = [c for c in merged if c.time <= rows[-1].time]
            if symbol == 'BTCUSDT':
                # Retain the recent continuous segment; old disk gaps must not
                # permanently poison all future requests after a long outage.
                for i in range(len(merged)-1, 0, -1):
                    if merged[i].time != merged[i-1].time + step:
                        logger.warning('BTC archive gap at %s; using continuous recent segment', merged[i].time)
                        merged = merged[i:]
                        note += 'Older archive gap excluded from this analysis. '
                        break
            validate_candles(merged, timeframe, now=now, contiguous=symbol=='BTCUSDT')
            note += ('Closed bars only; archive grows on successful refreshes. '
                     'Broker gaps remain gaps. Horizon counts available bars, not wall-clock minutes. ')
            if len(rows) < requested:
                note += f'Source supplied {len(rows)} of {requested} requested bars. '
            data = Dataset(merged,source,time.time(),requested,note)
            self.cache[key] = data
            return data


history_service = HistoryService()
