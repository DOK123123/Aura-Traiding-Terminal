"""Auto Paper: offline causal signals, atomic duplicates, recovery and security."""
import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import json
import uuid

import pytest

from app.models import Candle
from app.paper.auto import Auto,Signal,STRATEGY_VERSION,AUDIT_LIMIT
from app.paper.engine import Engine
from app.paper.models import PaperError,Bar,Settings
from app.paper.signals import SignalReader
from app.paper.service import Service
from app.paper.market import Market
from app.paper.storage import Store
from tests.test_paper_engine import ledger,window,payload,manual_close


@pytest.fixture
def auto(ledger):
    engine,clock=ledger
    config=engine.snapshot()['settings'];config.update(risk_per_trade_pct='1',maximum_simultaneous_positions=1)
    engine.configure(config) # Activation now requires explicit safe settings, not silent caps.
    manager=Auto(engine)
    manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    return manager,engine,clock


def next_signal(auto,direction='LONG',**changes):
    manager,engine,clock=auto;clock[0]+=60000
    win=window(clock)
    signal=Signal(win.symbol,win.timeframe,win.source,win.bars[-1].time,direction,D('72'))
    signal=replace(signal,**changes)
    return win,signal,manager.state()['generation']


def run_entry(auto,direction='LONG',**changes):
    win,signal,generation=next_signal(auto,direction,**changes)
    auto[0].process(win,signal,generation)
    return auto[1].snapshot()['open_positions']


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_auto_confirmed_long_short_metadata_risk(side,auto):
    trade=run_entry(auto,side)[0]
    assert trade['direction']==side and trade['execution_mode']=='PAPER' and trade['entry_type']=='AUTO_SIGNAL'
    assert trade['signal_direction']==side and trade['signal_confidence']=='72'
    assert trade['signal_timestamp']==trade['entry_price_time']
    assert trade['strategy_version']==STRATEGY_VERSION and trade['market_data_source']==trade['source']
    assert trade['stop_policy']=='PAPER_SETTINGS' and D(trade['risk_pct'])<=1
    assert D(trade['risk_usdt'])<=100 and D(trade['position_size']).as_tuple().exponent==-12
    assert auto[0].state()['decisions'][0]['trade_opened'] is True


@pytest.mark.parametrize('side,price,reason',[('LONG','125','TAKE_PROFIT'),('LONG','70','STOP_LOSS'),('SHORT','75','TAKE_PROFIT'),('SHORT','130','STOP_LOSS')])
def test_auto_protective_exits(side,price,reason,auto):
    trade=run_entry(auto,side)[0];auto[2][0]+=60000
    auto[1].advance(window(auto[2],price))
    assert auto[1].trade(trade['id'])['exit_reason']==reason


def test_default_off_no_automatic_execution(ledger):
    engine,clock=ledger;manager=Auto(engine)
    assert manager.state()['status']=='OFF'
    win=window(clock);signal=Signal('BTCUSDT','15m','Other',1,'LONG',D(100))
    assert not manager.needs_signal(win)
    with pytest.raises(PaperError,match='AUTOMATIC_EXECUTION_DISABLED'):engine.handle_signal(signal)
    assert not engine.snapshot()['open_positions']


def test_auto_off_logs_without_trade(auto):
    manager,engine,clock=auto;manager.configure(False)
    win,signal,generation=next_signal(auto)
    manager.process(win,signal,generation)
    assert not engine.snapshot()['open_positions']
    assert manager.state()['decisions'][0]['rejection_reason']=='AUTO_OFF'


def test_activation_wait_and_no_signal(auto):
    manager,engine,clock=auto
    assert manager.state()['last_rejection_reason']=='ACTIVATION_BASELINE'
    win,signal,generation=next_signal(auto,'WAIT');manager.process(win,signal,generation)
    assert manager.state()['last_rejection_reason']=='NO_SIGNAL' and not engine.snapshot()['open_positions']


def test_sl_tp_policy_explicit_skip(auto):
    manager,engine,clock=auto
    manager.configure(False);manager.configure(True,window(clock),fallback_policy='SKIP')
    run_entry(auto)
    assert manager.state()['last_rejection_reason']=='STOPS_UNAVAILABLE' and not engine.snapshot()['open_positions']


