"""History integrity and protective exits are separate, virtual-only transitions.

Never replace an unverified history anchor. Protection advances its own cursor;
resuming entries requires the original anchor and a complete fresh snapshot.
"""
from copy import deepcopy
from .core import SOURCE, event, protect, validate
from .strategies import STEPS
from app.automated.engine import DemoError, mark, risk_reason
from app.lab.models import digest, LabError

HISTORY_CODES = {'HISTORY_CANDLE_MISSING', 'HISTORY_CANDLE_CHANGED', 'HISTORY_INCOMPLETE'}
LEGACY_HISTORY = 'SOURCE_CORRECTION_OR_HISTORY_MISSING'


def history_issue(state: dict, bars: list, now: int) -> dict | None:
    step = STEPS[state['config']['timeframe']]
    watermark = state['watermark']
    prior = next((b for b in bars if b.time + step == watermark), None)
    code = None
    if watermark is not None:
        if prior is None:
            code = 'HISTORY_CANDLE_MISSING'
        elif digest(prior.data()) != state['last_bar_hash']:
            code = 'HISTORY_CANDLE_CHANGED'
    if code is None and any(b.time - a.time != step for a, b in zip(bars, bars[1:])):
        code = 'HISTORY_INCOMPLETE'
    if code is None:
        return None
    missing = next((a.time + step for a, b in zip(bars, bars[1:]) if b.time - a.time != step), None)
    return dict(code=code, candle_timestamp=(missing if code=='HISTORY_INCOMPLETE' else watermark-step),
                anchor_timestamp=None if watermark is None else watermark-step,
                gap_timestamp=missing, source=SOURCE,
                old_ohlcv_hash=None if code=='HISTORY_INCOMPLETE' else state['last_bar_hash'],
                new_ohlcv_hash=digest(prior.data()) if prior and code!='HISTORY_INCOMPLETE' else None, detected_at=now)


def paper_status(state: dict) -> str:
    if state['mode'] == 'OFF':
        return 'PAPER_OFF'
    if state['mode'] == 'ON':
        return 'PAPER_ON'
    if state['mode'] == 'PAUSED':
        if state.get('protection_status')=='EMERGENCY_UNTRUSTED_DATA' or state.get('last_error')=='HISTORY_SOURCE_UNAVAILABLE':
            return 'PAPER_PAUSED_DATA'
        return 'PAPER_PAUSED_HISTORY' if state.get('history_guard') or state.get('last_error') in HISTORY_CODES | {LEGACY_HISTORY} else 'PAPER_PAUSED_DATA'
    return 'SCHEDULER_ERROR'


def transition(old: dict, state: dict, now: int, run_id: str, reason: str | None = None) -> list:
    previous, current = paper_status(old), paper_status(state)
    # Include mode changes such as PAUSED -> EMERGENCY even if display class agrees.
    if previous == current and old['mode'] == state['mode']:
        return []
    cause=reason or ('FRESH_DATA_RECOVERED' if old['mode']=='PAUSED' and state['mode']=='ON' else state['last_error'] or state['last_decision'])
    body = dict(previous=previous, status=current, previous_mode=old['mode'], mode=state['mode'],
                reason=cause, detected_at=now, scheduler_run_id=run_id)
    state['last_status_transition'] = body
    return [event(state, 'STATE_TRANSITION', run_id.rsplit(':', 1)[-1], now, body)]


def protective_advance(old: dict, bars: list, now: int) -> tuple[dict, list]:
    """No entries, queued strategy exits or indicator/trailing changes.

    A missing catch-up interval is disclosed, never filled with invented bars.
    Only actually received closed candles after entry/cursor can trigger exits.
    """
    state = deepcopy(old)
    validate(state)
    step = STEPS[state['config']['timeframe']]
    if not bars or len(bars) > 1300:
        raise DemoError('INVALID_MARKET_DATA')
    try:
        for bar in bars:
            bar.validate(step, now)
    except (LabError, AttributeError):
        raise DemoError('INVALID_MARKET_DATA') from None
    if any(b.time - a.time != step for a, b in zip(bars, bars[1:])):
        raise DemoError('HISTORY_INCOMPLETE')
    if bars[-1].time + step != now // step * step:
        raise DemoError('STALE_DATA')
    events = []
    cursor = max(state.get('protection_watermark') or 0, state['watermark'] or 0)
    position = state['position']
    if position:
        cursor = max(cursor, position['entry_time'])
    fresh = [b for b in bars if b.time >= cursor]
    if fresh and fresh[0].time > cursor:
        state['protection_gap'] = dict(from_timestamp=cursor, to_timestamp=fresh[0].time,
                                       detected_at=now, reason='UNOBSERVED_PROTECTION_INTERVAL')
    state['pending'] = None
    state['pending_exit'] = None
    for bar in fresh:
        ev = protect(state, bar, step)
        if ev:
            events.append(ev)
        mark(state, bar, bar.time + step)
    state['protection_watermark'] = max(cursor, bars[-1].time + step)
    state['protection_bar_hash'] = digest(bars[-1].data())
    state['last_price'] = str(bars[-1].close)
    state['last_success_at'] = now
    state['last_fresh_closed_at'] = bars[-1].time + step
    state['protection_status'] = 'FRESH_PROTECTION_GAP' if state.get('protection_gap') else 'FRESH_PROTECTION'
    if state['position'] and fresh:
        events.append(event(state, 'POSITION_UPDATE', bars[-1].time + step, now,
                            dict(position=deepcopy(state['position']), equity=state['equity'], protective_only=True)))
    if risk_reason(state):
        state['data_recovery_armed'] = False
    return state, events
