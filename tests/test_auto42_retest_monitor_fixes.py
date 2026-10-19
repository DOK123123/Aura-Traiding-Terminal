"""Offline regressions only; no production signals, storage or exchange calls."""
import asyncio
from bisect import bisect_left
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import gzip
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.automated.strategy import strategy
from app.automated.live_monitor import monitor_view, SCHEMA
from app.automated.engine import initial
from app.intelligence.market_context import analyze_window
from app.lab.local_csv import load_binance_csv
from app.lab.models import digest, LabError
from research.market_intelligence.structure import segment_states
from tests.test_auto42 import fixture, Market, bar, DUMMY_TOKEN, DUMMY_OWNER
from tests.test_market_intelligence import pivots


def mirrored(bars):
    return [replace(b, open=D(200)-b.open, close=D(200)-b.close,
                    high=D(200)-b.low, low=D(200)-b.high) for b in bars]


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
@pytest.mark.parametrize('retest_index', [271, 272])
def test_continuation_breakout_cannot_replace_waiting_setup_or_restart_eight_bar_expiry(side, retest_index):
    bars = pivots()
    bars[263] = replace(bars[263], open=D(112), high=D(114), low=D(111), close=D(113))
    # Pullback without a confirmed retest, then another crossing of the level.
    bars[264] = replace(bars[264], open=D(113), high=D(114), low=D('111.9'), close=D(112))
    bars[265] = replace(bars[265], open=D('113.9'), high=D(115), low=D('113.9'), close=D(114))
    for i in range(266, 273):
        bars.append(replace(bars[-1], time=bars[-1].time+900, open=D(114),
                            high=D(115), low=D('113.9'), close=D(114)))
    bars[retest_index] = replace(bars[retest_index], open=D(112), low=D(112), close=D(113))
    if side == 'SHORT':
        bars = mirrored(bars)
    rows = segment_states(bars)
    assert rows[263]['breakout'] == side and rows[265]['breakout'] == side
    assert rows[264]['retest'] is None and rows[265]['retest'] is None
    # The original deadline is inclusive at 8 bars, expired at 9; the intervening
    # continuation must not reset it. At most one retest per completed setup.
    assert rows[retest_index]['retest'] == (side if retest_index == 271 else None)
    if retest_index == 271:
        assert rows[271]['retest_origin']['breakout_closed_at'] == bars[263].time+900
        assert rows[272]['retest'] is None
    prefix = segment_states(bars[:retest_index])
    assert prefix == rows[:retest_index]


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_cancelled_setup_allows_new_opposite_setup(side):
    bars = pivots()
    bars[263] = replace(bars[263], open=D(112), high=D(114), low=D(111), close=D(113))
    bars[264] = replace(bars[264], open=D(113), high=D(114), low=D(110), close=D(111))
    bars[265] = replace(bars[265], open=D(100), high=D(101), low=D(94), close=D(95))
    if side == 'SHORT':
        bars = mirrored(bars)
    rows = segment_states(bars)
    opposite = 'SHORT' if side == 'LONG' else 'LONG'
    assert rows[264]['failed_breakout'] == opposite
    assert rows[265]['breakout'] == opposite
    assert rows[265]['breakout_level'] is not None


