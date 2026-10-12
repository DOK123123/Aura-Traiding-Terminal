"""Offline diagnostic/control-flow evidence, not real-market performance results."""
import asyncio
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.models import Candle
from app.paper.auto import Auto, Signal
from app.paper.engine import Engine
from app.paper.market import Market
from app.paper.models import PaperError, Settings
from app.paper.service import Service
from app.paper.storage import Store
from scripts import diagnose_aura_auto as diagnostic


START, END = diagnostic.period('2026-10-12')


def candles(warmup=500, extra=0):
    # Deliberately synthetic, only for offline integrity/control-flow tests.
    return [Candle(t,100.,101.,99.,100.,10.) for t in range(START-warmup*900, END+extra*900, 900)]


def snapshot(tmp_path, rows):
    path=tmp_path/'snapshot.json'
    path.write_text(json.dumps(dict(symbol='BTCUSDT',timeframe='15m',source=diagnostic.SOURCE,
                                    candles=[asdict(c) for c in rows])))
    return path


def test_exact_calendar_warmup_and_forming_exclusion(tmp_path):
    data, digest, excluded=diagnostic.load_snapshot(snapshot(tmp_path,candles(extra=1)),START,END,500)
    assert END-START==30*86400 and len(data)==500+2880
    assert data[-1].time+900==END and excluded==1 and len(digest)==64


@pytest.mark.parametrize('defect',['duplicate','gap','order','warmup','range'])
def test_incomplete_or_unordered_snapshot_is_not_performance(tmp_path,defect):
    rows=candles()
    if defect=='duplicate':rows.insert(510,rows[510])
    if defect=='gap':rows.pop(510)
    if defect=='order':rows[510],rows[511]=rows[511],rows[510]
    if defect=='warmup':rows.pop(0)
    if defect=='range':rows.pop()
    with pytest.raises(ValueError):diagnostic.load_snapshot(snapshot(tmp_path,rows),START,END,500)


def test_no_history_is_unknown_not_zero_profit(tmp_path):
    output=tmp_path/'unavailable.json'
    assert diagnostic.main(['--end-date','2026-10-12','--output',str(output)])==2
    data=json.loads(output.read_text())
    assert data['status']=='NO_HISTORY' and data['expected_candles']==2880
    assert data['signals'] is None and data['net_realized_pnl'] is None
    assert data['settings']['commission_pct']=='0.10'
    assert data['settings']['risk_per_trade_pct']=='1'
    assert data['settings']['maximum_position_size_usdt']=='2000'
    assert data['settings']['maximum_simultaneous_positions']==1


def test_output_cannot_overwrite_live_journal(tmp_path):
    output=tmp_path/'paper.sqlite3';output.write_bytes(b'original')
    with pytest.raises(SystemExit):diagnostic.main(['--output',str(output)])
    assert output.read_bytes()==b'original'


def live_fixture(tmp_path,monkeypatch):
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-offline-owner-only')
    clock=[START*1000]
    rows=[Candle(START-900,100.,101.,99.,100.,10.)]
    async def fetch(symbol,timeframe):
        return dict(symbol=symbol,timeframe=timeframe,source=diagnostic.SOURCE,stale=False,
                    fetched_at=diagnostic.utc(clock[0]/1000),last_closed_at=rows[-1].time+900,
                    candles=[asdict(c) for c in rows])
    market=Market(fetch,clock=lambda:clock[0])
    engine=Engine(Store(tmp_path/'isolated.sqlite3'),Settings(),clock=lambda:clock[0])
    auto=Auto(engine)
    async def read(window):
        return Signal('BTCUSDT','15m',diagnostic.SOURCE,window.bars[-1].time,'LONG',Decimal(70))
    reader=AsyncMock();reader.read.side_effect=read
    service=Service(market,engine,reader);service.auto=auto
    return service,clock,rows,reader