@pytest.mark.parametrize('changes,code',[({'stop_loss':'101'},'INVALID_SL'),({'take_profit':'99'},'INVALID_TP'),
 ({'stop_loss':'NaN'},'INVALID_SL'),({'take_profit':'0'},'INVALID_TP'),({'source':'Other'},'SOURCE_MISMATCH'),
 ({'timeframe':'5m'},'TIMEFRAME_MISMATCH'),({'symbol':'XAUUSD'},'SOURCE_MISMATCH'),({'candle_time':0},'SNAPSHOT_MISMATCH'),
 ({'confidence':D('NaN')},'SIGNAL_ERROR'),({'direction':'BUY'},'SIGNAL_ERROR')])
def test_auto_rejects_bad_signals(auto,changes,code):
    run_entry(auto,**changes)
    assert not auto[1].snapshot()['open_positions']
    assert auto[0].state()['last_rejection_reason']==code


def test_exact_candle_never_opens_twice_parallel_restart_retention(auto):
    manager,engine,clock=auto;win,signal,generation=next_signal(auto)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:manager.process(win,signal,generation),range(2)))
    assert len(engine.snapshot()['open_positions'])==1
    assert len([r for r in manager.state()['decisions'] if r['trade_opened']])==1
    recovered=Auto(Engine(Store(engine.store.path),clock=lambda:clock[0]))
    assert recovered.state()['status']=='PAUSED' and recovered.state()['manual_resume']
    recovered.configure(True,win,fallback_policy='PAPER_SETTINGS')
    recovered.process(win,signal,recovered.state()['generation'])
    with engine.store.transaction() as db:db.execute('DELETE FROM auto_decisions')
    recovered.process(win,signal,recovered.state()['generation'])
    assert len(engine.snapshot()['open_positions'])==1
    assert recovered.state()['watermarks']['1m']==win.bars[-1].time


def test_duplicate_after_close_does_not_reopen(auto):
    manager,engine,clock=auto;win,signal,generation=next_signal(auto);manager.process(win,signal,generation)
    trade=engine.snapshot()['open_positions'][0]
    manual_close(engine,clock,trade,'101')
    # REST reconnect can send the same decision candle again with a fresh delivery timestamp.
    duplicate=replace(win,observed_at=clock[0])
    manager.process(duplicate,signal,generation)
    assert not engine.snapshot()['open_positions'] and engine.snapshot()['statistics']['total_trades']==1


def test_single_position_limit_including_manual(auto):
    manager,engine,clock=auto
    win=window(clock);engine.open(payload(win),win)
    run_entry(auto)
    assert len(engine.snapshot()['open_positions'])==1
    assert manager.state()['last_rejection_reason']=='POSITION_ALREADY_OPEN'


def test_stale_window_pauses_no_trade(auto):
    manager,engine,clock=auto;win,signal,generation=next_signal(auto);clock[0]+=30001
    manager.process(win,signal,generation)
    assert manager.state()['status']=='PAUSED' and manager.state()['last_rejection_reason']=='STALE_DATA'
    assert not engine.snapshot()['open_positions']


def test_gap_pauses_and_old_missed_candles_never_trade(auto):
    manager,engine,clock=auto;clock[0]+=600000
    win=window(clock);signal=Signal('BTCUSDT','1m',win.source,win.bars[-1].time,'LONG',D(70))
    manager.process(win,signal,manager.state()['generation'])
    assert manager.state()['last_rejection_reason']=='MARKET_GAP' and not engine.snapshot()['open_positions']


def test_contiguous_recovery_logs_old_candles_without_backfill_entries(auto):
    manager,engine,clock=auto;start=clock[0]//1000;clock[0]+=180000
    bars=[Bar(start+i*60,D(100),D(100),D(100),D(100)) for i in range(3)]
    win=window(clock,bars=bars);signal=Signal('BTCUSDT','1m',win.source,bars[-1].time,'LONG',D(70))
    manager.process(win,signal,manager.state()['generation'])
    rows=manager.state()['decisions']
    assert sum(r['trade_opened'] for r in rows)==1
    assert sum(r['rejection_reason']=='MISSED_CANDLE_NO_ENTRY' for r in rows)==2


def test_generation_rejects_signal_arriving_after_off_or_scope_change(auto):
    manager,engine,clock=auto;win,signal,generation=next_signal(auto);manager.configure(False)
    result=manager.process(win,signal,generation)
    assert result['obsolete'] and not engine.snapshot()['open_positions']
    manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    manager.fail('SIGNAL_ERROR',win,generation)
    assert manager.state()['status']=='ON'


