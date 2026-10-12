"""Offline accounting, candle fill, recovery and execution-boundary regressions."""
import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import sqlite3
import uuid

import pytest

from app.paper.engine import Engine, fee
from app.paper.models import Bar, Window, Settings, PaperError
from app.paper.storage import Store


@pytest.fixture
def ledger(tmp_path):
    clock = [1800000060000]
    settings = replace(Settings(),maximum_simultaneous_positions=3,commission_pct=D('0'),maximum_position_size_usdt=D('10000'),risk_per_trade_pct=D('10'),stop_loss_pct=D('20'),take_profit_pct=D('20'))
    engine = Engine(Store(tmp_path/'paper.sqlite3'),settings,lambda:clock[0])
    return engine,clock


def window(clock,price='100',bars=None,source='Binance'):
    end = clock[0]//60000*60
    bars = bars or (Bar(end-60,D(price),D(price),D(price),D(price)),)
    return Window('BTCUSDT','1m',source,clock[0],tuple(bars))


def payload(win,direction='LONG',size='1',**kwargs):
    result = dict(request_id=str(uuid.uuid4()),symbol=win.symbol,timeframe=win.timeframe,direction=direction,
                  expected_source=win.source,expected_price=str(win.bars[-1].close),expected_candle_time=win.bars[-1].time,
                  position_size=size,stop_loss=None,take_profit=None,entry_reason='Offline hypothesis',signal_id=None)
    result.update(kwargs)
    return result


def opened(ledger,direction='LONG',**kwargs):
    engine,clock=ledger
    win=window(clock)
    return engine.open(payload(win,direction,**kwargs),win)


def manual_close(engine,clock,trade,price):
    clock[0]+=60000
    win=window(clock,price)
    return engine.close(trade['id'],dict(request_id=str(uuid.uuid4()),exit_reason='Offline close'),win)


@pytest.mark.parametrize('side,exit_price,pnl',[('LONG','110','10'),('LONG','90','-10'),('SHORT','90','10'),('SHORT','110','-10')])
def test_long_short_profit_loss(ledger,side,exit_price,pnl):
    engine,clock=ledger
    trade=opened(ledger,side)
    result=manual_close(engine,clock,trade,exit_price)
    assert D(result['realized_pnl'])==D(pnl)
    assert D(result['pnl_pct'])==D(pnl)
    assert D(engine.snapshot()['statistics']['current_balance'])==D('10000')+D(pnl)


def test_commission_entry_exit_and_liquidation_equity(ledger):
    engine,clock=ledger
    config=engine.snapshot()['settings'];config['commission_pct']='0.10';engine.configure(config)
    trade=opened(ledger)
    assert D(trade['entry_fee'])==D('0.1')
    assert D(engine.snapshot()['statistics']['equity'])==D('9999.8')
    result=manual_close(engine,clock,trade,'110')
    assert D(result['exit_fee'])==D('0.11')
    assert D(result['commissions'])==D('0.21')
    assert D(result['gross_price_pnl'])==10
    assert D(result['realized_pnl'])==D('9.79')
    assert D(engine.snapshot()['statistics']['current_balance'])==D('10009.79')


@pytest.mark.parametrize('side,high,low,expected,reason',[
 ('LONG','110','79','80','STOP_LOSS'),('LONG','121','90','120','TAKE_PROFIT'),
 ('SHORT','121','90','120','STOP_LOSS'),('SHORT','110','79','80','TAKE_PROFIT'),
 ('LONG','125','75','80','STOP_LOSS_AMBIGUOUS'),('SHORT','125','75','120','STOP_LOSS_AMBIGUOUS')])
