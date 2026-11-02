"""Three causal manual hypotheses. No execution, account or qualification authority.

Frozen v1: 260 closed native bars, 2+2 pivots, ATR14 Wilder, EMA20/50,
minimum 1.5 ATR stop and .25 ATR structural buffer, nearest opposing pivot TP.
Score is the equal-weight fraction of strategy conditions, never win probability.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from app.hunter.engine import ema, wilder
from app.hunter.market import SOURCE, STEPS, fresh_quote, validate_bars
from app.hunter.costs import risk_reward, entry_fill

VERSION = 'AURA5_EXPLAINABLE_V1'
MODEL_HASH = hashlib.sha256(b''.join(p.read_bytes() for p in (
    Path(__file__), *(Path(__file__).parents[1]/'hunter'/name
                       for name in ('engine.py', 'costs.py', 'market.py', 'rules.json'))))).hexdigest()
NAMES = {'TREND_PULLBACK': 'Trend Pullback', 'BREAKOUT_RETEST': 'Breakout + Retest',
         'MOMENTUM_DIVERGENCE': 'Momentum Divergence'}


def unknown(frame: str, reason: str) -> list[dict]:
    return [dict(version=VERSION, model_sha256=MODEL_HASH, frame=frame,
                 strategy=k, name=v, direction=side, state='UNKNOWN', score=None,
                 entry=None, sl=None, tp=None, net_rr=None, gross_rr=None,
                 costs=None, checks=[], rejection=[reason], edge='NO_EDGE_FOUND',
                 statistical_status='UNVALIDATED', probability_tp_before_sl=None,
                 manual_only=True, exchange_execution=False)
            for side in ('LONG', 'SHORT') for k, v in NAMES.items()]


def indicators(rows: list) -> dict:
    x = np.asarray(rows, dtype=float)
    c, h, l = x[:, 4], x[:, 2], x[:, 3]
    previous = np.r_[c[0], c[:-1]]
    atr = wilder(np.maximum(h-l, np.maximum(abs(h-previous), abs(l-previous))))
    gain, loss = wilder(np.maximum(np.diff(c), 0)), wilder(np.maximum(-np.diff(c), 0))
    rs = np.divide(gain, loss, out=np.full(len(loss), np.inf), where=loss > 0)
    rsi = np.r_[np.nan, np.where((gain == 0) & (loss == 0), 50, 100-100/(1+rs))]
    macd = ema(c, 12)-ema(c, 26)
    signal = np.r_[np.full(25, np.nan), ema(macd[25:], 9)]
    return {'ema20': ema(c, 20), 'ema50': ema(c, 50), 'atr': atr, 'rsi': rsi,
            'macd': macd, 'histogram': macd-signal}


def pivots(rows: list, step: int) -> list[dict]:
    output = []
    for i in range(2, len(rows)-2):
        for kind, column, sign in (('LOW', 3, -1), ('HIGH', 2, 1)):
            if all(sign*(rows[i][column]-rows[j][column]) > 0
                   for j in (i-2, i-1, i+1, i+2)):
                output.append({'kind': kind, 'price': rows[i][column], 'index': i,
                               'time': rows[i][0], 'confirmed_at': rows[i+2][0]+step})
    return output


def evaluate(rows: list, frame: str, quote: dict, now: float) -> list[dict]:
    """Same bounded seed for archive/live; future/forming bars are not accepted."""
    if frame not in STEPS:
        raise ValueError('INVALID_FRAME')
    step = STEPS[frame]
    if type(now) not in (float, int) or not math.isfinite(now):
        return unknown(frame, 'INVALID_CLOCK')
    if not fresh_quote(quote, now):
        return unknown(frame, 'STALE_OR_UNVERIFIED_BITGET_QUOTE')
    try:
        validate_bars(rows, step)
    except (ValueError, TypeError):
        return unknown(frame, 'INVALID_OHLCV_OR_GAP')
    if len(rows) < 260 or rows[-1][0]+step != int(now//step)*step:
        return unknown(frame, 'INCOMPLETE_OR_STALE_CLOSED_HISTORY')
    b = rows[-260:]
    m = indicators(b)
    a = float(m['atr'][-1])
    if not a > 0 or not all(math.isfinite(float(v[-1])) for v in m.values()):
        return unknown(frame, 'INDICATOR_WARMUP_OR_ZERO_ATR')
    z, p = b[-1], b[-2]
    # Before the signal candle: pivots cannot be confirmed by the signal itself.
    swings = pivots(b[:-1], step)
    cutoff = z[0]+step
    output = []
    for side, sign in (('LONG', 1), ('SHORT', -1)):
        long = sign == 1
        own = [v for v in swings if v['kind'] == ('LOW' if long else 'HIGH')]
        opposite = [v for v in swings if v['kind'] == ('HIGH' if long else 'LOW')]
        for strategy, name in NAMES.items():
            checks = []
            def check(code, passed, actual, required):
                checks.append({'code': code, 'passed': bool(passed), 'actual': actual, 'required': required})
            anchor = None
            if strategy == 'TREND_PULLBACK':
                check('EMA_TREND', sign*(m['ema20'][-1]-m['ema50'][-1]) > .1*a,
                      [float(m['ema20'][-1]), float(m['ema50'][-1])], 'EMA20 > EMA50 + .1ATR' if long else 'EMA20 < EMA50 − .1ATR')
                structure = len(own) >= 2 and len(opposite) >= 2 and sign*(own[-1]['price']-own[-2]['price']) > 0 and sign*(opposite[-1]['price']-opposite[-2]['price']) > 0
                check('TREND_STRUCTURE', structure, {'own': own[-2:], 'opposite': opposite[-2:]}, 'HH/HL' if long else 'LH/LL')
                lo, hi = sorted([float(m['ema20'][-2]), float(m['ema50'][-2])])
                check('PULLBACK', p[3] <= hi+.25*a and p[2] >= lo-.25*a, [p[3], p[2]], [lo-.25*a, hi+.25*a])
                check('RSI', 45 <= m['rsi'][-1] <= 70 if long else 30 <= m['rsi'][-1] <= 55,
                      float(m['rsi'][-1]), '45–70' if long else '30–55')
                anchor = min(p[3], z[3]) if long else max(p[2], z[2])
            elif strategy == 'BREAKOUT_RETEST':
                detected = None
                # Each level must be known before its breakout, with a separate retest.
                for j in range(len(b)-6, len(b)-1):
                    levels = [v for v in swings if v['kind'] == ('HIGH' if long else 'LOW') and v['confirmed_at'] <= b[j][0]]
                    if not levels:
                        continue
                    level = levels[-1]
                    av = float(m['atr'][j-1])
                    volume = sum(v[5] for v in b[j-20:j])/20
                    broken = sign*(b[j][4]-level['price']) > .1*av and sign*(b[j-1][4]-level['price']) <= 0
                    held = all(sign*(v[4]-level['price']) >= -.25*av for v in b[j+1:-1])
                    retest = -.5*a <= sign*((z[3] if long else z[2])-level['price']) <= .25*a and sign*(z[4]-level['price']) > .1*a
                    item = {'level': level, 'breakout_at': b[j][0]+step, 'relative_volume': b[j][5]/volume if volume > 0 else 0,
                            'broken': broken, 'held': held, 'retest': retest}
                    if detected is None or sum(bool(item[k]) for k in ('broken', 'held', 'retest')) > sum(bool(detected[k]) for k in ('broken', 'held', 'retest')):
                        detected = item
                    if broken and held and retest and item['relative_volume'] >= 1.2:
                        detected = item
                        break
                for key, label in [('broken', 'PRIOR_LEVEL_BREAK'), ('held', 'LEVEL_HELD'), ('retest', 'SEPARATE_RETEST')]:
                    check(label, detected and detected[key], detected, 'Заранее известный pivot; пробой > .1ATR; отдельный возврат без потери уровня')
                check('BREAK_VOLUME', detected and detected['relative_volume'] >= 1.2, detected['relative_volume'] if detected else None, 'Объём пробоя / предыдущие 20 ≥ 1.2')
                if detected:
                    anchor = min(z[3], detected['level']['price']) if long else max(z[2], detected['level']['price'])
            else:
                pair = own[-2:]
                recent = len(pair) == 2 and pair[-1]['index']-pair[0]['index'] <= 50 and len(b)-1-pair[-1]['index'] <= 10 and pair[0]['index'] >= 34
                check('CONFIRMED_PIVOTS', recent, pair, 'Два pivot 2+2, интервал ≤50 свечей, последний ≤10 свечей назад')
                price_div = rsi_div = macd_div = False
                evidence = None
                if recent:
                    first, last = pair
                    u, v = first['index'], last['index']
                    price_div = sign*(last['price']-first['price']) < 0
                    rsi_div = sign*(m['rsi'][v]-m['rsi'][u]) > 0
                    macd_div = sign*(m['macd'][v]-m['macd'][u]) > 0
                    evidence = {'first': first, 'last': last, 'rsi': [float(m['rsi'][u]), float(m['rsi'][v])],
                                'macd': [float(m['macd'][u]), float(m['macd'][v])]}
                    anchor = min(z[3], last['price']) if long else max(z[2], last['price'])
                check('PRICE_DIVERGENCE', price_div, evidence, 'Новый low' if long else 'Новый high')
                check('RSI_DIVERGENCE', rsi_div, evidence, 'RSI на втором экстремуме выше' if long else 'RSI на втором экстремуме ниже')
                check('MACD_DIVERGENCE', macd_div, evidence, 'MACD на втором экстремуме выше' if long else 'MACD на втором экстремуме ниже')
                check('MOMENTUM_TURN', sign*(m['histogram'][-1]-m['histogram'][-2]) > 0,
                      [float(m['histogram'][-2]), float(m['histogram'][-1])], 'Гистограмма меняется в сторону разворота')
            check('CLOSED_CANDLE_CONFIRMATION', sign*(z[4]-z[1]) > 0 and sign*(z[4]-(p[2] if long else p[3])) > 0,
                  {'open': z[1], 'close': z[4], 'previous_high': p[2], 'previous_low': p[3]}, 'Направленная закрытая свеча за предыдущим high/low')
            rejection = [v['code'] for v in checks if not v['passed']]
            entry = float(quote['ask' if long else 'bid'])
            hold = max(1, min(12, 14400//step))
            sl = tp = costs = stop_info = target_info = None
            # No level plan for failed technical setups; no fabricated market levels.
            if not rejection:
                if anchor is None or sign*(entry-anchor) <= 0:
                    rejection.append('NO_STRUCTURAL_INVALIDATION_BEHIND_ENTRY')
                else:
                    distance = max(1.5*a, sign*(entry-anchor)+.25*a)
                    sl = entry-sign*distance
                    targets = [v for v in opposite if sign*(v['price']-entry) > 0]
                    target = min(targets, key=lambda v: sign*(v['price']-entry)) if targets else None
                    if target is None:
                        rejection.append('NO_KNOWN_OPPOSING_PIVOT_TARGET')
                    else:
                        tp = target['price']
                        target_info = {'pivot': target, 'reason': 'Ближайший известный встречный pivot; цель не растягивается ради R/R'}
                        costs = risk_reward(entry, sl, tp, side, step, hold, quote['ask']-quote['bid'])
                        if costs is None or costs['net_rr'] < 1.5:
                            rejection.append('NET_RR_BELOW_1_5_OR_INVALID_GEOMETRY')
                    stop_info = {'atr': a, 'atr_period': 14, 'atr_method': 'WILDER', 'anchor': anchor,
                                 'anchor_kind': 'PULLBACK_EXTREME' if strategy == 'TREND_PULLBACK' else 'RETEST_LEVEL_EXTREME' if strategy == 'BREAKOUT_RETEST' else 'DIVERGENCE_EXTREME',
                                 'formula': 'SL = Entry − max(1.5 × ATR14, Entry − anchor + .25 × ATR14)' if long else 'SL = Entry + max(1.5 × ATR14, anchor − Entry + .25 × ATR14)',
                                 'distance_usdt': distance, 'distance_percent': 100*distance/entry,
                                 'reason': 'За уровнем отмены с буфером ≥.25 ATR и дистанцией ≥1.5 ATR; стоп не сужается ради R/R'}
                if abs(entry-z[4]) > .25*a or abs(entry_fill(entry, side, quoted=True)-z[4]) > .25*a:
                    rejection.append('OUTSIDE_CLOSED_SIGNAL_ENTRY_ZONE')
            valid_levels = costs is not None and sl > 0 and tp > 0
            identity = f'{VERSION}:{MODEL_HASH}:{frame}:{strategy}:{side}:{cutoff}'
            output.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'version': VERSION, 'model_sha256': MODEL_HASH,
                           'source': SOURCE, 'frame': frame, 'strategy': strategy, 'name': name, 'direction': side,
                           'state': 'REJECTED' if rejection else 'WATCH', 'score': round(100*sum(v['passed'] for v in checks)/len(checks)),
                           'score_basis': 'Равные доли выполненных условий выбранной стратегии; не вероятность прибыли',
                           'checks': checks, 'rejection': rejection, 'indicators': {k: float(v[-1]) for k, v in m.items()},
                           'closed_at': cutoff, 'valid_until': cutoff+step, 'quote_time': quote['time'], 'quote_received_at': quote['received_at'],
                           'entry': entry if valid_levels else None, 'sl': sl if valid_levels else None, 'tp': tp if valid_levels else None,
                           'net_rr': costs['net_rr'] if valid_levels else None, 'gross_rr': sign*(tp-entry)/abs(entry-sl) if valid_levels else None,
                           'costs': costs if valid_levels else None, 'stop_explanation': stop_info, 'target_explanation': target_info,
                           'entry_reason': 'Текущий Ask для LONG / Bid для SHORT после закрытого подтверждения; котировка и модельное исполнение не дальше .25 ATR от закрытия',
                           'confirmation': 'Все условия стратегии на закрытых свечах, свежие Bid/Ask, допустимая зона входа и Net R/R ≥1.5; статистической квалификации нет',
                           'horizon': {'min_seconds': min(hold*step, max(900, step)), 'max_seconds': hold*step, 'hold_bars': hold,
                                       'time_exit': 'Если сценарий не достиг SL/TP, пересмотреть выход не позже Entry time + max_seconds; оценка, не гарантия'},
                           'cancel': 'Потеря структурного anchor, достижение SL/TP, выход из зоны входа, новая свеча до входа, устаревшие данные или Net R/R <1.5',
                           'edge': 'NO_EDGE_FOUND', 'statistical_status': 'UNVALIDATED', 'probability_tp_before_sl': None,
                           'manual_only': True, 'exchange_execution': False})
    return output


def from_store(store, quotes: dict, now: float, running: bool) -> list[dict]:
    """Read the captured native candle seed. Never write an observation or trade."""
    output = []
    with store.connection() as db:
        for frame in STEPS:
            row = db.execute('SELECT payload FROM inputs WHERE frame=? ORDER BY seq DESC LIMIT 1', (frame,)).fetchone()
            if not running or row is None:
                output.extend(unknown(frame, 'OBSERVER_STOPPED_OR_NO_CAPTURED_HISTORY'))
                continue
            try:
                captured = json.loads(row['payload'])['snapshot']
                if captured['source'] != SOURCE or captured['frame'] != frame or captured['step'] != STEPS[frame]:
                    raise ValueError('SOURCE_MISMATCH')
                output.extend(evaluate(captured['bars'], frame, quotes.get(frame, {}), now))
            except (ValueError, KeyError, TypeError):
                output.extend(unknown(frame, 'CAPTURED_INPUT_UNAVAILABLE'))
    return output
