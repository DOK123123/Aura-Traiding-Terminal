"""Offline cancellation and owner-confirmation regressions with disposable ledgers."""
import asyncio
from dataclasses import replace
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from app.intelligence.service import Service as ReplayService
from app.paper.auto import Auto, Signal
from app.paper.engine import Engine
from app.paper.models import Bar, Settings, Window
from app.paper.service import Service
from app.paper.storage import Store


def closed_window(clock):
    end = clock[0] // 60000 * 60
    bar = Bar(end - 60, Decimal('100'), Decimal('100'), Decimal('100'), Decimal('100'))
    return Window('BTCUSDT', '1m', 'Binance', clock[0], (bar,))


def command(window):
    return dict(request_id=str(uuid.uuid4()), symbol='BTCUSDT', timeframe='1m',
                direction='LONG', expected_source=window.source, expected_price='100',
                expected_candle_time=window.bars[-1].time, position_size='1',
                stop_loss=None, take_profit=None, entry_reason='Offline safety regression',
                signal_id=None)


class ServiceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'paper.sqlite3'
        self.clock = [1800000060000]
        settings = replace(Settings(), commission_pct=Decimal('0.1'))
        self.engine = Engine(Store(self.path), settings, lambda: self.clock[0])

    def test_cancelled_open_same_id_retry_and_restart_charge_once(self):
        for committed_before_cancel in (False, True):
            with self.subTest(committed_before_cancel=committed_before_cancel):
                path = Path(self.temp.name) / ('committed.sqlite3' if committed_before_cancel else 'pending.sqlite3')
                engine = Engine(Store(path), replace(Settings(), commission_pct=Decimal('0.1')),
                                lambda: self.clock[0])
                window = closed_window(self.clock)
                body = command(window)
                market = AsyncMock()
                market.window.return_value = window
                service = Service(market, engine)
                entered, retry_entered, release, finished = (threading.Event() for _ in range(4))
                original = engine.open
                calls = []
                call_lock = threading.Lock()
                outcomes = []

                def gated_open(payload, quote):
                    with call_lock:
                        calls.append(payload['request_id'])
                        first = len(calls) == 1
                    if not first:
                        retry_entered.set()
                        return original(payload, quote)
                    try:
                        result = original(payload, quote) if committed_before_cancel else None
                        entered.set()
                        if not release.wait(5):
                            raise AssertionError('Test did not release the mutation worker')
                        result = result or original(payload, quote)
                        outcomes.append(result)
                        return result
                    finally:
                        finished.set()

                async def run():
                    with patch.object(engine, 'open', side_effect=gated_open):
                        request = asyncio.create_task(service.open(body))
                        retry = None
                        try:
                            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                            request.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await request
                            retry = asyncio.create_task(service.open(body))
                            if not committed_before_cancel:
                                self.assertTrue(await asyncio.to_thread(retry_entered.wait, 5))
                            result = await asyncio.wait_for(retry, 5)
                            release.set()
                            self.assertTrue(await asyncio.to_thread(finished.wait, 5))
                            return result, await service.state()
                        finally:
                            release.set()
                            if not request.done():
                                request.cancel()
                            if retry is not None and not retry.done():
                                retry.cancel()
                            await asyncio.gather(request, *([retry] if retry is not None else []),
                                                 return_exceptions=True)

                result, state = asyncio.run(run())
                self.assertEqual(outcomes[0]['id'], result['id'])
                self.assertEqual(len(state['open_positions']), 1)
                self.assertEqual(state['closed_trades'], [])
                self.assertEqual(Decimal(state['statistics']['current_balance']), Decimal('9999.9'))
                self.assertEqual(Decimal(result['entry_fee']), Decimal('0.1'))
                if committed_before_cancel:
                    self.assertEqual(market.window.await_count, 1)
                restored = Engine(Store(path), clock=lambda: self.clock[0])
                self.assertEqual(restored.replay(body['request_id'], 'open', body)['id'], result['id'])
                self.assertEqual(len(restored.snapshot()['open_positions']), 1)
                with restored.store.transaction(write=False) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 1)

    def test_off_acknowledgement_rejects_signal_already_in_flight(self):
        market = AsyncMock()
        market.window.side_effect = lambda *_: closed_window(self.clock)
        reader = AsyncMock()
        service = Service(market, self.engine, reader)
        service.auto = Auto(self.engine)
        entered, release = asyncio.Event(), asyncio.Event()

        async def signal(quote):
            entered.set()
            await release.wait()
            return Signal(quote.symbol, quote.timeframe, quote.source,
                          quote.bars[-1].time, 'LONG', Decimal('72'))

        reader.read.side_effect = signal

        async def run():
            body = dict(enabled=True, symbol='BTCUSDT', timeframe='1m',
                        expected_source='Binance', fallback_policy='PAPER_SETTINGS')
            armed = await service.configure_auto(body)
            self.clock[0] += 60000
            tick = asyncio.create_task(service.auto_tick())
            try:
                await asyncio.wait_for(entered.wait(), 5)
                stopped = await service.configure_auto(dict(body, enabled=False))
                self.assertEqual(stopped['status'], 'OFF')
                self.assertGreater(stopped['generation'], armed['generation'])
                release.set()
                await asyncio.wait_for(tick, 5)
                return stopped, await service.state()
            finally:
                release.set()
                if not tick.done():
                    tick.cancel()
                await asyncio.gather(tick, return_exceptions=True)

        with patch.dict('os.environ', {'AURA_TESTNET_VIEW_PASSWORD': 'dummy-offline-owner-password'}):
            stopped, state = asyncio.run(run())
        self.assertEqual(state['auto_paper']['status'], 'OFF')
        self.assertEqual(state['auto_paper']['generation'], stopped['generation'])
        self.assertEqual(state['open_positions'], [])
        self.assertEqual(state['closed_trades'], [])
        self.assertFalse(any(row['trade_opened'] for row in state['auto_paper']['decisions']))
        restored = Engine(Store(self.path), clock=lambda: self.clock[0])
        self.assertEqual(Auto(restored).state()['status'], 'OFF')
        self.assertEqual(restored.snapshot()['open_positions'], [])

    def test_unconfirmed_replay_preserves_old_history_and_separate_paper_ledger(self):
        paper_window = closed_window(self.clock)
        trade = self.engine.open(command(paper_window), paper_window)
        paper_before = self.engine.snapshot()
        paper_hash = hashlib.sha256(self.path.read_bytes()).digest()
        replay = ReplayService(Path(self.temp.name) / 'replay.sqlite3', clock=lambda: 1000.)
        old = replay.create('15m', 1672531200, True)['session_id']
        proposal = replay.proposal(old, True)['proposal']['id']
        replay.decide(old, proposal, True)
        history = None
        for _ in range(12):
            history = replay.advance(old, 32)
            if history['portfolio']['trades']:
                break
        self.assertEqual(len(history['portfolio']['trades']), 1)
        history = replay.state(old)

        unconfirmed = replay.create('15m', 1672531200, True)['session_id']
        replay.proposal(unconfirmed, True)
        view = replay.advance(unconfirmed, 32)
        self.assertEqual(view['proposal']['status'], 'EXPIRED')
        self.assertEqual(view['portfolio']['trades'], [])
        self.assertIsNone(view['portfolio']['open_position'])
        self.assertEqual(Decimal(view['portfolio']['metrics']['net_profit']), 0)
        self.assertEqual(replay.state(old), history)
        with replay.db() as db:
            self.assertEqual(replay.load(db, unconfirmed)['confirmed'], [])
        self.assertEqual(self.engine.snapshot(), paper_before)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), paper_hash)
        self.assertEqual(self.engine.trade(trade['id'])['status'], 'OPEN')
        restored = ReplayService(replay.path, clock=lambda: 1000.)
        self.assertEqual(restored.state(old), history)
        self.assertEqual(restored.state(unconfirmed)['portfolio']['trades'], [])


if __name__ == '__main__':
    unittest.main()