def test_actual_service_after_baseline_new_candle_and_duplicate(tmp_path,monkeypatch):
    service,clock,rows,reader=live_fixture(tmp_path,monkeypatch)
    async def run():
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        await service.auto_tick()
        reader.read.assert_not_called()
        assert service.auto.state()['last_rejection_reason']=='ACTIVATION_BASELINE'
        rows.append(Candle(START,100.,101.,99.,100.,10.));clock[0]+=900000
        await service.auto_tick()
        assert service.auto.state()['last_processed_candle']==clock[0]
        assert service.auto.state()['last_action']=='OPENED'
        assert len(service.engine.snapshot()['open_positions'])==1
        await service.auto_tick()
        assert reader.read.call_count==1
        assert len(service.engine.snapshot()['open_positions'])==1
    asyncio.run(run())


def test_actual_service_missing_ticks_do_not_replay_intermediate_signals(tmp_path,monkeypatch):
    service,clock,rows,reader=live_fixture(tmp_path,monkeypatch)
    async def run():
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        rows.extend(Candle(START+i*900,100.,101.,99.,100.,10.) for i in range(3));clock[0]+=2700000
        await service.auto_tick()
        audit=service.auto.state()['decisions']
        assert sum(d['rejection_reason']=='MISSED_CANDLE_NO_ENTRY' for d in audit)==2
        assert reader.read.call_count==1
        assert service.auto.state()['last_action']=='OPENED'
    asyncio.run(run())


def test_signal_unavailable_retains_watermark_and_backs_off(tmp_path,monkeypatch):
    service,clock,rows,reader=live_fixture(tmp_path,monkeypatch)
    async def run():
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        rows.append(Candle(START,100.,101.,99.,100.,10.));clock[0]+=900000
        reader.read.side_effect=PaperError('SIGNAL_UNAVAILABLE')
        await service.auto_tick()
        state=service.auto.state()
        assert state['status']=='PAUSED' and state['last_rejection_reason']=='SIGNAL_UNAVAILABLE'
        assert state['watermarks']['15m']==START-900
        await service.auto_tick()
        assert reader.read.call_count==1 and not service.engine.snapshot()['open_positions']
        clock[0]+=15000
        await service.auto_tick()
        assert reader.read.call_count==2 and service.auto.state()['watermarks']['15m']==START-900
    asyncio.run(run())


def test_replay_invokes_actual_signal_reader_and_isolated_production_engine(tmp_path):
    # Real unchanged pattern formula over synthetic flat OHLCV, NOT a BTC performance run.
    rows=[Candle(t,100.,101.,99.,100.,10.) for t in range(START-500*900,START+900,900)]
    result=asyncio.run(diagnostic.replay(rows,START,START+900))
    assert result['status']=='COMPLETE' and result['observed_candles']==1
    assert result['entries']==0 and result['closed_trades']==0
    assert result['decisions'][0]['rejection_reason']=='NO_SIGNAL'
    assert result['net_realized_pnl']=='0'
    assert result['activation_baseline_utc']==diagnostic.utc(START-900)
    assert not (tmp_path/'paper.sqlite3').exists()