def test_sl_tp_and_ambiguous_bar(ledger,side,high,low,expected,reason):
    engine,clock=ledger;trade=opened(ledger,side)
    clock[0]+=60000
    b=Bar(clock[0]//1000-60,D('100'),D(high),D(low),D('100'))
    engine.advance(window(clock,bars=[b]))
    result=engine.trade(trade['id'])
    assert result['status']=='CLOSED'
    assert D(result['exit_price'])==D(expected)
    assert result['exit_reason']==reason


@pytest.mark.parametrize('side,price,expected',[('LONG','70','70'),('SHORT','130','130')])
def test_adverse_gap_stop_fill(ledger,side,price,expected):
    engine,clock=ledger;trade=opened(ledger,side)
    clock[0]+=60000;engine.advance(window(clock,price))
    assert D(engine.trade(trade['id'])['exit_price'])==D(expected)


def test_first_partial_bar_never_uses_preentry_high_low(ledger):
    engine,clock=ledger;clock[0]+=10000;trade=opened(ledger)
    clock[0]+=60000
    b=Bar(clock[0]//60000*60-60,D('100'),D('130'),D('70'),D('101'))
    engine.advance(window(clock,bars=[b]))
    assert engine.trade(trade['id'])['status']=='OPEN'


def test_sizing_includes_fees_and_rounding(ledger):
    engine,clock=ledger;config=engine.snapshot()['settings']
    config.update(commission_pct='0.1',risk_per_trade_pct='1',maximum_position_size_usdt='10000',stop_loss_pct='2')
    engine.configure(config);trade=opened(ledger,size=None)
    assert D(trade['risk_usdt'])<=D('100')
    assert D(trade['position_size'])<=D('100')/D('2.198')
    assert D(trade['reserved_notional'])+D(trade['entry_fee'])<=10000
    assert D(trade['position_size']).as_tuple().exponent==-12


@pytest.mark.parametrize('config,kwargs,code',[
 ({'risk_per_trade_pct':'0.01'},{'size':'1'},'RISK_LIMIT'),
 ({'maximum_position_size_usdt':'50'},{'size':'1'},'POSITION_SIZE_LIMIT'),
 ({},{'size':'0.0000000000001'},'INVALID_POSITION_SIZE'),
 ({},{'stop_loss':'101'},'INVALID_STOPS'),
 ({},{'take_profit':'99'},'INVALID_STOPS'),
 ({'commission_pct':'10'},{'take_profit':'101'},'INVALID_STOPS')])
def test_risk_rules(ledger,config,kwargs,code):
    engine,_=ledger;settings=engine.snapshot()['settings'];settings.update(config);engine.configure(settings)
    with pytest.raises(PaperError,match=code):opened(ledger,**kwargs)
    assert not engine.snapshot()['open_positions']


def test_simultaneous_limit(ledger):
    engine,_=ledger;settings=engine.snapshot()['settings'];settings['maximum_simultaneous_positions']=1;engine.configure(settings)
    opened(ledger)
    with pytest.raises(PaperError,match='POSITION_LIMIT'):opened(ledger)


def test_insufficient_virtual_balance(ledger):
    engine,_=ledger;settings=engine.snapshot()['settings'];settings.update(starting_balance='100',risk_per_trade_pct='100',maximum_position_size_usdt='10000');engine.configure(settings)
    opened(ledger)
    with pytest.raises(PaperError,match='INSUFFICIENT_BALANCE'):opened(ledger)
    assert D(engine.snapshot()['statistics']['available_balance'])==0


def test_stale_source_and_quote_mismatch(ledger):
    engine,clock=ledger;win=window(clock);body=payload(win)
    clock[0]+=30001
    with pytest.raises(PaperError,match='STALE_DATA'):engine.open(body,win)
    win=window(clock)
    with pytest.raises(PaperError,match='SOURCE_MISMATCH'):engine.open(payload(win,expected_source='Other'),win)
    with pytest.raises(PaperError,match='QUOTE_CHANGED'):engine.open(payload(win,expected_price='101'),win)


def test_journal_persistence_restart_backup_and_recovery(ledger,tmp_path):
    engine,clock=ledger;trade=opened(ledger)
    restarted=Engine(Store(engine.store.path),clock=lambda:clock[0])
    assert restarted.trade(trade['id'])==trade
    clock[0]+=60000;restarted.advance(window(clock,'125'))
    assert restarted.trade(trade['id'])['exit_reason']=='TAKE_PROFIT'
    backup=tmp_path/'backup.sqlite3';backup.write_bytes(restarted.store.backup())
    restored=Engine(Store(backup),clock=lambda:clock[0])
    assert restored.snapshot()['statistics']==restarted.snapshot()['statistics']
    assert len(restored.snapshot()['equity_curve'])==3


def test_corruption_does_not_reset_balance(ledger):
    engine,_=ledger;opened(ledger)
    with engine.store.transaction() as db:engine.store.set(db,'balance','20000')
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))
    with engine.store.transaction(write=False) as db:assert engine.store.get(db,'balance')=='20000'


