"""Externally triggered controller. Public market reads, isolated virtual writes."""
import asyncio,logging,os,time,sqlite3
from copy import deepcopy
from .engine import initial,validate,advance,event,mark,risk_reason,DemoError,VERSION,POLICY,STEP
from .strategy import strategy,PARAMETERS
from .storage import SQLiteStore,SupabaseStore
from .diagnostics import configuration,error_category,connection_evidence
from app.forward.models import scheduler_secret_valid
from app.lab.models import money,text,digest
from decimal import Decimal as D

logger=logging.getLogger(__name__)
RETRYABLE_DATA={'STALE_DATA','UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','MTF_UNAVAILABLE','MARKET_TIMEOUT','NETWORK_ERROR'}


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
                    s.update(mode='ON',data_recovery_armed=False,pending=None,watermark=bars[-1].time+STEP,last_bar_hash=digest(bars[-1].data()),last_decision='ACTIVATION_BASELINE',last_error=None)
                elif action=='STOP':s.update(mode='OFF',data_recovery_armed=False,pending=None,last_error=None,last_decision='OWNER_STOP')
                elif action=='EMERGENCY':s.update(mode='EMERGENCY',emergency=True,data_recovery_armed=False,pending=None,last_error=None,last_decision='EMERGENCY_STOP')
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
        if await self.store.lookup(key):return self.tick_result(s,True,'NO_NEW_WORK',False,[])
        bars=None;decision=None;error=None
        try:
            if s['mode']=='ON' or s['position'] or s.get('data_recovery_armed',False):bars,decision,now=await self.snapshot()
        except (DemoError,ValueError,KeyError,TypeError) as exc:
            error=exc.code if isinstance(exc,DemoError) else 'INVALID_ANALYSIS';logger.warning('Auto42 market: code=%s',error)
        for attempt in range(3):
            old=envelope['state'];s=deepcopy(old);events=[];now=int(self.clock())
            # Same data must still be fresh after storage latency/concurrent changes.
            if bars and bars[-1].time+STEP!=now//STEP*STEP:error='STALE_DATA'
            if error:
                s['data_recovery_armed']=error in RETRYABLE_DATA and not risk_reason(s) and (s['mode']=='ON' or s.get('data_recovery_armed',False))
                s.update(pending=None,last_error=error,last_decision=error)
                if s['mode']=='ON':s['mode']='PAUSED'
                events.append(event(s,'ERROR',now//300,now,dict(reason=error)))
            elif bars is not None:
                try:
                    if decision.get('error'):
                        s['data_recovery_armed']=decision['error'] in RETRYABLE_DATA and not risk_reason(s) and (s['mode']=='ON' or s.get('data_recovery_armed',False))
                        s['pending']=None
                        if s['mode']=='ON':s['mode']='PAUSED'
                    if not decision.get('error') and s.get('data_recovery_armed',False) and s['mode']=='PAUSED' and not risk_reason(s):
                        s.update(mode='ON',data_recovery_armed=False)
                    s,events=advance(s,bars,decision,now)
                    if risk_reason(s):s['data_recovery_armed']=False
                    s['last_error']=decision.get('error');s['last_success_at']=now
                except DemoError as exc:
                    logger.warning('Auto42 settlement: code=%s',exc.code)
                    s=deepcopy(old);s.update(pending=None,last_error=exc.code,last_decision=exc.code,data_recovery_armed=False)
                    if s['mode']=='ON':s['mode']='PAUSED'
                    events=[event(s,'ERROR',now//300,now,dict(reason=exc.code))]
            else:s['last_success_at']=now
            missed=max(0,now//300-old['last_run_at']//300-1) if old['last_run_at'] is not None else 0
            s['missed_runs']+=missed
            s['last_run_at']=now
            processed=s['watermark']!=old['watermark']
            outcome='DATA_BLOCKED' if s['last_error'] else 'RISK_BLOCKED' if risk_reason(s) and s['mode']=='PAUSED' else 'CANDLE_PROCESSED' if processed else 'HEARTBEAT_OFF' if s['mode'] in ('OFF','EMERGENCY') and not s['position'] else 'NO_NEW_CANDLE'
            events.append(event(s,'TICK',now//300,now,dict(reason=s['last_decision'],mode=s['mode'],missed_slots=missed,success=s['last_error'] is None,tick_outcome=outcome,processed=processed)))
            events[-1]['id']=key
            try:
                result=await self.store.commit(envelope['revision'],s,events,key)
                return self.tick_result(result['state'],result['duplicate'],'NO_NEW_WORK' if result['duplicate'] else outcome,processed and not result['duplicate'],[] if result['duplicate'] else events)
            except DemoError as exc:
                if exc.code!='CONCURRENT_UPDATE' or attempt==2:raise
                envelope=await self.store.load()
                if envelope['state']['epoch']!=old['epoch']:raise DemoError('PORTFOLIO_RESET_DURING_TICK')
        raise DemoError('CONCURRENT_UPDATE')
    @staticmethod
    def tick_result(s,duplicate,outcome,processed,events):
        return dict(status='COMPLETED' if s['last_error'] is None else 'PAUSED',mode=s['mode'],
            paper_only=True,exchange_execution=False,duplicate=duplicate,state_saved=True,tick_outcome=outcome,
            processed_this_run=processed,last_processed_closed_at=s['watermark'],decision=s['last_error'] or s['last_decision'],
            opened_positions=sum(e['kind']=='OPEN' for e in events),closed_positions=sum(e['kind']=='CLOSE' for e in events))
    def diagnostics(self,state=None,*,error=None,last_saved_at=None,fresh=False):
        now=int(self.clock());config=configuration();storage=deepcopy(getattr(self.store,'diagnostics',{}))
        if not storage:storage=dict(status='ERROR' if error else 'UNKNOWN',checked_at=now if state or error else None,error_code=error)
        storage['backend']=self.store.backend if self.store else 'NOT_CONFIGURED'
        if error and error.startswith(('STORAGE_','CORRUPT_','INVALID_STORAGE')):storage.update(status='ERROR',error_code=error)
        if self.store is None:storage.update(status='ERROR',error_code=error or self.reason or 'STORAGE_NOT_CONFIGURED')
        storage['error_category']=error_category(storage.get('error_code'))
        storage['connection']=connection_evidence(self.store)
        blocked=error or (risk_reason(state) if state else None)
        if state:
            if not blocked and state['mode']!='ON':blocked=state['last_error'] or ('EMERGENCY_STOP' if state['emergency'] else 'AUTO_OFF')
            if not blocked and not fresh:blocked='STALE_DATA'
            if not blocked and not scheduler_configured():blocked='SCHEDULER_NOT_CONFIGURED'
            if not blocked and state['position']:blocked='POSITION_ALREADY_OPEN'
            if not blocked and state['pending'] is None:blocked=state['last_decision']
        protection='BLOCKED' if error else 'UNKNOWN' if state is None else 'BLOCKED' if blocked else 'OK'
        mode='ERROR' if error or state and state['last_error'] else 'STOPPED' if state and state['mode'] in ('PAUSED','EMERGENCY') else state['mode'] if state else 'ERROR'
        return dict(render_api='ONLINE',storage=storage,configuration=config,checked_at=now,
            scheduler_last_confirmed_at=state['last_run_at'] if state else None,
            scheduler_last_success_at=state['last_success_at'] if state else None,
            last_processed_closed_at=state['watermark'] if state else None,
            last_decision=state['last_decision'] if state else None,last_error=error or (state['last_error'] if state else None),
            last_saved_at=last_saved_at,auto_paper=mode,protection=protection,block_reason=blocked,
            recovery_pending=state.get('data_recovery_armed',False) if state else False)
    async def dashboard(self):
        if self.store is None:return dict(status='NOT_OPERATIONAL',reason=self.reason or 'STORAGE_NOT_CONFIGURED',paper_only=True,exchange_execution=False,state=None,diagnostics=self.diagnostics(error=self.reason or 'STORAGE_NOT_CONFIGURED'))
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
            diagnostics=self.diagnostics(s,last_saved_at=env.get('last_saved_at'),fresh=fresh),server_now=now,backend=self.store.backend,durable=self.store.durable,scheduler_configured=scheduler_configured(),
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
