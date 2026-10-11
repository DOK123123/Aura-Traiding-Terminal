"""Live delivery; REST history adapters remain unchanged."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import time
import logging

from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

from .gold import FAILURES, TradingViewGoldProvider, failure_reason
from .indicators import analyze
from .market_state import LiveWindow
from .models import Candle, INTERVALS, validate_candles, data_fresh
from .providers import DataUnavailable

logger = logging.getLogger(__name__)


def envelope(symbol, timeframe, source, mode, candle, *, closed=True, event_time=None, note="", clock_offset=0):
    now = time.time()
    return {
        "symbol": symbol, "timeframe": timeframe, "source": source, "mode": mode,
        "received_at": now, "event_time": event_time,
        "event_age_seconds": None if event_time is None else max(0, now + clock_offset - event_time / 1000),
        "clock_offset_seconds": clock_offset,
        "current_closed": closed, "note": note,
        "last_closed_at": candle.time + INTERVALS[timeframe] if closed else candle.time,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stale": (not data_fresh(candle, timeframe, now + clock_offset, closed=closed)
                  or mode in ('syncing', 'delayed')
                  or (event_time is not None and now + clock_offset - event_time / 1000 > 10)),
    }


def snapshot(candles, symbol, timeframe, source, mode, **kwargs):
    return {**envelope(symbol,timeframe,source,mode,candles[-1],**kwargs),
            "type":"snapshot", "candles":[asdict(c) for c in candles], "analysis":analyze(candles)}


def parse_binance(message, timeframe, clock_offset=0):
    if not isinstance(message, dict) or not isinstance(message.get('k'), dict):
        raise DataUnavailable('Malformed Binance event')
    if message.get('e') != 'kline' or message.get('s') != 'BTCUSDT':
        raise DataUnavailable('Unexpected Binance event')
    k = message['k']
    if k['s'] != 'BTCUSDT' or k['i'] != timeframe or not isinstance(k['x'], bool):
        raise DataUnavailable('Unexpected Binance kline')
    candle = Candle(int(k['t'])//1000, *[float(k[key]) for key in ('o','h','l','c','v')])
    event_time = int(message['E'])
    if event_time > (time.time()+clock_offset+10)*1000 or candle.time > time.time()+clock_offset+10:
        raise DataUnavailable('Future Binance event')
    if event_time <= 0 or time.time()+clock_offset-event_time/1000 > 15:
        raise DataUnavailable('Stale Binance event: fresh history required')
    return candle, k['x'], event_time


async def btc_messages(client, provider, timeframe, limit):
    delay = 2
    while True:
        try:
            # Connect first: the upstream socket buffers events during REST bootstrap.
            async with connect(f'wss://data-stream.binance.vision:443/ws/btcusdt@kline_{timeframe}',
                               open_timeout=10, close_timeout=2, max_queue=32) as upstream:
                response = await client.get('https://data-api.binance.vision/api/v3/time')
                response.raise_for_status()
                server_ms = int(response.json()['serverTime'])
                clock_offset = server_ms/1000 - time.time()
                history = await provider.fetch(client,timeframe,limit,now_ms=server_ms)
                window = LiveWindow(history,timeframe,limit,now=server_ms/1000)
                yield snapshot(history,'BTCUSDT',timeframe,provider.name,'syncing',
                               clock_offset=clock_offset,
                               note='История закрытых свечей; ожидаем событие Binance.')
                while True:
                    raw = await asyncio.wait_for(upstream.recv(), timeout=15)
                    candle, closed, event_time = parse_binance(json.loads(raw),timeframe,clock_offset)
                    rolled = window.apply(candle,closed,event_time)
                    if rolled is None:
                        continue
                    analysis = analyze(window.candles)
                    # Same candle: send just the latest indicator values, not 2000 rows.
                    if not rolled:
                        analysis['series'] = {key: values[-1:] for key,values in analysis['series'].items()}
                    payload = {**envelope('BTCUSDT',timeframe,provider.name,'streaming',candle,
                                           closed=closed,event_time=event_time,clock_offset=clock_offset,
                                           note='Binance WebSocket · текущая свеча предварительная.'),
                               'type':'update','candle':asdict(candle),'analysis':analysis,'rolled':rolled}
                    if rolled:
                        payload['candles'] = [asdict(c) for c in window.candles]
                    yield payload
                    delay = 2
        except FAILURES as exc:
            logger.warning('BTC stream %s/%s failed; retry in %ss: %s', timeframe, limit, delay, exc)
            yield {'type':'status','state':'reconnecting',
                   'message':f'BTC: {failure_reason(exc)}. Данные заморожены; переподключение через {delay} с.'}
            await asyncio.sleep(delay)
            delay = min(30,delay*2)


def gold_snapshot(candles, timeframe, limit, source, mode):
    if len(candles) != limit or any(a.time >= b.time for a,b in zip(candles,candles[1:])):
        raise DataUnavailable('Incomplete gold history')
    now, step = time.time(), INTERVALS[timeframe]
    validate_candles(candles, timeframe, now=now, closed=False, count=limit)
    if any(c.time % step or c.time > now+60 for c in candles) or now-candles[-1].time-step > 4*86400:
        raise DataUnavailable('Invalid or old gold history')
    return snapshot(candles,'XAUUSD',timeframe,source,mode,
                    closed=candles[-1].time+step <= now,
                    note=('OANDA / TradingView · '+('поток источника' if mode=='source_stream' else 'polling 30 с')+
                          '. Задержка котировки источника неизвестна; это не гарантированный realtime.'))


async def gold_messages(client, provider, timeframe, limit):
    while True:
        stream = TradingViewGoldProvider().stream(timeframe,limit)
        try:
            while True:
                candles = await asyncio.wait_for(anext(stream),timeout=60)
                yield gold_snapshot(candles,timeframe,limit,TradingViewGoldProvider.name,'source_stream')
        except FAILURES + (StopAsyncIteration,) as exc:
            logger.warning('Gold stream %s/%s failed: %s', timeframe, limit, exc)
            yield {'type':'status','state':'delayed','message':f'Поток XAUUSD: {failure_reason(exc)}. Переходим на polling 30 с.'}
        finally:
            await stream.aclose()
        poller = gold_poll_messages(client,provider,timeframe,limit)
        restart_at = time.monotonic()+120
        try:
            async for data in poller:
                yield data
                if time.monotonic() >= restart_at:
                    break
        finally:
            await poller.aclose()


async def gold_poll_messages(client, provider, timeframe, limit):
    """Poll whole source-consistent window every 30s; no realtime claim."""
    alternative = TradingViewGoldProvider()
    while True:
        started = time.monotonic()
        try:
            # The archive path is kept for REST. For current candles use OANDA,
            # replacing the entire window so quotes from brokers never mix.
            candles = await alternative.fetch(client,timeframe,limit,include_open=True)
            yield gold_snapshot(candles,timeframe,limit,alternative.name,'polling')
        except FAILURES as exc:
            logger.warning('Gold polling %s/%s failed: %s', timeframe, limit, exc)
            yield {'type':'status','state':'delayed',
                   'message':f'XAUUSD: {failure_reason(exc)}. Проверяем резервную историю; котировки могут задерживаться.'}
            try:
                async with asyncio.timeout(75):
                    candles = await provider.fetch(client,timeframe,limit)
                yield snapshot(candles,'XAUUSD',timeframe,candles.source,'delayed',
                               note='Доступна только история закрытых свечей. ' + candles.note)
            except FAILURES as fallback_error:
                logger.warning('Gold fallback %s/%s failed: %s', timeframe, limit, fallback_error)
                yield {'type':'status','state':'unavailable',
                       'message':f'XAUUSD недоступен: {failure_reason(fallback_error)}. Показанные данные заморожены; повтор автоматически.'}
        await asyncio.sleep(max(1,30-(time.monotonic()-started)))


async def serve_market(socket: WebSocket, client, providers):
    symbol = socket.query_params.get('symbol','BTCUSDT')
    timeframe = socket.query_params.get('timeframe','15m')
    limit_text = socket.query_params.get('limit','500')
    if symbol not in providers or timeframe not in INTERVALS or limit_text not in ('500','2000'):
        await socket.close(code=1008)
        return
    await socket.accept()
    generator = (btc_messages if symbol == 'BTCUSDT' else gold_messages)(client,providers[symbol],timeframe,int(limit_text))
    async def produce():
        async for payload in generator:
            await socket.send_json(payload)
    async def consume():
        while True:
            await socket.receive_text()
    producer, consumer = asyncio.create_task(produce()), asyncio.create_task(consume())
    try:
        done, _ = await asyncio.wait([producer,consumer],return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        producer.cancel()
        consumer.cancel()
        await asyncio.gather(producer,consumer,return_exceptions=True)
        await generator.aclose()
