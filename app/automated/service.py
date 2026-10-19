"""Externally triggered controller. Public market reads, isolated virtual writes."""
import asyncio,logging,os,time,sqlite3,uuid
from copy import deepcopy
from .engine import initial,validate,advance,event,mark,risk_reason,DemoError,VERSION,POLICY,STEP
from .strategy import strategy,PARAMETERS
from app.intelligence.market_context import SOURCE
from .market_data import snapshot_for_auto
from .storage import SQLiteStore,SupabaseStore
from .diagnostics import configuration,error_category,connection_evidence
from app.forward.models import scheduler_secret_valid
from app.lab.models import money,text,digest
from decimal import Decimal as D

logger=logging.getLogger(__name__)
RETRYABLE_DATA={'STALE_DATA','UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','MTF_UNAVAILABLE','MARKET_TIMEOUT','NETWORK_ERROR','RATE_LIMIT','UPSTREAM_HTTP_ERROR','PUBLIC_DATA_UNAVAILABLE'}


def scheduler_configured():
    token=os.getenv('AURA_AUTO42_SCHEDULER_SECRET','')
    return scheduler_secret_valid(token,os.getenv('AURA_TESTNET_VIEW_PASSWORD',''),os.getenv('AURA_AUTO42_SUPABASE_SERVICE_KEY','')) and token!=os.getenv('AURA_FORWARD_SCHEDULER_SECRET','')


