"""Offline regressions for immutable paper candles and adverse Lab opening fills."""
from dataclasses import replace
from decimal import Decimal as D
from fractions import Fraction as F
import uuid

import pytest

from app.lab.execution import simulate
from app.lab.models import Bar as LabBar, Baseline
from app.lab.strategies import Decision, decisions
from app.paper.engine import Engine, candle_fingerprint
from app.paper.models import Bar, PaperError, Settings, Window
from app.paper.storage import Store


def rational_ticks(value, *, ceiling=False):
    scaled = F(value) * 100000000
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    if ceiling:
        return whole + bool(remainder)
    return whole + (2 * remainder > scaled.denominator or
                    2 * remainder == scaled.denominator and whole % 2 == 1)


@pytest.fixture
def paper(tmp_path):
    clock = [1800000060000]
    settings = replace(Settings(), commission_pct=D('0'), risk_per_trade_pct=D('10'),
                       stop_loss_pct=D('10'), take_profit_pct=D('10'), maximum_simultaneous_positions=2)
    engine = Engine(Store(tmp_path / 'paper.sqlite3'), settings, lambda: clock[0])
    return engine, clock


def paper_window(clock, bar=None):
    bar = bar or Bar(clock[0] // 1000 - 60, D(100), D(105), D(95), D(100), D(10))
    return Window('BTCUSDT', '1m', 'offline-public', clock[0], (bar,))


def paper_payload(window, side='LONG'):
    bar = window.bars[-1]
    return dict(request_id=str(uuid.uuid4()), symbol=window.symbol,
                timeframe=window.timeframe, direction=side, expected_source=window.source,
                expected_price=str(bar.close), expected_candle_time=bar.time,
                position_size='1', stop_loss=None, take_profit=None,
                entry_reason='Offline safety regression', signal_id=None)


def paper_open(engine, window, side='LONG'):
    return engine.open(paper_payload(window, side), window)


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
@pytest.mark.parametrize('field,value', [('open', D(101)), ('high', D(111)),
                                       ('low', D(89)), ('volume', D(11))])
def test_paper_same_close_ohlcv_correction_pauses_without_retroactive_exit(paper, side, field, value):
    engine, clock = paper
    trade = paper_open(engine, paper_window(clock), side)
    assert len(trade['last_candle_fingerprint']) == 64
    clock[0] += 60000
    original = paper_window(clock)
    engine.advance(original)
    fingerprint = engine.trade(trade['id'])['last_candle_fingerprint']
    corrected = replace(original, bars=(replace(original.bars[0], **{field: value}),))
    engine.advance(corrected)
    paused = engine.trade(trade['id'])
    assert paused['status'] == 'OPEN'
    assert paused['market_error'] == 'CANDLE_CORRECTION'
    assert paused['candle_correction_detected'] is True
    assert paused['last_candle_fingerprint'] == fingerprint
    snapshot = engine.snapshot()
    assert snapshot['statistics']['equity'] is None
    assert snapshot['open_positions'][0]['data_status'] == 'CANDLE_CORRECTION'
    assert D(snapshot['statistics']['current_balance']) == 10000
    assert snapshot['statistics']['total_trades'] == 0


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_paper_correction_latch_survives_restart_missing_overlap_and_market_failure(paper, side):
    engine, clock = paper
    original = paper_window(clock)
    trade = paper_open(engine, original, side)
    engine.advance(replace(original, bars=(replace(original.bars[0], high=D(111)),)))
    restarted = Engine(Store(engine.store.path), clock=lambda: clock[0])
    restarted.unavailable('BTCUSDT', '1m', 'MARKET_UNAVAILABLE')
    restarted.advance(original)
    clock[0] += 60000
    next_window = paper_window(clock)
    restarted.advance(next_window)
    current = restarted.trade(trade['id'])
    assert current['last_candle_time'] == original.bars[0].time
    assert current['market_error'] == 'CANDLE_CORRECTION'
    assert current['candle_correction_detected'] is True
    assert restarted.snapshot()['statistics']['equity'] is None
    with pytest.raises(PaperError, match='INVALID_MARKET_DATA'):
        restarted.close(trade['id'], dict(request_id=str(uuid.uuid4()), exit_reason='Review required'), next_window)
    with pytest.raises(PaperError, match='STALE_DATA'):
        paper_open(restarted, next_window, side)


def test_paper_equivalent_decimal_scales_do_not_count_as_correction(paper):
    engine, clock = paper
    original = paper_window(clock)
    trade = paper_open(engine, original)
    equivalent = replace(original.bars[0], open=D('100.00'), high=D('105.0'),
                         low=D('95.000'), close=D('100.0'), volume=D('10.0000'))
    engine.advance(replace(original, bars=(equivalent,)))
    assert candle_fingerprint(equivalent) == trade['last_candle_fingerprint']
    assert engine.trade(trade['id'])['market_error'] is None
    assert engine.snapshot()['open_positions'][0]['data_status'] == 'FRESH'


def test_paper_unknown_volume_becomes_known_without_false_correction(paper):
    engine, clock = paper
    original = paper_window(clock)
    unknown = replace(original, bars=(replace(original.bars[0], volume=None),))
    trade = paper_open(engine, unknown)
    assert trade['last_candle_volume'] is None
    engine.advance(original)
    current = engine.trade(trade['id'])
    assert current['market_error'] is None
    assert D(current['last_candle_volume']) == 10
    engine.advance(unknown)
    assert D(engine.trade(trade['id'])['last_candle_volume']) == 10
    engine.advance(replace(original, bars=(replace(original.bars[0], volume=D(11)),)))
    assert engine.trade(trade['id'])['market_error'] == 'CANDLE_CORRECTION'


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
@pytest.mark.parametrize('command', ['open', 'close'])
def test_paper_rejected_command_commits_only_correction_observation(paper, side, command):
    engine, clock = paper
    settings = engine.snapshot()['settings']
    settings['commission_pct'] = '0.1'
    engine.configure(settings)
    original = paper_window(clock)
    trade = paper_open(engine, original, side)
    before = engine.snapshot()
    corrected = replace(original, bars=(replace(original.bars[0], high=D(111)),))
    with pytest.raises(PaperError, match='STALE_DATA' if command == 'open' else 'INVALID_MARKET_DATA'):
        if command == 'open':
            paper_open(engine, corrected, side)
        else:
            engine.close(trade['id'], dict(request_id=str(uuid.uuid4()), exit_reason='Offline review'), corrected)
    after = engine.snapshot()
    assert after['statistics']['current_balance'] == before['statistics']['current_balance']
    assert after['statistics']['total_commissions'] == before['statistics']['total_commissions']
    assert after['equity_curve'] == before['equity_curve']
    assert after['statistics']['equity'] is None
    assert engine.trade(trade['id'])['market_error'] == 'CANDLE_CORRECTION'
    with engine.store.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM trades').fetchone()[0] == 1
        assert engine.store.get(db, 'close_sequence') == '0'
    restarted = Engine(Store(engine.store.path), clock=lambda: clock[0])
    assert restarted.trade(trade['id'])['candle_correction_detected'] is True


def test_paper_command_replay_precedes_safety_observation(paper):
    engine, clock = paper
    original = paper_window(clock)
    payload = paper_payload(original)
    trade = engine.open(payload, original)
    corrected = replace(original, bars=(replace(original.bars[0], high=D(111)),))
    assert engine.open(payload, corrected) == trade
    assert engine.trade(trade['id'])['market_error'] is None
    with pytest.raises(PaperError, match='IDEMPOTENCY_CONFLICT'):
        engine.open(dict(payload, direction='SHORT'), corrected)
    assert engine.trade(trade['id'])['market_error'] is None
    clock[0] += 60000
    next_window = paper_window(clock)
    close_payload = dict(request_id=str(uuid.uuid4()), exit_reason='Offline close')
    closed = engine.close(trade['id'], close_payload, next_window)
    second = paper_open(engine, next_window)
    corrected_next = replace(next_window, bars=(replace(next_window.bars[0], high=D(111)),))
    assert engine.close(trade['id'], close_payload, corrected_next) == closed
    assert engine.trade(second['id'])['market_error'] is None
    assert engine.snapshot()['statistics']['total_trades'] == 1


@pytest.mark.parametrize('mismatch', ['source', 'timeframe'])
def test_paper_safety_observation_does_not_reconcile_another_market_scope(paper, mismatch):
    engine, clock = paper
    original = paper_window(clock)
    trade = paper_open(engine, original)
    changed = replace(original.bars[0], high=D(111))
    if mismatch == 'source':
        wrong_scope = replace(original, source='another-offline-source', bars=(changed,))
    else:
        clock[0] += 300000
        wrong_scope = replace(original, timeframe='5m', observed_at=clock[0], bars=(changed,))
    with pytest.raises(PaperError, match='SOURCE_MISMATCH'):
        engine.close(trade['id'], dict(request_id=str(uuid.uuid4()), exit_reason='Offline close'), wrong_scope)
    assert engine.trade(trade['id']) == trade


@pytest.mark.parametrize('overlap', [True, False])
def test_paper_legacy_restart_establishes_observed_fingerprint_without_replaying_ohlcv(paper, overlap):
    engine, clock = paper
    original = paper_window(clock)
    trade = paper_open(engine, original)
    trade.pop('last_candle_fingerprint')
    trade.pop('candle_correction_detected')
    trade.pop('last_candle_volume')
    with engine.store.transaction() as db:
        engine.store.save(db, trade)
    restarted = Engine(Store(engine.store.path), clock=lambda: clock[0])
    if overlap:
        # Historical highs were never stored by the old journal. Establish identity
        # without inventing a retroactive target fill from this observed version.
        observed = replace(original, bars=(replace(original.bars[0], high=D(111)),))
    else:
        clock[0] += 60000
        observed = paper_window(clock)
    restarted.advance(observed)
    current = restarted.trade(trade['id'])
    assert current['status'] == 'OPEN'
    assert current['market_error'] is None
    assert current['last_candle_fingerprint'] == candle_fingerprint(observed.bars[0])
    restarted.advance(replace(observed, bars=(replace(observed.bars[0], volume=D(11)),)))
    assert restarted.trade(trade['id'])['market_error'] == 'CANDLE_CORRECTION'


@pytest.mark.parametrize('field,value', [('last_candle_fingerprint', None),
                                       ('last_candle_fingerprint', 'g' * 64),
                                       ('last_candle_fingerprint', '0' * 63),
                                       ('candle_correction_detected', 1),
                                       ('candle_correction_detected', True),
                                       ('last_candle_volume', True),
                                       ('last_candle_volume', '-1'),
                                       ('last_candle_volume', 'NaN')])
def test_paper_corrupt_fingerprint_or_latch_fails_restart(paper, field, value):
    engine, clock = paper
    trade = paper_open(engine, paper_window(clock))
    trade[field] = value
    with engine.store.transaction() as db:
        engine.store.save(db, trade)
    with pytest.raises(PaperError, match='CORRUPT_JOURNAL'):
        Engine(Store(engine.store.path), clock=lambda: clock[0])


def lab_bar(stamp, *, op='100', high=None, low=None, close=None):
    price = D(op)
    return LabBar(stamp, price, D(high) if high is not None else price,
                  D(low) if low is not None else price, D(close) if close is not None else price, D(10))


def assert_lab_cashflows(run):
    net_ticks = 0
    for trade in run['trades']:
        entry, exit_, size = F(trade['entry_price']), F(trade['exit_price']), F(trade['size'])
        sign = 1 if trade['direction'] == 'LONG' else -1
        gross_ticks = rational_ticks(sign * (exit_ - entry) * size)
        pnl_ticks = gross_ticks - F(trade['fees']) * 100000000
        assert F(trade['gross_price_pnl']) * 100000000 == gross_ticks
        assert F(trade['realized_pnl']) * 100000000 == pnl_ticks
        net_ticks += pnl_ticks
    assert F(run['metrics']['final_balance']) * 100000000 == 10000 * 100000000 + net_ticks


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_lab_new_tight_stop_uses_raw_open_before_later_ambiguous_bar(side):
    bars = [lab_bar(0), lab_bar(900, high='101', low='99')]
    signals = [Decision(side, D('.04'), D('.08')), Decision()]
    run = simulate(bars, signals, 0, 2, 900, Baseline(fee_bps='0'))
    trade = run['trades'][0]
    expected = F(100) * (F(1999, 2000) if side == 'LONG' else F(2001, 2000))
    assert F(trade['exit_price']) == expected
    assert D(trade['exit_raw_price']) == 100
    assert trade['exit_time'] == trade['entry_time'] == 900
    assert trade['exit_reason'] == 'STOP_GAP'
    assert D(trade['risk_usdt']) <= D(trade['risk_budget_usdt'])
    assert_lab_cashflows(run)


@pytest.mark.parametrize('side,increment', [('LONG', D('.015')), ('SHORT', D('-.015'))])
def test_lab_frozen_donchian_can_have_stop_beyond_observed_open(side, increment):
    bars = [lab_bar(i * 900, op=str(D(100) + i * increment)) for i in range(22)]
    run = simulate(bars, decisions(bars, 'DONCHIAN'), 20, 22, 900, Baseline(fee_bps='0'))
    trade = run['trades'][0]
    assert trade['direction'] == side
    assert trade['exit_reason'] == 'STOP_GAP'
    assert D(trade['exit_raw_price']) == bars[21].open
    assert_lab_cashflows(run)


@pytest.mark.parametrize('side,gap', [('LONG', '90'), ('SHORT', '110')])
def test_lab_existing_stop_gap_still_precedes_scheduled_exit(side, gap):
    bars = [lab_bar(0), lab_bar(900), lab_bar(1800, op=gap)]
    signals = [Decision(side, D(2), D(4)), Decision(exit_long=True, exit_short=True), Decision()]
    run = simulate(bars, signals, 0, 3, 900, Baseline())
    trade = run['trades'][0]
    assert trade['exit_reason'] == 'STOP_GAP'
    assert D(trade['exit_raw_price']) == D(gap)
    assert trade['exit_time'] == 1800
    assert_lab_cashflows(run)


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_lab_normal_entry_ambiguous_bar_preserves_stop_and_fee_inclusive_sizing(side):
    bars = [lab_bar(0), lab_bar(900, high='106', low='94')]
    run = simulate(bars, [Decision(side, D(2), D(4)), Decision()], 0, 2, 900,
                   Baseline(max_notional='10000'))
    trade = run['trades'][0]
    assert trade['exit_reason'] == 'STOP_LOSS_AMBIGUOUS'
    assert trade['exit_time'] == 1800
    assert D(trade['exit_raw_price']) == D(trade['stop_loss'])
    entry, stop, size = F(trade['entry_price']), F(trade['stop_loss']), F(trade['size'])
    stop_fill = stop * (F(1999, 2000) if side == 'LONG' else F(2001, 2000))
    risk_ticks = (rational_ticks(abs(entry - stop_fill) * size, ceiling=True) +
                  rational_ticks(entry * size / 1000, ceiling=True) +
                  rational_ticks(stop_fill * size / 1000, ceiling=True))
    assert F(trade['risk_usdt']) * 100000000 == risk_ticks <= 100 * 100000000
    assert F(trade['notional']) + F(trade['entry_fee']) <= 10000
    assert F(trade['fees']) * 100000000 == (rational_ticks(entry * size / 1000, ceiling=True) +
                                           rational_ticks(F(trade['exit_price']) * size / 1000, ceiling=True))
    assert_lab_cashflows(run)