def test_idempotency_replay_and_conflict_after_restart(ledger):
    engine,clock=ledger;win=window(clock);body=payload(win)
    trade=engine.open(body,win);assert engine.open(body,win)==trade
    restarted=Engine(Store(engine.store.path),clock=lambda:clock[0])
    assert restarted.replay(body['request_id'],'open',body)==trade
    with pytest.raises(PaperError,match='IDEMPOTENCY_CONFLICT'):restarted.open(dict(body,direction='SHORT'),win)
    assert len(restarted.snapshot()['open_positions'])==1
    clock[0]+=60000;win=window(clock,'110');close=dict(request_id=str(uuid.uuid4()),exit_reason='Done')
    result=engine.close(trade['id'],close,win)
    assert engine.close(trade['id'],close,win)==result
    assert engine.open(body,window(clock,'100'))==result
    assert engine.snapshot()['statistics']['total_trades']==1


def test_duplicate_signal_id(ledger):
    opened(ledger,signal_id='offline-manual-id')
    with pytest.raises(PaperError,match='DUPLICATE_SIGNAL'):opened(ledger,signal_id='offline-manual-id')


def test_parallel_same_command_one_trade(ledger):
    engine,clock=ledger;win=window(clock);body=payload(win)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:engine.open(body,win),range(2)))
    assert results[0]['id']==results[1]['id']
    assert len(engine.snapshot()['open_positions'])==1


def test_same_bar_duplicate_no_extra_equity_points(ledger):
    engine,clock=ledger;trade=opened(ledger);n=len(engine.snapshot()['equity_curve'])
    engine.advance(window(clock));engine.advance(window(clock))
    assert len(engine.snapshot()['equity_curve'])==n
    assert engine.trade(trade['id'])['status']=='OPEN'


