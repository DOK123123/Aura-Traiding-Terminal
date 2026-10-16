"""Passive evidence from committed Auto42 transitions; never an execution engine."""
from copy import deepcopy
from decimal import Decimal as D
import os
import re

from app.lab.models import money,text,precise
from app.intelligence.market_context import SOURCE
from .engine import event

SCHEMA='AUTO42_LIVE_MONITOR_1'
EVENT_TYPES={'SIGNAL','REJECTED','OPEN','POSITION_UPDATE','CLOSE_TP','CLOSE_SL','ERROR'}


def origin(backend: str, durable: bool, instance: str) -> dict:
    commit=os.getenv('RENDER_GIT_COMMIT','')
    render=os.getenv('RENDER','').lower() in ('1','true')
    return dict(render=render,render_commit=commit if re.fullmatch(r'[a-f0-9]{40}',commit) else None,
        backend=backend,durable=durable,controller_instance=instance,
        production_evidence=render and backend=='SUPABASE_POSTGRES' and durable)


@precise
def position_view(s: dict) -> dict | None:
    p=s['position']
    if not p:return None
    allowed=('id','direction','symbol','timeframe','signal_at','entry_time','entry_price','entry_raw_price',
        'size','notional','stop_loss','take_profit','entry_fee','risk_usdt','risk_budget_usdt','source')
    value={k:p.get(k) for k in allowed}
    # Exactly the existing liquidation equity mark; no new quote or fill.
    unrealized=money(D(s['equity'])-D(s['balance']))
    value.update(marked_at=s['last_mark_at'],unrealized_after_exit_costs=text(unrealized),
        net_pnl_including_entry_fee=text(money(unrealized-D(p['entry_fee']))))
    return value


