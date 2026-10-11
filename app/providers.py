"""Public data adapters; add providers through PROVIDERS in main.py."""
import asyncio
from datetime import datetime, timedelta, timezone
import lzma
from pathlib import Path
import struct
import time
from typing import Protocol

import httpx

from .models import Candle, INTERVALS

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "dukascopy"


class DataUnavailable(Exception):
    pass


class Provider(Protocol):
    name: str
    note: str

    async def fetch(self, client: httpx.AsyncClient, timeframe: str, count: int) -> list[Candle]: ...


class BinanceProvider:
    name = "Binance · Spot"
    note = "BTCUSDT · объём в BTC. Только закрытые свечи; цена — последнее закрытие."

    async def fetch(self, client, timeframe, count, *, now_ms=None):
        now = int(time.time() * 1000) if now_ms is None else now_ms
        end = now
        rows = {}
        for _ in range(4):
            response = await client.get("https://data-api.binance.vision/api/v3/klines", params={
                "symbol": "BTCUSDT", "interval": timeframe, "limit": min(1000, count + 1 - len(rows)),
                "endTime": end,
            })
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            for row in batch:
                if int(row[6]) < now:
                    c = Candle(int(row[0]) // 1000, *map(float, row[1:6]))
                    rows[c.time] = c
            if len(rows) >= count:
                break
            end = int(batch[0][0]) - 1
        return sorted(rows.values(), key=lambda c: c.time)[-count:]


def decode_bi5(data: bytes, origin: int) -> list[Candle]:
    if not data:
        return []
    raw = lzma.decompress(data)
    if len(raw) % 24:
        raise ValueError("Invalid Dukascopy record length")
    # Dukascopy candle format: seconds, open, close, low, high, volume.
    return [Candle(origin + second, op / 1000, high / 1000, low / 1000, close / 1000, volume)
            for second, op, close, low, high, volume in struct.iter_unpack(">5If", raw)
            if op > 0 and close > 0 and volume >= 0]


def aggregate(candles: list[Candle], seconds: int, source_seconds: int, now: int) -> list[Candle]:
    groups = {}
    for candle in sorted({c.time: c for c in candles}.values(), key=lambda c: c.time):
        bucket = candle.time // seconds * seconds
        if bucket + seconds > now:
            continue
        groups.setdefault(bucket, []).append(candle)
    # Exclude partially published last buckets; market breaks are allowed within a bucket.
    latest_end = max((c.time + source_seconds for c in candles), default=0)
    return [Candle(t, rows[0].open, max(c.high for c in rows), min(c.low for c in rows),
                   rows[-1].close, sum(c.volume for c in rows))
            for t, rows in sorted(groups.items()) if t + seconds <= latest_end]


class DukascopyProvider:
    name = "Dukascopy · XAUUSD BID"
    note = "Исторические BID-котировки золота, возможна задержка публикации. Объём источника не является биржевым объёмом всего рынка. Цена — последнее доступное закрытие."

    async def _file(self, client, date, hourly):
        path = (f"XAUUSD/{date.year}/{date.month - 1:02d}/" +
                ("BID_candles_hour_1.bi5" if hourly else f"{date.day:02d}/BID_candles_min_1.bi5"))
        target = CACHE / path
        # Archives can be republished: cache for five minutes.
        if target.exists() and time.time() - target.stat().st_mtime < 300:
            content = target.read_bytes()
        else:
            url = "https://datafeed.dukascopy.com/datafeed/" + path
            response = await client.get(url)
            if response.status_code in (429, 503):
                # Respect short Retry-After values; never retry sooner than requested.
                retry_after = response.headers.get("Retry-After", "2")
                if retry_after.isdigit() and int(retry_after) <= 5:
                    await asyncio.sleep(max(1, int(retry_after)))
                    response = await client.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            content = response.content
            decoded = decode_bi5(content, int(date.timestamp()))
            if content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            return decoded
        return decode_bi5(content, int(date.timestamp()))

    async def fetch(self, client, timeframe, count):
        hourly = timeframe == "1h"
        now = datetime.now(timezone.utc)
        cursor = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if hourly:
            cursor = cursor.replace(day=1)
        all_candles = []
        for _ in range(6 if hourly else 16):
            dates = []
            for _ in range(3):
                dates.append(cursor)
                cursor = ((cursor - timedelta(days=1)).replace(day=1) if hourly else cursor - timedelta(days=1))
            # Settle all file requests before raising to avoid abandoned requests.
            chunks = await asyncio.gather(*(self._file(client, date, hourly) for date in dates), return_exceptions=True)
            for chunk in chunks:
                if isinstance(chunk, BaseException):
                    raise chunk
            all_candles.extend(c for chunk in chunks for c in chunk)
            result = aggregate(all_candles, INTERVALS[timeframe], 3600 if hourly else 60, int(now.timestamp()))
            if len(result) >= count:
                return result[-count:]
        return result[-count:]
