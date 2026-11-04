"""Causal evidence and risk invariants; never create any kind of account trade."""
import gzip
import json
from pathlib import Path
import pytest

from app.hunter.market import SOURCE
from app.hunter.store import Store
from app.manual_preview.explainable import evaluate, indicators, pivots, from_store
from scripts.replay_explainable import bars_for, outcome

BASE = json.load(gzip.open(Path(__file__).parents[1]/'research/strategy_engine/bitget-2026-07-10-15m.json.gz'))


def case(at=1787464800, frame='1h'):
    step = {'15m': 900, '1h': 3600, '4h': 14400}[frame]
    bars = [b for b in bars_for(BASE, step) if b[0]+step <= at][-260:]
    mid = bars[-1][4]
    q = dict(source=SOURCE, bid=mid*.9999, ask=mid*1.0001, last=mid, time=at, received_at=at)
    return bars, q


def test_three_real_independent_strategies_detect_both_sides_before_risk_gates():
    low_rr = 'NET_RR_BELOW_1_5_OR_INVALID_GEOMETRY'
    wide = 'STOP_WIDER_THAN_3_ATR'
    examples = [('TREND_PULLBACK', 'LONG', 1783098900, 'ENTRY_IN_OPPOSING_ZONE'),
                ('TREND_PULLBACK', 'SHORT', 1783227600, low_rr),
                ('BREAKOUT_RETEST', 'LONG', 1783988100, low_rr),
                ('BREAKOUT_RETEST', 'SHORT', 1783217700, low_rr),
                ('MOMENTUM_DIVERGENCE', 'LONG', 1783987200, wide),
                ('MOMENTUM_DIVERGENCE', 'SHORT', 1783127700, wide)]
    for strategy, side, at, reason in examples:
        b, q = case(at, '15m')
        rows = evaluate(b, '15m', q, at)
        assert len(rows) == 6
        x = next(x for x in rows if x['strategy'] == strategy and x['direction'] == side)
        assert all(c['passed'] for c in x['checks'])
        assert x['score'] == 100  # full pattern can still fail costs, not probability
        assert x['state'] == 'REJECTED'
        assert reason in x['rejection']
        if reason == wide:
            assert x['stop_explanation']['distance_atr'] > 3
        if reason == 'ENTRY_IN_OPPOSING_ZONE':
            assert x['tp'] is None
        assert x['stop_explanation']['atr'] > 0
        if strategy == 'MOMENTUM_DIVERGENCE':
            assert {'RSI_DIVERGENCE', 'MACD_DIVERGENCE', 'CONFIRMED_PIVOTS'} <= {c['code'] for c in x['checks']}


@pytest.mark.parametrize('mirror', [False, True])
def test_real_short_and_explicitly_synthetic_mirrored_long_stop_cost_and_horizon(mirror):
    at = 1787464800; b, q = case(at)
    if mirror:
        b = [[t, 152000-o, 152000-l, 152000-h, 152000-c, v] for t, o, h, l, c, v in b]
        q = {**q, 'bid': 152000-q['ask'], 'ask': 152000-q['bid'], 'last': 152000-q['last']}
    side = 'LONG' if mirror else 'SHORT'; sign = 1 if mirror else -1
    x = next(x for x in evaluate(b, '1h', q, at) if x['strategy'] == 'BREAKOUT_RETEST' and x['direction'] == side)
    assert x['state'] == 'WATCH'
    assert x['net_rr'] >= 1.5 and x['net_rr'] < x['gross_rr']
    s = x['stop_explanation']; a = s['atr']; anchor = s['anchor']
    assert sign*(anchor-x['sl']) >= .25*a-1e-8
    assert abs(x['entry']-x['sl']) >= 1.5*a-1e-8
    assert s['distance_usdt'] == pytest.approx(abs(x['entry']-x['sl']))
    assert s['distance_percent'] == pytest.approx(100*abs(x['entry']-x['sl'])/x['entry'])
    assert x['entry'] == q['ask' if mirror else 'bid']
    assert x['costs']['funding_reserve'] > 0
    assert x['costs']['entry_basis'] == 'EXECUTABLE_QUOTE'
    target = x['target_explanation']
    zone = target['zone']
    assert zone['confirmed_at'] <= b[-1][0] and zone['touches'] >= 2
    assert x['tp'] == zone['lower' if mirror else 'upper']
    assert s['distance_atr'] <= 3
    changed = {**q, 'bid': q['bid']-.01, 'ask': q['ask']+.01}
    updated = next(y for y in evaluate(b, '1h', changed, at) if y['id'] == x['id'])
    assert updated['entry'] != x['entry'] and updated['zones'] == x['zones']
    assert x['horizon']['max_seconds'] == 14400
    assert x['probability_tp_before_sl'] is None and x['edge'] == 'NO_EDGE_FOUND'


