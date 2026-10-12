"""Effective configuration/provenance and activation safety: offline only."""
from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from app.paper.models import Settings,PaperError
from app.paper.engine import Engine
from app.paper.storage import Store
from app.paper.auto import Auto
from app.paper.safety import preflight,validate_protection
from tests.test_paper_engine import ledger,window,payload,manual_close
from tests.test_paper_api import client,PASSWORD,HEADERS


def test_defaults_environment_and_persisted_precedence(tmp_path,monkeypatch):
    for field in Settings.__dataclass_fields__:monkeypatch.delenv('PAPER_'+field.upper(),raising=False)
    engine=Engine(Store(tmp_path/'paper.sqlite3'))
    effective=engine.snapshot()['effective_settings']
    assert effective['values']==Settings().to_dict()
    assert set(effective['initialization_sources'].values())=={'defaults'}
    monkeypatch.setenv('PAPER_STOP_LOSS_PCT','3')
    monkeypatch.setenv('PAPER_COMMISSION_PCT','0.04')
    another=Engine(Store(tmp_path/'other.sqlite3'))
    assert another.snapshot()['settings']['stop_loss_pct']=='3'
    sources=another.snapshot()['effective_settings']['initialization_sources']
    assert sources['stop_loss_pct']=='environment variables' and sources['risk_per_trade_pct']=='defaults'
    monkeypatch.setenv('PAPER_STOP_LOSS_PCT','NaN')
    # Existing valid persisted configuration must not be replaced/rejected by changed env.
    restored=Engine(Store(tmp_path/'other.sqlite3'))
    assert restored.snapshot()['settings']['stop_loss_pct']=='3'
    config=restored.snapshot()['settings'];config['stop_loss_pct']='2.5';restored.configure(config)
    assert set(restored.snapshot()['effective_settings']['initialization_sources'].values())=={'persisted configuration'}
    assert Engine(Store(tmp_path/'other.sqlite3')).snapshot()['settings']['stop_loss_pct']=='2.5'
    with pytest.raises(PaperError,match='INVALID_SETTINGS'):Engine(Store(tmp_path/'new.sqlite3'))


def test_legacy_sources_are_not_guessed(ledger):
    engine,_=ledger
    with engine.store.transaction() as db:db.execute("DELETE FROM meta WHERE key='settings_sources'")
    assert set(engine.snapshot()['effective_settings']['initialization_sources'].values())=={'persisted configuration (original source unknown)'}


@pytest.mark.parametrize('changes,code',[
 ({'risk_per_trade_pct':D('1.01')},'AUTO_PREFLIGHT_RISK'),
 ({'maximum_simultaneous_positions':2},'AUTO_PREFLIGHT_POSITIONS'),
 ({'stop_loss_pct':D('NaN')},'INVALID_SETTINGS'),
 ({'take_profit_pct':D('Infinity')},'INVALID_SETTINGS'),
 ({'stop_loss_pct':D('0')},'INVALID_SETTINGS'),
 ({'take_profit_pct':D('-1')},'INVALID_SETTINGS')])
def test_invalid_activation_does_not_mutate_settings_history_or_auto(ledger,changes,code):
    engine,clock=ledger
    config=Settings().to_dict();engine.configure(config);manager=Auto(engine)
    bad=replace(Settings(),**changes)
    with engine.store.transaction() as db:
        before=manager._state(db);trades=engine.store.trades(db)
    with patch.object(engine,'_settings',return_value=bad):
        with pytest.raises(PaperError,match=code):manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    assert manager.state()['status']=='OFF' and engine.snapshot()['settings']==config
    with engine.store.transaction() as db:assert manager._state(db)==before and engine.store.trades(db)==trades


@pytest.mark.parametrize('side,stop,target,valid',[
 ('LONG','98','104',True),('SHORT','102','96',True),
 ('LONG','102','104',False),('SHORT','98','96',False),
 ('LONG','98','96',False),('SHORT','102','104',False),
 ('LONG','100','104',False),('SHORT','102','100',False),
 ('LONG','NaN','104',False),('SHORT','102','Infinity',False),
 ('LONG','0','104',False),('SHORT','102','-1',False)])
def test_long_short_protection_math(side,stop,target,valid):
    if valid:validate_protection(side,D('100'),D(stop),D(target))
    else:
        with pytest.raises(PaperError,match='INVALID_STOPS'):validate_protection(side,D('100'),D(stop),D(target))


def test_policy_virtual_boundary_and_existing_positions():
    assert preflight(Settings(),'SKIP')['passed']
    assert 'skipped' in preflight(Settings(),'SKIP')['policy_note']
    assert preflight(Settings(),'INVALID')['errors']==['AUTO_PREFLIGHT_POLICY']
    with patch('app.paper.models.REAL_MONEY_EXECUTION',True):
        assert 'AUTO_PREFLIGHT_VIRTUAL' in preflight(Settings(),'PAPER_SETTINGS')['errors']
    invalid=dict(direction='LONG',entry_price='100',stop_loss='101',take_profit='104')
    assert preflight(Settings(),'PAPER_SETTINGS',opened=[invalid])['errors']==['AUTO_PREFLIGHT_STOPS']
    valid=dict(invalid,stop_loss='98')
    assert preflight(Settings(),'PAPER_SETTINGS',opened=[valid])['passed']
    assert preflight(Settings(),'PAPER_SETTINGS',opened=[valid,valid])['errors']==['AUTO_PREFLIGHT_POSITIONS']


