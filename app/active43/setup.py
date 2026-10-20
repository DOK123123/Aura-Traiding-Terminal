"""Explicit account preparation; existing SQL load is insert-only on conflict."""
from app.automated.engine import DemoError
from .core import validate,SCOPE,SOURCE
from .strategies import VERSION


def checked(service,env):
    validate(env['state'])
    if env['state']['config']!=service.config:raise DemoError('CONFIG_CHANGED')
    return env


async def initialize(service):
    service.ready()
    existing=await service.store.peek()
    attempted=existing is None
    if attempted:
        probe=await service.diagnostics.run()
        if probe['bitget']['status']!='CONNECTED':raise DemoError('INITIALIZATION_MARKET_UNVERIFIED')
        if probe['supabase']['status']!='CONNECTED':raise DemoError('INITIALIZATION_STORAGE_UNVERIFIED')
        # SQL validates the 10000/OFF/null-position seed, INSERT ... ON CONFLICT
        # DO NOTHING, then reads the winner. No reset, update or execution.
        saved=await service.load()
    else:saved=checked(service,existing)
    readback=await service.store.peek()
    if readback is None:raise DemoError('INITIALIZATION_READBACK_FAILED')
    checked(service,readback)
    if readback['state']['epoch']!=saved['state']['epoch'] or readback['revision']<saved['revision']:
        raise DemoError('INITIALIZATION_READBACK_FAILED')
    service.restored=True
    service.diagnostics.cached=None
    s=readback['state']
    # Do not claim which concurrent call won the insert: the existing RPC
    # does not return an inserted flag. Existing balances/modes are preserved.
    return dict(operation='INITIALIZE_PAPER_ACCOUNT',status='ACCOUNT_AVAILABLE',
        scope=SCOPE,market_source=SOURCE,strategy_version=VERSION,paper_only=True,exchange_execution=False,
        account_available=True,state_saved=True,readback_verified=True,
        initialization_attempted=attempted,existing_account_preserved=True,
        mode=s['mode'],position_present=s['position'] is not None,
        balance=s['balance'],initial_balance_matches=s['balance']=='10000',
        mode_changed_by_operation=False,trade_execution_performed=False,
        production_paper_verified=False)