def test_error_and_restart_require_explicit_resume(auto):
    manager,engine,clock=auto;manager.fail('SIGNAL_ERROR')
    assert manager.state()['status']=='ERROR' and manager.state()['manual_resume']
    run_entry(auto);assert not engine.snapshot()['open_positions']
    manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    assert run_entry(auto)


def test_transaction_failure_rolls_back_entry_and_watermark(auto):
    manager,engine,clock=auto;win,signal,generation=next_signal(auto)
    original=manager._record
    def fail(*args,**kwargs):raise RuntimeError('dummy-offline-failure')
    manager._record=fail
    with pytest.raises(RuntimeError):manager.process(win,signal,generation)
    assert not engine.snapshot()['open_positions']
    manager._record=original;manager.process(win,signal,generation)
    assert len(engine.snapshot()['open_positions'])==1


def test_auto_fee_and_manual_auto_statistics(auto):
    manager,engine,clock=auto
    config=engine.snapshot()['settings'];config['commission_pct']='0.1';engine.configure(config)
    trade=run_entry(auto)[0]
    manual_close(engine,clock,trade,'110')
    win=window(clock);manual=engine.open(payload(win,size='1'),win);manual_close(engine,clock,manual,'95')
    a,m,all_=[engine.snapshot(mode) for mode in ('AUTO','MANUAL','ALL')]
    assert a['statistics']['total_trades']==1 and m['statistics']['total_trades']==1
    assert D(all_['statistics']['net_pnl'])==D(a['statistics']['net_pnl'])+D(m['statistics']['net_pnl'])
    assert a['closed_trades'][0]['entry_type']=='AUTO_SIGNAL' and m['closed_trades'][0]['entry_type']=='MANUAL'
    assert D(trade['entry_fee'])>0 and D(a['statistics']['profit_factor'] or 0)==0
    assert len(a['equity_curve'])==len(all_['equity_curve'])
    assert D(m['statistics']['maximum_drawdown_usdt'])>0


def test_audit_retention_keeps_permanent_dedup_watermark(auto):
    manager,engine,clock=auto;state=manager.state();win=window(clock)
    with engine.store.transaction() as db:
        for i in range(AUDIT_LIMIT+10):
            manager._record(db,state,win,win.bars[-1].time+i*60,'NO_SIGNAL')
    assert manager.state()['decisions_retained']==AUDIT_LIMIT
    watermark=manager.state()['watermarks']['1m']
    clock[0]+=31*86400000
    with engine.store.transaction() as db:manager._prune(db)
    assert manager.state()['decisions_retained']==0 and manager.state()['watermarks']['1m']==watermark


