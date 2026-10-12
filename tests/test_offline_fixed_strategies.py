"""Synthetic fixtures test rules/accounting only, never historical performance."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import ast
import pytest

from app.lab.models import Bar, Baseline
from app.lab.strategies import Decision
from app.lab.execution import simulate
from scripts import offline_fixed_strategies as research


def bars(n=180):
    return [Bar(i*900, D(100+i%13), D(102+i%13), D(99+i%13), D(101+i%13), D(20)) for i in range(n)]


@pytest.mark.parametrize('name', research.NAMES)
def test_future_prices_cannot_change_prior_closed_signals(name):
    prior = bars(120)
    future = [Bar(i*900, D(9999), D(20000), D(1), D(15000), D(99999)) for i in range(120,180)]
    assert research.signals(prior+future, name)[:120] == research.signals(prior, name)


def test_donchian_excludes_current_high_and_protects_using_signal_close():
    rows = [Bar(i*900,D(100),D(101),D(99),D(100),D(20)) for i in range(51)]
    rows[-1] = Bar(50*900,D(100),D(110),D(99),D(102),D(20))
    decision = research.signals(rows, research.NAMES[0])[-1]
    assert decision.direction == 'LONG'
    assert decision.stop_distance == D('2.04')
    assert decision.target_distance == D('4.08')


def test_ema_is_crossover_event_not_persistent_alignment():
    rows = [Bar(i*900,D(100),D(101),D(99),D(100),D(20)) for i in range(60)]
    rows += [Bar(i*900,D(110),D(111),D(109),D(110),D(20)) for i in range(60,80)]
    decisions = research.signals(rows, research.NAMES[1])
    assert decisions[60].direction == 'LONG'
    assert all(d.direction is None for d in decisions[61:])


def test_atr_protection_independent_constant_true_range_oracle():
    rows = [Bar(i*900,D(100),D(101),D(99),D(100),D(20)) for i in range(51)]
    rows[-1] = Bar(50*900,D(100),D(103),D(99),D(102),D(20))
    decision = research.signals(rows, research.NAMES[2])[-1]
    expected = D(str((2*13+4)/14))
    assert decision.direction == 'LONG'
    assert decision.stop_distance == expected*2
    assert decision.target_distance == expected*4


def test_frozen_protocol_rejects_changes_before_execution(tmp_path):
    protocol, _ = research.freeze_protocol()
    assert protocol['split'] == '2026-08-01T00:00:00+00:00'
    changed = tmp_path/'protocol.json'
    changed.write_bytes(research.PROTOCOL_PATH.read_bytes()+b' ')
    with pytest.raises(ValueError,match='protocol hash mismatch'):
        research.freeze_protocol(changed)


def test_next_open_entry_has_no_preentry_high_low_execution():
    rows = [Bar(0,D(100),D(200),D(1),D(100),D(20)),
            Bar(900,D(103),D(104),D(102),D(103),D(20))]
    result = simulate(rows,[Decision('LONG',D(2),D(4)),Decision()],0,2,900,
                      Baseline(fee_bps='0',slippage_bps='0'))
    trade = result['trades'][0]
    assert trade['entry_time'] == trade['signal_time'] == 900
    assert trade['entry_raw_price'] == '103'
    assert trade['exit_reason'] == 'SEGMENT_END_CLOSE'


@pytest.mark.parametrize('side', ['LONG','SHORT'])
def test_ambiguous_entry_bar_always_uses_stop(side):
    rows = [Bar(0,D(100),D(101),D(99),D(100),D(20)),
            Bar(900,D(100),D(105),D(95),D(100),D(20))]
    result = simulate(rows,[Decision(side,D(2),D(4)),Decision()],0,2,900,Baseline())
    assert result['trades'][0]['exit_reason'] == 'STOP_LOSS_AMBIGUOUS'
    assert D(result['trades'][0]['realized_pnl']) < 0


def test_hold_reference_costs_equity_and_monthly_cashflows():
    start = 1785542400  # August UTC start
    rows = [Bar(start,D(100),D(101),D(99),D(100),D(20)),
            Bar(start+900,D(110),D(111),D(109),D(110),D(20))]
    result = research.buy_hold(rows,0,2,Baseline(),'2000')
    trade = result['trades'][0]
    assert D(trade['entry_price']) == D('100.05')
    assert D(trade['exit_price']) == D('109.945')
    assert D(trade['fees']) > 0 and D(trade['slippage_usdt']) > 0
    expected = D('10000')+D(trade['realized_pnl'])
    assert D(result['equity_curve'][-1]['equity']) == expected
    month = research.monthly(result,rows,0,2,Baseline())[0]
    assert D(month['cashflow_pnl']) == D(trade['realized_pnl'])
    assert month['closed_trades'] == 1


def test_split_starts_flat_and_result_is_deterministic():
    rows = bars(100)
    decisions = research.signals(rows,research.NAMES[0])
    decisions[59] = Decision('LONG',D(2),D(4))
    result = simulate(rows,decisions,60,80,900,Baseline())
    assert result == simulate(rows,decisions,60,80,900,Baseline())
    assert all(t['signal_time'] > rows[60].time for t in result['trades'])


def test_no_private_account_or_activation_dependencies():
    source = Path(research.__file__).read_text()
    tree = ast.parse(source)
    names = [n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(x in ','.join(names) for x in ('app.main','bybit','testnet','httpx','requests'))
    assert 'os.getenv' not in source and 'PAPER_DB_PATH' not in source
    assert 'create_order' not in source and 'cancel_order' not in source