def test_diagnostic_has_no_private_clients_or_settings_mutations():
    import ast
    source=Path(diagnostic.__file__).read_text()
    tree=ast.parse(source)
    modules=[node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert not any(x.startswith(('app.lab','app.bybit_demo','app.testnet','app.main')) for x in modules)
    assert not any(isinstance(n,ast.Attribute) and n.attr in ('post','put','patch','delete') for n in ast.walk(tree))
    assert 'PAPER_DB_PATH' not in source
    assert 'os.environ' not in source


@pytest.mark.parametrize('direction,exit_price',[('LONG',104.),('SHORT',96.)])
def test_diagnostic_real_paper_fees_and_trade_counts(monkeypatch,direction,exit_price):
    rows=[Candle(t,100.,101.,99.,100.,10.) for t in range(START-500*900,START+900,900)]
    rows.append(Candle(START+900,exit_price,exit_price+0.1,exit_price-0.1,exit_price,10.))
    async def controlled_read(self,window):
        # Synthetic trigger tests execution/accounting only; never historical evidence.
        side=direction if window.bars[-1].time==START else 'WAIT'
        return Signal('BTCUSDT','15m',diagnostic.SOURCE,window.bars[-1].time,side,Decimal(70))
    monkeypatch.setattr(diagnostic.SignalReader,'read',controlled_read)
    result=asyncio.run(diagnostic.replay(rows,START,START+1800))
    assert result['entries']==1 and result['closed_trades']==1
    assert result['signals'][direction]==1 and result['signals']['WAIT']==1
    assert result['trades'][0]['entry_fee']=='2.00000000'
    expected='75.92000000' if direction=='LONG' else '76.08000000'
    assert result['net_realized_pnl']==expected
    assert len(result['first_five_signals'])==1
    assert result['first_five_signals'][0]['signal_close_utc']==diagnostic.utc(START+900)


def test_restart_does_not_resume_or_reexecute_baseline(tmp_path,monkeypatch):
    service,clock,rows,reader=live_fixture(tmp_path,monkeypatch)
    async def run():
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        service.auto=Auto(service.engine)
        assert service.auto.state()['status']=='PAUSED' and service.auto.state()['manual_resume']
        rows.append(Candle(START,100.,101.,99.,100.,10.));clock[0]+=900000
        await service.auto_tick()
        reader.read.assert_not_called()
        assert not service.engine.snapshot()['open_positions']
    asyncio.run(run())


@pytest.mark.parametrize('case,expected',[('strong','LONG'),('wilson','WAIT'),
    ('confidence','WAIT'),('half_consistency','LONG'),('opposite_mtf','LONG')])
def test_production_confirmation_gates_are_not_risk_or_integration_errors(case,expected):
    """Controlled evidence only; no BTC performance claims or parameter changes."""
    from app.patterns.config import PatternConfig
    from app.patterns.signals import decide
    config=PatternConfig()
    n,successes=(20,16) if case=='confidence' else (40,24 if case=='wilson' else 36)
    stats={str(h):dict(up=successes,down=n-successes,flat=0,up_pct=100*successes/n,
                      down_pct=100*(n-successes)/n,average_move_pct=.5,median_move_pct=.4)
           for h in config.horizons}
    if case=='half_consistency':
        for h in ('5','10'):stats[h].update(average_move_pct=-.5,median_move_pct=-.4)
    facts=dict(ema20=101.,ema50=100.,rsi_change=1.,volatility_ratio=1.,
               distance_high_atr=2.,distance_low_atr=2.,volume_available=True)
    mtf=[dict(timeframe='1h',trend='Bearish',bars=50)] if case=='opposite_mtf' else []
    result=decide(stats,[dict(similarity=95.) for _ in range(n)],facts,mtf,config)
    assert result['signal']==expected
    if case=='wilson':
        assert result['directional_rate_pct']==60 and result['confidence']>=40
        assert result['wilson_lower_pct']<=50
    if case=='confidence':
        assert result['historical_matches']==20 and result['wilson_lower_pct']>50
        assert result['confidence']<40
    if case=='half_consistency':assert result['confidence_components']['consistency']==.5
    if case=='opposite_mtf':assert result['confidence_components']['mtf']==0


def test_cached_archive_missing_new_close_is_snapshot_mismatch_not_no_signal(tmp_path,monkeypatch):
    """Reproduce the public-history cache race; document, do not alter runtime."""
    from types import SimpleNamespace
    from app.paper.signals import SignalReader
    service,clock,rows,_=live_fixture(tmp_path,monkeypatch)
    cached=[Candle(t,100.,101.,99.,100.,10.) for t in range(START-500*900,START,900)]
    history=AsyncMock(return_value=SimpleNamespace(source=diagnostic.SOURCE,candles=cached))
    service.signals=SignalReader(history)
    async def run():
        service.auto.configure(True,await service.market.window('BTCUSDT','15m'),fallback_policy='PAPER_SETTINGS')
        rows.append(Candle(START,100.,101.,99.,100.,10.));clock[0]+=900000
        await service.auto_tick()
        state=service.auto.state()
        assert state['last_rejection_reason']=='SNAPSHOT_MISMATCH'
        assert state['last_signal'] is None and state['watermarks']['15m']==START
        assert not service.engine.snapshot()['open_positions']
        await service.auto_tick()
        assert history.call_count==1 # Current generic failure path consumes this candle.
    asyncio.run(run())