def test_armed_config_changes_rejected_without_clamping_or_history_loss(ledger):
    engine,clock=ledger;engine.configure(Settings().to_dict());manager=Auto(engine)
    manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')
    before=engine.snapshot()
    for changes,code in [({'risk_per_trade_pct':'5'},'AUTO_PREFLIGHT_RISK'),({'maximum_simultaneous_positions':3},'AUTO_PREFLIGHT_POSITIONS')]:
        config=dict(before['settings'],**changes)
        with pytest.raises(PaperError,match=code):engine.configure(config)
        assert engine.snapshot()==before and manager.state()['status']=='ON'
    manager.configure(False)
    config=dict(before['settings'],risk_per_trade_pct='5');engine.configure(config)
    assert engine.snapshot()['settings']['risk_per_trade_pct']=='5'
    with pytest.raises(PaperError,match='AUTO_PREFLIGHT_RISK'):manager.configure(True,window(clock),fallback_policy='PAPER_SETTINGS')


def test_effective_account_values_ignore_statistics_filter(ledger):
    engine,clock=ledger;trade=engine.open(payload(window(clock)),window(clock));manual_close(engine,clock,trade,'110')
    all_=engine.snapshot('ALL');auto=engine.snapshot('AUTO')
    assert auto['statistics']['current_balance']!=all_['statistics']['current_balance']
    assert auto['effective_settings']==all_['effective_settings']
    assert auto['effective_settings']['virtual_balance']==all_['statistics']['current_balance']
    assert auto['effective_settings']['slippage_supported'] is False and auto['effective_settings']['slippage_pct'] is None
    assert auto['effective_settings']['starting_balance_locked'] is True


def test_owner_api_visibility_preflight_and_existing_settings_endpoint(client):
    c,engine,clock=client
    # Fixture injects a new engine; keep its Auto coordinator attached to that ledger.
    from app.main import app
    app.state.paper.auto=Auto(engine)
    auth=('aura',PASSWORD)
    state=c.get('/api/paper/state',auth=auth).json()
    assert state['effective_settings']['values']==engine.snapshot()['settings']
    assert state['auto_paper']['safety_preflight']['passed'] is False
    body=dict(enabled=True,symbol='BTCUSDT',timeframe='1m',expected_source='Binance',fallback_policy='PAPER_SETTINGS')
    r=c.post('/api/paper/auto',json=body,auth=auth,headers=HEADERS)
    assert r.status_code==409 and r.json()['code']=='AUTO_PREFLIGHT_RISK'
    assert app.state.paper.auto.state()['status']=='OFF'
    assert c.post('/api/paper/settings',json=Settings().to_dict(),auth=auth,headers=HEADERS).status_code==200
    assert c.get('/api/paper/state',auth=auth).json()['auto_paper']['safety_preflight']['passed'] is True
    assert c.post('/api/paper/auto',json=body,auth=auth,headers=HEADERS).status_code==200
    assert engine.snapshot()['settings']==Settings().to_dict()
    assert not engine.snapshot()['open_positions'] # Enabling records baseline, not an entry.


@pytest.mark.parametrize('entry',[D('NaN'),D('sNaN'),D('Infinity'),D('0'),D('-1')])
def test_preflight_bad_reference_price_never_passes(entry):
    assert preflight(Settings(),'PAPER_SETTINGS',entry=entry)['errors']==['AUTO_PREFLIGHT_STOPS']


def test_existing_trade_history_preserved_by_visibility_and_safe_settings(ledger):
    engine,clock=ledger;trade=engine.open(payload(window(clock)),window(clock));manual_close(engine,clock,trade,'110')
    before=engine.snapshot()['closed_trades'];config=engine.snapshot()['settings'];config.update(risk_per_trade_pct='1',maximum_simultaneous_positions=1)
    engine.configure(config);manager=Auto(engine)
    assert manager.state()['safety_preflight']['passed'] and engine.snapshot()['closed_trades']==before
    manager.configure(True,window(clock),fallback_policy='SKIP')
    assert engine.snapshot()['closed_trades']==before and not engine.snapshot()['open_positions']


def test_malformed_optional_provenance_is_unknown_not_a_ledger_reset(ledger):
    engine,_=ledger;before=engine.snapshot()['settings']
    with engine.store.transaction() as db:engine.store.set(db,'settings_sources',json.dumps({'risk_per_trade_pct':['defaults']}))
    data=engine.snapshot()
    assert data['settings']==before
    assert data['effective_settings']['initialization_sources']['risk_per_trade_pct']=='persisted configuration (original source unknown)'


def test_fallback_formula_independent_fraction_oracle_and_decimal_context():
    from fractions import Fraction
    from decimal import localcontext
    from app.paper import safety
    original=safety.validate_protection;seen=[]
    def record(side,entry,stop,target):
        seen.append((side,entry,stop,target));original(side,entry,stop,target)
    settings=replace(Settings(),stop_loss_pct=D('0.000000000001'),take_profit_pct=D('3.125'))
    price=D('12345.67890123456789')
    with patch.object(safety,'validate_protection',side_effect=record),localcontext() as ctx:
        ctx.prec=3
        assert safety.preflight(settings,'PAPER_SETTINGS',entry=price)['passed']
    assert len(seen)==2
    for side,entry,stop,target in seen:
        sign=1 if side=='LONG' else -1
        assert Fraction(stop)==Fraction(price)*(1-sign*Fraction(settings.stop_loss_pct)/100)
        assert Fraction(target)==Fraction(price)*(1+sign*Fraction(settings.take_profit_pct)/100)
