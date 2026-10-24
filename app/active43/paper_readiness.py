"""Bounded owner-only readiness: fresh public market probe and read-only ledger reads.

Never loads/seeds/adopts a service account, rolls risk days, queues signals or ticks.
Scheduled evidence is an authenticated caller claim persisted with the commit,
not independent access to Cloudflare's audit log or proof the client received HTTP200.
"""
import asyncio
import re
from types import SimpleNamespace
from datetime import datetime, timezone
from app.automated.engine import DemoError, risk_reason
from .core import SCOPE, SOURCE, validate
from .market import Market
from .strategies import VERSION, config
from .selection import CHOICES
from .service import Service, scheduler_configured
from .readiness import SAFE_ERRORS


def utc(at: int) -> str:
    return datetime.fromtimestamp(at, timezone.utc).isoformat()


def reason(value: object) -> str:
    # Fixed enum of reasons produced by the relevant production paths.
    allowed = {'AUTO_OFF','POSITION_ALREADY_OPEN','SIGNAL_QUEUED_NEXT_OPEN',
        'BOUNCE_WARMUP','BOUNCE_NO_CONFIRMED_REJECTION','CLOSED_SUPPORT_BOUNCE',
        'CLOSED_RESISTANCE_REJECTION','ACTIVATION_BASELINE','OWNER_STOP',
        'HISTORY_RECOVERED_WAIT_NEXT_CANDLE','DAILY_LOSS_LIMIT','DRAWDOWN_LIMIT',
        'EMERGENCY_STOP','INSUFFICIENT_BALANCE','HISTORY_CANDLE_CHANGED',
        'HISTORY_CANDLE_MISSING','HISTORY_INCOMPLETE','HISTORY_SOURCE_UNAVAILABLE',
        'STALE_DATA','STALE_OR_MISMATCHED_DATA','FUTURES_FILTERS_CHANGED',
        'MINIMUM_SIZE_OR_NOTIONAL','RISK_OR_COST_FILTER','INVALID_STOPS_AT_NEXT_OPEN',
        'RISK_LIMIT','TARGET_AFTER_COSTS','POSITION_LIMIT','INVALID_SIGNAL',
        'FUTURES_FILTERS_UNAVAILABLE','SOURCE_CORRECTION_OR_HISTORY_MISSING'}
    return value if isinstance(value,str) and value in allowed else 'UNCLASSIFIED_DECISION'


def scheduler_evidence(rows: list[dict], state: dict, now: int) -> dict:
    ticks = []
    seen = set()
    for row in rows:
        if row.get('kind') != 'TICK' or row.get('epoch') != state['epoch']:
            continue
        key = row.get('id');created = row.get('created_at')
        match = re.fullmatch(re.escape(state['epoch'])+r':tick:([0-9]{1,12})',key or '')
        proof = row.get('payload',{}).get('scheduled_delivery',{})
        at = proof.get('scheduled_at');inv = proof.get('invocation_id')
        if (not match or key in seen or type(created) is not int
            or not int(match[1])*300 <= created < int(match[1])*300+360
            or proof.get('source') != 'CLOUDFLARE_SCHEDULED_REPORTED'
            or type(at) is not int or not 120 <= at % 300 < 300 or not 0 <= created-at <= 270
            or not isinstance(inv,str) or not re.fullmatch('[a-f0-9]{32}',inv)
            or proof.get('status') != 'COMPLETED' or proof.get('mode') != 'OFF'
            or type(proof.get('opened')) is not int or proof['opened'] != 0
            or type(proof.get('closed')) is not int or proof['closed'] != 0):
            continue
        seen.add(key)
        ticks.append(dict(tick_id=key,created_at=created,created_utc=utc(created),
                          scheduled_at=at,scheduled_utc=utc(at),invocation_id=inv,
                          render_commit=(row['payload'].get('render_commit') if isinstance(row['payload'].get('render_commit'),str)
                              and re.fullmatch('[a-f0-9]{40}',row['payload']['render_commit']) else None),
                          status='COMPLETED',mode='OFF',opened=0,closed=0,state_saved=True))
    ticks.sort(key=lambda x:x['scheduled_at'],reverse=True)
    ticks = ticks[:2]
    ok = (len(ticks)==2 and ticks[0]['scheduled_at']-ticks[1]['scheduled_at']==300
          and ticks[0]['invocation_id'] != ticks[1]['invocation_id']
          and 0 <= now-ticks[0]['created_at'] <= 360
          and 0 <= now-ticks[1]['created_at'] <= 660)
    return dict(status='PASS' if ok else 'BLOCKED',ticks=ticks,
                code=None if ok else 'TWO_RECENT_AUTOMATIC_OFF_TICKS_NOT_CONFIRMED',scan_limit=100,
                evidence='AUTHENTICATED_SCHEDULED_CLAIM_AND_IMMUTABLE_SUPABASE_RECEIPT',
                cloudflare_audit_verified=False,http_delivery_verified=False)


