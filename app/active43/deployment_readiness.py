"""Owner-only release gate. No seed, execution, changes or public credentials."""
import asyncio
import os
import re
from app.automated.engine import risk_reason
from app.lab.models import digest
from .core import SCOPE, SOURCE, validate
from .paper_readiness import scheduler_evidence

FINANCIAL = ('epoch','config','balance','equity','realized_pnl','fees','slippage',
             'trades','wins','losses','position','pending','pending_exit','data_recovery_armed','mode')


async def inspect(service) -> dict:
    commit=os.getenv('RENDER_GIT_COMMIT','')
    result=dict(status='BLOCKED',scope=SCOPE,market_source=SOURCE,read_only=True,state_changed=False,
        paper_only=True,exchange_execution=False,render_commit=commit if re.fullmatch('[a-f0-9]{40}',commit) else None,
        checked_at=int(service.clock()),account=None,scheduler=None,errors=[])
    try:
        async with asyncio.timeout(40):
            service.ready();env=await service.store.peek()
            if env is None:raise ValueError('ACCOUNT_UNVERIFIED')
            state=env['state'];validate(state)
            if not re.fullmatch('ACTIVE43_BITGET_[a-f0-9]{32}',state['epoch']):raise ValueError('ACCOUNT_UNVERIFIED')
            trades=[]
            # Hash actual immutable OPEN/CLOSE history, not only dashboard counters.
            counts={}
            for kind in ('OPEN','CLOSE'):
                before=None;count=0
                for _ in range(20):
                    rows=await service.store.history(epoch=state['epoch'],kind=kind,limit=200,before=before)
                    if any(r['kind']!=kind or r['epoch']!=state['epoch'] for r in rows):raise ValueError('HISTORY_UNVERIFIED')
                    seq=[r['seq'] for r in rows]
                    if any(type(x) is not int or x<=0 for x in seq) or seq!=sorted(set(seq),reverse=True):raise ValueError('HISTORY_UNVERIFIED')
                    if before is not None and any(x>=before for x in seq):raise ValueError('HISTORY_UNVERIFIED')
                    trades.extend(rows);count+=len(rows)
                    if len(rows)<200:break
                    before=rows[-1]['seq']
                else:raise ValueError('HISTORY_SCAN_LIMIT')
                counts[kind]=count
                if kind=='CLOSE' and count!=state['trades']:raise ValueError('HISTORY_UNVERIFIED')
            if counts['OPEN']!=counts['CLOSE']+int(state['position'] is not None):raise ValueError('HISTORY_UNVERIFIED')
            recent=await service.store.history(epoch=state['epoch'],limit=100)
            after=await service.store.peek()
            if after is None or after['revision']!=env['revision'] or after['state']!=state:raise ValueError('ACCOUNT_CHANGED_DURING_READ')
            risk=risk_reason(state)
            empty=state['mode']=='OFF' and all(state[k] is None for k in ('position','pending','pending_exit')) and state['data_recovery_armed'] is False
            result['account']=dict(mode=state['mode'],balance=state['balance'],open_positions=int(state['position'] is not None),
                pending_operations=int(state['pending'] is not None)+int(state['pending_exit'] is not None),risk_code=risk,
                ledger_sha256=digest(dict(financial={k:state[k] for k in FINANCIAL},trades=trades)))
            result['scheduler']=scheduler_evidence(recent,state,int(service.clock()))
            if not empty:result['errors'].append('EMPTY_OFF_ACCOUNT_REQUIRED')
            if risk:result['errors'].append('SAVED_RISK_GUARD_BLOCKED')
            if not result['render_commit']:result['errors'].append('RENDER_COMMIT_UNVERIFIED')
            result['status']='PASS' if not result['errors'] else 'BLOCKED'
            result['checked_at']=int(service.clock())
    except Exception:
        result['status']='BLOCKED';result['errors'].append('ACCOUNT_OR_HISTORY_READ_UNVERIFIED')
    return result