class Service:
    def __init__(self,market,store=None,clock=time.time,reason=None,quotes=None):
        self.market=market;self.store=store;self.clock=clock;self.reason=reason;self.task=None;self.closed=False
        self.quotes=quotes
        self.market_diagnostics=None
        self.last_confirmed=None
        self.activation_error=None
        self.monitor_instance=uuid.uuid4().hex
        self.monitor_capture_error=False
        self.monitor_write_error=None
    def ready(self):
        if self.store is None:raise DemoError(self.reason or 'STORAGE_NOT_CONFIGURED')
    async def close(self):
        self.closed=True
        if self.task and not self.task.done():self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if self.store:await self.store.close()
        if self.quotes:await self.quotes.close()
    async def snapshot(self):
        value=await snapshot_for_auto(self.market);bars=list(self.market.bars);now=int(self.clock())
        allowed={'OK','STALE','UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','NETWORK_ERROR','RATE_LIMIT',
            'REGION_RESTRICTED','UPSTREAM_HTTP_ERROR','INVALID_DATA','INVALID_TIMESTAMPS',
            'DUPLICATE_OR_UNORDERED','INVALID_CLOSE_TIME','INVALID_OHLCV','DATA_LIMIT',
            'INSUFFICIENT_HISTORY','MISSING_CANDLES','PUBLIC_DATA_UNAVAILABLE','UNAVAILABLE'}
        status=value.get('status') if value.get('status') in allowed else 'UNAVAILABLE'
        def stamp(x):
            return x if type(x) in (int,float) and 0<=x<10**12 else None
        self.market_diagnostics=dict(source=SOURCE,checked_at=now,
            last_closed_at=stamp(value.get('last_closed_at')),expected_closed_at=now//STEP*STEP,
            fetched_at=stamp(value.get('fetched_at')),analyzed_at=stamp(value.get('analyzed_at')),
            market_status=status,cache_requested_close=stamp((value.get('history') or {}).get('requested_end_exclusive')),
            cache_state='UNAVAILABLE' if status not in ('OK','STALE') else status,
            error_source='UPSTREAM' if status in {'UPSTREAM_TIMEOUT','NETWORK_ERROR','RATE_LIMIT','REGION_RESTRICTED','UPSTREAM_HTTP_ERROR','PUBLIC_DATA_UNAVAILABLE'} else 'ANALYSIS' if status=='ANALYSIS_TIMEOUT' else 'VALIDATION' if status not in ('OK','STALE') else 'FRESHNESS' if status=='STALE' else None)
        task=getattr(self.market,'task',None)
        self.market_diagnostics['analysis_task']='RUNNING' if task is not None and not task.done() else 'IDLE'
        if status=='ANALYSIS_TIMEOUT':
            self.market_diagnostics['error_source']='ANALYSIS_WAIT' if task is not None and not task.done() else 'ANALYSIS_COMPUTE' if getattr(self.market,'failure',None)=='ANALYSIS_TIMEOUT' else 'ANALYSIS_UNCLASSIFIED'
        logger.info('Auto42 market evidence: %s',self.market_diagnostics)
        if status not in ('OK','STALE'):
            raise DemoError(status)
        try:decision=strategy(value,bars,now)
        except DemoError as exc:
            if exc.code not in ('MTF_UNAVAILABLE','INVALID_ANALYSIS'):raise
            decision=dict(direction=None,reason=exc.code,error=exc.code,
                timeframe_alignment=getattr(exc,'alignment_snapshot',None))
        
        return bars,decision,now
    async def control(self,action,request_id,expected_revision=None):
        self.ready()
        if self.closed:raise DemoError('SERVICE_CLOSED')
        async with asyncio.timeout(45):
            for attempt in range(3):
                envelope=await self.store.load();self.last_confirmed=deepcopy(envelope);s=deepcopy(envelope['state']);now=int(self.clock());validate(s)
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
                    try:
                        bars,decision,now=await self.snapshot()
                    except DemoError as exc:
                        self.activation_error=dict(code=exc.code,checked_at=int(self.clock()),mode=s['mode'])
                        raise
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
                    self.last_confirmed=deepcopy(result);self.activation_error=None
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
        bars=None;decision=None;error=None;alignment_error=None
        try:
            if s['mode']=='ON' or s['position'] or s.get('data_recovery_armed',False):bars,decision,now=await self.snapshot()
        except (DemoError,ValueError,KeyError,TypeError) as exc:
            error=exc.code if isinstance(exc,DemoError) else 'INVALID_ANALYSIS';logger.warning('Auto42 market: code=%s',error)
            alignment_error=getattr(exc,'alignment_snapshot',None)
        for attempt in range(3):
            old=envelope['state'];s=deepcopy(old);events=[];now=int(self.clock())
            # Same data must still be fresh after storage latency/concurrent changes.
            if bars and bars[-1].time+STEP!=now//STEP*STEP:
                error='STALE_DATA'
                if self.market_diagnostics is not None:
                    self.market_diagnostics.update(checked_at=now,expected_closed_at=now//STEP*STEP,error_source='POST_STORAGE_FRESHNESS')
                logger.warning('Auto42 freshness after storage: %s',self.market_diagnostics)
            if error:
                s['data_recovery_armed']=error in RETRYABLE_DATA and not risk_reason(s) and (s['mode']=='ON' or s.get('data_recovery_armed',False))
                s.update(pending=None,last_error=error,last_decision=error)
                if s['mode']=='ON':s['mode']='PAUSED'
                events.append(event(s,'ERROR',now//300,now,dict(reason=error,market=self.market_diagnostics)))
                if alignment_error:
                    s['last_alignment_evaluation']=deepcopy(alignment_error)
                    events[-1]['payload']['timeframe_alignment']=deepcopy(alignment_error)
            elif bars is not None:
                try:
                    if decision.get('error'):
                        s['data_recovery_armed']=decision['error'] in RETRYABLE_DATA and not risk_reason(s) and (s['mode']=='ON' or s.get('data_recovery_armed',False))
                        s['pending']=None
                        if s['mode']=='ON':s['mode']='PAUSED'
                    if not decision.get('error') and s.get('data_recovery_armed',False) and s['mode']=='PAUSED' and not risk_reason(s):
                        s.update(mode='ON',data_recovery_armed=False)
                    s,events=advance(s,bars,decision,now)
                    if (decision.get('error') or any(e['kind']=='DECISION' for e in events)) and decision.get('timeframe_alignment'):
                        s['last_alignment_evaluation']=deepcopy(decision['timeframe_alignment'])
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
            # Observability is isolated from execution: do not re-run strategy,
            # change settlement or let a monitor failure skip protective exits.
            try:
                from .live_monitor import observe_tick,origin
                s,events=observe_tick(old,s,events,key,now,
                    origin(self.store.backend,self.store.durable,self.monitor_instance))
                self.monitor_capture_error=False
            except Exception:
                self.monitor_capture_error=True
                logger.warning('Auto42 monitor capture failed: code=MONITOR_CAPTURE_FAILED')
            try:
                result=await self.store.commit(envelope['revision'],s,events,key)
                self.monitor_write_error=None
                return self.tick_result(result['state'],result['duplicate'],'NO_NEW_WORK' if result['duplicate'] else outcome,processed and not result['duplicate'],[] if result['duplicate'] else events)
            except DemoError as exc:
                if exc.code!='CONCURRENT_UPDATE':self.monitor_write_error=exc.code
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
        if state is None and error and self.last_confirmed is not None:state=self.last_confirmed['state']
        if last_saved_at is None and self.last_confirmed is not None:last_saved_at=self.last_confirmed.get('last_saved_at')
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
        from .live_monitor import origin
        return dict(render_api='ONLINE',storage=storage,configuration=config,checked_at=now,
            runtime=origin(self.store.backend if self.store else 'NOT_CONFIGURED',bool(self.store and self.store.durable),self.monitor_instance),
            scheduler_last_confirmed_at=state['last_run_at'] if state else None,
            scheduler_last_success_at=state['last_success_at'] if state else None,
            last_processed_closed_at=state['watermark'] if state else None,
            last_decision=state['last_decision'] if state else None,last_error=error or (state['last_error'] if state else None),
            last_saved_at=last_saved_at,auto_paper=mode,protection=protection,block_reason=blocked,
            recovery_pending=state.get('data_recovery_armed',False) if state else False,
            market=self.market_diagnostics,owner_mode=state['mode'] if state else None,
            activation_error=self.activation_error)
    def operation_snapshot(self):
        if self.last_confirmed is None:return {}
        return dict(state=deepcopy(self.last_confirmed['state']),revision=self.last_confirmed['revision'],
            server_now=int(self.clock()),fresh=False,scheduler_configured=scheduler_configured())
    async def dashboard(self):
        if self.store is None:return dict(status='NOT_OPERATIONAL',reason=self.reason or 'STORAGE_NOT_CONFIGURED',paper_only=True,exchange_execution=False,state=None,diagnostics=self.diagnostics(error=self.reason or 'STORAGE_NOT_CONFIGURED'))
        env=await self.store.load();self.last_confirmed=deepcopy(env);s=env['state'];now=int(self.clock());recent=await self.store.history(epoch=s['epoch'],limit=60)
        fresh=s['last_mark_at'] is not None and 0<=now-s['last_mark_at']<900 and s['last_success_at'] is not None and 0<=now-s['last_success_at']<=360 and s['last_error'] is None
        operational=self.store.durable and scheduler_configured() and s['last_success_at'] is not None and 0<=now-s['last_success_at']<=360 and s['last_error'] is None
        trades=[e['payload'] for e in recent if e['kind']=='CLOSE']
        history_available=True;history_error=None
        try:
            trade_rows=await self.store.closed_trades(s['epoch'],limit=50)
            trades=[e['payload'] for e in trade_rows]
        except DemoError as exc:
            # Missing optional reader must not suppress the authoritative ledger.
            if exc.code!='STORAGE_SCHEMA_MISSING':raise
            history_available=False;history_error=exc.code;trade_rows=[]
        return dict(status='RECENT_TICK_OBSERVED' if operational else 'NOT_OPERATIONAL',state=s,revision=env['revision'],
            quote_available=self.quotes is not None,
            last_signal=deepcopy((s.get('live_paper_monitor') or {}).get('last_signal')),
            position_net_pnl=text(money(D(s['equity'])-D(s['balance'])-D(s['position']['entry_fee']))) if fresh and s['position'] else None,
            history_is_partial=not history_available or len(trade_rows)==50,
            history_error=history_error,history_available=history_available,
            history_cursor=trade_rows[-1]['seq'] if trade_rows else None,
            fresh=fresh,current_equity=s['equity'] if fresh else None,unrealized_pnl=text(money(D(s['equity'])-D(s['balance']))) if fresh and s['position'] else None,
            win_rate=text(money(D(s['wins'])/s['trades']*100)) if s['trades'] else None,
            profit_factor=text(money(D(s['gross_profit'])/D(s['gross_loss']))) if D(s['gross_loss']) else None,
            profit_factor_status='NO_LOSSES' if s['trades'] and not D(s['gross_loss']) else 'DEFINED' if D(s['gross_loss']) else 'NO_TRADES',
            missed_scheduler_slots=max(0,now//300-s['last_run_at']//300-1) if s['last_run_at'] is not None else None,
            diagnostics=self.diagnostics(s,last_saved_at=env.get('last_saved_at'),fresh=fresh),server_now=now,backend=self.store.backend,durable=self.store.durable,scheduler_configured=scheduler_configured(),
            policy=POLICY,strategy=PARAMETERS,trades=trades,events=recent,paper_only=True,exchange_execution=False)

    async def alignment_dashboard(self):
        from .alignment import present
        self.ready()
        envelope=await self.store.load()
        s=envelope['state'];now=int(self.clock())
        evidence=present(s.get('last_alignment_evaluation'),now)
        if (s['last_error'] or s['last_success_at'] is None or not 0<=now-s['last_success_at']<=360):
            evidence['current_data_fresh']=False
        return dict(evidence,read_only=True,
            paper_only=True,exchange_execution=False,live_autonomy='NOT_TESTED',
            portfolio_last_decision=s['last_decision'],portfolio_last_error=s['last_error'],
            last_processed_closed_at=s['watermark'],revision=envelope['revision'],server_now=now)

    async def live_monitor(self):
        from .live_monitor import monitor_view
        from .live_evidence import evidence
        self.ready()
        envelope=await self.store.load()
        rows=await self.store.history(epoch=envelope['state']['epoch'],limit=200)
        return dict(monitor_view(envelope,rows,now=int(self.clock()),backend=self.store.backend,
            durable=self.store.durable,capture_error=self.monitor_capture_error,storage_error=self.monitor_write_error),technical_test=evidence())


def configured(market):
    # Reuse the existing fixed-host PUBLIC quote reader only. No Practice
    # service/store/commands or quote-based Auto42 fills are introduced.
    from app.practice.market import Quotes
    url=os.getenv('AURA_AUTO42_SUPABASE_URL','');key=os.getenv('AURA_AUTO42_SUPABASE_SERVICE_KEY','');path=os.getenv('AURA_AUTO42_SQLITE_PATH','')
    try:
        if path and (url or key):raise DemoError('AMBIGUOUS_STORAGE')
        if path:
            if os.getenv('RENDER','').lower() in ('true','1'):raise DemoError('RENDER_REQUIRES_DURABLE_STORAGE')
            return Service(market,SQLiteStore(path),quotes=Quotes())
        if url and key:return Service(market,SupabaseStore(url,key),quotes=Quotes())
        return Service(market,reason='STORAGE_NOT_CONFIGURED')
    except (DemoError,sqlite3.Error,OSError) as exc:
        return Service(market,reason=exc.code if isinstance(exc,DemoError) else 'STORAGE_UNAVAILABLE')
