"""Externally triggered controller. Public market reads, isolated virtual writes."""
import asyncio,logging,os,time,sqlite3
from copy import deepcopy
from .engine import initial,validate,advance,event,mark,risk_reason,DemoError,VERSION,POLICY,STEP
from .strategy import strategy,PARAMETERS
from .storage import SQLiteStore,SupabaseStore
from app.forward.models import scheduler_secret_valid
from app.lab.models import money,text,digest
from decimal import Decimal as D

logger=logging.getLogger(__name__)


def scheduler_configured():
    token=os.getenv('AURA_AUTO42_SCHEDULER_SECRET','')
    return scheduler_secret_valid(token,os.getenv('AURA_TESTNET_VIEW_PASSWORD',''),os.getenv('AURA_AUTO42_SUPABASE_SERVICE_KEY','')) and token!=os.getenv('AURA_FORWARD_SCHEDULER_SECRET','')


class Service:
    def __init__(self,market,store=None,clock=time.time,reason=None):
        self.market=market;self.store=store;self.clock=clock;self.reason=reason;self.task=None;self.closed=False
    def ready(self):
        if self.store is None:raise DemoError(self.reason or 'STORAGE_NOT_CONFIGURED')
    async def close(self):
        self.closed=True
        if self.task and not self.task.done():self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if self.store:await self.store.close()
    async def snapshot(self):
        value=await self.market.snapshot('15m');bars=list(self.market.bars);now=int(self.clock())
        try:decision=strategy(value,bars,now)
        except DemoError as exc:
            if exc.code not in ('MTF_UNAVAILABLE','INVALID_ANALYSIS'):raise
            decision=dict(direction=None,reason=exc.code,error=exc.code)
        
        return bars,decision,now
    async def control(self,action,request_id,expected_revision=None):
        self.ready()
        if self.closed:raise DemoError('SERVICE_CLOSED')
        async with asyncio.timeout(45):
            for attempt in range(3):
                envelope=await self.store.load();s=deepcopy(envelope['state']);now=int(self.clock());validate(s)
                key='command:'+request_id
                prior=await self.store.lookup(key)
                if prior:
                    if prior['payload'].get('action')!=action:raise DemoError('IDEMPOTENCY_CONFLICT')
                    return dict(envelope,duplicate=True,paper_only=True,exchange_execution=False)
                # Stop/emergency require neither fresh market data nor scheduler availability.
                if action=='START':
                    if not scheduler_configured():raise DemoError('SCHEDULER_NOT_CONFIGURED')
                    if s['emergency']:raise DemoError('EMERGENCY_RESET_REQUIRED')
                    if expected_revision is not None and envelope['revision']!=expected_revision:raise DemoError('CONCURRENT_UPDATE')
                    if s['mode']=='ON':raise DemoError('ALREADY_ON')
                    bars,decision,now=await self.snapshot()
                    if decision.get('error'):raise DemoError(decision['error'])
                    if s['position']:
                        # Catch-up protective settlement must precede resuming entries.
                        raise DemoError('OPEN_POSITION_RESUME_REQUIRES_TICK')
                    mark(s,bars[-1],bars[-1].time+STEP)
                    reason=risk_reason(s)
                    if reason:raise DemoError(reason)
                    s.update(mode='ON',pending=None,watermark=bars[-1].time+STEP,last_bar_hash=digest(bars[-1].data()),last_decision='ACTIVATION_BASELINE',last_error=None)
                elif action=='STOP':s.update(mode='OFF',pending=None,last_decision='OWNER_STOP')
                elif action=='EMERGENCY':s.update(mode='EMERGENCY',emergency=True,pending=None,last_decision='EMERGENCY_STOP')
                elif action=='RESET':
                    if s['position']:raise DemoError('RESET_BLOCKED_OPEN_POSITION')
                    if s['mode']=='ON':raise DemoError('STOP_BEFORE_RESET')
                    previous=deepcopy(s);s=initial(now)
                else:raise DemoError('INVALID_ACTION')
                body=dict(action=action,request_id=request_id,mode=s['mode'])
                if action=='RESET':body['archived_account']=previous
                events=[event(s,'CONTROL',request_id,now,body)];events[0]['id']=key
                try:
                    result=await self.store.commit(envelope['revision'],s,events,key)
                    if result['duplicate']:
                        existing=await self.store.lookup(key)
                        if existing['payload'].get('action')!=action:raise DemoError('IDEMPOTENCY_CONFLICT')
                    return dict(result,paper_only=True,exchange_execution=False)
                except DemoError as exc:
                    if exc.code!='CONCURRENT_UPDATE' or attempt==2 or action=='START':raise
            raise DemoError('CONCURRENT_UPDATE')
    async def tick(self):
        self.ready()
        if self.closed:raise DemoError('SERVICE_CLOSED')
        if self.task is None or self.task.done():self.task=asyncio.create_task(self._bounded_tick())
        return await asyncio.shield(self.task)
    async def _bounded_tick(self):
        try:
            async with asyncio.timeout(55):return await self._tick()
        except TimeoutError:
            logger.warning('Auto42 tick: code=TICK_TIMEOUT');raise DemoError('TICK_TIMEOUT') from None
    async def _tick(self):
        envelope=await self.store.load();s=envelope['state'];now=int(self.clock());key=s['epoch']+':tick:'+str(now//300)
        if await self.store.lookup(key):return dict(status='COMPLETED' if s['last_error'] is None else 'PAUSED',mode=s['mode'],paper_only=True,exchange_execution=False,duplicate=True)
        bars=None;decision=None;error=None
        try:
            if s['mode']=='ON' or s['position']:bars,decision,now=await self.snapshot()
        except (DemoError,ValueError,KeyError,TypeError) as exc:
            error=exc.code if isinstance(exc,DemoError) else 'INVALID_ANALYSIS';logger.warning('Auto42 market: code=%s',error)
        for attempt in range(3):
            old=envelope['state'];s=deepcopy(old);events=[];now=int(self.clock())
            # Same data must still be fresh after storage latency/concurrent changes.
            if bars and bars[-1].time+STEP!=now//STEP*STEP:error='STALE_DATA'
            if error:
                s.update(pending=None,last_error=error,last_decision=error)
                if s['mode']=='ON':s['mode']='PAUSED'
                events.append(event(s,'ERROR',now//300,now,dict(reason=error)))
            elif bars is not None:
                try:
                    if decision.get('error'):
                        s['pending']=None
                        if s['mode']=='ON':s['mode']='PAUSED'
                    s,events=advance(s,bars,decision,now)
                    s['last_error']=decision.get('error');s['last_success_at']=now
                except DemoError as exc:
                    logger.warning('Auto42 settlement: code=%s',exc.code)
                    s=deepcopy(old);s.update(pending=None,last_error=exc.code,last_decision=exc.code)
                    if s['mode']=='ON':s['mode']='PAUSED'
                    events=[event(s,'ERROR',now//300,now,dict(reason=exc.code))]
            else:s['last_success_at']=now
            missed=max(0,now//300-old['last_run_at']//300-1) if old['last_run_at'] is not None else 0
            s['missed_runs']+=missed
            s['last_run_at']=now
            events.append(event(s,'TICK',now//300,now,dict(reason=s['last_decision'],mode=s['mode'],missed_slots=missed,success=s['last_error'] is None)))
            events[-1]['id']=key
            try:
                result=await self.store.commit(envelope['revision'],s,events,key)
                return dict(status='COMPLETED' if result['state']['last_error'] is None else 'PAUSED',
                    mode=result['state']['mode'],paper_only=True,exchange_execution=False,duplicate=result['duplicate'])
            except DemoError as exc:
                if exc.code!='CONCURRENT_UPDATE' or attempt==2:raise
                envelope=await self.store.load()
                if envelope['state']['epoch']!=old['epoch']:raise DemoError('PORTFOLIO_RESET_DURING_TICK')
        raise DemoError('CONCURRENT_UPDATE')
    async def dashboard(self):
        if self.store is None:return dict(status='NOT_OPERATIONAL',reason=self.reason or 'STORAGE_NOT_CONFIGURED',paper_only=True,exchange_execution=False,state=None)
        env=await self.store.load();s=env['state'];now=int(self.clock());recent=await self.store.history(epoch=s['epoch'],limit=60)
        fresh=s['last_mark_at'] is not None and 0<=now-s['last_mark_at']<900 and s['last_success_at'] is not None and 0<=now-s['last_success_at']<=360 and s['last_error'] is None
        operational=self.store.durable and scheduler_configured() and s['last_success_at'] is not None and 0<=now-s['last_success_at']<=360 and s['last_error'] is None
        trades=[e['payload'] for e in recent if e['kind']=='CLOSE']
        return dict(status='RECENT_TICK_OBSERVED' if operational else 'NOT_OPERATIONAL',state=s,revision=env['revision'],
            fresh=fresh,current_equity=s['equity'] if fresh else None,unrealized_pnl=text(money(D(s['equity'])-D(s['balance']))) if fresh and s['position'] else None,
            win_rate=text(money(D(s['wins'])/s['trades']*100)) if s['trades'] else None,
            profit_factor=text(money(D(s['gross_profit'])/D(s['gross_loss']))) if D(s['gross_loss']) else None,
            profit_factor_status='NO_LOSSES' if s['trades'] and not D(s['gross_loss']) else 'DEFINED' if D(s['gross_loss']) else 'NO_TRADES',
            missed_scheduler_slots=max(0,now//300-s['last_run_at']//300-1) if s['last_run_at'] is not None else None,
            server_now=now,backend=self.store.backend,durable=self.store.durable,scheduler_configured=scheduler_configured(),
            policy=POLICY,strategy=PARAMETERS,trades=trades,events=recent,paper_only=True,exchange_execution=False)


def configured(market):
    url=os.getenv('AURA_AUTO42_SUPABASE_URL','');key=os.getenv('AURA_AUTO42_SUPABASE_SERVICE_KEY','');path=os.getenv('AURA_AUTO42_SQLITE_PATH','')
    try:
        if path and (url or key):raise DemoError('AMBIGUOUS_STORAGE')
        if path:
            if os.getenv('RENDER','').lower() in ('true','1'):raise DemoError('RENDER_REQUIRES_DURABLE_STORAGE')
            return Service(market,SQLiteStore(path))
        if url and key:return Service(market,SupabaseStore(url,key))
        return Service(market,reason='STORAGE_NOT_CONFIGURED')
    except (DemoError,sqlite3.Error,OSError) as exc:
        return Service(market,reason=exc.code if isinstance(exc,DemoError) else 'STORAGE_UNAVAILABLE')