@pytest.mark.parametrize('defect', ['stale', 'future', 'foreign', 'crossed', 'gap', 'warmup', 'forming', 'nan'])
def test_invalid_data_unknown_with_no_invented_score_or_levels(defect):
    at = 1787464800; b, q = case(at)
    if defect == 'stale': q['time'] -= 6
    if defect == 'future': q['received_at'] += 1
    if defect == 'foreign': q['source'] = 'OTHER'
    if defect == 'crossed': q['ask'] = q['bid']-1
    if defect == 'gap': b.pop(20)
    if defect == 'warmup': b = b[-100:]
    if defect == 'forming': b.append([at, 100, 101, 99, 100, 1])
    if defect == 'nan': b[50][5] = float('nan')
    for x in evaluate(b, '1h', q, at):
        assert x['state'] == 'UNKNOWN'
        assert all(x[k] is None for k in ['score', 'entry', 'sl', 'tp', 'net_rr'])


def test_no_future_suffix_enters_indicators_or_decision():
    at = 1787464800; b, q = case(at)
    all_bars = bars_for(BASE, 3600)
    expected = evaluate(b, '1h', q, at)
    for row in all_bars:
        if row[0] >= at: row[1:5] = [100000, 110000, 90000, 105000]
    causal = [row for row in all_bars if row[0]+3600 <= at]
    assert evaluate(causal, '1h', q, at) == expected
    assert evaluate(causal[-260:], '1h', q, at) == expected
    assert all(v['confirmed_at'] <= at for v in pivots(b, 3600))


def test_independent_indicator_reference_linear_prices():
    # Linear +1 closes: seeded EMA20 is close−9.5, EMA50 is close−24.5.
    b = [[i*300, 1000+i-.5, 1000+i+2, 1000+i-2, 1000+i, 10] for i in range(260)]
    m = indicators(b)
    assert m['ema20'][-1] == pytest.approx(1259-9.5)
    assert m['ema50'][-1] == pytest.approx(1259-24.5)
    assert m['atr'][-1] == pytest.approx(4)
    assert m['rsi'][-1] == 100
    assert m['macd'][-1] == pytest.approx(7)
    assert abs(m['histogram'][-1]) < 1e-8


def test_read_store_is_pure_and_stale_frames_unknown(tmp_path):
    at = 1787464800; b, q = case(at)
    store = Store(tmp_path/'signals.sqlite')
    store.observe(dict(source=SOURCE, frame='1h', step=3600, bars=b, quote=q), [], at, {'approved': []})
    with store.connection() as db:
        before = db.total_changes
        original = list(db.execute('SELECT COUNT(*) FROM events'))[0][0]
    rows = from_store(store, {'1h': q}, at, True)
    assert len(rows) == 24
    assert sum(x['state'] == 'WATCH' for x in rows) == 1
    assert all(x['state'] == 'UNKNOWN' for x in rows if x['frame'] != '1h')
    with store.connection() as db:
        assert db.total_changes == before == 0
        assert list(db.execute('SELECT COUNT(*) FROM events'))[0][0] == original
    assert all(x['state'] == 'UNKNOWN' for x in from_store(store, {'1h': q}, at+6, True))
    assert all(x['state'] == 'UNKNOWN' for x in from_store(store, {'1h': q}, at, False))


def test_replay_next_open_gap_and_sl_first_not_signal_candle_fill():
    plan = dict(index=0, direction='LONG', sl=98, tp=108, hold_bars=1)
    # Signal candle crosses both levels; it must never exit the next-open plan.
    b = [[0, 100, 200, 1, 100, 1], [300, 100, 109, 97, 101, 1], [600, 100, 101, 99, 100, 1]]
    assert outcome(plan, b, 300)['outcome'] == 'SL'
    b[1] = [300, 110, 111, 109, 110, 1]
    assert outcome(plan, b, 300)['outcome'] == 'NO_FILL'


@pytest.mark.parametrize('strategy,side', [(k, s) for k in ('TREND_PULLBACK', 'BREAKOUT_RETEST', 'MOMENTUM_DIVERGENCE') for s in ('LONG', 'SHORT')])
def test_real_native_5m_patterns_have_closed_numeric_evidence_and_honest_risk_rejection(strategy, side):
    # Native exchange archive, independently fetched; no interpolation from 15m.
    payload = json.load(gzip.open(Path(__file__).parents[1]/'research/strategy_engine/bitget-native-5m-2026-11-02.json.gz'))
    assert payload['source'] == SOURCE and payload['frame'] == '5m'
    cutoffs = {('MOMENTUM_DIVERGENCE','SHORT'):1793046600, ('BREAKOUT_RETEST','SHORT'):1793047500,
               ('TREND_PULLBACK','LONG'):1793063400, ('TREND_PULLBACK','SHORT'):1793068500,
               ('BREAKOUT_RETEST','LONG'):1793088300, ('MOMENTUM_DIVERGENCE','LONG'):1793156100}
    at = cutoffs[strategy,side]
    b = [r for r in payload['bars'] if r[0]+300 <= at][-260:]
    mid = b[-1][4]
    q = dict(source=SOURCE, bid=mid*.9999, ask=mid*1.0001, last=mid, time=at, received_at=at)
    x = next(r for r in evaluate(b, '5m', q, at) if r['strategy'] == strategy and r['direction'] == side)
    assert all(c['passed'] for c in x['checks'])
    assert x['state'] == 'REJECTED' and x['rejection']
    assert x['score'] == 100 and x['indicators']['atr'] > 0
    assert x['horizon']['min_seconds'] == 900 and x['horizon']['max_seconds'] == 3600
    assert x['edge'] == 'NO_EDGE_FOUND' and x['probability_tp_before_sl'] is None
