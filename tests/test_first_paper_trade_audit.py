"""Offline causal signal-path regression; not a production signal or live proof."""
import asyncio
from unittest.mock import patch

from app.automated.service import Service
from app.automated.storage import SQLiteStore
from app.lab.models import digest
from tests.test_auto42 import Market, bar, fixture, DUMMY_TOKEN, DUMMY_OWNER


def test_alignment_rejection_persists_without_entry_then_accepted_signal_reaches_engine(tmp_path):
    async def run():
        bars, snapshot, now = fixture()
        market = Market(bars, snapshot)
        store = SQLiteStore(tmp_path / 'auto-paper-42.sqlite3', clock=lambda: now[0])
        service = Service(market, store, clock=lambda: now[0])

        def next_closed_bar(aligned):
            bars.append(bar(bars[-1].time + 900))
            now[0] += 900
            at = bars[-1].time + 900
            value = market.value
            value['last_closed_at'] = value['state']['timestamp'] = at
            value['history']['source_sha256'] = digest([b.data() for b in bars])
            mtf = value['state']['mtf']
            mtf['alignment'] = aligned
            mtf['h4']['direction'] = 1 if aligned else -1
            for key, step in (('h1', 3600), ('h4', 14400)):
                mtf[key]['closed_at'] = at // step * step
            value['structure_events'] = [
                dict(type='structure_event', value='BOS', confirmed_at=at - 900),
                dict(type='breakout', value='LONG', confirmed_at=at - 900),
            ]

        try:
            with patch.dict('os.environ', AURA_AUTO42_SCHEDULER_SECRET=DUMMY_TOKEN,
                            AURA_TESTNET_VIEW_PASSWORD=DUMMY_OWNER):
                await service.control('START', 'a' * 32)
            next_closed_bar(False)
            rejected = await service.tick()
            state = (await store.load())['state']
            assert rejected['decision'] == 'MTF_NOT_ALIGNED'
            assert rejected['state_saved'] and rejected['opened_positions'] == 0
            assert state['position'] is None and state['pending'] is None
            assert state['balance'] == '10000' and state['fees'] == '0'
            evidence = state['last_alignment_evaluation']
            assert evidence['strategy_reason'] == 'MTF_NOT_ALIGNED'
            assert evidence['actual_condition'] is False
            decisions = [e for e in await store.history() if e['kind'] == 'DECISION']
            assert decisions[-1]['payload']['signal']['reason'] == 'MTF_NOT_ALIGNED'

            next_closed_bar(True)
            queued = await service.tick()
            assert queued['decision'] == 'SIGNAL_QUEUED_NEXT_OPEN'
            assert queued['opened_positions'] == 0
            assert (await store.load())['state']['pending'] is not None
            next_closed_bar(True)
            opened = await service.tick()
            assert opened['opened_positions'] == 1
            assert (await store.load())['state']['position']['direction'] == 'LONG'
            duplicate = await service.tick()
            assert duplicate['duplicate'] and duplicate['opened_positions'] == 0
            assert sum(e['kind'] == 'OPEN' for e in await store.history()) == 1
        finally:
            await service.close()

    asyncio.run(run())
