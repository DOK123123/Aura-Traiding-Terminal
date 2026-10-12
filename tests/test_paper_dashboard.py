"""Offline dashboard contracts against unchanged Paper APIs/ledger; no exchange calls."""
import asyncio
import ast
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_EVEN
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.paper.auto import Auto, Signal
from app.paper.engine import Engine
from app.paper.models import PaperError
from app.paper.service import Service
from app.paper.storage import Store
from tests.test_paper_engine import ledger,window,payload,manual_close
from tests.test_paper_api import client,HEADERS,PASSWORD


@pytest.fixture
def dashboard(ledger):
    engine,clock=ledger
    config=engine.snapshot()['settings'];config.update(risk_per_trade_pct='1',maximum_simultaneous_positions=1,commission_pct='0.1')
    engine.configure(config)
    auto=Auto(engine)
    service=Service(SimpleNamespace(window=AsyncMock(return_value=window(clock))),engine)
    service.auto=auto
    return service,auto,engine,clock


@pytest.mark.parametrize('mode',['OFF','ON','PAUSED','ERROR'])
def test_dashboard_modes_are_server_authoritative_and_reads_do_not_activate(mode,dashboard):
    service,auto,engine,clock=dashboard
    if mode!='OFF':auto.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    if mode=='PAUSED':auto.fail('STALE_DATA')
    if mode=='ERROR':auto.fail('SIGNAL_ERROR')
    before=engine.snapshot();state_before=auto.state()
    data=asyncio.run(service.state('AUTO'))
    assert data['auto_paper']['status']==mode and data['statistics_scope']=='AUTO'
    assert data['effective_settings']['account_scope']=='ALL'
    assert data['auto_paper']==state_before and engine.snapshot()==before
    assert data['real_money_execution']=='DISABLED' and not data['open_positions']
    service.market.window.assert_not_called()


def enter_auto(dashboard,direction):
    service,auto,engine,clock=dashboard
    auto.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    clock[0]+=60000;win=window(clock)
    auto.process(win,Signal(win.symbol,win.timeframe,win.source,win.bars[-1].time,direction,D('70')),auto.state()['generation'])
    return engine.snapshot('AUTO')['open_positions'][0]


@pytest.mark.parametrize('direction,mark',[('LONG','101'),('SHORT','99')])
def test_auto_position_fields_and_pnl_independent_of_ui_formatting(direction,mark,dashboard):
    service,auto,engine,clock=dashboard
    trade=enter_auto(dashboard,direction)
    clock[0]+=60000;engine.advance(window(clock,mark))
    data=asyncio.run(service.state('AUTO'));position=data['open_positions'][0]
    assert position['entry_type']=='AUTO_SIGNAL' and position['execution_mode']=='PAPER'
    assert position['direction']==direction and position['data_status']=='FRESH'
    assert all(position[k] is not None for k in ('entry_price','position_size','stop_loss','take_profit','unrealized_pnl'))
    size=D(position['position_size']);tick=D('0.00000001');sign=1 if direction=='LONG' else -1
    gross=(sign*(D(mark)-D('100'))*size).quantize(tick,rounding=ROUND_HALF_EVEN)
    entry_fee=(D('100')*size*D('0.001')).quantize(tick,rounding=ROUND_CEILING)
    exit_fee=(D(mark)*size*D('0.001')).quantize(tick,rounding=ROUND_CEILING)
    assert D(position['entry_fee'])==entry_fee
    assert D(position['unrealized_pnl'])==gross-entry_fee-exit_fee
    assert data['statistics']['net_pnl']=='0' and data['statistics']['total_trades']==0
    assert D(data['effective_settings']['equity'])==D('10000')+gross-entry_fee-exit_fee


