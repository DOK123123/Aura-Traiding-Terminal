"""Opt-in public WS ticker preview with bounded REST fallback; no execution."""
import asyncio,json,logging,time
from copy import deepcopy
from websockets.asyncio.client import connect
from .client import Client,IDENTITY,WS,MarketError,number,stamp

log=logging.getLogger(__name__)

class TickerState:
    def __init__(self,clock=time.time):self.clock=clock;self.value=None;self.connected=False
    def reset(self):self.value=None;self.connected=False
    def apply(self,message):
        if not isinstance(message,dict):raise MarketError('INVALID_RESPONSE')
        if message.get('op')=='subscribe':
            if message.get('success') is not True:raise MarketError('SUBSCRIPTION_REJECTED')
            return False
        if message.get('op') in ('pong','ping') or message.get('ret_msg')=='pong':return False
        if message.get('topic')!='tickers.BTCUSDT' or message.get('type') not in ('snapshot','delta'):raise MarketError('SOURCE_MISMATCH')
        data=message.get('data');at=stamp(message.get('ts'));now=self.clock()
        if not isinstance(data,dict) or data.get('symbol')!='BTCUSDT':raise MarketError('SOURCE_MISMATCH')
        if at>now*1000+3000 or now*1000-at>10000:raise MarketError('STALE_DATA')
        if self.value and at<=self.value['server_at_ms']:return False
        if message['type']=='delta' and not self.value:raise MarketError('SNAPSHOT_REQUIRED')
        previous=self.value if message['type']=='delta' else {}
        last=data.get('lastPrice',previous.get('last_price'));mark=data.get('markPrice',previous.get('mark_price'))
        self.value=dict(identity=IDENTITY.data(),last_price=str(number(last,True)),mark_price=str(number(mark,True)),
            server_at_ms=at,received_at=now,transport='WEBSOCKET',status='LIVE',price_semantics='PUBLIC_TICKER_NOT_EXECUTION_AUTHORITY')
        self.connected=True;return True
    def read(self):
        if not self.value:return dict(identity=IDENTITY.data(),status='DISCONNECTED',last_price=None,mark_price=None)
        result=deepcopy(self.value);age=self.clock()-result['server_at_ms']/1000
        if not self.connected or not 0<=age<=10:result['status']='STALE'
        return result

class Feed:
    def __init__(self,client,connector=connect,clock=time.time):
        self.client=client;self.connector=connector;self.clock=clock;self.ticker=TickerState(clock)
        self.task=None;self.closed=False;self.rest_at=None;self.rest_value=None;self.rest_lock=asyncio.Lock();self.error=None
    def start(self):
        if self.task is None:self.task=asyncio.create_task(self.run())
    async def heartbeat(self,ws):
        while True:
            await asyncio.sleep(20);await ws.send(json.dumps({'op':'ping'}))
    async def run(self):
        backoff=1
        while not self.closed:
            heartbeat=None;started=self.clock();self.ticker.reset()
            try:
                await self.client.verify_instrument()
                async with self.connector(WS,open_timeout=5,close_timeout=2,ping_interval=None,max_size=65536,max_queue=16) as ws:
                    await ws.send(json.dumps({'op':'subscribe','args':['tickers.BTCUSDT']}))
                    heartbeat=asyncio.create_task(self.heartbeat(ws))
                    while not self.closed:
                        raw=await asyncio.wait_for(ws.recv(),25)
                        if heartbeat.done():heartbeat.result()
                        try:self.ticker.apply(json.loads(raw))
                        except (ValueError,TypeError):raise MarketError('INVALID_RESPONSE') from None
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.error=exc.code if isinstance(exc,MarketError) else 'WS_DISCONNECTED'
                log.warning('Bybit linear preview: code=%s',self.error)
            finally:
                self.ticker.reset()
                if heartbeat:
                    heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
            if self.clock()-started>=60:backoff=1
            if not self.closed:await asyncio.sleep(backoff);backoff=min(backoff*2,30)
    async def quote(self):
        value=self.ticker.read()
        if value['status']=='LIVE':return value
        async with self.rest_lock:
            if self.rest_at is None or self.clock()-self.rest_at>=15:
                self.rest_at=self.clock()
                try:self.rest_value=await self.client.quote();self.error=None
                except (MarketError,TimeoutError) as exc:self.error=exc.code if isinstance(exc,MarketError) else 'UPSTREAM_TIMEOUT'
            if self.rest_value:
                result=deepcopy(self.rest_value);age=self.clock()-result['server_at_ms']/1000
                result['status']='LIVE' if 0<=age<=10 else 'STALE';result['error']=self.error;return result
        return dict(value,error=self.error or 'DATA_UNAVAILABLE')
    async def close(self):
        self.closed=True
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        await self.client.close()
