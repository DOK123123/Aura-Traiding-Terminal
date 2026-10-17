"""Owner commands and independent protective quote monitor; never a strategy/scheduler."""
import asyncio
from decimal import Decimal as D
import os
import time
from app.lab.models import digest,text,money
from app.automated.engine import DemoError,dec,POLICY
from .core import transition,quote_checked,SCOPE
from .market import Quotes
from .storage import Store

class Service:
    def __init__(self,store=None,quotes=None,clock=time.time):
        self.store=store;self.quotes=quotes;self.clock=clock;self.lock=asyncio.Lock();self.task=None;self.error=None
    def ready(self):
        if not self.store:raise DemoError('PRACTICE_NOT_CONFIGURED')
    def start(self):
        if self.store:self.task=asyncio.create_task(self.monitor())
    async def close(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if self.quotes:await self.quotes.close()
        if self.store:await self.store.close()
    async def monitor(self):
        while True:
            try:await self.tick()
            except Exception:self.error='PRACTICE_MONITOR_UNAVAILABLE_NO_CONFIRMATION'
            await asyncio.sleep(3)
    async def quote(self):
        self.ready();return quote_checked(await self.quotes.get(),self.clock())
    async def view(self):
        self.ready();env=await self.store.load(int(self.clock()));s=env['state'];p=s['position'];q=s['last_quote']
        fresh=bool(q and -2000<=self.clock()*1000-q['time_ms']<=10000 and not self.error)
        net=text(money(dec(s['equity'])-dec(s['balance'])-dec(p['entry_fee']))) if p and fresh else None
        events=await self.store.history()
        return dict(scope=SCOPE,paper_only=True,real_orders=False,status='PRACTICE_ONLY_NOT_LIVE_VERIFIED',state=s,position_pnl_after_exit_costs=net,available_balance=text(max(D(0),money(dec(s['balance'])-(dec(p['notional']) if p else D(0))))),quote_fresh=fresh,error=self.error,events=events,history_is_partial=True,storage=dict(backend=self.store.backend,revision=env['revision'],last_saved_at=env['last_saved_at'],read_back_verified=True),policy=dict(POLICY,execution='MANUAL_FRESH_QUOTE',timeframe='QUOTE',classification='PAPER_PRACTICE_ONLY_NOT_STRATEGY'))
    async def command(self,kind,body):
        self.ready();key='practice:cmd:'+body['request_id'];binding=digest(dict(kind=kind,body=body))
        async with self.lock:
            previous=await self.store.history(limit=1,key=key)
            if previous:
                if previous[0].get('command_hash')!=binding:raise DemoError('IDEMPOTENCY_CONFLICT')
                return dict(confirmed=True,duplicate=True,receipt=previous[0],view=await self.view())
            env=await self.store.load(int(self.clock()));q=await self.quote()
            s,event=transition(env['state'],q,int(self.clock()),kind,body)
            event.update(id=key,command_hash=binding,command_id=body['request_id'])
            saved=await self.store.commit(env['revision'],s,event,key)
            # Only durable read-back constitutes confirmation; uncertain response stays an error.
            rows=await self.store.history(limit=1,key=key)
            if not rows or rows[0].get('command_hash')!=binding:raise DemoError('STORAGE_READBACK_FAILED_OUTCOME_UNKNOWN')
            self.error=None
            return dict(confirmed=True,duplicate=saved.get('duplicate',False),receipt=rows[0],view=await self.view())
    async def tick(self):
        self.ready()
        async with self.lock:
            env=await self.store.load(int(self.clock()));old=env['state']
            if not old['position']:
                self.error=None;return
            q=await self.quote()
            if old['last_quote']==q:
                self.error=None;return
            s,event=transition(old,q,int(self.clock()),'UPDATE',{})
            key='practice:mark:'+old['position']['id']+':'+str(q['trade_id']);event.update(id=key)
            await self.store.commit(env['revision'],s,event,key);self.error=None


def configured():
    if os.getenv('AURA_PRACTICE_ENABLED','').lower()!='true':return Service()
    url=os.getenv('AURA_PRACTICE_SUPABASE_URL','');key=os.getenv('AURA_PRACTICE_SUPABASE_SERVICE_KEY','')
    if not url or not key:return Service()
    try:return Service(Store(url,key),Quotes())
    except DemoError:return Service()
