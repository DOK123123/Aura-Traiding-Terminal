"""Owner-only OFF readiness snapshot. peek only; no seed, tick or state mutation."""
import asyncio
import os

from app.automated.engine import DemoError, risk_reason
from .core import SCOPE, SOURCE, validate
from .strategies import VERSION
from .storage import Store

SAFE_ERRORS = {
    'ACTIVE43_NOT_CONFIGURED', 'ACTIVE43_DISABLED', 'ACTIVE43_BITGET_DISABLED',
    'ACTIVE43_STORAGE_NOT_CONFIGURED', 'SERVICE_CLOSED', 'SCHEDULER_NOT_CONFIGURED',
    'STORAGE_URL_MISSING', 'STORAGE_URL_INVALID', 'STORAGE_KEY_MISSING', 'STORAGE_KEY_INVALID',
    'STORAGE_AUTH', 'STORAGE_PERMISSION_DENIED', 'STORAGE_SCHEMA_MISSING',
    'STORAGE_READ_TIMEOUT', 'STORAGE_INVALID_RESPONSE', 'STORAGE_RESPONSE_LIMIT',
    'CORRUPT_PORTFOLIO', 'ACTIVE_SCOPE_OR_CONFIG_MISMATCH', 'CONFIG_CHANGED',
    'STORAGE_DATABASE_UNAVAILABLE', 'STORAGE_RATE_LIMIT', 'STORAGE_HTTP_ERROR',
    'STORAGE_REDIRECT_BLOCKED', 'MODEL_CHANGED_RESET_REQUIRED', 'ACCOUNTING_ERROR',
    'OFF_READINESS_INCOMPLETE_STATE', 'SCHEDULER_ACCOUNT_NOT_INITIALIZED',
}


def blocked() -> dict:
    return dict(scope=SCOPE, market_source=SOURCE, strategy_version=VERSION,
        status='BLOCKED', read_only=True, state_changed=False, paper_only=True,
        exchange_execution=False, purpose='OFF_ONLY_ACCOUNT_PRECONDITIONS',
        read_confirmed=False, last_confirmed_read_at=None, mode=None,
        open_positions=None, pending=None, pending_exit=None, pending_operations=None,
        data_recovery_armed=None, risk_guards=dict(status='BLOCKED',code='STATE_UNVERIFIED'),
        scheduler_auth_configured=False, errors=['STATE_UNVERIFIED'])


async def inspect(service) -> dict:
    """Fresh validated DB snapshot; no cache or financial values returned."""
    from .service import scheduler_configured
    result = blocked()
    store = None
    own = False
    try:
        async with asyncio.timeout(14):
            store = service.store
            if store is None:
                # Same read-only fallback as existing diagnostics when module is disabled.
                store = Store(os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_URL',''),
                              os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY',''),service.config)
                own = True
            env = await store.peek()
            if env is None:
                raise DemoError('SCHEDULER_ACCOUNT_NOT_INITIALIZED')
            state = env['state']
            required = {'mode','position','pending','pending_exit','data_recovery_armed'}
            if (not isinstance(state,dict) or not required.issubset(state)
                or state['mode'] not in ('OFF','ON','PAUSED','EMERGENCY')
                or type(state['data_recovery_armed']) is not bool
                or any(state[k] is not None and (type(state[k]) is not dict or not state[k]) for k in ('position','pending'))
                or state['pending_exit'] is not None and (type(state['pending_exit']) is not str or not state['pending_exit'])):
                raise DemoError('OFF_READINESS_INCOMPLETE_STATE')
            validate(state)
            if state['config'] != service.config:
                raise DemoError('CONFIG_CHANGED')
            if type(env.get('revision')) is not int or env['revision'] < 1:
                raise DemoError('STORAGE_INVALID_RESPONSE')
            at = int(service.clock())
            if at <= 0:
                raise DemoError('STORAGE_INVALID_RESPONSE')
            risk = risk_reason(state)  # Exact production guard on saved state; no roll_day/mark.
            result.update(read_confirmed=True,last_confirmed_read_at=at,mode=state['mode'],
                open_positions=int(state['position'] is not None),pending=state['pending'] is not None,
                pending_exit=state['pending_exit'] is not None,
                pending_operations=int(state['pending'] is not None)+int(state['pending_exit'] is not None),
                data_recovery_armed=state['data_recovery_armed'],
                risk_guards=dict(status='BLOCKED' if risk else 'PASS',code=risk),
                scheduler_auth_configured=scheduler_configured(),errors=[])
            if state['mode'] != 'OFF':result['errors'].append('PAPER_NOT_OFF')
            if result['open_positions']:result['errors'].append('OPEN_POSITION_PRESENT')
            if result['pending_operations']:result['errors'].append('PENDING_OPERATION_PRESENT')
            if state['data_recovery_armed']:result['errors'].append('DATA_RECOVERY_ARMED')
            if risk:result['errors'].append(risk)
            if not result['scheduler_auth_configured']:result['errors'].append('SCHEDULER_NOT_CONFIGURED')
            try:service.ready()
            except DemoError as exc:
                result['errors'].append(exc.code if exc.code in SAFE_ERRORS else 'ACTIVE43_NOT_CONFIGURED')
            result['status'] = 'BLOCKED' if result['errors'] else 'PASS'
    except DemoError as exc:
        result = blocked()
        result['errors'] = [exc.code if exc.code in SAFE_ERRORS else 'STORAGE_READ_FAILED']
    except Exception:
        result = blocked()
        result['errors'] = ['STORAGE_READ_FAILED']
    finally:
        if own and store is not None:
            try:
                async with asyncio.timeout(2):await store.close()
            except Exception:
                result = blocked();result['errors'] = ['STORAGE_READ_FAILED']
    return result
