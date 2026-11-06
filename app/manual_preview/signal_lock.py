"""Pure, versioned signal lifecycle. No account or execution authority.

Only server-produced explainable evidence is accepted; scores alone never
qualify WATCH. Persistence and transport are injected, never local fallbacks.
"""
import copy
import hashlib
import math

from .explainable import VERSION, NAMES, MODEL_HASH
from app.hunter.costs import risk_reward
from app.hunter.market import SOURCE, STEPS, fresh_quote

ACTIVE = {'CANDIDATE', 'WATCH'}
TERMINAL = {'EXPIRED', 'INVALIDATED'}
PLAN_KEYS = ('entry', 'sl', 'tp', 'net_rr')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def identity(c):
    """Independent of quote, score, detection time and process lifetime."""
    parts = [VERSION, c['model_sha256'], c['strategy'], c['direction'], c['frame'], c['closed_at']]
    return hashlib.sha256(repr(parts).encode()).hexdigest()


def trusted(c, quote, now):
    try:
        step = STEPS[c['frame']]
        return (c['version'] == VERSION and c['source'] == SOURCE
                and c['strategy'] in NAMES and c['direction'] in ('LONG', 'SHORT')
                and c['model_sha256'] == MODEL_HASH
                and c['state'] in ('REJECTED', 'WATCH')
                and c['manual_only'] is True and c['exchange_execution'] is False
                and c['statistical_status'] == 'UNVALIDATED' and c['probability_tp_before_sl'] is None
                and type(c['score']) is int and 0 <= c['score'] <= 100
                and fresh_quote(quote, now)
                and c['quote_time'] == quote['time'] and c['quote_received_at'] == quote['received_at']
                and type(c['closed_at']) is int and c['closed_at'] == int(now // step) * step
                and c['valid_until'] == c['closed_at'] + step
                and isinstance(c['checks'], list) and 0 < len(c['checks']) <= 32
                and all(isinstance(x, dict) and type(x.get('passed')) is bool
                        and isinstance(x.get('code'), str) for x in c['checks'])
                and c['score'] == round(100 * sum(x['passed'] for x in c['checks']) / len(c['checks']))
                and isinstance(c['rejection'], list) and all(isinstance(x, str) for x in c['rejection']))
    except (KeyError, TypeError):
        return False


def watch(c, quote):
    try:
        sign = 1 if c['direction'] == 'LONG' else -1
        step = STEPS[c['frame']]
        hold = max(1, min(12, 14400 // step))
        costs = risk_reward(c['entry'], c['sl'], c['tp'], c['direction'], step, hold,
                            quote['ask'] - quote['bid'])
        return (c['state'] == 'WATCH' and all(x['passed'] for x in c['checks'])
                and not c['rejection'] and all(finite(c[k]) for k in PLAN_KEYS)
                and min(c['entry'], c['sl'], c['tp']) > 0 and c['net_rr'] >= 1.5
                and finite(c['costs']['net_loss']) and c['costs']['net_loss'] > 0
                and costs is not None and costs['net_rr'] >= 1.5
                and math.isclose(c['net_rr'], costs['net_rr'], rel_tol=1e-10)
                and math.isclose(c['costs']['net_loss'], costs['net_loss'], rel_tol=1e-10)
                and sign * (c['entry'] - c['sl']) > 0 and sign * (c['tp'] - c['entry']) > 0
                and c['entry'] == quote['ask' if sign == 1 else 'bid'])
    except (KeyError, TypeError):
        return False


def project(event, now):
    """Cached/durable WATCH must not become actionable after restart or sleep."""
    row = copy.deepcopy(event)
    if row['status'] not in TERMINAL:
        if now >= row['valid_until']:
            row['status'] = 'EXPIRED'
        elif not finite(now) or not 0 <= now - row['last_seen'] <= 5:
            row['status'] = 'UNKNOWN'
    row['plan'] = row['live_plan'] if row['status'] == 'WATCH' else None
    row.pop('live_plan', None)
    row['execution_enabled'] = False
    return row


def advance(state, candidates, quotes, now, running=True, cooldown=300):
    if not finite(now) or now < 0:
        raise ValueError('INVALID_CLOCK')
    result = copy.deepcopy(state or {'events': {}, 'notices': {}, 'cooldowns': {}})
    seen = set()
    for c in candidates:
        quote = quotes.get(c.get('frame')) if isinstance(c, dict) else None
        if not running or not trusted(c, quote, now):
            continue
        key = identity(c)
        qualified = watch(c, quote)
        eligible = qualified or c['score'] >= 70
        event = result['events'].get(key)
        if event is not None and now < event.get('last_seen', now):
            continue  # A delayed sample must not roll back freshness/history.
        if event is None:
            if not eligible:
                continue
            if len(result['events']) >= 2000:
                raise ValueError('SIGNAL_HISTORY_CAPACITY')  # Never silently forget dedup IDs.
            event = {'id': key, 'direction': c['direction'], 'frame': c['frame'],
                     'strategy': c['strategy'], 'detected_at': now, 'valid_until': c['valid_until'],
                     'initial_score': c['score'], 'status': 'CANDIDATE', 'archive_plan': None}
            result['events'][key] = event
        seen.add(key)
        if event['status'] in TERMINAL:
            continue
        # Hysteresis: score fluctuations cannot create/re-arm an event. A WATCH
        # that loses mandatory conditions becomes terminal INVALIDATED.
        previous = event['status']
        status = 'WATCH' if qualified else 'INVALIDATED' if previous == 'WATCH' or event['archive_plan'] else 'CANDIDATE'
        archived = event['archive_plan']
        if archived:
            exit_quote = quote['bid' if c['direction'] == 'LONG' else 'ask']
            crossed = (exit_quote <= archived['sl'] or exit_quote >= archived['tp']) if c['direction'] == 'LONG' else (exit_quote >= archived['sl'] or exit_quote <= archived['tp'])
            if crossed:
                status = 'INVALIDATED'
        if status == 'CANDIDATE' and c['score'] < 65:
            status = 'INVALIDATED'
        plan = {**{k: c[k] for k in PLAN_KEYS}, 'risk_usdt_per_btc': c['costs']['net_loss']} if qualified and status == 'WATCH' else None
        event.update(status=status, score=c['score'], last_seen=now, live_plan=plan,
                     reasons=list(c['rejection']),
                     missing=[x['code'] for x in c['checks'] if not x['passed']])
        if plan and event['archive_plan'] is None:
            event['archive_plan'] = copy.deepcopy(plan)
        if status in ACTIVE:
            notice_id = key + ':' + status
            stream = ':'.join((c['frame'], c['strategy'], c['direction'], status))
            if notice_id not in result['notices'] and now - result['cooldowns'].get(stream, -1e20) >= cooldown:
                result['notices'][notice_id] = {'id': notice_id, 'event_id': key, 'status': status,
                                              'score': c['score'], 'at': now}
                result['cooldowns'][stream] = now
    for key, event in result['events'].items():
        if event['status'] not in TERMINAL:
            if now >= event['valid_until']:
                event.update(status='EXPIRED', live_plan=None)
            elif key not in seen:
                event.update(status='UNKNOWN', live_plan=None)
    return result


class Service:
    """Store CAS persists lifecycle and dedup notices in one transaction."""
    def __init__(self, store):
        if store is None:
            raise ValueError('DURABLE_STORE_REQUIRED')
        self.store = store

    def step(self, candidates, quotes, now, running=True):
        for _ in range(3):
            version, state = self.store.load()
            updated = advance(state, candidates, quotes, now, running)
            if self.store.compare_and_swap(version, updated):
                return [project(row, now) for row in updated['events'].values()]
        raise ValueError('SIGNAL_LOCK_WRITE_CONFLICT')
