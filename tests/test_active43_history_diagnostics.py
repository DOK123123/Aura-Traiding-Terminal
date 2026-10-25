"""Regression checks for audit-only Bitget history mismatch diagnostics."""
from decimal import Decimal
from app.lab.models import Bar, digest
from app.active43.core import SOURCE
from app.active43.recovery import history_issue


def bar(volume='1', close='100'):
    return Bar(300, Decimal('100'), Decimal('101'), Decimal('99'), Decimal(close), Decimal(volume))


def state(anchor):
    return {'config': {'timeframe': '5m'}, 'watermark': 600,
            'last_bar_hash': digest(anchor.data()),
            'last_anchor_ohlcv': anchor.data()}


def test_volume_only_change_is_diagnostic_and_still_blocks():
    original = bar()
    issue = history_issue(state(original), [bar(volume='2')], 910)
    assert issue['code'] == 'HISTORY_CANDLE_CHANGED'
    assert issue['changed_fields'] == ['volume']
    assert issue['old_anchor_ohlcv']['volume'] == '1'
    assert issue['new_anchor_ohlcv']['volume'] == '2'
    assert issue['source'] == SOURCE


def test_price_change_is_diagnostic_and_still_blocks():
    original = bar()
    issue = history_issue(state(original), [bar(close='100.5')], 910)
    assert issue['code'] == 'HISTORY_CANDLE_CHANGED'
    assert issue['changed_fields'] == ['close']


def test_unchanged_anchor_has_no_issue():
    original = bar()
    assert history_issue(state(original), [original], 910) is None


def test_legacy_hash_only_does_not_invent_fields():
    original = bar()
    legacy = state(original)
    legacy.pop('last_anchor_ohlcv')
    issue = history_issue(legacy, [bar(volume='2')], 910)
    assert issue['code'] == 'HISTORY_CANDLE_CHANGED'
    assert issue['changed_fields'] is None
    assert issue['old_anchor_ohlcv'] is None


def test_tampered_anchor_is_not_used_as_evidence():
    original = bar()
    tampered = state(original)
    tampered['last_anchor_ohlcv']['volume'] = '999'
    issue = history_issue(tampered, [bar(volume='2')], 910)
    assert issue['changed_fields'] is None
