"""Regression tests for the offline August research adapter."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.models import Candle
from app.patterns.config import PatternConfig
from app.patterns.engine import evaluate
from app.patterns.features import Features, build_features
import app.paper.signals as production_signals
from scripts import replay_aura_august_research as research
from scripts.replay_aura_august_research import CONFIGS, END, START, _causal_features


def test_research_config_matrix_is_exact_and_production_is_present():
    assert CONFIGS == {
        'A': {'similarity': 75, 'minimum_sample': 20},
        'B': {'similarity': 60, 'minimum_sample': 20},
        'C': {'similarity': 60, 'minimum_sample': 10},
        'D': {'similarity': 60, 'minimum_sample': 5},
        'E': {'similarity': 65, 'minimum_sample': 5},
    }
    assert START < END and (END - START) // 900 == 2976
    default = PatternConfig().model_dump()
    for values in CONFIGS.values():
        current = PatternConfig(minimum_similarity=values['similarity'],
                                minimum_sample=values['minimum_sample']).model_dump()
        for field in default.keys() - {'minimum_similarity', 'minimum_sample'}:
            assert current[field] == default[field]


def test_causal_prefix_cannot_expose_future_feature_rows():
    vectors = np.arange(24, dtype=float).reshape(6, 4)
    facts = [{'i': i} for i in range(6)]
    features = Features(vectors, facts, 0)
    prefix = _causal_features(features, 3)
    assert prefix.vectors.shape == (3, 4)
    assert prefix.facts == facts[:3]
    vectors[4, 0] = 999999
    assert prefix.vectors[-1, 0] == 8


def test_research_adapter_has_no_network_or_exchange_write_imports():
    path = Path(__file__).parents[1] / 'scripts' / 'replay_aura_august_research.py'
    tree = ast.parse(path.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or '')
    assert not any(name in ','.join(imports) for name in ('httpx', 'requests', 'socket', 'bybit', 'testnet'))
    source = path.read_text()
    assert 'create_order' not in source and 'cancel_order' not in source


def rows(n):
    return [Candle(i * 900, 100 + i * .03, 101 + i * .03,
                   99 + i * .03, 100 + i * .03, 20 + i % 13) for i in range(n)]


@pytest.mark.parametrize('values', list(CONFIGS.values()))
def test_actual_future_prices_do_not_change_research_signal(values):
    past = rows(550)
    future = [Candle(i * 900, 10000., 20000., 1., 15000., 999999.) for i in range(550, 650)]
    config = PatternConfig(minimum_similarity=values['similarity'],
                           minimum_sample=values['minimum_sample'])
    combined = build_features(past + future, 20, 500)
    direct = evaluate(past, 900, 500, config, 549, None, False)
    cached = evaluate(past, 900, 500, config, 549, _causal_features(combined, 550), False)
    assert cached == direct


def test_real_signal_reader_replay_restores_modules_and_isolates_ledger(monkeypatch):
    candles = rows(603)
    monkeypatch.setattr(research, 'START', candles[600].time)
    original_config = production_signals.PatternConfig
    original_evaluate = production_signals.evaluate
    result = asyncio.run(research._run_one(candles, 600, PatternConfig(), 'UNIT', 20))
    assert result['signal_reader'].startswith('UNCHANGED_PRODUCTION')
    assert len(result['decisions']) == 3
    assert result['signals'] == {'LONG': 0, 'SHORT': 0, 'WAIT': 3}
    assert result['decision_counts'] == {'NO_SIGNAL': 3}
    assert result['trades'] == []
    assert production_signals.PatternConfig is original_config
    assert production_signals.evaluate is original_evaluate


def test_missing_first_august_candle_rejected_even_if_last_is_present(monkeypatch):
    bars = [SimpleNamespace(time=START - 900)]
    bars += [SimpleNamespace(time=t) for t in range(START + 900, END, 900)]
    monkeypatch.setattr(research, 'load_binance_csv', lambda _: (bars, {}))
    with pytest.raises(ValueError, match='August coverage is incomplete'):
        research._load(Path('not-read.csv'))
