"""Cache/adaptor regressions use synthetic fixtures, never performance evidence."""
import ast
from pathlib import Path

import numpy as np
import pytest

from app.models import Candle
from app.patterns.config import PatternConfig
from app.patterns.engine import evaluate
from app.patterns.features import build_features
from scripts.replay_aura_csv import CausalFeatureCache, main


def candles(n=650):
    return [Candle(i*900,100+i*.03,101+i*.03,99+i*.03,100+i*.03,20+i%13) for i in range(n)]


def test_cached_production_results_identical_to_direct_prefixes():
    rows=candles();cache=CausalFeatureCache(rows)
    assert cache.verify([499,549,649])==[499,549,649]
    for n in (500,550,650):
        direct=build_features(rows[:n],20,500)
        np.testing.assert_array_equal(cache.features.vectors[:n],direct.vectors)
        assert cache.features.facts[:n]==direct.facts


def test_future_prices_do_not_change_cached_past_decision():
    prefix=candles(550)
    future=[Candle(i*900,10000.,20000.,1.,15000.,999999.) for i in range(550,650)]
    a=CausalFeatureCache(prefix)
    b=CausalFeatureCache(prefix+future)
    left=a(prefix,900,500,PatternConfig(),549,None,False)
    right=b(prefix,900,500,PatternConfig(),549,None,False)
    assert left==right==evaluate(prefix,900,500,PatternConfig(),549,None,False)


def test_changed_prefix_or_scope_rejected():
    rows=candles();cache=CausalFeatureCache(rows)
    changed=rows[:550];changed[-1]=Candle(changed[-1].time,101.,103.,100.,102.,1.)
    with pytest.raises(ValueError,match='prefix mismatch'):cache(changed,900,500,PatternConfig())
    with pytest.raises(ValueError):cache(rows,3600,500,PatternConfig())
    with pytest.raises(ValueError):cache(rows,900,2000,PatternConfig())
    with pytest.raises(ValueError):cache(rows,900,500,PatternConfig(minimum_confidence=41))
    with pytest.raises(ValueError):cache(rows,900,500,PatternConfig(),target=500)


def test_no_exchange_clients_live_env_or_account_dependencies():
    source=(Path(__file__).parents[1]/'scripts/replay_aura_csv.py').read_text()
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            names=node.module or '' if isinstance(node,ast.ImportFrom) else ','.join(a.name for a in node.names)
            assert not any(x in names for x in ('app.main','bybit','testnet','httpx','requests','socket'))
    assert 'PAPER_DB_PATH' not in source and 'os.getenv' not in source


def test_existing_output_never_overwritten(tmp_path):
    output=tmp_path/'existing.json';output.write_bytes(b'preserve')
    with pytest.raises(SystemExit):main(['absent.csv','--output',str(output)])
    assert output.read_bytes()==b'preserve'
