"""Offline synthetic lifecycle fixtures; never published as real market events."""
from copy import deepcopy
import json
from app.manual_preview.lifecycle import reduce_signal, scenario_id


def fixture():
    return dict(strategy='TREND_PULLBACK', direction='LONG', frame='15m',
                structure={'pivot_time': 900, 'kind': 'LOW'}, score=75,
                checks=[{'code': 'TREND', 'passed': True}, {'code': 'CANDLE', 'passed': False}],
                rejection=['CANDLE'], valid_until=3000, entry=100, sl=95, tp=110, net_rr=1.7)


def test_500_ticks_keep_identity_admission_and_watch_plan():
    c = fixture()
    row, event = reduce_signal(None, c, 1000, trusted=True)
    assert event['to'] == 'CANDIDATE'
    identity = row['id']
    for i in range(500):
        c['score'] = 71 + i % 20
        row, event = reduce_signal(row, c, 1001+i, trusted=True)
        assert row['id'] == identity and event is None and row['detected_at'] == 1000
    c['checks'][1]['passed'] = True
    c['rejection'] = []
    row, event = reduce_signal(row, c, 1600, trusted=True)
    assert event['to'] == 'WATCH'
    plan = deepcopy(row['current_plan'])
    c['entry'] = 101
    row, event = reduce_signal(row, c, 1601, trusted=True)
    assert event is None and row['current_plan'] == plan
    row, event = reduce_signal(row, c, 1602, trusted=True, invalidated=True)
    assert event['to'] == 'INVALIDATED' and row['current_plan'] is None


def test_restart_expiry_and_idempotency(tmp_path):
    c = fixture()
    row, _ = reduce_signal(None, c, 1000, trusted=True)
    path = tmp_path/'fixture-state.json'
    path.write_text(json.dumps(row))
    restored = json.loads(path.read_text())
    row, event = reduce_signal(restored, c, 3000, trusted=True)
    assert event['to'] == 'EXPIRED'
    row2, event2 = reduce_signal(row, c, 3001, trusted=True)
    assert row2 == row and event2 is None


def test_stale_is_immediate_terminal_unknown_no_plan_or_resurrection():
    c = fixture()
    row, _ = reduce_signal(None, c, 1000, trusted=True)
    row, event = reduce_signal(row, c, 1001, trusted=False)
    assert event['to'] == 'UNKNOWN' and row['current_plan'] is None
    recovered, event = reduce_signal(row, c, 1002, trusted=True)
    assert recovered == row and event is None


def test_threshold_hysteresis_and_identity():
    c = fixture()
    c['score'] = 69
    assert reduce_signal(None, c, 1000, trusted=True) == (None, None)
    c['score'] = 70
    row, _ = reduce_signal(None, c, 1000, trusted=True)
    c['score'] = 66
    row, event = reduce_signal(row, c, 1001, trusted=True)
    assert row['status'] == 'CANDIDATE' and event is None
    c['score'] = 64
    row, event = reduce_signal(row, c, 1002, trusted=True)
    assert event['to'] == 'INVALIDATED'
    identity = scenario_id(c)
    c.update(score=99, entry=101, quote_time=2000)
    assert scenario_id(c) == identity
    c['structure']['pivot_time'] = 1800
    assert scenario_id(c) != identity


def test_failed_checks_and_invalid_geometry_never_watch():
    c = fixture()
    c['score'] = 100
    row, _ = reduce_signal(None, c, 1000, trusted=True)
    assert row['status'] == 'CANDIDATE'
    c['checks'][1]['passed'] = True
    c['rejection'] = []
    c['sl'] = 110
    row, _ = reduce_signal(row, c, 1001, trusted=True)
    assert row['status'] == 'CANDIDATE' and row['current_plan'] is None