def test_correction_out_of_order_gap_and_manual_gap_close(ledger):
    engine,clock=ledger;trade=opened(ledger)
    engine.advance(window(clock,'101'))
    assert engine.trade(trade['id'])['market_error']=='CANDLE_CORRECTION'
    assert engine.snapshot()['statistics']['equity'] is None
    engine.advance(window(clock))
    earlier=Bar(clock[0]//1000-120,D(100),D(100),D(100),D(100))
    engine.advance(window(clock,bars=[earlier]))
    assert engine.trade(trade['id'])['market_error']=='OUT_OF_ORDER'
    clock[0]+=180000
    engine.advance(window(clock))
    assert engine.trade(trade['id'])['market_error']=='MARKET_GAP'
    result=engine.close(trade['id'],dict(request_id=str(uuid.uuid4()),exit_reason='Gap acknowledged'),window(clock,'101'))
    assert result['exit_reason']=='MANUAL_HISTORY_GAP: Gap acknowledged'


def test_statistics_winrate_profitfactor_drawdown_curve(ledger):
    engine,clock=ledger
    for price in ('110','95','110','100'):
        trade=opened(ledger);manual_close(engine,clock,trade,price)
    s=engine.snapshot()['statistics']
    assert s['total_trades']==4 and s['winning_trades']==2 and s['losing_trades']==1 and s['breakeven_trades']==1
    assert D(s['win_rate'])==50 and D(s['profit_factor'])==4
    assert D(s['gross_profit'])==20 and D(s['gross_loss'])==5 and D(s['net_pnl'])==15
    assert D(s['average_win'])==10 and D(s['average_loss'])==5
    assert D(s['maximum_drawdown_pct'])==D('0.04995005')
    assert D(s['maximum_drawdown_usdt'])==5
    assert D(s['equity'])==10015 and D(s['return_pct'])==D('0.15')
    assert s['consecutive_wins']==0 and s['consecutive_losses']==0
    assert s['maximum_consecutive_wins']==1 and s['maximum_consecutive_losses']==1
    curve=engine.snapshot()['equity_curve'];assert D(curve[0]['equity'])==10000 and D(curve[-1]['equity'])==10015


def test_undefined_stats_and_stale_equity(ledger):
    engine,clock=ledger;s=engine.snapshot()['statistics']
    assert s['profit_factor'] is None and s['win_rate'] is None and s['average_win'] is None
    opened(ledger);clock[0]+=30001
    assert engine.snapshot()['statistics']['equity'] is None
    assert engine.snapshot()['open_positions'][0]['unrealized_pnl'] is None
    engine.unavailable('BTCUSDT','1m','SOURCE_MISMATCH')
    win=window(clock)
    # A different timeframe cannot refresh the old position's stale mark.
    from dataclasses import replace
    bar=Bar(clock[0]//300000*300-300,D(100),D(100),D(100),D(100))
    other=replace(win,timeframe='5m',bars=(bar,))
    with pytest.raises(PaperError,match='STALE_DATA'):
        engine.open(payload(other),other)


@pytest.mark.parametrize('raw',['NaN','Infinity','1e3','-1','0','1.00000000000000000001',1.2,True,None,'<script>'])
def test_malformed_money(ledger,raw):
    with pytest.raises(PaperError):opened(ledger,size=raw if raw is not None else 'NaN')


@pytest.mark.parametrize('mutate',[lambda w:replace(w,bars=(replace(w.bars[0],high=D('NaN')),)),
 lambda w:replace(w,bars=(replace(w.bars[0],low=D('101')),)),lambda w:replace(w,observed_at=w.observed_at+2000),
 lambda w:replace(w,bars=(replace(w.bars[0],time=w.bars[0].time+1),)),lambda w:replace(w,symbol='XAUUSD')])
def test_invalid_windows(ledger,mutate):
    engine,clock=ledger;win=window(clock)
    with pytest.raises(PaperError):engine.open(payload(win),mutate(win))


def test_external_decimal_context_cannot_change_accounting(ledger):
    engine,clock=ledger
    with localcontext() as ctx:
        ctx.prec=6
        trade=opened(ledger,size='1.123456789012')
        result=manual_close(engine,clock,trade,'110')
    assert D(result['realized_pnl'])==D('11.23456789')


def test_settings_locked_after_trade_and_snapshot_old_fee(ledger):
    engine,clock=ledger;trade=opened(ledger);settings=engine.snapshot()['settings']
    settings['starting_balance']='20000'
    with pytest.raises(PaperError,match='STARTING_BALANCE_LOCKED'):engine.configure(settings)
    settings['starting_balance']='10000';settings['commission_pct']='1';engine.configure(settings)
    result=manual_close(engine,clock,trade,'110');assert D(result['commissions'])==0


def test_core_cannot_call_exchange_or_auto_execute(ledger):
    engine,_=ledger
    with pytest.raises(PaperError,match='AUTOMATIC_EXECUTION_DISABLED'):engine.handle_signal({'side':'LONG'})
    root=Path(__file__).resolve().parents[1]/'app'/'paper'
    for name in ('engine.py','storage.py','models.py'):
        tree=ast.parse((root/name).read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                imported=node.module if isinstance(node,ast.ImportFrom) else ','.join(a.name for a in node.names)
                assert not any(s in (imported or '') for s in ('httpx','requests','bybit','testnet','socket','urllib'))
    assert engine.snapshot()['real_money_execution']=='DISABLED'
    assert engine.snapshot()['automatic_signal_execution'] is False


def test_missing_version_never_reinitializes_existing_journal(ledger):
    engine,_=ledger
    with engine.store.transaction() as db:db.execute("DELETE FROM meta WHERE key='version'")
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))


def test_tampered_fee_or_pnl_rejected_on_restart(ledger):
    engine,clock=ledger;trade=opened(ledger)
    with engine.store.transaction() as db:
        trade['entry_fee']='-10';engine.store.save(db,trade);engine.store.set(db,'balance','10010')
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path),clock=lambda:clock[0])