@pytest.mark.parametrize('at,side,level,origin', [
    (1791517500, 'LONG', '82129.00000000', 1791516600),
    (1791914400, 'SHORT', '83222.28000000', 1791911700),
])
def test_real_btcusdt_closed_15m_retest_keeps_original_level_on_new_breakout(at, side, level, origin):
    bars, _ = load_binance_csv(Path('docs/data/AURA_TIMEFRAME_ALIGNMENT_BTCUSDT_15m.csv'))
    times = [b.time for b in bars]
    window = bars[bisect_left(times, at//14400*14400-4160*900):bisect_left(times, at)]
    value = analyze_window(window, at+30)['15m']
    state = value['state']
    assert state['symbol'] == 'BTCUSDT' and state['timeframe'] == '15m'
    assert state['retest'] == side and state['breakout'] == side
    assert state['breakout_level'] == level
    assert state['retest_origin'] == dict(direction=side, level=level, breakout_closed_at=origin)
    assert origin < at and at-origin <= 8*900
    value['freshness'] = dict(status='FRESH')
    assert strategy(value, window, at+30)['reason'] == 'MTF_NOT_ALIGNED'
    # Appending deliberately changed future prices cannot rewrite prior states.
    native = segment_states(window)
    future = replace(window[-1], time=at, open=D(100000), high=D(110000), low=D(90000), close=D(105000))
    assert segment_states(window+[future])[:-1] == native
    with pytest.raises(LabError):
        analyze_window(window+[future], at+30)  # Forming bar is inadmissible.


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_execution_reject_survives_following_decisions_and_restart(tmp_path, side):
    async def run():
        bars, snapshot, now = fixture(side)
        market = Market(bars, snapshot)
        path = tmp_path/'auto-paper-42.sqlite3'
        store = SQLiteStore(path, clock=lambda:now[0])
        service = Service(market, store, clock=lambda:now[0])

        def next_bar(price='100'):
            bars.append(bar(bars[-1].time+900, open=price, high=str(D(price)+1),
                            low=str(D(price)-1), close=price))
            now[0] += 900
            at = bars[-1].time+900
            value = market.value
            value['last_closed_at'] = value['state']['timestamp'] = at
            value['history']['source_sha256'] = digest([b.data() for b in bars])
            for key, step in (('h1',3600),('h4',14400)):
                value['state']['mtf'][key]['closed_at'] = at//step*step
            value['state']['retest_origin']['breakout_closed_at'] = at-900
            value['structure_events'] = [dict(type='structure_event',value='BOS',confirmed_at=at-900),
                                         dict(type='breakout',value=side,confirmed_at=at-900)]

        try:
            with patch.dict('os.environ',AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN,
                            AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
                await service.control('START','a'*32)
            next_bar()
            await service.tick()
            assert (await store.load())['state']['pending'] is not None
            next_bar('106' if side == 'LONG' else '94')
            market.value['state']['retest'] = None
            await service.tick()
            view = await service.live_monitor()
            assert view['last_decision'] == 'NO_CONFIRMED_SETUP'
            assert view['entry_rejection']['reason'] == 'INVALID_STOPS_AT_NEXT_OPEN'
            original = deepcopy(view['execution_rejection'])
            assert original['details']['stage'] == 'EXECUTION'
            assert view['latest_check']['reason'] == 'NO_CONFIRMED_SETUP'
            assert view['strategy_rejection']['reason'] == 'NO_CONFIRMED_SETUP'
            next_bar()
            market.value['state']['mtf']['alignment'] = False
            market.value['state']['mtf']['h4']['direction'] *= -1
            await service.tick()
            await service.close()
            service = Service(market,SQLiteStore(path,clock=lambda:now[0]),clock=lambda:now[0])
            view = await service.live_monitor()
            assert view['entry_rejection'] == original == view['execution_rejection']
            assert view['latest_check']['reason'] == 'MTF_NOT_ALIGNED'
            assert view['strategy_rejection']['reason'] == 'MTF_NOT_ALIGNED'
            assert view['latest_check']['closed_candle_at'] > original['closed_candle_at']
            assert view['balance'] == '10000' and view['fees'] == '0' and view['position'] is None
            before = await service.store.load()
            assert (await service.tick())['duplicate']
            assert await service.store.load() == before
            assert not any(e['kind'] in ('OPEN','CLOSE') for e in await service.store.history(limit=200))
            assert not view['live_cycle_verified']
            next_bar()
            market.value['state']['mtf']['alignment'] = True
            market.value['state']['mtf']['h4']['direction'] *= -1
            market.value['state']['retest'] = side
            await service.tick()
            view = await service.live_monitor()
            assert view['execution_rejection'] == original
            assert view['latest_check']['reason'] == 'SIGNAL_QUEUED_NEXT_OPEN'
            assert view['strategy_rejection']['reason'] == 'MTF_NOT_ALIGNED'
            assert view['position'] is None and view['fees'] == '0'
        finally:
            await service.close()
    asyncio.run(run())


def test_legacy_monitor_snapshot_is_not_falsely_reclassified_as_execution_failure():
    state = initial(1800000000)
    legacy = dict(reason='LEGACY_STAGE_UNKNOWN',utc_timestamp=1800000000)
    state['live_paper_monitor'] = dict(schema=SCHEMA,last_rejection=legacy)
    view = monitor_view(dict(state=state,revision=1),[],now=1800000000,
                        backend='SQLITE',durable=False)
    assert view['entry_rejection'] == legacy
    assert view['execution_rejection'] is None and view['strategy_rejection'] is None
    assert view['latest_check'] is None and not view['live_cycle_verified']


def test_rebuilt_analogs_preserve_frozen_matching_features_and_outcomes():
    # Fingerprints from main before this fix. Context retest/failed_breakout
    # labels are rebuilt honestly; matching inputs and outcome samples stay fixed.
    pack = json.loads(gzip.decompress(Path('app/intelligence/data/analogs-v4.json.gz').read_bytes()))
    assert len(pack['states']) == 4136
    assert digest(pack['normalizers']) == '478e42ec4c832ea6f98cdb713d8d48bffc3f50550b91d883863ac90730540edf'
    matching = [{k:v for k,v in row.items() if k != 'context'} for row in pack['states']]
    assert digest(matching) == '52aa747f5f8ee9d3d1f8251ab56efa7e26f2986401f1233454df7e61828828b2'
