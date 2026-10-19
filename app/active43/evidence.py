"""Compact evidence from committed events only. Never runs/recomputes signals."""
from copy import deepcopy
import os,re


def verified(s):
    proof=s.get('production_cycle') or {}
    if not isinstance(proof,dict) or s.get('monitor_error'):return False
    opened=proof.get('open') or {};closed=proof.get('close') or {}
    if not isinstance(opened,dict) or not isinstance(closed,dict):return False
    signal=opened.get('signal') or {}
    if not isinstance(signal,dict):return False
    origins=[v.get('origin') or {} for v in (signal,opened,closed)]
    if any(not isinstance(o,dict) or o.get('render_native') is not True or not isinstance(o.get('render_commit'),str)
           or not re.fullmatch('[a-f0-9]{40}',o['render_commit']) for o in origins):return False
    times=[v.get('recorded_at') for v in (signal,opened,closed)]
    at=opened.get('signal_at');sha=signal.get('source_sha256')
    if any(type(t) is not int or t<0 for t in times) or times!=sorted(times):return False
    if type(at) is not int or signal.get('signal_at')!=at or not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):return False
    position=s['epoch']+':position:'+str(at)
    reason=closed.get('exit_reason','')
    return (proof.get('scope')=='AURA43_ACTIVE_PAPER' and proof.get('natural_render_cycle') is True
            and opened.get('updated') is True and proof.get('position_id')==position and opened.get('position_id')==position
            and isinstance(reason,str) and (reason.startswith(('STOP','TAKE_PROFIT')) or reason=='STRATEGY_EXIT_NEXT_OPEN'))


def observe(state,events,now,*,market_native,durable,backend):
    s=deepcopy(state);commit=os.getenv('RENDER_GIT_COMMIT','')
    native=(market_native and durable and backend=='SUPABASE_ACTIVE43' and os.getenv('RENDER','').lower() in ('1','true')
            and bool(re.fullmatch('[a-f0-9]{40}',commit)))
    provenance=dict(render_native=native,render_commit=commit if re.fullmatch('[a-f0-9]{40}',commit) else None)
    for ev in events:
        p=ev['payload'];kind=ev['kind']
        if kind=='SIGNAL' and p.get('direction') in ('LONG','SHORT'):
            s['signal_evidence']=dict(signal_at=p['signal_at'],source_sha256=p.get('source_sha256'),origin=provenance,recorded_at=now)
        elif kind=='OPEN':
            signal=s.get('signal_evidence')
            if not isinstance(signal,dict):signal=None
            s['open_evidence']=dict(position_id=p['id'],signal_at=p['signal_at'],origin=provenance,recorded_at=now,updated=False,
                signal=deepcopy(signal) if signal and signal['signal_at']==p['signal_at'] else None)
        elif kind=='POSITION_UPDATE':
            chain=s.get('open_evidence')
            if isinstance(chain,dict) and p['position']['id']==chain.get('position_id'):chain['updated']=True
        elif kind=='CLOSE':
            chain=s.get('open_evidence') or {}
            if not isinstance(chain,dict):chain={}
            signal=chain.get('signal') or {}
            if not isinstance(signal,dict):signal={}
            sha=signal.get('source_sha256') or ''
            if not isinstance(sha,str):sha=''
            if (native and chain.get('position_id')==p['id'] and chain.get('updated') and chain.get('origin',{}).get('render_native')
                and signal.get('origin',{}).get('render_native') and re.fullmatch('[a-f0-9]{64}',sha)):
                s['production_cycle']=dict(scope='AURA43_ACTIVE_PAPER',natural_render_cycle=True,position_id=p['id'],
                    open=deepcopy(chain),close=dict(recorded_at=now,exit_time=p['exit_time'],exit_reason=p['exit_reason'],realized_pnl=p['realized_pnl'],origin=provenance))
    return s
