"""Offline regression: legacy Historical Pattern and Auto42 are separate ledgers.

Synthetic candles exercise ownership, persistence and idempotency only. They are
not production observations or profitability evidence; no network is permitted.
"""
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from app.automated.api import router as auto42_router
from app.automated.service import Service as Auto42Service
from app.automated.storage import SQLiteStore
from app.lab.models import digest
from app.paper.api import router as legacy_router
from app.paper.auto import Auto
from app.paper.engine import Engine
from app.paper.models import Bar as PaperBar, Settings, Window
from app.paper.service import Service as LegacyService
from app.paper.storage import Store
from tests.test_auto42 import DUMMY_OWNER, DUMMY_TOKEN, Market, bar, fixture


class ModeIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.bars, snapshot, self.now = fixture()
        self.market = Market(self.bars, snapshot)
        self.auto42_path = root / 'auto-paper-42.sqlite3'
        self.auto42 = Auto42Service(
            self.market, SQLiteStore(self.auto42_path, clock=lambda: self.now[0]),
            clock=lambda: self.now[0])
        settings = replace(Settings(), risk_per_trade_pct=Decimal('1'),
                           maximum_simultaneous_positions=1)
        self.legacy_engine = Engine(Store(root / 'legacy.sqlite3'), settings,
                                    clock=lambda: self.now[0] * 1000)
        self.legacy_auto = Auto(self.legacy_engine)
        self.legacy = LegacyService(
            SimpleNamespace(window=AsyncMock(side_effect=self.legacy_window)),
            self.legacy_engine)
        self.legacy.auto = self.legacy_auto
        self.app = FastAPI()
        self.app.include_router(legacy_router)
        self.app.include_router(auto42_router)
        self.app.state.paper = self.legacy
        self.app.state.auto42 = self.auto42
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                       base_url='http://test')
        self.environment = patch.dict('os.environ', {
            'AURA_TESTNET_VIEW_PASSWORD': DUMMY_OWNER,
            'AURA_AUTO42_SCHEDULER_SECRET': DUMMY_TOKEN,
            'AURA_AUTO42_SUPABASE_SERVICE_KEY': '',
            'AURA_FORWARD_SCHEDULER_SECRET': '',
        })
        self.environment.start()
        self.owner = ('aura', DUMMY_OWNER)
        self.headers = {'X-Aura-Paper': 'local-only', 'Origin': 'http://test'}
        self.tick_headers = {'X-Aura-Auto42-Token': DUMMY_TOKEN}

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.app.state.auto42.close()
        await self.legacy.close()
        self.environment.stop()
        self.folder.cleanup()

    async def legacy_window(self, symbol, timeframe):
        end = self.now[0] // 900 * 900
        return Window(symbol, timeframe, 'Binance · Spot', self.now[0] * 1000,
                      (PaperBar(end - 900, *[Decimal('100')] * 4),))

    async def status42(self):
        response = await self.client.get('/api/auto42/status', auth=self.owner)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        # All diagnostics in this endpoint must describe this same portfolio.
        self.assertEqual(body['state']['mode'], body['diagnostics']['auto_paper'])
        self.assertTrue(body['paper_only'])
        self.assertFalse(body['exchange_execution'])
        return body

    async def legacy_status(self):
        response = await self.client.get('/api/paper/state?scope=AUTO', auth=self.owner)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def control42(self, action, key):
        revision = (await self.status42())['revision']
        response = await self.client.post('/api/auto42/control', auth=self.owner,
            headers=self.headers, json=dict(action=action, request_id=key * 32,
                confirmation='START PAPER' if action == 'START' else '',
                expected_revision=revision if action == 'START' else None))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def configure_legacy(self, enabled):
        response = await self.client.post('/api/paper/auto', auth=self.owner,
            headers=self.headers, json=dict(enabled=enabled, symbol='BTCUSDT',
                timeframe='15m', expected_source='Binance · Spot',
                fallback_policy='PAPER_SETTINGS'))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def tick(self):
        response = await self.client.post('/api/auto42/tick', headers=self.tick_headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def add_closed_candle(self):
        self.bars.append(bar(self.bars[-1].time + 900))
        self.now[0] += 900
        at = self.bars[-1].time + 900
        value = self.market.value
        value['last_closed_at'] = at
        value['state']['timestamp'] = at
        value['history']['source_sha256'] = digest([b.data() for b in self.bars])
        for name, step in [('h1', 3600), ('h4', 14400)]:
            value['state']['mtf'][name]['closed_at'] = at // step * step
        value['state']['retest_origin']['breakout_closed_at'] = at-900
        value['structure_events'] = [
            dict(type='structure_event', value='BOS', confirmed_at=at - 900),
            dict(type='breakout', value='LONG', confirmed_at=at - 900)]

    async def restart_auto42(self):
        await self.app.state.auto42.close()
        self.app.state.auto42 = Auto42Service(self.market,
            SQLiteStore(self.auto42_path, clock=lambda: self.now[0]),
            clock=lambda: self.now[0])

    async def test_upper_legacy_activation_does_not_activate_or_write_auto42(self):
        before = await self.app.state.auto42.store.load()
        result = await self.configure_legacy(True)
        self.assertEqual(result['status'], 'ON')
        self.assertEqual(result['last_rejection_reason'], 'ACTIVATION_BASELINE')
        self.assertEqual((await self.legacy_status())['auto_paper']['status'], 'ON')
        self.assertEqual((await self.status42())['state']['mode'], 'OFF')
        self.assertEqual(await self.app.state.auto42.store.load(), before)
        self.assertEqual(await self.app.state.auto42.store.history(), [])

    async def test_auto42_on_survives_status_tick_and_restart_without_legacy_writes(self):
        legacy_state = self.legacy_auto.state()
        legacy_ledger = self.legacy_engine.snapshot()
        started = await self.control42('START', 'a')
        self.assertEqual(started['state']['mode'], 'ON')
        self.assertEqual(started['state']['last_decision'], 'ACTIVATION_BASELINE')
        baseline = started['state']['watermark']
        for _ in range(2):
            self.assertEqual((await self.status42())['state']['mode'], 'ON')
        first = await self.tick()
        duplicate = await self.tick()
        self.assertEqual(first['mode'], 'ON')
        self.assertEqual(duplicate['mode'], 'ON')
        self.assertEqual(duplicate['tick_outcome'], 'NO_NEW_WORK')
        await self.restart_auto42()
        restored = await self.status42()
        self.assertEqual(restored['state']['mode'], 'ON')
        self.assertEqual(restored['state']['watermark'], baseline)
        self.assertEqual(restored['state']['balance'], '10000')
        self.assertEqual(self.legacy_auto.state(), legacy_state)
        self.assertEqual(self.legacy_engine.snapshot(), legacy_ledger)
        self.assertEqual(self.market.reads, 2)  # START + first nonduplicate ON tick.

    async def test_owner_stop_and_off_heartbeat_persist_without_rearming_other_engine(self):
        await self.configure_legacy(True)
        await self.control42('START', 'a')
        stopped = await self.control42('STOP', 'b')
        self.assertEqual(stopped['state']['mode'], 'OFF')
        reads = self.market.reads
        baseline = stopped['state']['watermark']
        self.now[0] += 300
        heartbeat = await self.tick()
        self.assertEqual(heartbeat['tick_outcome'], 'HEARTBEAT_OFF')
        self.assertEqual(heartbeat['decision'], 'OWNER_STOP')
        self.assertEqual(heartbeat['opened_positions'], 0)
        self.assertEqual(self.market.reads, reads)
        await self.restart_auto42()
        self.now[0] += 300
        await self.tick()
        restored = await self.status42()
        self.assertEqual(restored['state']['mode'], 'OFF')
        self.assertEqual(restored['state']['watermark'], baseline)
        self.assertEqual(restored['state']['last_decision'], 'OWNER_STOP')
        self.assertFalse(restored['state']['data_recovery_armed'])
        self.assertEqual((await self.legacy_status())['auto_paper']['status'], 'ON')

    async def test_legacy_stop_leaves_auto42_on_and_its_journal_unchanged(self):
        await self.configure_legacy(True)
        await self.control42('START', 'a')
        before = await self.app.state.auto42.store.load()
        events = await self.app.state.auto42.store.history()
        stopped = await self.configure_legacy(False)
        self.assertEqual(stopped['status'], 'OFF')
        self.assertEqual((await self.status42())['state']['mode'], 'ON')
        self.assertEqual(await self.app.state.auto42.store.load(), before)
        self.assertEqual(await self.app.state.auto42.store.history(), events)

    async def test_restart_duplicate_tick_opens_one_auto42_position_only(self):
        before = self.legacy_engine.snapshot()
        await self.control42('START', 'a')
        self.add_closed_candle()
        queued = await self.tick()
        self.assertEqual(queued['decision'], 'SIGNAL_QUEUED_NEXT_OPEN')
        await self.restart_auto42()
        self.add_closed_candle()
        opened = await self.tick()
        repeated = await self.tick()
        self.assertEqual(opened['opened_positions'], 1)
        self.assertEqual(repeated['opened_positions'], 0)
        await self.restart_auto42()
        self.assertEqual((await self.tick())['opened_positions'], 0)
        current = await self.status42()
        self.assertEqual(current['state']['mode'], 'ON')
        self.assertIsNotNone(current['state']['position'])
        events = await self.app.state.auto42.store.history()
        self.assertEqual(sum(e['kind'] == 'OPEN' for e in events), 1)
        self.assertEqual(self.legacy_engine.snapshot(), before)
        self.assertEqual(self.legacy_auto.state()['status'], 'OFF')
