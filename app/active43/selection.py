"""Explicit owner selection; immutable receipt authorizes restart/multi-instance adoption."""
from copy import deepcopy
from app.automated.engine import DemoError
from app.lab.models import digest
from .core import validate,event
from .strategies import config

CHOICES={'DONCHIAN_15M':config(), 'BOUNCE_5M':config('SR_BOUNCE','5m')}
CLEAR=('watermark','last_bar_hash','last_mark_at','last_success_at','last_price','last_signal','last_check',
       'production_cycle','signal_evidence','open_evidence','monitor_error')


async def adopt(service,env):
    state=env['state'];validate(state)
    if state['config']!=service.config:
        key=state.get('strategy_change_id')
        if not isinstance(key,str) or not key.startswith('active43:bitget:strategy:'):raise DemoError('CONFIG_CHANGED')
        receipt=await service.store.lookup(key)
        if (not receipt or receipt['kind']!='STRATEGY_CHANGE' or receipt['epoch']!=state['epoch']
            or receipt['payload'].get('config')!=state['config'] or state['config'] not in CHOICES.values()):raise DemoError('CONFIG_CHANGED')
        service.config=deepcopy(state['config'])
        service.store.config=deepcopy(service.config)
        if service.market is not None:service.market.cache=None
    return env


async def select(service,choice,request_id,revision):
    service.ready();target=CHOICES[choice];key='active43:bitget:strategy:'+request_id
    async with service.lock:
        env=await service.store.peek()
        if env is None:raise DemoError('SCHEDULER_ACCOUNT_NOT_INITIALIZED')
        await adopt(service,env)
        state=env['state'];service.require_empty_off(state)
        receipt=await service.store.lookup(key)
        if receipt:
            if receipt['payload'].get('config')!=target or state['config']!=target:raise DemoError('IDEMPOTENCY_CONFLICT')
            return dict(state_saved=True,duplicate=True,paper_only=True,exchange_execution=False)
        if revision!=env['revision']:raise DemoError('CONCURRENT_UPDATE')
        if state['config']==target:return dict(state_saved=True,duplicate=True,paper_only=True,exchange_execution=False)
        if state['config'] not in CHOICES.values():raise DemoError('CONFIG_CHANGED')
        changed=deepcopy(state)
        changed.update(config=deepcopy(target),config_hash=digest(target),strategy_change_id=key,
                       last_error=None,last_decision='STRATEGY_CHANGED',recovery_status='STRATEGY_CHANGED_OFF')
        for field in CLEAR:changed[field]=None
        ev=event(changed,'STRATEGY_CHANGE',request_id,int(service.clock()),dict(config=deepcopy(target)))
        ev['id']=key
        saved=await service.store.select_strategy(env['revision'],changed,ev,key)
        # A missing receipt is an uncertain outcome, never an acknowledged selection.
        receipt=await service.store.lookup(key)
        if not receipt or receipt['payload'].get('config')!=target:raise DemoError('STORAGE_READBACK_OUTCOME_UNKNOWN')
        await adopt(service,saved)
        service.diagnostics.cached=None
        return dict(state_saved=True,duplicate=saved.get('duplicate',False),paper_only=True,exchange_execution=False)
