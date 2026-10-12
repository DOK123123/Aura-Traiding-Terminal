"""Synthetic fixtures test diagnostics, never real BTC strategy profitability."""
import ast
import asyncio
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import backtest_aura_history as lab
from scripts import diagnose_aura_auto as core
from app.models import Candle
from app.paper.auto import Signal
from app.paper.models import Settings
from app.patterns.engine import evaluate
from app.patterns.config import PatternConfig


def test_calendar_ranges_and_unknown_performance(tmp_path):
    output=tmp_path/'unknown.json'
    assert lab.main(['--end-date','2026-10-12','--output',str(output)])==2
    data=json.loads(output.read_text())
    assert not data['actual_backtest_performed']
    a,b=data['results']
    assert [a['days'],b['days']]==[30,90]
    assert [a['expected_candles'],b['expected_candles']]==[2880,8640]
    assert a['start_utc'].startswith('2026-09-12') and b['start_utc'].startswith('2026-07-14')
    assert a['status']==b['status']=='NO_HISTORY'
    assert a['net_realized_pnl'] is None and b['signals'] is None


def test_stages_cannot_be_reversed_or_truncated_silently(tmp_path):
    with pytest.raises(SystemExit):lab.main(['--periods','90','30','--output',str(tmp_path/'out.json')])
    with pytest.raises(ValueError):core.period('2026-10-12',31)


def test_settings_provenance_and_no_credentials_accepted(tmp_path):
    settings,policy,source,_=lab.configuration()
    assert settings==Settings() and policy=='PAPER_SETTINGS' and 'not verified' in source
    path=tmp_path/'settings.json'
    path.write_text(json.dumps(dict(settings=Settings().to_dict(),fallback_policy='SKIP')))
    assert lab.configuration(path)[1]=='SKIP'
    path.write_text(json.dumps(dict(settings=Settings().to_dict(),fallback_policy='SKIP',api_secret='dummy')))
    with pytest.raises(ValueError):lab.configuration(path)


def test_monthly_realized_cohort_fees_and_independent_drawdown():
    import datetime
    ts=lambda d:int(datetime.datetime.fromisoformat(d).replace(tzinfo=datetime.timezone.utc).timestamp()*1000)
    start=ts('2026-09-01')//1000;end=ts('2026-10-01')//1000
    decisions=[dict(timestamp=ts('2026-09-02'),signal_result='LONG',rejection_reason=None),
               dict(timestamp=ts('2026-09-03'),signal_result='WAIT',rejection_reason='NO_SIGNAL')]
    trades=[dict(status='CLOSED',entry_time=ts('2026-08-31'),exit_time=ts('2026-09-02'),entry_fee='1',exit_fee='2',realized_pnl='10'),
            dict(status='CLOSED',entry_time=ts('2026-09-01'),exit_time=ts('2026-09-03'),entry_fee='3',exit_fee='4',realized_pnl='-5')]
    curve=[dict(recorded_at=ts('2026-08-31'),balance='10000',equity='10000'),
           dict(recorded_at=ts('2026-09-02'),balance='10010',equity='9950'),
           dict(recorded_at=ts('2026-09-03'),balance='10005',equity='10025')]
    rows=lab.monthly(dict(decisions=decisions,trades=trades,equity_curve=curve),[],start,end,Settings())
    month=next(r for r in rows if r['month']=='2026-09')
    assert month['closed_trades']==2 and month['entries']==1
    assert Decimal(month['net_realized_pnl'])==5 and Decimal(month['profit_factor'])==2
    assert Decimal(month['fees_charged'])==9 # August entry fee excluded; closed trade net includes it.
    assert Decimal(month['win_rate'])==50 and Decimal(month['maximum_drawdown_pct'])==Decimal('.5')


def test_month_undefined_metrics_and_missing_equity():
    point=dict(recorded_at=1800000000000,balance='10000',equity=None)
    result=dict(decisions=[],trades=[],equity_curve=[point])
    bar=Candle(1800000000,100.,100.,100.,100.,1.)
    row=lab.monthly(result,[bar],bar.time,bar.time+900,Settings())[0]
    assert row['candles']==1 and row['win_rate'] is None and row['profit_factor'] is None
    assert row['maximum_drawdown_pct'] is None


def test_production_evidence_is_observed_without_signal_changes():
    rows=[Candle(t,100.,101.,99.,100.,10.) for t in range(1800000000-500*900,1800000000,900)]
    data=evaluate(rows,900,500,PatternConfig(),include_charts=False)
    explanation=lab.evidence(data)
    assert data['signal']=='WAIT' and explanation['candidate'] is None
    assert 'MINIMUM_SAMPLE' in explanation['failed'] and 'WILSON' in explanation['failed']


def test_configurable_fee_uses_production_money_math(monkeypatch):
    start=1800000000
    rows=[Candle(t,100.,101.,99.,100.,10.) for t in range(start-500*900,start+900,900)]
    rows.append(Candle(start+900,104.,104.1,103.9,104.,10.))
    async def controlled(self,window):
        return Signal('BTCUSDT','15m',core.SOURCE,window.bars[-1].time,
                      'LONG' if window.bars[-1].time==start else 'WAIT',Decimal(72))
    monkeypatch.setattr(core.SignalReader,'read',controlled)
    settings=Settings(commission_pct=Decimal('.20'))
    result=asyncio.run(core.replay(rows,start,start+1800,settings=settings))
    assert result['closed_trades']==1 and Decimal(result['net_realized_pnl'])==Decimal('71.84')
    skipped=asyncio.run(core.replay(rows,start,start+1800,settings=settings,fallback_policy='SKIP'))
    assert skipped['entries']==0 and skipped['rejections']=={'STOPS_UNAVAILABLE':1}


def test_real_production_replay_is_causal_reproducible_and_isolated():
    start=1800000000
    rows=[Candle(t,100.,101.,99.,100.,10.) for t in range(start-500*900,start+1800,900)]
    a=asyncio.run(lab.measured_replay(rows,start,start+1800,Settings(),'PAPER_SETTINGS',30))
    b=asyncio.run(lab.measured_replay(rows,start,start+1800,Settings(),'PAPER_SETTINGS',30))
    assert a==b and a['observed_candles']==2 and a['signals']['WAIT']==2
    assert a['strategy_gate_failures']['MINIMUM_SAMPLE']==2
    with pytest.raises(ValueError):
        asyncio.run(lab.measured_replay(rows+[Candle(start+1800,100.,101.,99.,100.,10.)],start,start+1800,Settings(),'PAPER_SETTINGS',30))


def test_failed_30_day_fetch_stops_before_90_day_network(tmp_path,monkeypatch):
    fake=AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(core,'fetch_snapshot',fake)
    args=SimpleNamespace(paper_config=None,fetch_dir=tmp_path/'new',periods=[30,90],end_date='2026-10-12',
                         warmup=10000,snapshot=None,max_seconds=10)
    data=asyncio.run(lab.run(args))
    assert fake.call_count==1 and not data['actual_backtest_performed']
    assert data['results'][0]['status']=='INCOMPLETE' and data['results'][1]['status']=='NOT_RUN'


def test_runtime_no_exchange_writes_or_live_state_dependencies():
    tree=ast.parse(Path(lab.__file__).read_text())
    modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(n.startswith(('app.main','app.lab','app.bybit_demo','app.testnet')) for n in modules)
    assert not any(isinstance(n,ast.Attribute) and n.attr in ('post','put','delete') for n in ast.walk(tree))
    source=Path(lab.__file__).read_text()
    assert 'PAPER_DB_PATH' not in source and 'os.environ' not in source
