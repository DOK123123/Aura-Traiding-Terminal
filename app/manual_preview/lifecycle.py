"""Pure Aura 5 scenario reducer. Persistence/transport must commit its result atomically.

No market fetching, account access or execution. Scores are never probabilities.
Terminal episodes cannot be resurrected by score oscillation or quote recovery.
"""
from copy import deepcopy
import hashlib
import json
import math

TERMINAL = frozenset({'INVALIDATED', 'EXPIRED', 'UNKNOWN'})


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def scenario_id(candidate: dict) -> str:
    """Closed structural anchor, not quote time, price, score or tick sequence."""
    anchor = candidate.get('structure')
    if not isinstance(anchor, dict) or not anchor or len(json.dumps(anchor)) > 4096:
        raise ValueError('STRUCTURE_REQUIRED')
    if (candidate.get('direction') not in ('LONG', 'SHORT')
            or candidate.get('frame') not in ('5m', '15m', '1h', '4h')
            or candidate.get('strategy') not in ('TREND_PULLBACK', 'BREAKOUT_RETEST', 'MOMENTUM_DIVERGENCE')):
        raise ValueError('INVALID_IDENTITY')
    raw = json.dumps(['AURA5_SIGNAL_V1', candidate['strategy'], candidate['direction'],
                      candidate['frame'], anchor], sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def valid_plan(c: dict) -> bool:
    if not all(number(c.get(k)) and c[k] > 0 for k in ('entry', 'sl', 'tp', 'net_rr')):
        return False
    return c['net_rr'] >= 1.5 and (c['sl'] < c['entry'] < c['tp'] if c['direction'] == 'LONG'
                                 else c['tp'] < c['entry'] < c['sl'])


def reduce_signal(previous: dict | None, candidate: dict, now: float, *, trusted: bool,
                  invalidated: bool = False,
                  invalidation_reason: str = 'MANDATORY_CONDITION_LOST') -> tuple[dict | None, dict | None]:
    """Return immutable record and at most one idempotent transition event.

    Admission >=70; retention >=65 is score hysteresis only. Mandatory checks,
    freshness, expiry and structural invalidation never receive hysteresis.
    UNKNOWN retires this episode; recovery requires a new structural identity.
    """
    if not number(now) or now < 0:
        raise ValueError('INVALID_CLOCK')
    identity = scenario_id(candidate)
    if previous and previous['id'] != identity:
        raise ValueError('IDENTITY_MISMATCH')
    score = candidate.get('score')
    valid_score = number(score) and 0 <= score <= 100
    checks = candidate.get('checks')
    mandatory = (isinstance(checks, list) and bool(checks)
                 and all(isinstance(x, dict) and x.get('passed') is True for x in checks)
                 and candidate.get('rejection') == [])
    deadline = candidate.get('valid_until')
    admissible = trusted and valid_score and number(deadline) and deadline > now
    if previous is None and (not admissible or score < 70):
        return None, None
    row = deepcopy(previous) if previous else {
        'id': identity, 'strategy': candidate['strategy'], 'direction': candidate['direction'],
        'frame': candidate['frame'], 'structure': deepcopy(candidate['structure']),
        'detected_at': now, 'initial_score': score, 'initial': deepcopy(candidate),
        'valid_until': deadline, 'revision': 0, 'notified': [], 'history': [],
        'edge': 'NO_EDGE_FOUND', 'exchange_execution': False,
    }
    old = row.get('status')
    if old in TERMINAL:
        return row, None
    if not trusted or not valid_score:
        state, reason = 'UNKNOWN', 'UNTRUSTED_OR_STALE_DATA'
    elif now >= row['valid_until']:
        state, reason = 'EXPIRED', 'DEADLINE_REACHED'
    elif invalidated or score < 65 or old == 'WATCH' and not (mandatory and valid_plan(candidate)):
        state = 'INVALIDATED'
        reason = (invalidation_reason if invalidated and invalidation_reason in
                  {'STRUCTURE_REPLACED', 'LOCKED_PLAN_LEVEL_REACHED'} else 'MANDATORY_CONDITION_LOST')
    elif mandatory and valid_plan(candidate):
        state, reason = 'WATCH', 'ALL_MANDATORY_CONDITIONS_MET'
    else:
        state, reason = 'CANDIDATE', 'MISSING_MANDATORY_CONDITIONS'
    # Initial evidence is immutable history; never explain a current score with
    # the conditions from the first observation of this structural episode.
    if trusted:
        row['score'] = score
        row['current_checks'] = deepcopy(checks) if isinstance(checks, list) else []
        row['score_details'] = deepcopy(candidate.get('score_details'))
        row['market_regime'] = deepcopy(candidate.get('market_regime'))
        row['last_evaluated_at'] = now
    if state == 'WATCH':
        row['last_confirmed_at'] = now
    if trusted:
        row['missing'] = list(dict.fromkeys([x.get('code') for x in checks or [] if isinstance(x, dict) and x.get('passed') is not True] + candidate.get('rejection', [])))
    row['current_plan'] = ({k: candidate[k] for k in ('entry', 'sl', 'tp', 'net_rr')}
                           if state == 'WATCH' else None)
    row['plan_absence_reasons'] = ([] if state == 'WATCH' else
        list(dict.fromkeys([reason, *row['missing'],
                           *([] if valid_plan(candidate) else ['NO_VALID_RISK_PLAN'])])))
    if state == 'WATCH' and old != 'WATCH':
        row['watch_plan'] = deepcopy(row['current_plan'])
    elif state == 'WATCH':
        # The locked plan never drifts with ticks. Structural validation is caller-owned.
        row['current_plan'] = deepcopy(row['watch_plan'])
    if state == old:
        return row, None
    row['revision'] += 1
    row['status'], row['changed_at'] = state, now
    event = {'id': f'{identity}:{row["revision"]}', 'scenario_id': identity,
             'from': old, 'to': state, 'at': now, 'reason': reason,
             'score': score, 'plan': deepcopy(row['current_plan'])}
    row['history'].append(event)
    return row, event
