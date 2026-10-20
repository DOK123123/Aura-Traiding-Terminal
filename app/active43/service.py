"""Opt-in Active43 controller. Independent authority, ledger and decision state."""
import asyncio,json,os,time,uuid
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from app.automated.engine import DemoError,risk_reason,mark
from app.lab.models import digest,money,text
from app.forward.models import scheduler_secret_valid
from .core import initial,validate,advance,event,SCOPE,POLICY,SOURCE
from .strategies import config,STEPS,VERSION
from .storage import Store
from .market import Market,Quotes
from .evidence import observe,verified

RETRYABLE={'STALE_DATA','MARKET_UNAVAILABLE','FUTURES_FILTERS_UNAVAILABLE','FUTURES_FILTERS_CHANGED','STALE_OR_MISMATCHED_DATA',
    'REGION_OR_ACCESS_RESTRICTED','RATE_LIMIT','UPSTREAM_TIMEOUT','NETWORK_ERROR','HTTP_ERROR','UPSTREAM_API_ERROR',
    'UPSTREAM_CLOCK_OR_STALE_RESPONSE','REDIRECT_BLOCKED'}


def selected():
    path=Path(__file__).with_name('selection.json')
    if not path.exists():return config()
    if path.stat().st_size>8192:raise DemoError('CONFIG_INVALID')
    try:
        value=json.loads(path.read_text())['config']
        if value!=config(value['strategy'],value['timeframe']):raise ValueError()
        return value
    except (ValueError,KeyError,TypeError):raise DemoError('CONFIG_INVALID') from None


