"""Production Service/Auto retry regression tests: offline, virtual funds only."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from unittest.mock import AsyncMock

import pytest

from app.models import Candle
from app.paper.auto import Auto, Signal, SIGNAL_FAILURE_LIMIT, SIGNAL_RETRY_DELAY_MS
from app.paper.engine import Engine
from app.paper.market import Market
from app.paper.models import PaperError, Settings
from app.paper.service import Service
from app.paper.storage import Store

BASE=1800000000
SOURCE='Binance · Spot'


@pytest.fixture
def replay(tmp_path,monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-offline-owner-only')
    clock=[BASE*1000]
    rows=[Candle(BASE-900,100.,101.,99.,100.,10.)]
    async def fetch(symbol,timeframe):
        return dict(symbol=symbol,timeframe=timeframe,source=SOURCE,stale=False,
                    fetched_at=datetime.fromtimestamp(clock[0]/1000,timezone.utc).isoformat(),
                    last_closed_at=rows[-1].time+900,candles=[asdict(c) for c in rows])
    engine=Engine(Store(tmp_path/'paper.sqlite3'),Settings(),clock=lambda:clock[0])
    reader=AsyncMock()
    async def long(window):
        return Signal(window.symbol,window.timeframe,window.source,window.bars[-1].time,'LONG',Decimal(70))
    reader.read.side_effect=long
    service=Service(Market(fetch,clock=lambda:clock[0]),engine,reader)
    service.auto=Auto(engine)
    return service,clock,rows,reader,long


async def activate(replay):
    service,clock,rows,_,_=replay
    service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
    rows.append(Candle(BASE,100.,101.,99.,100.,10.));clock[0]+=900000


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_temporary_failure_then_success_same_candle_exactly_one_entry(replay,caplog,failure_code):
    service,clock,rows,reader,long=replay
    async def run():
        await activate(replay)
        reader.read.side_effect=PaperError(failure_code)
        await service.auto_tick()
        failed=service.auto.state()
        assert failed['watermarks']['15m']==BASE-900
        assert failed['last_processed_candle']==BASE*1000
        assert failed['status']=='PAUSED' and not failed['manual_resume']
        assert failed['signal_retry']['failures']==1
        assert all(d['candle_time']!=BASE for d in failed['decisions'])
        await service.auto_tick() # cooldown polls neither read nor consume the candle
        assert reader.read.call_count==1 and service.auto.state()['watermarks']['15m']==BASE-900
        clock[0]+=SIGNAL_RETRY_DELAY_MS
        reader.read.side_effect=long
        await service.auto_tick()
        success=service.auto.state()
        assert success['status']=='ON' and success['signal_retry'] is None
        assert success['watermarks']['15m']==BASE and success['last_action']=='OPENED'
        assert sum(d['trade_opened'] for d in success['decisions'])==1
        await service.auto_tick()
        assert reader.read.call_count==2 and len(service.engine.snapshot()['open_positions'])==1
    asyncio.run(run())
    assert 'failures=1/3' in caplog.text and failure_code in caplog.text
    assert 'dummy-offline-owner-only' not in caplog.text


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_repeated_failure_budget_is_persisted_and_finite(replay,failure_code):
    service,clock,_,reader,_=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError(failure_code)
        for failure in range(1,SIGNAL_FAILURE_LIMIT+1):
            await service.auto_tick()
            state=service.auto.state()
            assert state['watermarks']['15m']==BASE-900
            assert state['signal_retry']['failures']==failure
            clock[0]+=failure*SIGNAL_RETRY_DELAY_MS
        assert state['last_rejection_reason']=='SIGNAL_RETRY_EXHAUSTED'
        assert state['status']=='PAUSED' and state['manual_resume']
        for _ in range(10):await service.auto_tick()
        # A later transient market error must not rearm an exhausted retry budget.
        service.auto.fail('MARKET_UNAVAILABLE')
        await service.auto_tick()
        assert service.auto.state()['manual_resume']
        assert reader.read.call_count==SIGNAL_FAILURE_LIMIT
        assert service.auto.state()['watermarks']['15m']==BASE-900
        assert not service.engine.snapshot()['open_positions']
    asyncio.run(run())


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_new_candle_supersedes_pending_one_without_historical_entry(replay,failure_code):
    service,clock,rows,reader,long=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError(failure_code)
        await service.auto_tick()
        rows.append(Candle(BASE+900,100.,101.,99.,100.,10.));clock[0]+=900000
        reader.read.side_effect=long;await service.auto_tick()
        state=service.auto.state()
        pending=next(d for d in state['decisions'] if d['candle_time']==BASE)
        assert pending['rejection_reason']=='MISSED_CANDLE_NO_ENTRY' and not pending['trade_opened']
        assert state['signal_retry'] is None and state['watermarks']['15m']==BASE+900
        assert service.engine.snapshot()['open_positions'][0]['entry_candle']==BASE+900
    asyncio.run(run())


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_pending_retry_missing_history_pauses_no_entry(replay,failure_code):
    service,clock,rows,reader,long=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError(failure_code)
        await service.auto_tick()
        rows[:]=[Candle(BASE+2700,100.,101.,99.,100.,10.)];clock[0]+=2700000
        reader.read.side_effect=long;await service.auto_tick()
        assert service.auto.state()['last_rejection_reason']=='MARKET_GAP'
        assert not service.engine.snapshot()['open_positions']
    asyncio.run(run())


def test_new_candles_do_not_reset_consecutive_failure_budget(replay):
    service,clock,rows,reader,_=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError('SIGNAL_UNAVAILABLE')
        for failure in range(1,4):
            await service.auto_tick()
            assert service.auto.state()['signal_retry']['failures']==failure
            rows.append(Candle(rows[-1].time+900,100.,101.,99.,100.,10.));clock[0]+=900000
        await service.auto_tick()
        assert reader.read.call_count==3
        assert service.auto.state()['manual_resume']
        assert service.auto.state()['watermarks']['15m']==BASE-900
    asyncio.run(run())


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_pending_retry_restart_requires_resume_without_resetting_budget(replay,failure_code):
    service,clock,_,reader,long=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError(failure_code)
        await service.auto_tick()
        recovered=Engine(Store(service.engine.store.path),clock=lambda:clock[0])
        service.engine=recovered;service.auto=Auto(recovered)
        state=service.auto.state()
        assert state['status']=='PAUSED' and state['manual_resume']
        assert state['signal_retry']['failures']==1 and state['watermarks']['15m']==BASE-900
        clock[0]+=SIGNAL_RETRY_DELAY_MS;reader.read.side_effect=long
        await service.auto_tick()
        assert reader.read.call_count==1 and service.auto.state()['watermarks']['15m']==BASE-900
        assert not service.engine.snapshot()['open_positions']
        # Explicit resume preserves the existing latest-candle baseline policy.
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        await service.auto_tick()
        assert reader.read.call_count==1 and service.auto.state()['signal_retry'] is None
    asyncio.run(run())


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_stale_retry_does_not_read_or_consume_pending_candle(replay,failure_code):
    service,clock,_,reader,long=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError(failure_code)
        await service.auto_tick();clock[0]+=1800001
        reader.read.side_effect=long;await service.auto_tick()
        assert reader.read.call_count==1
        assert service.auto.state()['watermarks']['15m']==BASE-900
        assert not service.engine.snapshot()['open_positions']
    asyncio.run(run())


def test_rest_rollback_cannot_execute_older_than_pending_signal(replay):
    service,clock,rows,reader,long=replay
    async def run():
        await activate(replay)
        rows.append(Candle(BASE+900,100.,101.,99.,100.,10.));clock[0]+=900000
        reader.read.side_effect=PaperError('SIGNAL_UNAVAILABLE');await service.auto_tick()
        rows.pop();clock[0]+=SIGNAL_RETRY_DELAY_MS;reader.read.side_effect=long
        await service.auto_tick()
        assert reader.read.call_count==1 and not service.engine.snapshot()['open_positions']
        assert service.auto.state()['watermarks']['15m']==BASE-900
        assert service.auto.state()['signal_retry']['candle_time']==BASE+900
        assert service.auto.state()['status']=='PAUSED'
    asyncio.run(run())


def test_stop_while_retry_pending_prevents_entry(replay):
    service,clock,_,reader,long=replay
    async def run():
        await activate(replay);reader.read.side_effect=PaperError('SIGNAL_UNAVAILABLE')
        await service.auto_tick();service.auto.configure(False)
        clock[0]+=SIGNAL_RETRY_DELAY_MS;reader.read.side_effect=long
        await service.auto_tick()
        assert reader.read.call_count==1 and service.auto.state()['status']=='OFF'
        assert not service.engine.snapshot()['open_positions']
    asyncio.run(run())


def test_late_failure_after_success_does_not_pause_or_retry(replay):
    service,_,_,_,_=replay
    async def run():
        await activate(replay);window=await service.market.window('BTCUSDT','15m')
        generation=service.auto.state()['generation']
        await service.auto_tick()
        service.auto.fail('SIGNAL_UNAVAILABLE',window,generation)
        assert service.auto.state()['status']=='ON' and service.auto.state()['signal_retry'] is None
        assert len(service.engine.snapshot()['open_positions'])==1
    asyncio.run(run())


def test_legacy_journal_migrates_and_corrupt_retry_fails_closed(replay):
    service,_,_,_,_=replay
    store=service.engine.store
    with store.transaction() as db:
        state=json.loads(store.get(db,'auto_paper'));state.pop('signal_retry')
        store.set(db,'auto_paper',json.dumps(state))
    assert Auto(service.engine).state()['status']=='OFF'
    with store.transaction() as db:
        state['signal_retry']={'failures':True}
        store.set(db,'auto_paper',json.dumps(state))
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Auto(service.engine)


@pytest.mark.parametrize('failure_code',['SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'])
def test_slow_failure_still_counts_towards_bounded_retry(replay,failure_code):
    service,clock,_,reader,_=replay
    async def slow(window):
        clock[0]+=31000 # snapshot delivery expires while the read is in flight
        raise PaperError(failure_code)
    async def run():
        await activate(replay);reader.read.side_effect=slow
        for n in range(1,4):
            await service.auto_tick()
            state=service.auto.state()
            assert state['signal_retry']['failures']==n
            assert state['watermarks']['15m']==BASE-900
            clock[0]+=15000*n
        await service.auto_tick()
        assert reader.read.call_count==3 and state['manual_resume']
        assert not service.engine.snapshot()['open_positions']
    asyncio.run(run())


def test_alternating_snapshot_and_signal_errors_share_one_budget(replay):
    service,clock,_,reader,_=replay
    async def run():
        await activate(replay)
        for n,code in enumerate(('SNAPSHOT_MISMATCH','SIGNAL_UNAVAILABLE','SNAPSHOT_MISMATCH'),1):
            reader.read.side_effect=PaperError(code)
            await service.auto_tick()
            assert service.auto.state()['signal_retry']['failures']==n
            clock[0]+=n*15000
        await service.auto_tick()
        assert reader.read.call_count==3
        assert service.auto.state()['last_rejection_reason']=='SIGNAL_RETRY_EXHAUSTED'
        assert service.auto.state()['watermarks']['15m']==BASE-900
    asyncio.run(run())
