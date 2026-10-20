"""Opt-in Render Cron (--once) or paid worker. Existing Bitget Paper Service.

No initialize, START, signal injection, account reset, private exchange or HTTP
control calls. This process is intentionally separate from app.main/start_web.
"""
import argparse
import asyncio
import json
import math
import os
import signal
import time
from collections.abc import Callable
from datetime import datetime, timezone

from app.automated.engine import DemoError
from app.active43.service import Service, configured
from scripts.active43_scheduler import AUTH_CODES, DIAGNOSTIC_CODES, verified

ENABLED = 'AURA_ACTIVE43_BITGET_RENDER_SCHEDULER_ENABLED'
INTERVAL = 300
OFFSET = 120  # Same UTC phase as the existing 2-59/5 cron.
CODES = AUTH_CODES | DIAGNOSTIC_CODES | {
    'ACTIVE43_NOT_CONFIGURED', 'SERVICE_CLOSED', 'MARKET_UNAVAILABLE', 'STALE_DATA',
    'INVALID_MARKET_DATA', 'MISSING_CANDLES', 'SOURCE_CORRECTION_OR_HISTORY_MISSING',
    'SNAPSHOT_MISMATCH', 'CONFIG_INVALID', 'CONCURRENT_UPDATE', 'PORTFOLIO_CHANGED',
    'STORAGE_READBACK_OUTCOME_UNKNOWN', 'TICK_TIMEOUT_OUTCOME_UNKNOWN',
    'STALE_EXECUTION_AT_COMMIT', 'EMERGENCY_STOP', 'DAILY_LOSS_LIMIT', 'DRAWDOWN_LIMIT',
    'WORKER_INVALID_RESULT', 'WORKER_CLOCK_INVALID',
}


def safe_code(value: object) -> str:
    return value if type(value) is str and value in CODES else 'WORKER_UNCLASSIFIED_ERROR'


def next_delay(now: float) -> float:
    """Skip missed wall-clock slots; never invent or replay scheduler runs."""
    if not math.isfinite(now) or now < 0:
        raise DemoError('WORKER_CLOCK_INVALID')
    due = (math.floor((now - OFFSET) / INTERVAL) + 1) * INTERVAL + OFFSET
    return due - now


def log(event: str, fields: dict, emit: Callable[[str], None] = print) -> None:
    # Callers supply only whitelisted fields; never an exception, env or account.
    emit(json.dumps(dict(component='ACTIVE43_BITGET_RENDER_SCHEDULER', event=event,
                         timestamp=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                         paper_only=True, exchange_execution=False, **fields), sort_keys=True))


async def tick(service: Service, emit: Callable[[str], None] = print) -> bool:
    """Same production tick and SQL transaction; refuse to seed a missing account."""
    try:
        service.ready()
        if await service.store.peek() is None:
            raise DemoError('SCHEDULER_ACCOUNT_NOT_INITIALIZED')
        result = await service.tick()
        if type(result) is not dict or result.get('status') not in ('COMPLETED', 'PAUSED'):
            raise DemoError('WORKER_INVALID_RESULT')
        if not verified(dict(result, status='COMPLETED')):
            raise DemoError('WORKER_INVALID_RESULT')
        fields = {k: result[k] for k in ('mode', 'processed', 'duplicate', 'opened', 'closed', 'state_saved')}
        fields.update(status=result['status'], code=safe_code(result.get('decision')) if result['status']=='PAUSED' else None)
        log('TICK_SAVED', fields, emit)
        return result['status'] == 'COMPLETED'
    except DemoError as exc:
        log('ERROR', dict(code=safe_code(exc.code), outcome_confirmed=False), emit)
    except Exception:
        # Do not disclose upstream response bodies, URLs, credentials or traceback.
        log('ERROR', dict(code='WORKER_UNEXPECTED_ERROR', outcome_confirmed=False), emit)
    return False


async def wait(stop: asyncio.Event, delay: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except TimeoutError:
        pass


async def run(service: Service | None, stop: asyncio.Event, *, enabled: bool = False,
              once: bool = False, clock: Callable[[], float] = time.time,
              waiter: Callable = wait, emit: Callable[[str], None] = print) -> int:
    """Serial ticks, one startup attempt then UTC :02/:07/...; no overlap/catch-up."""
    outcome = True
    try:
        while not stop.is_set():
            if enabled:
                if service is None:
                    log('ERROR', dict(code='ACTIVE43_NOT_CONFIGURED', outcome_confirmed=False), emit)
                    outcome = False
                else:
                    outcome = await tick(service, emit)
            else:
                log('IDLE', dict(code='WORKER_DISABLED', state_changed=False), emit)
            if once or stop.is_set():
                break
            delay = next_delay(clock())
            log('WAITING', dict(next_in_seconds=round(delay, 3), interval_seconds=INTERVAL), emit)
            await waiter(stop, delay)
    finally:
        if service is not None:
            await service.close()
        log('STOPPED', dict(state_changed=False), emit)
    return 0 if outcome else 1


async def main(once: bool = False) -> int:
    # Exact, independent opt-in. A Render worker deployment never changes mode ON/OFF.
    enabled = os.getenv(ENABLED) == 'true'
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    # Disabled by default: do not even construct market/database clients.
    service = configured() if enabled else None
    try:
        return await run(service, stop, enabled=enabled, once=once)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='required for Render Cron: one existing tick if scheduler opt-in is true; never enables Paper')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.once)))