def observe_tick(old: dict, state: dict, events: list, run_id: str, now: int, provenance: dict) -> tuple[dict,list]:
    """Add bounded evidence only, to the same CAS commit as original transitions.

    Work on copies so failure cannot partially modify financial state/events.
    No history backfill: legacy positions have no fabricated OPEN evidence.
    """
    s=deepcopy(state);out=deepcopy(events)
    prior=s.get('live_paper_monitor') or {}
    summary=deepcopy(prior) if prior.get('schema')==SCHEMA else dict(schema=SCHEMA)
    records=[]

    def add(kind,closed_at,reason,position_id=None,*,details=None):
        row=dict(schema=SCHEMA,event_id=run_id+':live:'+str(len(records)),event_type=kind,utc_timestamp=now,position_id=position_id,
            scheduler_run_id=run_id,closed_candle_at=closed_at,
            candle_id='BTCUSDT:15m:close:'+str(closed_at) if closed_at is not None else None,
            reason=reason,source=SOURCE,origin=deepcopy(provenance),details=details or {})
        records.append(row)
        return row

    for ev in events:
        p=ev['payload'];kind=ev['kind']
        if kind=='DECISION':
            signal=p.get('signal') or {};at=p.get('closed_at')
            if signal.get('direction') in ('LONG','SHORT'):
                candidate=s['epoch']+':position:'+str(at)
                summary['last_signal']=add('SIGNAL',at,signal['reason'],candidate,
                    details=dict(direction=signal['direction'],signal_at=at,
                        stop_loss=signal.get('stop_loss'),take_profit=signal.get('take_profit')))
            if p.get('reason')!='SIGNAL_QUEUED_NEXT_OPEN':
                summary['last_rejection']=add('REJECTED',at,p.get('reason'),
                    s['position']['id'] if s['position'] else None)
        elif kind=='REJECT':
            summary['last_rejection']=add('REJECTED',int(ev['id'].rsplit(':',1)[-1])+900,p.get('reason'),
                (old.get('pending') or {}).get('signal_at') and s['epoch']+':position:'+str(old['pending']['signal_at']))
        elif kind=='OPEN':
            summary['last_open']=add('OPEN',p['entry_time']+900,p['reason'],p['id'],
                details={k:p.get(k) for k in ('entry_time','signal_at','entry_price','size','notional','stop_loss','take_profit',
                    'entry_fee','direction','risk_usdt','risk_budget_usdt')})
            signal=summary.get('last_signal')
            summary['last_open']['signal']=deepcopy(signal) if signal and signal['position_id']==p['id'] else None
        elif kind=='CLOSE':
            exit_reason=p.get('exit_reason','')
            event_type='CLOSE_TP' if exit_reason.startswith('TAKE_PROFIT') else 'CLOSE_SL' if exit_reason.startswith('STOP') else 'ERROR'
            closed_at=p['exit_time']+900 if exit_reason in ('STOP_GAP','TAKE_PROFIT_GAP_CONSERVATIVE') else p['exit_time']
            closed=add(event_type,closed_at,exit_reason,p['id'],
                details={k:p.get(k) for k in ('entry_time','signal_at','entry_price','exit_time','exit_price','exit_fee',
                    'entry_fee','fees','realized_pnl','gross_price_pnl','direction')})
            summary['last_close']=closed
            opened=summary.get('last_open')
            if (event_type in ('CLOSE_TP','CLOSE_SL') and opened and opened['position_id']==closed['position_id']
                    and opened['utc_timestamp']<=closed['utc_timestamp']
                    and opened.get('signal') and opened['origin'].get('production_evidence') and provenance.get('production_evidence')
                    and opened['origin'].get('render_commit') and provenance.get('render_commit')):
                summary['verified_cycle']=dict(open=deepcopy(opened),close=deepcopy(closed))
        elif kind=='ERROR':
            summary['last_error']=add('ERROR',s['watermark'],p.get('reason'),s['position']['id'] if s['position'] else None,
                details=dict(candle_role='LAST_PROCESSED',attempted_closed_at=now//900*900))
    # Missing-MTF decisions can still accompany protective exits; retain the
    # error independently instead of treating them as successful strategy signals.
    if s.get('last_error') and not any(r['event_type']=='ERROR' for r in records):
        summary['last_error']=add('ERROR',s['watermark'],s['last_error'],s['position']['id'] if s['position'] else None)
    if s['position'] and s['last_mark_at']!=old['last_mark_at']:
        summary['last_position_update']=add('POSITION_UPDATE',s['last_mark_at'],'CLOSED_CANDLE_LIQUIDATION_MARK',
            s['position']['id'],details=position_view(s))
    # Always retain just one snapshot per category, not an unbounded state log.
    summary.update(last_scheduler_run_id=run_id,last_scheduler_tick_at=now,
        last_processed_closed_at=s['watermark'],observed_mode=s['mode'])
    for i,row in enumerate(records):
        e=event(s,'LIVE_MONITOR',run_id+':'+str(i),now,row)
        e['id']=run_id+':live:'+str(i)
        out.append(e)
    s['live_paper_monitor']=summary
    return s,out


def monitor_view(envelope: dict, events: list, *, now: int, backend: str, durable: bool, capture_error: bool=False, storage_error: str | None=None) -> dict:
    s=envelope['state'];summary=s.get('live_paper_monitor') or {}
    summary=summary if summary.get('schema')==SCHEMA else {}
    cycle=summary.get('verified_cycle')
    # Trust only matching durable, Render-labelled OPEN/CLOSE evidence, not an
    # offline PASS, a legacy CLOSE, position presence or an account trade count.
    qualified=bool(backend=='SUPABASE_POSTGRES' and durable and cycle and cycle['open'].get('signal')
        and cycle['open']['position_id']==cycle['close']['position_id']
        and cycle['open']['origin'].get('production_evidence') and cycle['close']['origin'].get('production_evidence')
        and cycle['open']['origin'].get('render_commit') and cycle['close']['origin'].get('render_commit'))
    error=storage_error or s['last_error'] or ('MONITOR_CAPTURE_FAILED' if capture_error else None)
    status='FAILED' if error else 'VERIFIED' if qualified else 'WAITING_FOR_REAL_SIGNAL'
    fresh=(s['last_mark_at'] is not None and 0<=now-s['last_mark_at']<900
        and s['last_success_at'] is not None and 0<=now-s['last_success_at']<=360 and not s['last_error'])
    position=position_view(s)
    if position and not fresh:
        position['last_known_net_pnl']=position['net_pnl_including_entry_fee']
        position['net_pnl_including_entry_fee']=None
        position['unrealized_after_exit_costs']=None
    rows=[dict(e['payload'],event_id=e['id']) for e in events if e['kind']=='LIVE_MONITOR']
    rows.sort(key=lambda r:(r['utc_timestamp'],r['event_id']),reverse=True)
    reason=error or ('COMMITTED_RENDER_SUPABASE_OPEN_CLOSE' if qualified else
        'WAITING_FOR_CLOSE' if s['position'] else 'WAITING_FOR_NEXT_OPEN' if s['pending'] else 'NO_VERIFIED_PRODUCTION_CYCLE')
    return dict(status=status,reason=reason,
        read_only=True,paper_only=True,exchange_execution=False,schema=SCHEMA,
        live_cycle_verified=qualified,verification_scope='RECORDED_SCHEDULER_OPEN_CLOSE_ON_RENDER_WITH_DURABLE_STATE',
        server_now=now,mode=s['mode'],last_scheduler_tick=s['last_run_at'],last_successful_tick=s['last_success_at'],
        scheduler_recent=s['last_run_at'] is not None and 0<=now-s['last_run_at']<=360,
        last_processed_closed_at=s['watermark'],last_signal=summary.get('last_signal'),
        entry_rejection=summary.get('last_rejection'),last_decision=s['last_decision'],last_error=error,
        position=position,position_mark_fresh=fresh,pending_signal_at=(s['pending'] or {}).get('signal_at'),
        last_open=summary.get('last_open'),last_close=summary.get('last_close'),verified_cycle=cycle if qualified else None,
        balance=s['balance'],equity=s['equity'] if fresh else None,realized_pnl=s['realized_pnl'],fees=s['fees'],
        storage=dict(backend=backend,durable=durable,state_read_verified=True,revision=envelope['revision'],
            last_saved_at=envelope.get('last_saved_at'),last_recorded_run_id=summary.get('last_scheduler_run_id'),
            last_write_error_in_this_process=storage_error),
        events=rows,events_window_limit=200,history_is_partial=True,
        restart_live='NOT_OBSERVED',browser_closed_live='NOT_OBSERVED',
        limitations=['Closed-candle marks, not streaming unrealized PnL.',
            'Legacy events are not backfilled; isolated tests can never establish live verification.',
            'An OPEN/CLOSE cycle does not prove future uptime or profitability.'])
