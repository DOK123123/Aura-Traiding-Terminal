"""Opt-in Active43 controller. Independent authority, ledger and decision state."""
import asyncio,json,logging,os,re,time,uuid
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
from .recovery import HISTORY_CODES,LEGACY_HISTORY,history_issue,paper_status,protective_advance,transition

logger=logging.getLogger(__name__)

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
        self.readiness_lock=asyncio.Lock()
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
        from .selection import adopt
        await adopt(self,env)
        self.restored=True;return env
    async def select_strategy(self,choice,request_id,revision):
        from .selection import select
        return await select(self,choice,request_id,revision)
    async def snapshot(self):
        return self.checked_snapshot(await self.market.snapshot(self.config))
    def checked_snapshot(self,value):
        bars,decision,_=value;now=int(self.clock());step=STEPS[self.config['timeframe']]
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
                before=env['state'];s=deepcopy(before);now=int(self.clock())
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
                             last_anchor_ohlcv=bars[-1].data(),
                             pending=None,pending_exit=None,last_error=None,last_decision='ACTIVATION_BASELINE',recovery_status='OWNER_STARTED',data_recovery_armed=False)
                    s.update(history_guard=None,protection_watermark=None,protection_bar_hash=None,protection_gap=None,
                             last_fresh_closed_at=None,last_source_error=None,protection_status='FRESH_PROTECTION')
                elif action=='STOP':s.update(mode='OFF',pending=None,pending_exit=None,data_recovery_armed=False,last_error=None,last_decision='OWNER_STOP')
                elif action=='EMERGENCY':s.update(mode='EMERGENCY',emergency=True,pending=None,pending_exit=None,data_recovery_armed=False,last_decision='EMERGENCY_STOP')
                else:raise DemoError('INVALID_ACTION')
                ev=event(s,'CONTROL',request_id,now,dict(action=action));ev['id']=key
                try:
                    await self.store.commit(env['revision'],s,[ev]+transition(before,s,now,key,reason={'START':'OWNER_STARTED','STOP':'OWNER_STOP','EMERGENCY':'EMERGENCY_STOP'}[action]),key)
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
    def evaluate(self,old,data,error,protection,protection_error,now):
        """Evaluate from a CAS snapshot; never commit or call controls here."""
        s=deepcopy(old);events=[];step=STEPS[self.config['timeframe']]
        retry_allowed=(old['mode']=='ON' or old.get('data_recovery_armed',False)
                       or (old['mode']=='PAUSED' and old.get('last_error')==LEGACY_HISTORY))
        issue=None
        try:
            if error:raise DemoError(error)
            if data:
                bars,decision,_=data
                # Revalidate after CAS retries/time spent waiting for storage.
                self.checked_snapshot(data)
                issue=history_issue(s,bars,now)
                if issue:raise DemoError(issue['code'])
                s['history_guard']=None
                recovering=(s['mode']=='PAUSED' and retry_allowed and not risk_reason(s))
                if s.get('protection_watermark'):
                    # Protection already accounted for these bars. Do not replay
                    # exits, invent retrospective entries or reuse old signals.
                    s.update(watermark=bars[-1].time+step,last_bar_hash=digest(bars[-1].data()),pending=None,pending_exit=None)
                    s['last_decision']='HISTORY_RECOVERED_WAIT_NEXT_CANDLE'
                if decision.get('error'):
                    if s['mode']=='ON':s.update(mode='PAUSED',data_recovery_armed=True)
                    s['pending']=None;s['pending_exit']=None
                elif recovering:
                    s.update(mode='ON',data_recovery_armed=False,recovery_status='FRESH_DATA_RECOVERED',last_decision='HISTORY_RECOVERED_WAIT_NEXT_CANDLE')
                s,events=advance(s,bars,decision,now)
                # Audit only the last processed closed candle. Never infer a
                # historical correction from a hash without stored field values.
                if s.get('watermark') is not None:
                    anchor=next((b for b in bars if b.time+step==s['watermark']),None)
                    if anchor is not None and digest(anchor.data())==s['last_bar_hash']:
                        s['last_anchor_ohlcv']=anchor.data()
                s.update(history_guard=None,protection_watermark=None,protection_bar_hash=None,
                         last_error=decision.get('error'),last_source_error=None,last_success_at=now,last_fresh_closed_at=bars[-1].time+step,
                         protection_status='FRESH_PROTECTION_GAP' if s.get('protection_gap') else 'FRESH_PROTECTION')
                if decision.get('error'):
                    s['last_decision']=decision['error']
                    events.append(event(s,'ERROR',now//300,now,dict(reason=decision['error'])))
            if risk_reason(s):s['data_recovery_armed']=False
            return s,events
        except DemoError as exc:
            original=exc.code
            code=({'MISSING_CANDLES':'HISTORY_INCOMPLETE','INCOMPLETE_HISTORY':'HISTORY_INCOMPLETE'}).get(original,original)
            if code in ('MARKET_UNAVAILABLE','UPSTREAM_TIMEOUT','NETWORK_ERROR','HTTP_ERROR','UPSTREAM_API_ERROR'):
                code='HISTORY_SOURCE_UNAVAILABLE'
            s=deepcopy(old)
            s.update(pending=None,pending_exit=None,last_error=code,last_source_error=original,last_decision=code,recovery_status='DATA_BLOCKED')
            if issue:s['history_guard']=issue
            elif code in HISTORY_CODES and not s.get('history_guard'):
                s['history_guard']=dict(code=code,candle_timestamp=None if code=='HISTORY_INCOMPLETE' or s['watermark'] is None else s['watermark']-step,
                    source=SOURCE,old_ohlcv_hash=s['last_bar_hash'],new_ohlcv_hash=None,detected_at=now)
            s['data_recovery_armed']=retry_allowed and not risk_reason(s) and (original in RETRYABLE or code in HISTORY_CODES or code=='HISTORY_SOURCE_UNAVAILABLE')
            if s['mode']=='ON':s['mode']='PAUSED'
            details=dict(reason=code,source_error=original,source=SOURCE,detected_at=now,
                         candle_timestamp=None if code in ('HISTORY_INCOMPLETE','HISTORY_SOURCE_UNAVAILABLE') or s['watermark'] is None else s['watermark']-step,
                         anchor_timestamp=None if s['watermark'] is None else s['watermark']-step,
                         old_ohlcv_hash=s['last_bar_hash'],new_ohlcv_hash=None)
            if issue:details.update(issue)
            # Never use an old cached quote or a failed snapshot for protection.
            trustworthy=data if data else protection
            if s['position'] and trustworthy:
                try:
                    bars,_,_=self.checked_snapshot(trustworthy)
                    # Only the contiguous suffix is eligible when older history
                    # has a gap. protective_advance discloses any coverage gap.
                    cut=max([i+1 for i,(a,b) in enumerate(zip(bars,bars[1:])) if b.time-a.time!=step],default=0)
                    s,events=protective_advance(s,bars[cut:],now)
                except DemoError as protection_exc:
                    s['protection_status']='EMERGENCY_UNTRUSTED_DATA'
                    details['protection_error']=protection_exc.code
            elif s['position']:
                s['protection_status']='EMERGENCY_UNTRUSTED_DATA'
                details['protection_error']=protection_error or original
            else:s['protection_status']='NO_OPEN_POSITION'
            events.append(event(s,'ERROR',now//300,now,details))
            return s,events
    async def _tick(self,require_off=False):
        env=await self.load();now=int(self.clock());key=env['state']['epoch']+':tick:'+str(now//300)
        if require_off:self.require_empty_off(env['state'])
        receipt=await self.store.lookup(key)
        if receipt:return self.result(env['state'],[],True,False,receipt,key)
        data=None;error=None;protection=None;protection_error=None
        if env['state']['mode']=='ON' or env['state']['position'] or env['state'].get('data_recovery_armed') or (env['state']['mode']=='PAUSED' and env['state'].get('last_error')==LEGACY_HISTORY):
            try:data=await self.snapshot()
            except DemoError as exc:error=exc.code
            if error and env['state']['position'] and hasattr(self.market,'protection_snapshot'):
                try:protection=self.checked_snapshot(await self.market.protection_snapshot(self.config))
                except DemoError as exc:protection_error=exc.code
        for attempt in range(3):
            if require_off:self.require_empty_off(env['state'])
            old=env['state'];s=deepcopy(old);events=[];now=int(self.clock());step=STEPS[self.config['timeframe']]
            s,events=self.evaluate(old,data,error,protection,protection_error,now)
            s['missed_runs']+=max(0,now//300-old['last_run_at']//300-1) if old['last_run_at'] else 0
            if not s['last_error']:s['last_successful_run_at']=now
            s['last_run_at']=now;s['recovery_status']='POSITION_RESTORED' if s['position'] and s.get('controller_boot')!=self.boot else s['recovery_status']
            s['controller_boot']=self.boot
            events.extend(transition(old,s,now,key))
            try:
                s=observe(s,events,now,market_native=isinstance(self.market,Market),durable=self.store.durable,backend=self.store.backend)
                s['monitor_error']=None
            except Exception:
                # Passive evidence cannot block an otherwise valid protective close.
                s['monitor_error']='EVIDENCE_CAPTURE_FAILED'
            commit=os.getenv('RENDER_GIT_COMMIT','')
            tick=event(s,'TICK',now//300,now,dict(reason=s['last_decision'],success=s['last_error'] is None,
                render_commit=commit if re.fullmatch('[a-f0-9]{40}',commit) else None));tick['id']=key;events.append(tick)
            from .attribution import scheduled_delivery
            if scheduled_delivery.get() is not None:
                tick['payload']['scheduled_delivery']=dict(scheduled_delivery.get(),
                    status='COMPLETED' if not s['last_error'] else 'PAUSED',mode=s['mode'],
                    opened=sum(e['kind']=='OPEN' for e in events),closed=sum(e['kind']=='CLOSE' for e in events))
            try:
                saved=await self.store.commit(env['revision'],s,events,key)
                # All success responses are checked by reading the immutable tick
                # receipt, so an uncertain DB outcome never reports an OPEN.
                receipt=await self.store.lookup(key)
                if not receipt:raise DemoError('STORAGE_READBACK_OUTCOME_UNKNOWN')
                if not saved['duplicate']:
                    for ev in events:
                        if ev['kind'] in ('ERROR','STATE_TRANSITION'):
                            logger.warning('ACTIVE43_STATE %s',json.dumps({'event':ev['kind'],'scheduler_run_id':key,**ev['payload']},sort_keys=True))
                return self.result(saved['state'],[] if saved['duplicate'] else events,saved['duplicate'],saved['state']['watermark']!=old['watermark'],receipt,key)
            except DemoError as exc:
                if exc.code!='CONCURRENT_UPDATE' or attempt==2:raise
                env=await self.load()
                if env['state']['epoch']!=old['epoch']:raise DemoError('PORTFOLIO_CHANGED')
                if env['state']['config']!=old['config']:raise DemoError('CONFIG_CHANGED')
    @staticmethod
    def result(s,events,duplicate,processed,receipt,key):
        # Evidence comes from the immutable read-back receipt, never from a
        # newly generated ID or an assumed successful commit/HTTP response.
        if (receipt.get('id')!=key or receipt.get('kind')!='TICK' or receipt.get('epoch')!=s['epoch']
            or type(receipt.get('created_at')) is not int or receipt['created_at']<0 or not isinstance(receipt.get('payload'),dict)
            or receipt.get('payload',{}).get('scope')!=SCOPE):raise DemoError('STORAGE_READBACK_OUTCOME_UNKNOWN')
        match=re.fullmatch(r'ACTIVE43_BITGET_[a-f0-9]{32}:tick:([0-9]{1,12})',key)
        if not match:raise DemoError('STORAGE_READBACK_OUTCOME_UNKNOWN')
        commit=os.getenv('RENDER_GIT_COMMIT','');origin=receipt['payload'].get('render_commit')
        return dict(status='PAUSED' if s['last_error'] else 'COMPLETED',paper_only=True,exchange_execution=False,
            tick_id=key,tick_created_at=receipt['created_at'],tick_slot_start=int(match[1])*300,tick_receipt_verified=True,
            render_commit=commit if re.fullmatch('[a-f0-9]{40}',commit) else None,
            tick_render_commit=origin if isinstance(origin,str) and re.fullmatch('[a-f0-9]{40}',origin) else None,
            paper_status=paper_status(s),protection_status=s.get('protection_status'),
            scope=SCOPE,market_source=SOURCE,strategy_version=VERSION,state_saved=True,duplicate=duplicate,processed=processed and not duplicate,
            last_processed_closed_at=s['watermark'],mode=s['mode'],decision=s['last_error'] or s['last_decision'],
            opened=sum(e['kind']=='OPEN' for e in events),closed=sum(e['kind']=='CLOSE' for e in events),
            production_paper_verified=verified(s))
    async def dashboard(self):
        self.ready();env=await self.load();s=env['state'];now=int(self.clock());step=STEPS[self.config['timeframe']]
        trades=await self.store.history(epoch=s['epoch'],kind='CLOSE',limit=50)
        fresh=s['last_mark_at'] is not None and 0<=now-s['last_mark_at']<step and s['last_success_at'] is not None and 0<=now-s['last_success_at']<360 and (not s['last_error'] or s.get('protection_status') in ('FRESH_PROTECTION','FRESH_PROTECTION_GAP'))
        cached=getattr(self.market,'cache',None)
        chart=None
        if cached and cached[1].get('source')==SOURCE and cached[1].get('config_hash')==digest(self.config):
            chart=dict(source=SOURCE,timeframe=self.config['timeframe'],closed_at=cached[0][-1].time+step,
                       bars=[b.data() for b in cached[0][-120:]],read_only=True)
        from .selection import CHOICES
        return dict(strategy_switch_allowed=(s['mode']=='OFF' and all(s.get(k) is None for k in ('position','pending','pending_exit'))
            and s.get('data_recovery_armed') is False and not risk_reason(s)
            and s['config'] in CHOICES.values()),
            chart=chart,scope=SCOPE,state=s,revision=env['revision'],last_saved_at=env['last_saved_at'],server_now=now,
            paper_status=paper_status(s),health_status='SCHEDULER_ERROR' if not scheduler_configured() or s['last_run_at'] is None or not 0<=now-s['last_run_at']<=360 else paper_status(s),
            protection_status=('EMERGENCY_UNTRUSTED_DATA' if not fresh else s.get('protection_status')) if s['position'] else 'NO_OPEN_POSITION',last_status_transition=s.get('last_status_transition'),
            candle_age_seconds=None if s.get('last_fresh_closed_at') is None or s['last_mark_at'] is None else max(0,now-s['last_fresh_closed_at']),
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
