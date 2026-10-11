"""XAUUSD failover. Each result comes entirely from one real data feed."""
import asyncio
from email.utils import parsedate_to_datetime
import json
import lzma
import time
import uuid
import logging

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from .models import Candle, INTERVALS
from .providers import DataUnavailable, DukascopyProvider

logger = logging.getLogger(__name__)


class CandleBatch(list):
    def __init__(self, candles, source, note, fallback=False, reason=None):
        super().__init__(candles)
        self.source, self.note = source, note
        self.fallback, self.reason = fallback, reason


def frame(payload):
    return f"~m~{len(payload)}~m~{payload}"


class FrameDecoder:
    """Decode length-prefixed messages, including split/combined frames."""
    def __init__(self):
        self.buffer = ""

    def feed(self, data):
        self.buffer += data
        if len(self.buffer) > 4_000_000:
            raise DataUnavailable("Chart response too large")
        messages = []
        while self.buffer:
            if not self.buffer.startswith("~m~"):
                if "~m~".startswith(self.buffer):
                    break
                raise DataUnavailable("Invalid chart framing")
            marker = self.buffer.find("~m~", 3)
            if marker < 0:
                break
            size = int(self.buffer[3:marker])
            if not 0 < size <= 4_000_000:
                raise DataUnavailable("Invalid chart frame size")
            start = marker + 3
            if len(self.buffer) < start + size:
                break
            messages.append(self.buffer[start:start + size])
            self.buffer = self.buffer[start + size:]
        return messages