def test_maximum_drawdown_retained_after_curve_truncation(ledger):
    engine,clock=ledger;trade=opened(ledger);manual_close(engine,clock,trade,'90')
    for _ in range(501):
        with engine.store.transaction() as db:engine._point(db,clock[0])
    state=engine.snapshot()
    assert state['equity_curve_truncated'] is True and len(state['equity_curve'])==500
    assert D(state['statistics']['maximum_drawdown_usdt'])==10


@pytest.mark.parametrize('key,value',[('peak',None),('maximum_drawdown_pct','NaN'),('close_sequence','not-an-integer'),('maximum_drawdown_usdt','777')])
def test_audit_corrupt_metadata_fails_at_startup(ledger,key,value):
    engine,_=ledger
    with engine.store.transaction() as db:
        if value is None:db.execute('DELETE FROM meta WHERE key=?',(key,))
        else:engine.store.set(db,key,value)
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))


@pytest.mark.parametrize('change',[{'stop_loss':'-80'},{'take_profit':'90'},{'observed_at':None},{'pnl_pct':'999'},{'last_candle_time':1}])
def test_audit_corrupt_trade_fields_fail_at_startup(ledger,change):
    engine,clock=ledger;trade=opened(ledger)
    if 'pnl_pct' in change:trade=manual_close(engine,clock,trade,'110')
    trade.update(change)
    with engine.store.transaction() as db:engine.store.save(db,trade)
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))


def test_audit_indexed_status_mismatch_fails_at_startup(ledger):
    engine,_=ledger;trade=opened(ledger)
    with engine.store.transaction() as db:db.execute("UPDATE trades SET status='CLOSED' WHERE id=?",(trade['id'],))
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))


def test_audit_missing_idempotency_journal_fails_at_startup(ledger):
    engine,_=ledger;opened(ledger)
    with engine.store.transaction() as db:db.execute('DELETE FROM requests')
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))


def test_audit_missing_equity_curve_fails_at_startup(ledger):
    engine,_=ledger
    with engine.store.transaction() as db:db.execute('DELETE FROM curve')
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))


def test_audit_restart_replay_preserves_historical_drawdown(ledger):
    engine,clock=ledger;trade=opened(ledger)
    start=clock[0]//1000
    bars=[Bar(start+i*60,D(p),D(p),D(p),D(p)) for i,p in enumerate(('90','100','100','100','100'))]
    clock[0]+=300000
    restarted=Engine(Store(engine.store.path),clock=lambda:clock[0])
    restarted.advance(window(clock,bars=bars))
    assert D(restarted.snapshot()['statistics']['maximum_drawdown_usdt'])==10
    curve=restarted.snapshot()['equity_curve']
    assert D(curve[2]['equity'])==9990


def test_audit_historical_curve_never_uses_future_trade_cashflow(ledger):
    engine,clock=ledger;first=opened(ledger)
    start=clock[0]//1000;clock[0]+=180000
    # A later trade on another timeframe has already charged an entry fee.
    config=engine.snapshot()['settings'];config['commission_pct']='1';engine.configure(config)
    # Refresh the first position before manual new entry; future mark must not enter replay equity.
    engine.advance(window(clock,bars=[Bar(start+i*60,D(100),D(100),D(100),D(100)) for i in range(3)]))
    opened(ledger)
    with engine.store.transaction() as db:
        engine._point(db,clock[0],(start+60)*1000,historical=True)
    assert engine.snapshot()['equity_curve'][-1]['equity'] is None


@pytest.mark.parametrize('field,value',[('equity','NaN'),('drawdown_pct','25'),('peak','1')])
def test_audit_corrupt_curve_fails_at_startup(ledger,field,value):
    engine,_=ledger
    with engine.store.transaction() as db:db.execute('UPDATE curve SET '+field+'=?',(value,))
    with pytest.raises(PaperError,match='CORRUPT_JOURNAL'):Engine(Store(engine.store.path))
