"""Offline synchronization of public history and the verified Paper window."""
import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models import Candle
from app.patterns.history import Archive, Dataset, HistoryService
from app.paper.auto import Auto
from app.paper.engine import Engine
from app.paper.market import Market
from app.paper.models import Settings
from app.paper.service import Service
from app.paper.signals import SignalReader
from app.paper.storage import Store

BASE=1800000000
SOURCE='Binance · Spot'


@pytest.fixture
def history(tmp_path,monkeypatch):
    clock=[(BASE+900)*1000]
    monkeypatch.setattr('app.patterns.history.time.time',lambda:clock[0]/1000)
    old=[Candle(t,100.,101.,99.,100.,10.) for t in range(BASE-500*900,BASE,900)]
    fresh=old+[Candle(BASE,100.,101.,99.,100.,10.)]
    service=HistoryService(Archive(tmp_path/'history.sqlite3'))
    service.cache[('BTCUSDT','15m')]=Dataset(old,SOURCE,clock[0]/1000,10000,'synthetic test only')
    service.binance=AsyncMock(return_value=fresh)
    return service,clock,old,fresh


def test_cached_previous_close_forces_refresh_and_reuses_synchronized_result(history):
    service,_,_,fresh=history
    async def run():
        data=await service.get(None,'BTCUSDT','15m',required_candles=fresh[-500:],required_source=SOURCE)
        assert data.candles==fresh and service.binance.call_count==1
        again=await service.get(None,'BTCUSDT','15m',required_candles=fresh[-500:],required_source=SOURCE)
        assert again is data and service.binance.call_count==1
    asyncio.run(run())


def test_regular_historical_read_retains_existing_cache_semantics(history):
    service,_,old,_=history
    data=asyncio.run(service.get(None,'BTCUSDT','15m'))
    assert data.candles==old and service.binance.call_count==0


@pytest.mark.parametrize('field',['open','high','low','close','volume','source'])
def test_same_timestamp_but_changed_ohlcv_or_source_cannot_reuse_cache(history,field):
    service,clock,old,fresh=history
    wrong=list(fresh)
    if field!='source':wrong[-1]=replace(wrong[-1],**{field:getattr(wrong[-1],field)+(.1 if field!='low' else -.1)})
    service.cache[('BTCUSDT','15m')]=Dataset(wrong,'Other' if field=='source' else SOURCE,clock[0]/1000,10000,'test')
    data=asyncio.run(service.get(None,'BTCUSDT','15m',required_candles=fresh[-500:],required_source=SOURCE))
    assert data.candles==fresh and data.source==SOURCE and service.binance.call_count==1


def test_concurrent_same_window_refreshes_only_once(history):
    service,_,_,fresh=history
    async def run():
        a,b=await asyncio.gather(*(service.get(None,'BTCUSDT','15m',required_candles=fresh[-500:],required_source=SOURCE) for _ in range(2)))
        assert a is b and service.binance.call_count==1
    asyncio.run(run())


def test_later_archive_candles_do_not_invalidate_matching_past_window(history):
    service,clock,_,fresh=history
    service.cache[('BTCUSDT','15m')]=Dataset(fresh,SOURCE,clock[0]/1000,10000,'test')
    required=fresh[-5:-1]
    data=asyncio.run(service.get(None,'BTCUSDT','15m',required_candles=required,required_source=SOURCE))
    assert data.candles==fresh and service.binance.call_count==0


def test_refresh_failure_never_returns_old_cache_as_success(history):
    service,_,_,fresh=history
    service.binance.side_effect=TimeoutError()
    with pytest.raises(TimeoutError):
        asyncio.run(service.get(None,'BTCUSDT','15m',required_candles=fresh[-500:],required_source=SOURCE))


@pytest.mark.parametrize('defect',['forming','gap','duplicate','empty'])
def test_invalid_required_window_is_rejected_before_fetch(history,defect):
    service,_,_,fresh=history
    required={'forming':[Candle(BASE+900,100.,101.,99.,100.,10.)],
              'gap':[fresh[-3],fresh[-1]],'duplicate':[fresh[-1],fresh[-1]],'empty':[]}[defect]
    with pytest.raises(ValueError):
        asyncio.run(service.get(None,'BTCUSDT','15m',required_candles=required,required_source=SOURCE))
    assert service.binance.call_count==0


def test_end_to_end_old_rest_then_synced_retry_opens_exactly_once(history,tmp_path,monkeypatch):
    archive,clock,old,fresh=history
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-offline-owner-only')
    archive.binance.side_effect=[old,fresh]
    # Synthetic LONG validates integration/control flow, not actual BTC profitability.
    seen=[]
    def evaluate(candles,step,context,config,target,features,charts):
        seen.append(candles)
        assert candles==fresh and context==500 and config.minimum_confidence==40
        return dict(status='OK',as_of=BASE+900,signal='LONG',confidence=72)
    monkeypatch.setattr('app.paper.signals.evaluate',evaluate)
    async def read(symbol,timeframe,**requirements):
        return await archive.get(None,symbol,timeframe,**requirements)
    rows=list(old)
    async def fetch(symbol,timeframe):
        return dict(symbol=symbol,timeframe=timeframe,source=SOURCE,stale=False,
                    fetched_at=datetime.fromtimestamp(clock[0]/1000,timezone.utc).isoformat(),
                    last_closed_at=rows[-1].time+900,candles=[asdict(c) for c in rows[-500:]])
    engine=Engine(Store(tmp_path/'paper.sqlite3'),Settings(),clock=lambda:clock[0])
    service=Service(Market(fetch,clock=lambda:clock[0]),engine,SignalReader(read,synchronize=True))
    service.auto=Auto(engine)
    async def run():
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        rows.append(fresh[-1])
        await service.auto_tick()
        state=service.auto.state()
        assert state['last_rejection_reason']=='SNAPSHOT_MISMATCH'
        assert state['watermarks']['15m']==BASE-900 and state['signal_retry']['failures']==1
        assert not seen and not engine.snapshot()['open_positions']
        await service.auto_tick()
        assert archive.binance.call_count==1
        clock[0]+=15000;await service.auto_tick()
        assert archive.binance.call_count==2 and len(seen)==1
        assert service.auto.state()['signal_retry'] is None
        assert service.auto.state()['watermarks']['15m']==BASE
        assert len(engine.snapshot()['open_positions'])==1
        await service.auto_tick()
        assert archive.binance.call_count==2 and len(engine.snapshot()['open_positions'])==1
    asyncio.run(run())
