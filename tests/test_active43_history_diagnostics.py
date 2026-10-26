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


def test_format_only_difference_is_exactly_equal_with_verified_legacy_fields():
    original=bar(volume='1.00')
    assert history_issue(state(original),[bar(volume='1')],910) is None


def test_numeric_correction_remains_a_real_mismatch():
    original=bar(volume='1.00')
    issue=history_issue(state(original),[bar(volume='1.01')],910)
    assert issue['code']=='HISTORY_CANDLE_CHANGED'
    assert issue['change_classification']=='NUMERIC_VALUES_CHANGED'
    assert issue['numeric_changed_fields']==['volume']


def test_hash_only_or_tampered_evidence_never_claims_a_format_change():
    for saved in (dict(state(bar(volume='1.0')),last_anchor_ohlcv=None),dict(state(bar(volume='1.0')),last_anchor_ohlcv=bar(volume='3').data())):
        issue=history_issue(saved,[bar(volume='1.00')],910)
        assert issue['code']=='HISTORY_CANDLE_CHANGED'
        assert issue['change_classification']=='UNDETERMINED'

def test_production_incident_20261025_late_close_and_volume_revision():
    """Captured Bitget 5m incident: same timestamp, changed close and BTC volume.

    This regression intentionally documents the current fail-closed behavior;
    it does not authorize silently accepting a rewritten closed candle.
    """
    original = Bar(1792941900, Decimal('80513.1'), Decimal('80551'),
                   Decimal('80513.1'), Decimal('80545'), Decimal('41.1909'))
    revised = Bar(1792941900, Decimal('80513.1'), Decimal('80551'),
                  Decimal('80513.1'), Decimal('80550.4'), Decimal('41.4947'))
    saved = {'config': {'timeframe': '5m'}, 'watermark': 1792942200,
             'last_bar_hash': digest(original.data()),
             'last_anchor_ohlcv': original.data()}
    incident = history_issue(saved, [revised], 1792942976)
    assert incident['code'] == 'HISTORY_CANDLE_CHANGED'
    assert incident['change_classification'] == 'NUMERIC_VALUES_CHANGED'
    assert incident['numeric_changed_fields'] == ['close', 'volume']
    assert incident['anchor_timestamp'] == 1792941900
    assert incident['old_anchor_ohlcv'] == original.data()
    assert incident['new_anchor_ohlcv'] == revised.data()
    assert incident['old_ohlcv_hash'] != incident['new_ohlcv_hash']