def test_no_exchange_client_or_write_endpoint_in_auto_package():
    root=Path(__file__).resolve().parents[1]/'app'/'paper'
    for name in ('auto.py','signals.py','engine.py'):
        tree=ast.parse((root/name).read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=node.module or '' if isinstance(node,ast.ImportFrom) else ','.join(a.name for a in node.names)
                assert not any(n in names for n in ('bybit','testnet','httpx','requests','socket'))
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                assert node.func.attr not in ('post','put','patch','delete')


def test_signal_reader_excludes_all_future_candles_and_uses_existing_defaults(monkeypatch):
    clock=[1800000060000];win=window(clock);end=win.bars[-1].time
    candles=[Candle(end-(499-i)*60,100,100,100,100,1) for i in range(500)]
    future=[Candle(end+60*i,1000,1000,1000,1000,1000) for i in range(1,30)]
    history=AsyncMock(return_value=SimpleNamespace(source='Binance',candles=candles+future))
    seen=[]
    def evaluate_stub(rows,step,context,config,target,features,charts):
        seen.append(rows)
        assert len(rows)==500 and rows[-1].time==end and context==500 and target==499
        assert config.model_dump()==__import__('app.patterns.config',fromlist=['PatternConfig']).PatternConfig().model_dump()
        return {'status':'OK','as_of':end+60,'signal':'LONG','confidence':72}
    monkeypatch.setattr('app.paper.signals.evaluate',evaluate_stub)
    first=asyncio.run(SignalReader(history).read(win))
    history.return_value=SimpleNamespace(source='Binance',candles=candles)
    second=asyncio.run(SignalReader(history).read(win))
    assert first==second and seen[0]==seen[1]


@pytest.mark.parametrize('defect,code',[('source','SOURCE_MISMATCH'),('price','SNAPSHOT_MISMATCH'),('time','INVALID_DATA')])
def test_signal_reader_snapshot_mismatch_no_execution(defect,code):
    clock=[1800000060000];win=window(clock);end=win.bars[-1].time
    rows=[Candle(end-(499-i)*60,100,100,100,100,1) for i in range(500)]
    source='Other' if defect=='source' else 'Binance'
    if defect=='price':rows[-1]=Candle(end,101,101,101,101,1)
    if defect=='time':rows[10]=replace(rows[10],time=rows[10].time-60)
    async def run():
        with pytest.raises(PaperError) as error:await SignalReader(AsyncMock(return_value=SimpleNamespace(source=source,candles=rows))).read(win)
        if defect!='time':assert error.value.code==code
    asyncio.run(run())


def test_real_pattern_signal_is_causal_under_future_perturbation():
    from app.patterns.engine import evaluate
    from app.patterns.config import PatternConfig
    end=1800000000
    rows=[Candle(end-(599-i)*60,100+i%20,101+i%20,99+i%20,100+i%20,1) for i in range(600)]
    future=[Candle(end+60*i,50000,60000,1,50000,999999) for i in range(1,20)]
    win=window([1800000060000],bars=[Bar(c.time,D(str(c.open)),D(str(c.high)),D(str(c.low)),D(str(c.close))) for c in rows[-500:]])
    async def run(data):return await SignalReader(AsyncMock(return_value=SimpleNamespace(source='Binance',candles=data))).read(win)
    assert asyncio.run(run(rows))==asyncio.run(run(rows+future))


def test_service_auto_independent_of_private_accounts(auto,monkeypatch):
    manager,engine,clock=auto
    monkeypatch.setenv('AURA_TESTNET_VIEW_PASSWORD','dummy-auto-owner-password')
    market=SimpleNamespace(window=AsyncMock())
    signals=SimpleNamespace(read=AsyncMock())
    service=Service(market,engine,signals);service.auto=manager
    win,signal,_=next_signal(auto);market.window.return_value=win;signals.read.return_value=signal
    asyncio.run(service.auto_tick())
    assert len(engine.snapshot()['open_positions'])==1
    assert not hasattr(service,'bybit') and not hasattr(service,'testnet')
    asyncio.run(service.auto_tick());assert signals.read.call_count==1


def test_off_and_owner_removed_never_call_signal_reader(auto,monkeypatch):
    manager,engine,clock=auto;manager.configure(False)
    market=SimpleNamespace(window=AsyncMock(return_value=window(clock)))
    reader=SimpleNamespace(read=AsyncMock())
    service=Service(market,engine,reader);service.auto=manager
    asyncio.run(service.auto_tick());reader.read.assert_not_called()
    manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    monkeypatch.delenv('AURA_TESTNET_VIEW_PASSWORD',raising=False)
    asyncio.run(service.auto_tick())
    assert manager.state()['last_rejection_reason']=='OWNER_NOT_CONFIGURED'


def test_auto_actual_risk_rejection_logged_and_not_charged(auto):
    manager,engine,clock=auto
    config=engine.snapshot()['settings'];config['risk_per_trade_pct']='0.000000000001';engine.configure(config)
    run_entry(auto)
    assert not engine.snapshot()['open_positions']
    assert manager.state()['last_rejection_reason']=='INSUFFICIENT_BALANCE'
    assert D(engine.snapshot()['statistics']['current_balance'])==10000


def test_auto_default_conservative_new_account(tmp_path):
    e=Engine(Store(tmp_path/'default.sqlite3'))
    assert e.snapshot()['settings']['risk_per_trade_pct']=='1'
    assert e.snapshot()['settings']['maximum_simultaneous_positions']==1
    assert D(e.snapshot()['settings']['starting_balance'])==10000


def test_legacy_manual_curve_migration_preserves_history(ledger):
    engine,clock=ledger;win=window(clock);t=engine.open(payload(win),win);manual_close(engine,clock,t,'110')
    before=engine.snapshot()['statistics']
    with engine.store.transaction() as db:db.execute('DELETE FROM curve_slices')
    recovered=Engine(Store(engine.store.path),clock=lambda:clock[0])
    assert recovered.snapshot()['statistics']==before
    assert recovered.snapshot('MANUAL')['statistics']==before
    assert D(recovered.snapshot('AUTO')['statistics']['net_pnl'])==0


def test_auto_backup_restores_trades_watermarks_and_stays_paused(auto,tmp_path):
    manager,engine,clock=auto;run_entry(auto)
    file=tmp_path/'auto-backup.sqlite3';file.write_bytes(engine.store.backup())
    restored=Engine(Store(file),clock=lambda:clock[0]);state=Auto(restored).state()
    assert state['status']=='PAUSED' and state['watermarks']==manager.state()['watermarks']
    assert restored.snapshot('AUTO')['open_positions']==engine.snapshot('AUTO')['open_positions']


def test_manual_entry_cannot_exceed_global_one_position_while_auto_armed(auto):
    manager,engine,clock=auto;run_entry(auto)
    win=window(clock)
    with pytest.raises(PaperError,match='POSITION_LIMIT'):engine.open(payload(win),win)
    assert len(engine.snapshot()['open_positions'])==1


def test_auto_live_balance_exhaustion_rejects_without_fake_funding(auto):
    manager,engine,clock=auto;config=engine.snapshot()['settings'];config['starting_balance']='0.01';engine.configure(config)
    config=engine.snapshot()['settings'];config['commission_pct']='10';engine.configure(config)
    run_entry(auto)
    # Default stop/target economics cannot pay 10% per-side fees, even with tiny sizing.
    assert not engine.snapshot()['open_positions']
    assert manager.state()['last_rejection_reason']=='INVALID_STOPS'
    assert D(engine.snapshot()['statistics']['current_balance'])==D('0.01')


def test_corrupt_auto_configuration_never_arms_by_environment(ledger):
    engine,clock=ledger;manager=Auto(engine)
    with engine.store.transaction() as db:
        state=manager._state(db);state.update(status='ON',enabled=True,configured=False)
        manager._save(db,state)
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Auto(engine)


def test_real_signal_lookahead_does_not_read_current_unclosed_bar():
    clock=[1800000060000];win=window(clock);end=win.bars[-1].time
    rows=[Candle(end-(499-i)*60,100,100,100,100,1) for i in range(500)]
    forming=Candle(end+60,99999,99999,99999,99999,99999)
    history=AsyncMock(return_value=SimpleNamespace(source='Binance',candles=rows+[forming]))
    first=asyncio.run(SignalReader(history).read(win))
    history.return_value=SimpleNamespace(source='Binance',candles=rows)
    assert asyncio.run(SignalReader(history).read(win))==first


@pytest.mark.parametrize('side,exit_price',[('LONG','110'),('SHORT','90'),('SHORT','110')])
def test_auto_accounting_matches_independent_integer_tick_oracle(auto,side,exit_price):
    from fractions import Fraction as F
    from tests.test_audit_math import nearest_ticks,ceiling_ticks,TICKS
    manager,engine,clock=auto;config=engine.snapshot()['settings'];config['commission_pct']='0.1';engine.configure(config)
    trade=run_entry(auto,side)[0];q=F(trade['position_size']);sign=1 if side=='LONG' else -1
    gross=nearest_ticks(sign*(F(exit_price)-100)*q)
    entry_fee=ceiling_ticks(100*q/F(1000));exit_fee=ceiling_ticks(F(exit_price)*q/F(1000))
    result=manual_close(engine,clock,trade,exit_price)
    assert F(result['realized_pnl'])*TICKS==gross-entry_fee-exit_fee
    assert F(engine.snapshot('AUTO')['statistics']['current_balance'])*TICKS==10000*TICKS+gross-entry_fee-exit_fee


def test_auto_decimal_context_and_drawdown_reference(auto):
    from decimal import localcontext
    manager,engine,clock=auto
    with localcontext() as context:
        context.prec=6
        trade=run_entry(auto)[0]
    clock[0]+=60000;engine.advance(window(clock,'90'))
    s=engine.snapshot('AUTO')['statistics']
    expected=D(trade['position_size'])*10
    assert D(s['maximum_drawdown_usdt'])==expected.quantize(D('0.00000001'))
    assert D(s['equity'])==10000-D(s['maximum_drawdown_usdt'])


def test_corrupt_attribution_curve_fails_closed(auto):
    manager,engine,clock=auto;run_entry(auto)
    with engine.store.transaction() as db:
        db.execute("UPDATE curve_slices SET balance='20000' WHERE entry_type='AUTO'")
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path),clock=lambda:clock[0])
