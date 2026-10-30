"""Observed counts, trace parity and coverage; no market/order traffic."""
import asyncio
import copy
import gzip
import json
from pathlib import Path

import pytest

from app.hunter.engine import Prepared,FAMILIES
from app.hunter.store import Store,MODEL_HASH
from app.hunter.diagnostics import explain,failure_code
from app.hunter.main import Hunter
from tests.test_hunter6 import plan,bars,quote,OfflineMarket
from tests.test_hunter6_forward import sample
from tests.test_preview_signals import integrated
from tests.test_manual_preview import AUTH


def test_counters_count_closed_cutoffs_once_and_provenance_is_exact(tmp_path):
    s=Store(tmp_path/'d.sqlite');s.observe(sample(),[],96001.,{'approved':[]})
    s.observe(sample(96002.),[],96002.,{'approved':[]})
    for hours in (24,48):
        d=s.diagnostics(96002.,hours)
        assert len(d['groups'])==48 and d['unique_frame_candles_evaluated']==1
        groups=[g for g in d['groups'] if g['frame']=='5m']
        assert all(g['candles_evaluated']==1 for g in groups)
        assert all(g['candles_evaluated']==0 for g in d['groups'] if g['frame']!='5m')
        assert d['coverage']['5m']['samples']==2 and d['coverage']['5m']['cadence_observed_seconds']==1
        assert d['coverage']['15m']['samples']==0 and not d['continuous_hosting_verified']
        assert all(g['delivered_alerts'] is None and g['acknowledged_alerts'] is None for g in d['groups'])
        row=d['recent_decisions'][0]
        assert row['closed_candle_close']==96000 and row['closed_candle_close_utc']=='1970-01-02T02:40:00Z'
        assert row['bid_ask_age_seconds']==0 and row['model_sha256']==MODEL_HASH
        assert row['input_sha256']==s.export_inputs('5m')['items'][0]['sha256']


def test_failures_and_restart_do_not_invent_candles_or_coverage(tmp_path):
    path=tmp_path/'d.sqlite';s=Store(path);s.observe(sample(),[],96001.,{'approved':[]})
    s.record_frame_failure('15m',96002.,'QUOTE_GAP');s.record_frame_failure('5m',96100.,'STALE_CANDLES')
    other=Store(path);other.record_frame_failure('5m',96101.,'PUBLIC_FRAME_UNAVAILABLE')
    d=other.diagnostics(96101.,24)
    assert d['journal_instance']==s.journal_instance and other.session_id!=s.session_id
    assert d['writer_sessions_in_window']==2 and d['unique_frame_candles_evaluated']==1
    assert d['coverage']['5m']['unobserved_gap_seconds']==99
    assert all(g['quote_gaps']==1 and g['candles_evaluated']==0 for g in d['groups'] if g['frame']=='15m')
    fresh=Store(tmp_path/'lost.sqlite')
    assert fresh.journal_instance!=s.journal_instance
    assert fresh.diagnostics(96101.,48)['history_before_instance']=='UNKNOWN_OR_LOST'
    assert fresh.diagnostics(96101.,48)['first_recorded_observation_utc'] is None


def test_watch_outbox_is_separate_and_never_qualifies_confirmed(tmp_path,monkeypatch):
    p=plan();monkeypatch.setattr(Prepared,'plans',lambda self,i,family,**kw:[copy.deepcopy(p)] if family=='TREND_PULLBACK' else [])
    s=Store(tmp_path/'watch.sqlite');s.observe(sample(),[],96001.,{'approved':[]})
    d=s.snapshot(96001.,{'5m':quote(96001.)})
    assert len(d['watch_alerts'])==1 and d['alerts']==[]
    assert d['records'][0]['plan']['statistical_status']=='UNVALIDATED'
    assert s.snapshot(96032.,{'5m':quote(96032.)})['watch_alerts']==[]
    assert s.snapshot(96002.,{'5m':quote(96001.)},'OBSERVER_STOPPED')['watch_alerts']==[]
    assert s.snapshot(96008.,{'5m':quote(96001.)})['watch_alerts']==[]


def test_raw_upstream_error_never_enters_journal(tmp_path):
    assert failure_code(ValueError('DUMMY_SECRET_AND_URL'))=='PUBLIC_FRAME_UNAVAILABLE'
    assert failure_code(ValueError('STALE_OR_CONFLICTING_QUOTE'))=='QUOTE_GAP'
    assert failure_code(RuntimeError('DUMMY_SECRET_AND_URL'),'observer')=='OBSERVER_PROCESSING_FAILED'
    class Down(OfflineMarket):
        async def snapshot(self,frame):raise ValueError('DUMMY_SECRET_AND_URL')
    async def run():
        s=Store(tmp_path/'fail.sqlite');h=Hunter(s,Down(),{'approved':[]});await h.cycle()
        data=s.export_diagnostics(h.last_cycle_at,kind='samples')
        assert 'DUMMY_SECRET' not in json.dumps(data) and len(data['items'])==4
    asyncio.run(run())


