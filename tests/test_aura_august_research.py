"""Regression tests for the offline August research adapter."""
import ast
from pathlib import Path

import numpy as np

from app.patterns.features import Features
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