class TradingViewGoldProvider:
    name = "TradingView · OANDA:XAUUSD"
    note = ("Резервный источник: OANDA:XAUUSD через публичный график TradingView. "
            "Брокерские OTC-котировки золота, не COMEX и не токен. "
            "Объём, если доступен, — объём/активность источника, не всего рынка. "
            "Цена — последнее закрытие. Неофициальный API без гарантии доступности.")

    async def fetch(self, client, timeframe, count, *, include_open=False):
        stream = self.stream(timeframe, count, include_open=include_open)
        try:
            async with asyncio.timeout(45):
                return await anext(stream)
        finally:
            await stream.aclose()

    async def stream(self, timeframe, count, *, include_open=True):
        session = "cs_" + uuid.uuid4().hex[:12]
        decoder = FrameDecoder()
        rows = {}
        now = int(time.time())
        resolved = False
        completed = False
        # One connection owns one source-specific series. Caller bounds silence.
        async with connect("wss://data.tradingview.com/socket.io/websocket",
                           origin="https://www.tradingview.com", open_timeout=10,
                           close_timeout=2, max_size=4_000_000) as socket:
            async def send(method, params):
                await socket.send(frame(json.dumps({"m": method, "p": params}, separators=(",", ":"))))
            # Anonymous chart access only; no login, user credentials or permission flags.
            await send("set_auth_token", ["unauthorized_user_token"])
            await send("chart_create_session", [session, ""])
            await send("resolve_symbol", [session, "gold", '={"symbol":"OANDA:XAUUSD","session":"regular"}'])
            await send("create_series", [session, "prices", "prices", "gold", str(INTERVALS[timeframe] // 60), count + 1])
            async for incoming in socket:
                if not isinstance(incoming, str):
                    raise DataUnavailable("Unexpected binary chart message")
                for payload in decoder.feed(incoming):
                    if payload.startswith("~h~"):
                        await socket.send(frame(payload))
                        continue
                    message = json.loads(payload)
                    if not isinstance(message, dict):
                        raise DataUnavailable('Malformed chart message')
                    method = message.get("m")
                    params = message.get("p", [])
                    if not isinstance(params, list):
                        raise DataUnavailable('Malformed chart parameters')
                    if method in ("critical_error", "protocol_error", "series_error", "symbol_error"):
                        raise DataUnavailable(f"TradingView: {method}")
                    if method == "symbol_resolved":
                        metadata = params[2]
                        if not isinstance(metadata, dict):
                            raise DataUnavailable('Malformed gold instrument metadata')
                        if metadata.get("name") != "XAUUSD" or metadata.get("exchange") != "OANDA":
                            raise DataUnavailable("Unexpected resolved gold instrument")
                        resolved = True
                    if method in ("timescale_update", "du"):
                        if len(params) < 2 or not isinstance(params[1], dict):
                            raise DataUnavailable('Malformed gold series update')
                        prices = params[1].get("prices", {})
                        if not isinstance(prices, dict):
                            raise DataUnavailable('Malformed gold price series')
                        now = int(time.time())
                        for item in prices.get("s", []):
                            values = item["v"]
                            stamp = int(values[0])
                            if stamp + INTERVALS[timeframe] <= now or (include_open and stamp <= now+60):
                                volume = values[5] if len(values) > 5 else None
                                rows[stamp] = Candle(stamp, *map(float, values[1:5]),
                                                     None if volume is None else float(volume))
                        if completed:
                            ordered = sorted(rows.values(), key=lambda c:c.time)[-count:]
                            rows = {c.time:c for c in ordered}
                            yield ordered
                    if method == "series_completed" and params[1] == "prices":
                        if not resolved:
                            raise DataUnavailable("Gold instrument was not verified")
                        completed = True
                        yield sorted(rows.values(), key=lambda c: c.time)[-count:]
        raise DataUnavailable("TradingView closed before completing history")


FAILURES = (httpx.HTTPError, WebSocketException, DataUnavailable, TimeoutError,
            ValueError, TypeError, KeyError, IndexError, lzma.LZMAError, OSError)


def failure_reason(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "таймаут"
    if isinstance(exc, DataUnavailable):
        return str(exc)
    return "ошибка соединения или формата данных"


def cooldown(exc):
    seconds = 120
    if isinstance(exc, httpx.HTTPStatusError):
        value = exc.response.headers.get("Retry-After", "")
        try:
            seconds = max(seconds, int(value) if value.isdigit()
                          else parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            pass
    return seconds


def validate_history(candles, timeframe, count):
    if len(candles) != count:
        raise DataUnavailable(f"неполная история: {len(candles)} из {count} свечей")
    step, now = INTERVALS[timeframe], time.time()
    if any(c.time % step or c.time + step > now for c in candles):
        raise DataUnavailable("неверное время или незакрытые свечи")
    if any(a.time >= b.time for a, b in zip(candles, candles[1:])):
        raise DataUnavailable("неверный порядок или дубликаты свечей")
    # Allows weekend/holiday closures, rejects old archive snapshots as fallback success.
    if now - candles[-1].time - step > 4 * 86400:
        raise DataUnavailable("последняя свеча старше четырёх дней")


class GoldProvider:
    name = "XAUUSD · Dukascopy / TradingView"
    note = ""

    def __init__(self, primary=None, alternative=None):
        self.primary = primary or DukascopyProvider()
        self.alternative = alternative or TradingViewGoldProvider()
        self.retry_at = 0
        self.reason = None
        self.lock = asyncio.Lock()

    async def fetch(self, client, timeframe, count):
        # Serialize gold loads so an outage does not trigger concurrent primary probes.
        async with self.lock:
            if time.monotonic() >= self.retry_at:
                try:
                    async with asyncio.timeout(25):
                        candles = await self.primary.fetch(client, timeframe, count)
                    validate_history(candles, timeframe, count)
                    self.reason = None
                    return CandleBatch(candles, self.primary.name, self.primary.note)
                except FAILURES as exc:
                    logger.warning('Dukascopy %s/%s failed; using fallback: %s', timeframe, count, exc)
                    self.reason = failure_reason(exc)
                    self.retry_at = time.monotonic() + cooldown(exc)
            try:
                candles = await self.alternative.fetch(client, timeframe, count)
                validate_history(candles, timeframe, count)
                return CandleBatch(candles, self.alternative.name, self.alternative.note, True, self.reason)
            except FAILURES as exc:
                logger.warning('Gold fallback %s/%s failed: %s', timeframe, count, exc)
                raise DataUnavailable(f"Dukascopy: {self.reason}; TradingView: {failure_reason(exc)}. "
                                      "Реальные данные недоступны; повторите запрос позже.") from exc