async def inspect(service: Service) -> dict:
    result = dict(scope=SCOPE,market_source=SOURCE,strategy_version=VERSION,
        purpose='PAPER_START_READINESS',status='BLOCKED',read_only=True,state_changed=False,
        paper_only=True,exchange_execution=False,checked_at=int(service.clock()),
        errors=[],account=None,market=None,signal=None,scheduler=None,events=[],
        production_paper_verified=False)
    try:
        async with asyncio.timeout(45):
            service.ready()
            if service.store is None:raise DemoError('ACTIVE43_STORAGE_NOT_CONFIGURED')
            env = await service.store.peek()
            if env is None:raise DemoError('SCHEDULER_ACCOUNT_NOT_INITIALIZED')
            state = env['state'];validate(state)
            if not re.fullmatch('ACTIVE43_BITGET_[a-f0-9]{32}',state['epoch']):
                raise DemoError('CORRUPT_PORTFOLIO')
            if state['config'] not in CHOICES.values():raise DemoError('CONFIG_CHANGED')
            if type(env.get('revision')) is not int or env['revision'] < 1:raise DemoError('STORAGE_INVALID_RESPONSE')
            risk = risk_reason(state)
            result['account'] = dict(mode=state['mode'],balance=state['balance'],
                realized_pnl=state['realized_pnl'],fees=state['fees'],closed_trades=state['trades'],
                open_positions=int(state['position'] is not None),pending=state['pending'] is not None,
                pending_exit=state['pending_exit'] is not None,data_recovery_armed=state['data_recovery_armed'],
                position=(dict(direction=state['position']['direction'],entry_price=state['position']['entry_price'],
                    size=state['position']['size'],stop_loss=state['position'].get('active_stop',state['position']['stop_loss']),
                    take_profit=state['position']['take_profit']) if state['position'] else None),
                strategy=state['config']['strategy'],timeframe=state['config']['timeframe'],
                risk_code=risk,last_confirmed_read_at=int(service.clock()),last_saved_at=env.get('last_saved_at'))
            for blocked,code in ((state['mode']!='OFF','PAPER_NOT_OFF'),
                (state['position'] is not None,'OPEN_POSITION_PRESENT'),
                (state['pending'] is not None or state['pending_exit'] is not None,'PENDING_OPERATION_PRESENT'),
                (state['data_recovery_armed'],'DATA_RECOVERY_ARMED'),
                (state['config']!=config('SR_BOUNCE','5m'),'SR_BOUNCE_5M_NOT_SELECTED'),
                (not scheduler_configured(),'SCHEDULER_NOT_CONFIGURED')):
                if blocked:result['errors'].append(code)
            if risk:result['errors'].append(risk)
            async def market_probe():
                # Separate instance: no production cache/config/cursor changes.
                market = Market(clock=service.clock)
                try:
                    started = service.clock()
                    bars,decision,_ = await market.snapshot(config('SR_BOUNCE','5m'))
                    bars,decision,received = Service.checked_snapshot(
                        SimpleNamespace(clock=service.clock,config=config('SR_BOUNCE','5m')),
                        (bars,decision,service.clock()))
                    if len(bars)<1000 or any(b.time-a.time!=300 for a,b in zip(bars,bars[1:])):
                        raise DemoError('HISTORY_INCOMPLETE')
                    end=bars[-1].time+300
                    result['market']=dict(status='PASS' if not decision.get('error') else 'BLOCKED',
                        last_open_at=bars[-1].time,last_closed_at=end,last_closed_utc=utc(end),
                        received_at=received,received_utc=utc(received),candle_age_seconds=received-end,
                        request_duration_ms=round((service.clock()-started)*1000),history_complete=True,
                        bars=len(bars),history_start_at=bars[0].time,source_sha256=decision['source_sha256'])
                    last=state.get('last_signal') or {}
                    result['signal']=dict(saved_signal=(dict(direction=last['direction'],signal_at=last.get('signal_at'),
                        reason=reason(last.get('reason'))) if last.get('direction') in ('LONG','SHORT') else None),evaluated_at=received,signal_at=decision['signal_at'],
                        direction=decision.get('direction'),strategy_reason=reason(decision.get('reason')),
                        entry_blocker=risk or ('AUTO_OFF' if state['mode']!='ON' else
                            'POSITION_ALREADY_OPEN' if state['position'] else reason(decision.get('reason'))),
                        production_last_decision=reason(state.get('last_decision')),preview_only=True,
                        stop_loss=decision.get('stop_loss'),take_profit=decision.get('take_profit'))
                    if decision.get('error'):
                        result['market']['code']=reason(decision['error'])
                        result['errors'].append(reason(decision['error']))
                except Exception as exc:
                    codes={'UPSTREAM_CLOCK_OR_STALE_RESPONSE','UPSTREAM_TIMEOUT','NETWORK_ERROR',
                        'REGION_OR_ACCESS_RESTRICTED','RATE_LIMIT','HTTP_ERROR','UPSTREAM_API_ERROR',
                        'FUTURES_FILTERS_CHANGED','FUTURES_FILTERS_UNAVAILABLE','HISTORY_INCOMPLETE',
                        'INCOMPLETE_HISTORY','MISSING_CANDLES','STALE_DATA','STALE_OR_MISMATCHED_DATA',
                        'MARKET_UNAVAILABLE','INVALID_MARKET_DATA','SOURCE_MISMATCH'}
                    code=getattr(exc,'code',None)
                    code=code if code in codes else 'FRESH_5M_SNAPSHOT_NOT_CONFIRMED'
                    result['market']=dict(status='BLOCKED',code=code)
                    result['errors'].append(code)
                finally:await market.close()
            async def ledger_probe():
                try:
                    rows=await service.store.history(epoch=state['epoch'],limit=100)
                except Exception as exc:
                    code=exc.code if isinstance(exc,DemoError) and exc.code in SAFE_ERRORS else 'EVENT_HISTORY_READ_FAILED'
                    result['scheduler']=dict(status='BLOCKED',code=code,ticks=[])
                    result['errors'].append(code)
                    return
                now=int(service.clock())
                result['scheduler']=scheduler_evidence(rows,state,now)
                if result['scheduler']['status']!='PASS':result['errors'].append(result['scheduler']['code'])
                result['events']=[dict(kind=r['kind'],created_at=r['created_at'],
                    reason=reason(r.get('payload',{}).get('reason'))) for r in rows[:10]
                    if r.get('kind') in ('OPEN','CLOSE','TICK','SIGNAL','REJECT','DECISION','ERROR','STATE_TRANSITION')]
            async with asyncio.TaskGroup() as group:
                group.create_task(market_probe())
                group.create_task(ledger_probe())
            # A concurrent START, trade, strategy change or heartbeat invalidates this
            # point-in-time snapshot. Never mix different revisions into READY.
            after=await service.store.peek()
            if after is None or after['revision']!=env['revision'] or after['state']!=state:
                result['errors'].append('ACCOUNT_CHANGED_DURING_READ')
            if result['market'] and result['market'].get('status')=='PASS' and result['market'].get('last_closed_at')!=int(service.clock())//300*300:
                result['errors'].append('MARKET_SNAPSHOT_EXPIRED')
            result['checked_at']=int(service.clock())
            result['status']='BLOCKED' if result['errors'] else 'READY'
    except Exception as exc:
        safe = exc.code if isinstance(exc,DemoError) and exc.code in SAFE_ERRORS else 'READINESS_READ_FAILED'
        result['errors'].append(safe)
        result['status']='BLOCKED'
    return result