def test_24_and_48_hour_windows_do_not_invent_missing_recent_activity(tmp_path):
    s=Store(tmp_path/'windows.sqlite');s.observe(sample(),[],96001.,{'approved':[]})
    now=96001.+25*3600
    assert s.diagnostics(now,24)['unique_frame_candles_evaluated']==0
    assert s.diagnostics(now,48)['unique_frame_candles_evaluated']==1
    assert s.diagnostics(now,24)['coverage']['5m']['samples']==0
    assert not s.diagnostics(now,24)['coverage']['5m']['coverage_complete']


def test_trace_failure_rolls_back_success_counters_and_watermark(tmp_path,monkeypatch):
    import app.hunter.store as module
    s=Store(tmp_path/'atomic.sqlite');original=module.explain
    def fail(*args,**kwargs):raise ValueError('DUMMY_TRACE_FAILED')
    monkeypatch.setattr(module,'explain',fail)
    with pytest.raises(ValueError,match='DUMMY_TRACE_FAILED'):s.observe(sample(),[],96001.,{'approved':[]})
    assert s.diagnostics(96001.)['unique_frame_candles_evaluated']==0
    assert s.diagnostics(96001.)['coverage']['5m']['samples']==0
    assert s.export_inputs('5m')['items']==[]
    monkeypatch.setattr(module,'explain',original);s.observe(sample(),[],96001.,{'approved':[]})
    assert s.diagnostics(96001.)['unique_frame_candles_evaluated']==1


def test_native_positive_plan_and_mirrored_unit_fixture_trace_both_sides():
    path=Path(__file__).resolve().parents[1]/'docs/aura6/native_probe/4h.json'
    captured=json.loads(path.read_text())['items'][0]['payload'];rows=captured['snapshot']['bars']
    center=rows[-1][4];mirror=[[r[0],2*center-r[1],2*center-r[3],2*center-r[2],2*center-r[4],r[5]] for r in rows]
    sides=set()
    for data in [rows,mirror]:
        prepared=Prepared(data,'4h');plans=[p for f in FAMILIES for p in prepared.plans(259,f,watch=True)]
        traced=explain(prepared,plans,data[-1][0]+14400,MODEL_HASH,replay=True)
        assert all(r['trace_integrity']=='OK' for r in traced)
        sides.update(p['direction'] for p in plans if p['technical_trigger'])
    assert sides=={'LONG','SHORT'}  # Mirror is explicitly software fixture, not second real market evidence.


def test_owner_pagination_and_no_http_ack_route(integrated):
    c=integrated
    for _ in range(100):
        d=c.get('/api/preview/signals/diagnostics?hours=24',auth=AUTH).json()
        if d.get('unique_frame_candles_evaluated'):break
    assert d['scope']=='AURA5_SIGNAL_DIAGNOSTICS'
    for path in ['/api/preview/signals/diagnostics?hours=48','/api/preview/signals/journal?kind=samples']:
        assert c.get(path).status_code==401
        assert c.get(path,auth=AUTH).status_code==200
        assert c.post(path,auth=AUTH).status_code==403
    for suffix in ['hours=25','hours=100','hours=true']:
        assert c.get('/api/preview/signals/diagnostics?'+suffix,auth=AUTH).status_code==422
    assert c.get('/api/preview/signals/journal?limit=1001',auth=AUTH).status_code==422
    assert c.get('/api/preview/signals/journal?kind=private',auth=AUTH).status_code==422
    first=c.get('/api/preview/signals/journal?kind=samples&limit=1',auth=AUTH).json()
    next_page=c.get('/api/preview/signals/journal?kind=samples&limit=1&after='+str(first['next_after']),auth=AUTH).json()
    assert first['items'][0]['seq']!=next_page['items'][0]['seq']
    assert not first['includes_private_account_data']


def test_saved_replay_is_deterministic_and_reports_absent_forward(tmp_path,monkeypatch):
    from research.aura5_issue66.run import run
    import research.aura5_issue66.run as replay
    from research.aura5_cost_audit.baseline import engine,diagnostics,MODEL_HASH as original_hash
    monkeypatch.setattr(replay,'Prepared',engine.Prepared)
    monkeypatch.setattr(replay,'MODEL_HASH',original_hash)
    monkeypatch.setattr(replay,'explain',diagnostics.explain)
    monkeypatch.setattr(replay,'DIAGNOSTICS_HASH',diagnostics.DIAGNOSTICS_HASH)
    out=tmp_path/'replay';s=run(out);saved=Path('docs/aura_trader5/issue66/replay')
    assert s['frames']=={'5m':576,'15m':192,'1h':48,'4h':12} and s['decisions']==9936
    assert sum(g['candidates'] for g in s['windows']['48']['groups'])==229
    assert sum(g['planning_rejected'] for g in s['windows']['48']['groups'])==229
    assert sum(g['rule_plans'] for g in s['windows']['48']['groups'])==0
    assert s['live_deliveries'] is None and s['actual_forward_uptime_seconds'] is None
    assert not s['profitability_evaluated'] and s['orders']==0
    for name in ['summary.json','counts.csv','decisions.json.gz']:assert (out/name).read_bytes()==(saved/name).read_bytes()
    assert all(r['bid_ask_age_seconds'] is None for r in json.loads(gzip.decompress((out/'decisions.json.gz').read_bytes())))