def test_manual_and_auto_journals_never_contaminate_dashboard_attribution(dashboard):
    service,auto,engine,clock=dashboard
    manual=engine.open(payload(window(clock),size='1'),window(clock));manual_close(engine,clock,manual,'110')
    trade=enter_auto(dashboard,'SHORT');manual_close(engine,clock,trade,'105')
    all_=asyncio.run(service.state('ALL'));manual_=asyncio.run(service.state('MANUAL'));automatic=asyncio.run(service.state('AUTO'))
    assert automatic['statistics']['total_trades']==1 and manual_['statistics']['total_trades']==1
    assert D(all_['statistics']['net_pnl'])==D(automatic['statistics']['net_pnl'])+D(manual_['statistics']['net_pnl'])
    assert automatic['effective_settings']['virtual_balance']==all_['statistics']['current_balance']
    assert automatic['effective_settings']==manual_['effective_settings']
    assert all(t['entry_type']=='AUTO_SIGNAL' for t in automatic['closed_trades'])
    assert all(t['entry_type']=='MANUAL' for t in manual_['closed_trades'])


@pytest.mark.parametrize('policy',['SKIP','PAPER_SETTINGS'])
def test_saved_policy_and_restart_are_not_changed_by_dashboard_reads(policy,dashboard):
    service,auto,engine,clock=dashboard
    auto.configure(True,window(clock),fallback_policy=policy)
    restored=Engine(Store(engine.store.path),clock=lambda:clock[0]);restarted=Auto(restored)
    service.engine=restored;service.auto=restarted
    data=asyncio.run(service.state('AUTO'))
    assert data['auto_paper']['status']=='PAUSED' and data['auto_paper']['fallback_policy']==policy
    assert data['auto_paper']['last_rejection_reason']=='RESTART_REQUIRES_RESUME'
    assert not restored.snapshot()['open_positions']


def test_stale_marks_are_null_not_fabricated_pnl(dashboard):
    service,auto,engine,clock=dashboard;enter_auto(dashboard,'LONG')
    clock[0]+=31000
    data=asyncio.run(service.state('AUTO'))
    assert data['effective_settings']['equity'] is None
    assert data['open_positions'][0]['unrealized_pnl'] is None
    assert data['open_positions'][0]['data_status']=='STALE_DATA'


def test_dashboard_api_owner_preflight_off_and_no_new_route(client):
    c,engine,clock=client
    from app.main import app
    app.state.paper.auto=Auto(engine);auth=('aura',PASSWORD)
    assert c.get('/api/paper/state?scope=AUTO').status_code==401
    before=engine.snapshot()
    result=c.get('/api/paper/state?scope=AUTO',auth=auth).json()
    assert result['auto_paper']['status']=='OFF' and result['statistics_scope']=='AUTO'
    assert engine.snapshot()==before
    body=dict(enabled=True,symbol='BTCUSDT',timeframe='1m',expected_source='Binance',fallback_policy='SKIP')
    rejected=c.post('/api/paper/auto',json=body,auth=auth,headers=HEADERS)
    assert rejected.status_code==409 and rejected.json()['code']=='AUTO_PREFLIGHT_RISK'
    assert app.state.paper.auto.state()['status']=='OFF'
    app.state.paper.market.window=AsyncMock(side_effect=PaperError('MARKET_UNAVAILABLE'))
    assert c.post('/api/paper/auto',json={'enabled':False},auth=auth,headers=HEADERS).json()['status']=='OFF'
    app.state.paper.market.window.assert_not_called()
    paths=app.openapi()['paths']
    assert {p for p,v in paths.items() if p.startswith('/api/paper/') and 'post' in v}=={
      '/api/paper/auto','/api/paper/settings','/api/paper/refresh','/api/paper/positions/open','/api/paper/positions/{trade_id}/close'}


def test_mobile_dashboard_markup_and_no_private_exchange_dependencies():
    root=Path(__file__).resolve().parents[1];html=(root/'static/index.html').read_text()
    paper=html[html.index('<section class="panel patterns paper"'):html.index('<section class="panel patterns lab"')]
    assert paper.index('paper-dashboard-title')<paper.index('paper-direction')<paper.index('paper-settings-title')
    assert 'REAL MONEY EXECUTION = DISABLED' in paper and 'Нет свежих данных' in paper
    assert all(label in paper for label in ('Ручная виртуальная сделка','Журнал и статистика','Настройки, политика','Журнал решений'))
    for file in (root/'app/paper').glob('*.py'):
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                name=node.module or '' if isinstance(node,ast.ImportFrom) else ','.join(a.name for a in node.names)
                assert not any(x in name for x in ('bybit_demo','testnet','httpx','requests','socket'))