def scheduler_configured():
    token=os.getenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','')
    return (scheduler_secret_valid(token,os.getenv('AURA_TESTNET_VIEW_PASSWORD',''),os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY',''))
            and token not in (os.getenv('AURA_AUTO42_SCHEDULER_SECRET',''),os.getenv('AURA_FORWARD_SCHEDULER_SECRET',''),os.getenv('AURA_ACTIVE43_SCHEDULER_SECRET','')))


def scheduler_auth_configuration():
    """Owner-only configuration metadata, never credential values or fingerprints."""
    token=os.getenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','')
    alternatives=('AURA_AUTO42_SCHEDULER_SECRET','AURA_FORWARD_SCHEDULER_SECRET',
        'AURA_ACTIVE43_SCHEDULER_SECRET','AURA_TESTNET_VIEW_PASSWORD','AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY')
    return dict(secret_variable='AURA_ACTIVE43_BITGET_SCHEDULER_SECRET',
        header_name='X-Aura-Active43-Bitget-Token',endpoint='/api/active43/diagnostics/scheduler',
        token_present=bool(token),token_format_valid=32<=len(token)<=256 and token.isascii() and token.isprintable(),
        token_has_outer_whitespace=token!=token.strip(),
        conflicts_with_variables=[name for name in alternatives if token and token==os.getenv(name,'')],
        configured=scheduler_configured(),config_source='CURRENT_PROCESS_ENV_NO_FALLBACK',
        reads_environment_on_each_request=True,
        environment_changes_require_process_restart=True)


class Service:
    def __init__(self,store=None,market=None,cfg=None,clock=time.time,quotes=None,reason=None):
        self.store=store;self.market=market;self.config=cfg or config();self.clock=clock;self.quotes=quotes;self.reason=reason
        from .diagnostics import Diagnostics
        self.diagnostics=Diagnostics(self)
        self.task=None;self.off_task=None;self.closed=False;self.lock=asyncio.Lock();self.boot=uuid.uuid4().hex;self.restored=False
    def ready(self):
        if self.store is None:raise DemoError(self.reason or 'ACTIVE43_NOT_CONFIGURED')
        if self.closed:raise DemoError('SERVICE_CLOSED')
    async def close(self):
        self.closed=True
        await self.diagnostics.close()
        for task in (self.task,self.off_task):
            if task and not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        for component in (self.store,self.market,self.quotes):
            if component:await component.close()
    async def load(self):
        env=await self.store.load(int(self.clock()));validate(env['state'])
        if env['state']['config']!=self.config:raise DemoError('CONFIG_CHANGED')
        self.restored=True;return env
    async def snapshot(self):
        bars,decision,_=await self.market.snapshot(self.config);now=int(self.clock());step=STEPS[self.config['timeframe']]
        if (not bars or not isinstance(decision,dict) or decision.get('source')!=SOURCE or bars[-1].time+step!=now//step*step or decision.get('signal_at')!=now//step*step
            or decision.get('source_sha256')!=digest([b.data() for b in bars])):raise DemoError('STALE_OR_MISMATCHED_DATA')
        return bars,decision,now
    async def control(self,action,request_id,expected_revision=None):
        self.ready();key='active43:bitget:control:'+request_id
        async with self.lock:
            for attempt in range(3):
                env=await self.load();old=await self.store.lookup(key)
                if old:
                    if old['payload'].get('action')!=action:raise DemoError('IDEMPOTENCY_CONFLICT')
                    return dict(duplicate=True,state_saved=True,paper_only=True,exchange_execution=False)
                s=deepcopy(env['state']);now=int(self.clock())
                if action=='START':
                    if expected_revision!=env['revision']:raise DemoError('CONCURRENT_UPDATE')
                    if not scheduler_configured():raise DemoError('SCHEDULER_NOT_CONFIGURED')
                    if s['mode']=='ON':raise DemoError('ALREADY_ON')
                    if s['position']:raise DemoError('OPEN_POSITION_REQUIRES_PROTECTIVE_TICK')
                    if s['emergency']:raise DemoError('EMERGENCY_STOP')
                    bars,decision,now=await self.snapshot()
                    if decision.get('error'):raise DemoError(decision['error'])
                    mark(s,bars[-1],bars[-1].time+STEPS[self.config['timeframe']])
                    if risk_reason(s):raise DemoError(risk_reason(s))
                    s.update(mode='ON',watermark=bars[-1].time+STEPS[self.config['timeframe']],last_bar_hash=digest(bars[-1].data()),
                             pending=None,pending_exit=None,last_error=None,last_decision='ACTIVATION_BASELINE',recovery_status='OWNER_STARTED',data_recovery_armed=False)
                elif action=='STOP':s.update(mode='OFF',pending=None,pending_exit=None,data_recovery_armed=False,last_error=None,last_decision='OWNER_STOP')
                elif action=='EMERGENCY':s.update(mode='EMERGENCY',emergency=True,pending=None,pending_exit=None,data_recovery_armed=False,last_decision='EMERGENCY_STOP')
                else:raise DemoError('INVALID_ACTION')
                ev=event(s,'CONTROL',request_id,now,dict(action=action));ev['id']=key
                try:
                    await self.store.commit(env['revision'],s,[ev],key)
                    return dict(duplicate=False,state_saved=True,paper_only=True,exchange_execution=False)
                except DemoError as exc:
                    if exc.code!='CONCURRENT_UPDATE' or attempt==2 or action=='START':raise
    async def initialize(self):
        from .setup import initialize
        return await initialize(self)
    @staticmethod
    def require_empty_off(s):
        if s['mode']!='OFF' or any(s.get(k) is not None for k in ('position','pending','pending_exit')) or s.get('data_recovery_armed'):
            raise DemoError('OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT')
        if risk_reason(s):raise DemoError('OFF_TICK_ACCOUNT_RISK_BLOCKED')
    async def verify_off_tick(self):
        self.ready()
        existing=await self.store.peek()
        if existing is None:raise DemoError('SCHEDULER_ACCOUNT_NOT_INITIALIZED')
        validate(existing['state']);self.require_empty_off(existing['state'])
        if self.off_task is None or self.off_task.done():
            self.off_task=asyncio.create_task(self._bounded_tick(require_off=True))
        result=await asyncio.shield(self.off_task)
        if result['mode']!='OFF' or result['opened']!=0 or result['closed']!=0:
            raise DemoError('OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT')
        self.diagnostics.cached=None
        return dict(result,verification_only=True)
    async def tick(self):
        self.ready()
        if self.task is None or self.task.done():self.task=asyncio.create_task(self._bounded_tick())
        return await asyncio.shield(self.task)
    async def _bounded_tick(self,require_off=False):
        try:
            async with asyncio.timeout(50):
                return await self._tick(require_off=True) if require_off else await self._tick()
        except TimeoutError:raise DemoError('TICK_TIMEOUT_OUTCOME_UNKNOWN') from None
    async def _tick(self,require_off=False):
        env=await self.load();now=int(self.clock());key=env['state']['epoch']+':tick:'+str(now//300)
        if require_off:self.require_empty_off(env['state'])
        if await self.store.lookup(key):return self.result(env['state'],[],True,False)
        data=None;error=None
        if env['state']['mode']=='ON' or env['state']['position'] or env['state'].get('data_recovery_armed'):
            try:data=await self.snapshot()
            except DemoError as exc:error=exc.code
        for attempt in range(3):
            if require_off:self.require_empty_off(env['state'])
            old=env['state'];s=deepcopy(old);events=[];now=int(self.clock());step=STEPS[self.config['timeframe']]
            try:
                if data:
                    bars,decision,_=data
                    if bars[-1].time+step!=now//step*step:raise DemoError('STALE_DATA')
                    if decision.get('error'):
                        if s['mode']=='ON':s.update(mode='PAUSED',data_recovery_armed=True)
                        s['pending']=None;s['pending_exit']=None
                    elif s['mode']=='PAUSED' and s.get('data_recovery_armed') and not risk_reason(s):
                        s.update(mode='ON',data_recovery_armed=False,recovery_status='FRESH_DATA_RECOVERED')
                    s,events=advance(s,bars,decision,now)
                    s['last_error']=decision.get('error');s['last_success_at']=now
                    if decision.get('error'):
                        s['last_decision']=decision['error']
                        events.append(event(s,'ERROR',now//300,now,dict(reason=decision['error'])))
                elif error:raise DemoError(error)
                if risk_reason(s):s['data_recovery_armed']=False
            except DemoError as exc:
                s=deepcopy(old);s.update(pending=None,pending_exit=None,last_error=exc.code,last_decision=exc.code,recovery_status='DATA_BLOCKED')
                s['data_recovery_armed']=exc.code in RETRYABLE and not risk_reason(s) and (s['mode']=='ON' or s.get('data_recovery_armed',False))
                if s['mode']=='ON':s['mode']='PAUSED'
                events=[event(s,'ERROR',now//300,now,dict(reason=exc.code))]
            s['missed_runs']+=max(0,now//300-old['last_run_at']//300-1) if old['last_run_at'] else 0
            if not s['last_error']:s['last_successful_run_at']=now
            s['last_run_at']=now;s['recovery_status']='POSITION_RESTORED' if s['position'] and s.get('controller_boot')!=self.boot else s['recovery_status']
            s['controller_boot']=self.boot
            try:
                s=observe(s,events,now,market_native=isinstance(self.market,Market),durable=self.store.durable,backend=self.store.backend)
                s['monitor_error']=None
            except Exception:
                # Passive evidence cannot block an otherwise valid protective close.
                s['monitor_error']='EVIDENCE_CAPTURE_FAILED'
            tick=event(s,'TICK',now//300,now,dict(reason=s['last_decision'],success=s['last_error'] is None));tick['id']=key;events.append(tick)
            try:
                saved=await self.store.commit(env['revision'],s,events,key)
                # All success responses are checked by reading the immutable tick
                # receipt, so an uncertain DB outcome never reports an OPEN.
                if not await self.store.lookup(key):raise DemoError('STORAGE_READBACK_OUTCOME_UNKNOWN')
                return self.result(saved['state'],[] if saved['duplicate'] else events,saved['duplicate'],saved['state']['watermark']!=old['watermark'])
            except DemoError as exc:
                if exc.code!='CONCURRENT_UPDATE' or attempt==2:raise
                env=await self.load()
                if env['state']['epoch']!=old['epoch']:raise DemoError('PORTFOLIO_CHANGED')
    @staticmethod
    def result(s,events,duplicate,processed):
        return dict(status='PAUSED' if s['last_error'] else 'COMPLETED',paper_only=True,exchange_execution=False,
            scope=SCOPE,market_source=SOURCE,strategy_version=VERSION,state_saved=True,duplicate=duplicate,processed=processed and not duplicate,
            last_processed_closed_at=s['watermark'],mode=s['mode'],decision=s['last_error'] or s['last_decision'],
            opened=sum(e['kind']=='OPEN' for e in events),closed=sum(e['kind']=='CLOSE' for e in events),
            production_paper_verified=verified(s))
    async def dashboard(self):
        self.ready();env=await self.load();s=env['state'];now=int(self.clock());step=STEPS[self.config['timeframe']]
        trades=await self.store.history(epoch=s['epoch'],kind='CLOSE',limit=50)
        fresh=s['last_mark_at'] is not None and 0<=now-s['last_mark_at']<step and s['last_success_at'] is not None and 0<=now-s['last_success_at']<360 and not s['last_error']
        cached=getattr(self.market,'cache',None)
        chart=None
        if cached and cached[1].get('source')==SOURCE and cached[1].get('config_hash')==digest(self.config):
            chart=dict(source=SOURCE,timeframe=self.config['timeframe'],closed_at=cached[0][-1].time+step,
                       bars=[b.data() for b in cached[0][-120:]],read_only=True)
        return dict(chart=chart,scope=SCOPE,state=s,revision=env['revision'],last_saved_at=env['last_saved_at'],server_now=now,
            market_status='FRESH_CLOSED_CANDLES' if fresh else 'NOT_FRESH',storage_status='CONNECTED',scheduler_configured=scheduler_configured(),
            position_net_pnl=text(money(D(s['equity'])-D(s['balance'])-D(s['position']['entry_fee']))) if fresh and s['position'] else None,
            current_equity=s['equity'] if fresh else None,win_rate=text(money(D(s['wins'])/s['trades']*100)) if s['trades'] else None,
            trades=[e['payload'] for e in trades],history_cursor=trades[-1]['seq'] if trades else None,history_has_more=len(trades)==50,
            policy=dict(POLICY,timeframe=self.config['timeframe']),restart_readback=self.restored,production_paper_verified=verified(s),
            scheduler_status=('NOT_CONFIGURED' if not scheduler_configured() else 'NEVER_SEEN' if s['last_run_at'] is None else 'FRESH' if 0<=now-s['last_run_at']<=360 else 'STALE'),
            scheduler_age_seconds=None if s['last_run_at'] is None else max(0,now-s['last_run_at']),
            analysis_at=s['watermark'],last_market_success_at=s['last_success_at'],last_successful_run_at=s.get('last_successful_run_at'),market_source=SOURCE,
            live_status='PRODUCTION_PAPER_VERIFIED' if verified(s) else 'WAITING_FOR_REAL_SIGNAL',paper_only=True,exchange_execution=False)


def configured():
    # The dedicated Bitget flag is sufficient when the legacy global flag is absent.
    # An explicit global false remains a kill switch; this never changes durable mode.
    generic=os.getenv('AURA_ACTIVE43_ENABLED')
    if generic is not None and generic.lower()!='true':return Service(reason='ACTIVE43_DISABLED')
    if os.getenv('AURA_ACTIVE43_BITGET_ENABLED','').lower()!='true':return Service(reason='ACTIVE43_BITGET_DISABLED')
    url=os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_URL','');key=os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY','')
    if not url or not key:return Service(reason='ACTIVE43_STORAGE_NOT_CONFIGURED')
    try:
        cfg=selected();return Service(Store(url,key,cfg),Market(),cfg,quotes=Quotes())
    except DemoError as exc:return Service(reason=exc.code)
    except OSError:return Service(reason='CONFIG_INVALID')
