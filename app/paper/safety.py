"""Pure virtual-only activation audit; no exchange or signal-strategy dependency."""
from decimal import Decimal, localcontext
from . import models
from .models import Settings, PaperError, decimal

D = Decimal


def validate_protection(direction: str, entry: Decimal, stop: Decimal, target: Decimal) -> None:
    """Match existing directional protection requirements, without changing fills."""
    if direction not in ('LONG','SHORT'):
        raise PaperError('INVALID_STOPS')
    if any(not isinstance(v, Decimal) or not v.is_finite() or not 0 < v <= D('1000000000000') for v in (entry,stop,target)):
        raise PaperError('INVALID_STOPS')
    sign = 1 if direction == 'LONG' else -1
    if sign*(entry-stop) <= 0 or sign*(target-entry) <= 0:
        raise PaperError('INVALID_STOPS')


def preflight(settings: Settings, policy: str, *, entry: Decimal = D('1'), opened: tuple | list = ()) -> dict:
    """Read-only audit. Caller enforces it inside the same settings transaction."""
    errors = []
    try:
        settings.validate()
    except PaperError:
        errors.append('INVALID_SETTINGS')
    if not errors:
        if settings.risk_per_trade_pct > 1:
            errors.append('AUTO_PREFLIGHT_RISK')
        if settings.maximum_simultaneous_positions != 1 or len(opened) > 1:
            errors.append('AUTO_PREFLIGHT_POSITIONS')
        try:
            with localcontext() as ctx:
                ctx.prec = 64
                if not isinstance(entry,Decimal) or not entry.is_finite() or not 0 < entry <= D('1000000000000'):
                    raise PaperError('INVALID_STOPS')
                for direction, sign in (('LONG',1),('SHORT',-1)):
                    validate_protection(direction,entry,entry*(1-sign*settings.stop_loss_pct/100),
                                        entry*(1+sign*settings.take_profit_pct/100))
            for trade in opened:
                validate_protection(trade['direction'],decimal(trade['entry_price'],positive=True),
                                    decimal(trade['stop_loss'],positive=True),decimal(trade['take_profit'],positive=True))
        except (PaperError,KeyError,TypeError):
            errors.append('AUTO_PREFLIGHT_STOPS')
    if policy not in ('SKIP','PAPER_SETTINGS'):
        errors.append('AUTO_PREFLIGHT_POLICY')
    if models.REAL_MONEY_EXECUTION is not False:
        errors.append('AUTO_PREFLIGHT_VIRTUAL')
    return dict(passed=not errors, errors=errors, protective_policy=policy,
                policy_note='Signals without complete strategy SL/TP are skipped.' if policy=='SKIP' else
                'Explicit paper-only percentage fallback; actual entry SL/TP are revalidated.',
                virtual_only=models.REAL_MONEY_EXECUTION is False,exchange_order_placement=False,
                scope='Configuration audit only; fresh market/source and every entry are checked separately.')


def require_preflight(settings: Settings, policy: str, *, entry: Decimal = D('1'), opened: tuple | list = ()) -> dict:
    result = preflight(settings,policy,entry=entry,opened=opened)
    if not result['passed']:
        raise PaperError(result['errors'][0])
    return result
