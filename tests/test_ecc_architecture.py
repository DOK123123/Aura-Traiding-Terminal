"""Provenance closure and real worker capacity survive source changes/cancellation."""
import asyncio
from decimal import Decimal
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.async_workers import run_in_slot
from app.intelligence.service import Service, IntelligenceError
from app.lab.models import digest
from app.models import Candle
from app.paper.signals import SignalReader
from app.patterns import api
from research.market_intelligence.pipeline import protocol as intelligence_protocol
from scripts.pattern_research import protocol as pattern_protocol
from scripts.run_pattern_research import compatible_protocol

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('dependency', ['series.py', 'local_csv.py'])
def test_changed_series_or_csv_dependency_invalidates_research_protocols(dependency):
    original = Path.read_bytes
    pattern_before = pattern_protocol()
    intelligence_before = intelligence_protocol(ROOT)

    def changed(path):
        raw = original(path)
        return raw + b'\n# altered dependency\n' if path == ROOT/'app/lab'/dependency else raw

    with patch.object(Path, 'read_bytes', changed):
        pattern_after = pattern_protocol()
        intelligence_after = intelligence_protocol(ROOT)
        assert pattern_before['source_hash'] != pattern_after['source_hash']
        assert not compatible_protocol(pattern_before, pattern_after)
        assert digest(intelligence_before) != digest(intelligence_after)
        assert intelligence_before['software'][f'app/lab/{dependency}'] != intelligence_after['software'][f'app/lab/{dependency}']


@pytest.mark.parametrize('dependency', ['models.py', 'indicators.py', 'strategies.py'])
def test_changed_replay_dependency_rejects_existing_session_without_reset(tmp_path, dependency):
    path = tmp_path/'replay.sqlite3'
    before = Service(path)
    session = before.create('15m', 1672531200, True)
    ident = session['session_id']
    with before.db() as db:
        payload = db.execute('SELECT payload FROM sessions WHERE id=?', (ident,)).fetchone()[0]
    assert Service(path).state(ident) == session
    original = Path.read_bytes

    def changed(file):
        raw = original(file)
        return raw + b'\n# altered dependency\n' if file == ROOT/'app/lab'/dependency else raw

    with patch.object(Path, 'read_bytes', changed):
        after = Service(path)
    assert before.software_sha != after.software_sha
    with pytest.raises(IntelligenceError, match='SOFTWARE_CHANGED'):
        after.state(ident)
    with after.db() as db:
        assert db.execute('SELECT payload FROM sessions WHERE id=?', (ident,)).fetchone()[0] == payload


@pytest.mark.parametrize('entrypoint', ['analyze', 'backtest', 'paper_signal'])
@pytest.mark.parametrize('canceled_worker_fails', [False, True])
def test_repeated_cancellation_retains_real_worker_slot(entrypoint, canceled_worker_fails, monkeypatch):
    candles = [Candle(1577836800+i*900, 100, 102, 98, 100, 10) for i in range(500)]
    cutoff = candles[-1].time+900
    data = SimpleNamespace(candles=candles, source='Binance · Spot', fetched_at=0,
                           requested=500, note='offline dummy fixture')
    slots = asyncio.Semaphore(1)
    release, started = Event(), Event()
    mutex = Lock()
    counts = {'active': 0, 'peak': 0, 'calls': 0}

    def worker(*args):
        with mutex:
            counts['active'] += 1
            counts['calls'] += 1
            worker_index = counts['calls']
            counts['peak'] = max(counts['peak'], counts['active'])
        started.set()
        try:
            assert release.wait(3), 'offline worker was not released'
            if canceled_worker_fails and worker_index == 1:
                raise ValueError('canceled offline worker failed')
            return dict(status='OK', as_of=cutoff, signal='WAIT', confidence=0,
                        explanation={'risks': []})
        finally:
            with mutex:
                counts['active'] -= 1

    if entrypoint == 'paper_signal':
        from app.paper import signals
        monkeypatch.setattr(signals, 'evaluate', worker)
        window = SimpleNamespace(symbol='BTCUSDT', timeframe='15m', source=data.source,
            bars=[SimpleNamespace(time=c.time, **{key: Decimal(str(getattr(c, key)))
                for key in ('open', 'high', 'low', 'close', 'volume')}) for c in candles])
        reader = SignalReader(AsyncMock(return_value=data))
        reader.slots = slots
        call = lambda: reader.read(window)
    else:
        monkeypatch.setattr(api, 'compute_slots', slots)
        monkeypatch.setattr(api.history_service, 'get', AsyncMock(return_value=data))
        monkeypatch.setattr(api, 'evaluate' if entrypoint == 'analyze' else 'replay', worker)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(client=None)))
        body = api.PatternRequest(symbol='BTCUSDT', chart_source=data.source) if entrypoint == 'analyze' else api.BacktestRequest(symbol='BTCUSDT')
        endpoint = api.analyze_patterns if entrypoint == 'analyze' else api.backtest_patterns
        call = lambda: endpoint(body, request)

    async def scenario():
        first = asyncio.create_task(call())
        second = None
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(.005)
            assert started.is_set()
            first.cancel()
            await asyncio.sleep(.01)
            first.cancel()  # A second timeout/disconnect cannot release the slot.
            second = asyncio.create_task(call())
            await asyncio.sleep(.03)
            assert not first.done()
            assert not second.done()
            with mutex:
                assert counts['calls'] == counts['active'] == counts['peak'] == 1
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            result = await second
            if entrypoint == 'paper_signal':
                assert result.direction == 'WAIT'
            else:
                assert result['signal'] == 'WAIT'
            assert counts == {'active': 0, 'peak': 1, 'calls': 2}
        finally:
            release.set()
            if second is not None:
                await asyncio.gather(first, second, return_exceptions=True)
            else:
                await asyncio.gather(first, return_exceptions=True)

    asyncio.run(scenario())


def test_worker_exception_and_queued_cancellation_release_capacity():
    async def scenario():
        slots = asyncio.Semaphore(1)
        calls = []

        def fail():
            raise ValueError('offline worker failure')

        with pytest.raises(ValueError, match='offline worker failure'):
            await run_in_slot(slots, fail)
        async with slots:
            queued = asyncio.create_task(run_in_slot(slots, lambda: calls.append(True)))
            await asyncio.sleep(0)
            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued
        assert not calls
        assert await run_in_slot(slots, lambda: 42) == 42

    asyncio.run(scenario())
